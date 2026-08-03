#!/usr/bin/env bash
# =============================================================================
# JTCS ERP Deployment Console (Ubuntu / Linux)
# Same menu as JTCS_ERP.bat — run with:  bash JTCS_ERP.sh
# Or:  chmod +x JTCS_ERP.sh && ./JTCS_ERP.sh
# =============================================================================
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
LOG_DIR="${ROOT}/deployment/logs"
mkdir -p "$LOG_DIR"

C_RESET=$'\033[0m'
C_GREEN=$'\033[92m'
C_RED=$'\033[91m'
C_YELLOW=$'\033[93m'
C_CYAN=$'\033[96m'
C_BOLD=$'\033[1m'

VPS_HOST="200.141.5.68"
VPS_USER="root"
VPS_PORT="22"
VPS_PATH="/root/JTCS-final"
PUBLIC_HEALTH_URL="https://app.jtcsxpert.com/health"
LOCAL_BRANCH=""
ON_VPS=0

pass() { echo "${C_GREEN}[PASS]${C_RESET} $*"; }
fail() { echo "${C_RED}[FAIL]${C_RESET} $*"; }
info() { echo "${C_CYAN}[INFO]${C_RESET} $*"; }
warn() { echo "${C_YELLOW}[WARN]${C_RESET} $*"; }

pause() { read -r -p "Press Enter to continue..." _; }

load_vps_env() {
  local f="${ROOT}/deploy_vps.env"
  if [[ -f "$f" ]]; then
    # shellcheck disable=SC1090
    set -a
    # strip CR if file edited on Windows
    source <(sed 's/\r$//' "$f" | grep -vE '^\s*#' | grep -vE '^\s*$')
    set +a
  fi
  [[ "$VPS_PATH" == "~/JTCS-final" ]] && VPS_PATH="/root/JTCS-final"
  [[ -z "${PUBLIC_HEALTH_URL:-}" ]] && PUBLIC_HEALTH_URL="https://app.jtcsxpert.com/health"
}

init_branch() {
  LOCAL_BRANCH="$(git -C "$ROOT" branch --show-current 2>/dev/null || true)"
  [[ -z "$LOCAL_BRANCH" ]] && LOCAL_BRANCH="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  [[ -z "$LOCAL_BRANCH" || "$LOCAL_BRANCH" == "HEAD" ]] && LOCAL_BRANCH="DETACHED"
}

detect_on_vps() {
  ON_VPS=0
  if [[ "$(pwd -P)" == "$(readlink -f "$VPS_PATH" 2>/dev/null || echo "$VPS_PATH")" ]]; then
    ON_VPS=1
  elif [[ -d /root/JTCS-final/.git && "$ROOT" == "/root/JTCS-final" ]]; then
    ON_VPS=1
  elif systemctl cat jtcs-erp >/dev/null 2>&1 && [[ -f "${ROOT}/deployment/deploy.sh" ]]; then
    # Heuristic: running on a host that already has the service + this repo
    if [[ "$(hostname -I 2>/dev/null || true)" == *"${VPS_HOST}"* ]] || [[ "${HOSTNAME:-}" == srv* ]]; then
      ON_VPS=1
    fi
  fi
}

require_git() {
  command -v git >/dev/null 2>&1 || { fail "git not found"; return 1; }
}

require_ssh() {
  command -v ssh >/dev/null 2>&1 || { fail "ssh not found"; return 1; }
}

ssh_run() {
  local cmd="$1"
  info "SSH ${VPS_USER}@${VPS_HOST} …"
  ssh -p "$VPS_PORT" -o StrictHostKeyChecking=accept-new \
    "${VPS_USER}@${VPS_HOST}" "$cmd"
}

remote_or_local() {
  # Run command on VPS (SSH) or locally if already on VPS
  local cmd="$1"
  if [[ "$ON_VPS" -eq 1 ]]; then
    info "Running on this VPS (no SSH)…"
    bash -lc "cd '$VPS_PATH' && $cmd"
  else
    require_ssh || return 1
    ssh_run "cd '$VPS_PATH' && $cmd"
  fi
}

run_public_health() {
  local code
  code="$(curl -fsS -o /dev/null -w '%{http_code}' --max-time 25 \
    -H 'Cache-Control: no-cache' "$PUBLIC_HEALTH_URL" 2>/dev/null || true)"
  if [[ "$code" == "200" || "$code" == "204" ]]; then
    pass "Health HTTP ${code} — ${PUBLIC_HEALTH_URL}"
    return 0
  fi
  fail "Health HTTP ${code:-none} — ${PUBLIC_HEALTH_URL}"
  return 1
}

push_and_sync_vps() {
  require_git || return 1
  init_branch
  if [[ "$LOCAL_BRANCH" == "DETACHED" ]]; then
    fail "Detached HEAD — checkout a branch first"
    return 1
  fi
  info "Syncing branch ${LOCAL_BRANCH} → GitHub → VPS…"
  git -C "$ROOT" add -A
  if ! git -C "$ROOT" diff --cached --quiet; then
    git -C "$ROOT" commit -m "deploy sync ${LOCAL_BRANCH}" || {
      fail "Commit failed during sync"
      return 1
    }
    pass "Committed local deploy files"
  else
    info "Nothing new to commit"
  fi
  git -C "$ROOT" push -u origin HEAD || {
    fail "Push failed — VPS cannot get new scripts"
    return 1
  }
  pass "Pushed origin/${LOCAL_BRANCH}"

  if [[ "$ON_VPS" -eq 1 ]]; then
    (
      cd "$VPS_PATH" || exit 1
      ENV_BAK="/tmp/jtcs.env.bak.$$"
      [[ -f erp/.env ]] && cp erp/.env "$ENV_BAK"
      git fetch origin "$LOCAL_BRANCH"
      git checkout -B "$LOCAL_BRANCH" "origin/${LOCAL_BRANCH}"
      git reset --hard "origin/${LOCAL_BRANCH}"
      if [[ -f "$ENV_BAK" ]]; then cp "$ENV_BAK" erp/.env; rm -f "$ENV_BAK"; fi
      test -f deployment/install_service.sh && test -f deployment/deploy.sh
    ) || {
      fail "Local VPS git sync failed"
      return 1
    }
  else
    require_ssh || return 1
    ssh_run "cd '$VPS_PATH' && ENV_BAK=/tmp/jtcs.env.bak.\$\$ && if [ -f erp/.env ]; then cp erp/.env \$ENV_BAK; fi && git fetch origin $LOCAL_BRANCH && git checkout -B $LOCAL_BRANCH origin/$LOCAL_BRANCH && git reset --hard origin/$LOCAL_BRANCH && if [ -f \$ENV_BAK ]; then cp \$ENV_BAK erp/.env; rm -f \$ENV_BAK; fi && test -f deployment/install_service.sh && test -f deployment/deploy.sh" || {
      fail "VPS git sync failed — remote scripts still missing"
      return 1
    }
  fi
  pass "VPS synced — deployment scripts present"
  return 0
}

show_deploy_summary() {
  init_branch
  local commit
  commit="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo
  echo "  ${C_CYAN}========================================${C_RESET}"
  echo "  ${C_BOLD}Deployment Summary${C_RESET}"
  echo "  ${C_CYAN}========================================${C_RESET}"
  echo "  Branch     : ${LOCAL_BRANCH}"
  echo "  Commit     : ${commit}"
  echo "  App URL    : https://app.jtcsxpert.com"
  echo "  Health URL : ${PUBLIC_HEALTH_URL}"
  echo "  When       : $(date '+%Y-%m-%d %H:%M:%S %z')"
  echo "  Mode       : $([[ $ON_VPS -eq 1 ]] && echo 'ON VPS' || echo 'SSH → VPS')"
  echo "  ${C_CYAN}========================================${C_RESET}"
}

# ---------------------------------------------------------------------------
# Menu actions
# ---------------------------------------------------------------------------
git_status() {
  require_git || return
  init_branch
  info "Git status (branch=${LOCAL_BRANCH})"
  git -C "$ROOT" status -sb
  echo
  git -C "$ROOT" log -3 --oneline
}

git_add() {
  require_git || return
  git -C "$ROOT" add -A && pass "Staged all changes" || fail "git add failed"
  git -C "$ROOT" status -sb
}

git_commit() {
  require_git || return
  local msg
  read -r -p "Commit message: " msg
  [[ -z "$msg" ]] && msg="update $(date '+%d-%m-%Y %H%M')"
  git -C "$ROOT" add -A
  if git -C "$ROOT" diff --cached --quiet; then
    info "Nothing new to commit"
  else
    git -C "$ROOT" commit -m "$msg" && pass "Committed: $msg" || fail "Commit failed"
  fi
}

git_push() {
  require_git || return
  init_branch
  [[ "$LOCAL_BRANCH" == "DETACHED" ]] && { fail "Detached HEAD"; return; }
  info "Pushing current branch: ${LOCAL_BRANCH}"
  git -C "$ROOT" push -u origin HEAD && pass "Push OK — origin/${LOCAL_BRANCH}" || fail "Push failed"
}

git_pull() {
  require_git || return
  init_branch
  git -C "$ROOT" pull --ff-only origin "$LOCAL_BRANCH" && pass "Pull OK" || fail "Pull failed"
}

deploy_vps() {
  require_git || return
  init_branch
  [[ "$LOCAL_BRANCH" == "DETACHED" ]] && { fail "Detached HEAD"; return; }
  local logf="${LOG_DIR}/deploy_$(date +%Y%m%d_%H%M%S).log"
  info "Branch=${LOCAL_BRANCH}  Target=${VPS_USER}@${VPS_HOST}:${VPS_PATH}"
  info "Canonical script: deployment/deploy.sh"
  if [[ "$ON_VPS" -eq 1 ]]; then
    (
      cd "$VPS_PATH" && export BRANCH="$LOCAL_BRANCH" VPS_APP_DIR="$VPS_PATH" GIT_BRANCH="$LOCAL_BRANCH"
      bash deployment/deploy.sh
    ) 2>&1 | tee "$logf"
  else
    require_ssh || return
    ssh -p "$VPS_PORT" -o StrictHostKeyChecking=accept-new \
      "${VPS_USER}@${VPS_HOST}" \
      "cd '$VPS_PATH' && export BRANCH='$LOCAL_BRANCH' VPS_APP_DIR='$VPS_PATH' GIT_BRANCH='$LOCAL_BRANCH' && bash deployment/deploy.sh" \
      2>&1 | tee "$logf"
  fi
  if grep -q '===DEPLOY_RESULT:SUCCESS===' "$logf"; then
    pass "VPS deploy script reported SUCCESS"
    run_public_health || fail "Public health failed after deploy"
    show_deploy_summary
  else
    fail "VPS deploy failed or SUCCESS marker missing"
    echo "Log: $logf"
  fi
}

oneclick() {
  require_git || return
  init_branch
  [[ "$LOCAL_BRANCH" == "DETACHED" ]] && { fail "Detached HEAD"; return; }
  echo "${C_BOLD}[9] ONE CLICK Push + Deploy${C_RESET}"
  echo
  echo "${C_CYAN}Step 1/10${C_RESET} Git Status"
  git -C "$ROOT" status -sb
  echo
  echo "${C_CYAN}Step 2/10${C_RESET} Git Add"
  git -C "$ROOT" add -A && pass "Staged"
  echo "${C_CYAN}Step 3/10${C_RESET} Commit"
  local msg
  read -r -p "Commit message (Enter = auto): " msg
  [[ -z "$msg" ]] && msg="deploy $(date '+%d-%m-%Y %H%M')"
  if git -C "$ROOT" diff --cached --quiet; then
    info "Nothing new to commit"
  else
    git -C "$ROOT" commit -m "$msg" || { fail "Commit failed — abort"; return; }
    pass "Committed"
  fi
  echo "${C_CYAN}Step 4/10${C_RESET} Detect current branch"
  init_branch
  pass "Current branch = ${LOCAL_BRANCH}"
  echo "${C_CYAN}Step 5/10${C_RESET} Push origin HEAD"
  git -C "$ROOT" push -u origin HEAD || { fail "Push failed — abort"; return; }
  pass "Push OK"
  echo "${C_CYAN}Step 6-7/10${C_RESET} deployment/deploy.sh"
  local logf="${LOG_DIR}/oneclick_$(date +%Y%m%d_%H%M%S).log"
  if [[ "$ON_VPS" -eq 1 ]]; then
    (
      cd "$VPS_PATH" && export BRANCH="$LOCAL_BRANCH" VPS_APP_DIR="$VPS_PATH" GIT_BRANCH="$LOCAL_BRANCH"
      bash deployment/deploy.sh
    ) 2>&1 | tee "$logf"
  else
    require_ssh || return
    ssh -p "$VPS_PORT" -o StrictHostKeyChecking=accept-new \
      "${VPS_USER}@${VPS_HOST}" \
      "cd '$VPS_PATH' && export BRANCH='$LOCAL_BRANCH' VPS_APP_DIR='$VPS_PATH' GIT_BRANCH='$LOCAL_BRANCH' && bash deployment/deploy.sh" \
      2>&1 | tee "$logf"
  fi
  echo "${C_CYAN}Step 8/10${C_RESET} Read deployment result"
  if ! grep -q '===DEPLOY_RESULT:SUCCESS===' "$logf"; then
    fail "Deploy FAILED — SUCCESS marker not found"
    echo "--- last 40 lines ---"
    tail -n 40 "$logf"
    return
  fi
  pass "Deploy script SUCCESS"
  echo "${C_CYAN}Step 9/10${C_RESET} Public health"
  run_public_health || { fail "Health URL not HTTP 200 — deployment FAILED"; return; }
  echo "${C_CYAN}Step 10/10${C_RESET} Summary"
  show_deploy_summary
  pass "ONE CLICK DEPLOY COMPLETE"
  echo "Log: $logf"
}

restart_app() {
  push_and_sync_vps || return
  remote_or_local "export VPS_APP_DIR='$VPS_PATH' && bash deployment/install_service.sh" \
    && { pass "Service restart OK"; run_public_health; } \
    || fail "Restart/service repair FAILED"
}

health_check() {
  info "Public health…"
  run_public_health || true
  push_and_sync_vps || return
  info "VPS healthcheck…"
  remote_or_local "export VPS_APP_DIR='$VPS_PATH' && bash deployment/healthcheck.sh" || true
}

install_service() {
  echo "${C_BOLD}[10] Install/Repair VPS Service${C_RESET}"
  push_and_sync_vps || return
  remote_or_local "export VPS_APP_DIR='$VPS_PATH' && bash deployment/install_service.sh" \
    && { pass "Service install/repair OK"; run_public_health; } \
    || fail "Service install FAILED"
}

vps_status() {
  push_and_sync_vps || return
  remote_or_local "export VPS_APP_DIR='$VPS_PATH' && bash deployment/vps_status.sh" || true
}

show_branch() {
  require_git || return
  init_branch
  pass "Local branch: ${LOCAL_BRANCH}"
  git -C "$ROOT" branch -vv
}

show_commit() {
  require_git || return
  git -C "$ROOT" log -1 --format=fuller
  echo
  git -C "$ROOT" rev-parse HEAD
}

open_logs() {
  info "Local logs: ${LOG_DIR}"
  ls -lt "$LOG_DIR" 2>/dev/null | head -20 || echo "(empty)"
  echo
  info "VPS logs: /var/log/jtcs-erp/"
  remote_or_local "ls -lt /var/log/jtcs-erp 2>/dev/null | head -20; echo; echo '--- history ---'; tail -n 40 /var/log/jtcs-erp/deploy_history.log 2>/dev/null || echo '(no history yet)'" || true
}

rollback() {
  echo "${C_YELLOW}WARNING:${C_RESET} Rollback restores previous app files. SQL data is NOT overwritten by default."
  local confirm
  read -r -p "Type YES to rollback latest backup: " confirm
  [[ "$confirm" == "YES" ]] || { info "Rollback cancelled"; return; }
  push_and_sync_vps || return
  remote_or_local "export VPS_APP_DIR='$VPS_PATH' && bash deployment/rollback.sh --latest --reason manual-sh" \
    && { pass "Rollback finished"; run_public_health; } \
    || fail "Rollback FAILED"
}

repair() {
  push_and_sync_vps || return
  remote_or_local "export BRANCH='$LOCAL_BRANCH' VPS_APP_DIR='$VPS_PATH' GIT_BRANCH='$LOCAL_BRANCH' && bash deployment/repair.sh" \
    && { pass "Repair OK"; run_public_health; } \
    || fail "Repair FAILED"
}

diagnostics() {
  echo "${C_BOLD}[17] Full Diagnostics${C_RESET}"
  init_branch
  info "--- LOCAL ---"
  command -v git >/dev/null && pass "Git" || fail "Git"
  command -v ssh >/dev/null && pass "SSH" || fail "SSH"
  pass "Branch ${LOCAL_BRANCH}"
  pass "Commit $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  run_public_health || true
  echo
  info "--- VPS ---"
  push_and_sync_vps || return
  remote_or_local "export VPS_APP_DIR='$VPS_PATH' && bash deployment/diagnostics.sh" || true
}

db_structure_sync() {
  echo "${C_BOLD}[19] Check DB structure Local vs VPS + Update VPS${C_RESET}"
  echo
  warn "Policy: SCHEMA only — tables/columns. SQL DATA is never copied or wiped."
  echo
  require_git || return
  init_branch
  local py="${ROOT}/erp/.venv/bin/python"
  [[ -x "$py" ]] || py="${ROOT}/erp/.venv/Scripts/python.exe"
  if [[ ! -x "$py" && ! -f "$py" ]]; then
    fail "Local venv missing — run option 18 Install first"
    return
  fi
  local dump="${LOG_DIR}/schema_local_$$.json"
  echo "${C_CYAN}Step 1/5${C_RESET} Dump LOCAL database structure"
  (cd "${ROOT}/erp" && "$py" scripts/compare_and_sync_schema.py --dump "$dump") || {
    fail "Local schema dump failed — check erp/.env"
    return
  }
  pass "Local schema dumped → $dump"

  echo "${C_CYAN}Step 2/5${C_RESET} Push + sync code to VPS"
  push_and_sync_vps || return

  echo "${C_CYAN}Step 3/5${C_RESET} Upload schema dump to VPS"
  if [[ "$ON_VPS" -eq 1 ]]; then
    cp "$dump" /tmp/jtcs_schema_local.json
  else
    require_ssh || return
    scp -P "$VPS_PORT" -o StrictHostKeyChecking=accept-new \
      "$dump" "${VPS_USER}@${VPS_HOST}:/tmp/jtcs_schema_local.json" || {
      fail "scp upload failed"
      return
    }
  fi
  pass "Dump ready on VPS: /tmp/jtcs_schema_local.json"

  echo "${C_CYAN}Step 4/5${C_RESET} Apply numbered migrations on VPS"
  remote_or_local "cd '$VPS_PATH/erp' && if [ -x .venv/bin/python ]; then .venv/bin/python scripts/apply_schema_migrations.py; else python3 scripts/apply_schema_migrations.py; fi" \
    && pass "VPS migrations OK" \
    || fail "VPS migrations reported errors — continuing to column sync"

  echo "${C_CYAN}Step 5/5${C_RESET} Compare + add missing columns on VPS"
  if remote_or_local "cd '$VPS_PATH/erp' && if [ -x .venv/bin/python ]; then .venv/bin/python scripts/compare_and_sync_schema.py --sync-from /tmp/jtcs_schema_local.json; else python3 scripts/compare_and_sync_schema.py --sync-from /tmp/jtcs_schema_local.json; fi"; then
    pass "DB structure sync COMPLETE — VPS columns match local"
  else
    fail "Schema sync finished with warnings/errors (missing tables need migrations)"
  fi
}

# ---------------------------------------------------------------------------
# Local tools (this machine — Ubuntu PC or VPS)
# ---------------------------------------------------------------------------
local_menu() {
  while true; do
    clear
    echo
    echo "  ${C_CYAN}========================================${C_RESET}"
    echo "  ${C_BOLD}Local Development Tools (Ubuntu)${C_RESET}"
    echo "  ${C_CYAN}========================================${C_RESET}"
    echo
    echo "   1. Install (venv + requirements)"
    echo "   2. Start local server (gunicorn / flask)"
    echo "   3. Stop local server (port 8000)"
    echo "   4. Run auth tests"
    echo "   5. Open local login (xdg-open)"
    echo "   6. Edit erp/.env"
    echo "   D. Database SCHEMA update only (data safe)"
    echo "   0. Back to main menu"
    echo
    local lchoice
    read -r -p "Select: " lchoice
    lchoice="${lchoice// /}"
    case "$lchoice" in
      1) local_install; pause ;;
      2) local_start ;;
      3) local_stop; pause ;;
      4) local_test; pause ;;
      5) local_browser ;;
      6) local_env ;;
      D|d) local_schema; pause ;;
      0) return ;;
      *) fail "Invalid option"; pause ;;
    esac
  done
}

local_install() {
  info "Creating venv and installing requirements…"
  cd "${ROOT}/erp" || { fail "erp folder not found"; return; }
  command -v python3 >/dev/null || { fail "python3 not found"; return; }
  [[ -x .venv/bin/python ]] || python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install --upgrade pip
  [[ -f requirements.txt ]] && pip install -r requirements.txt
  pip install -q "gunicorn>=22.0.0"
  [[ ! -f .env && -f .env.example ]] && cp .env.example .env
  pass "Local install done"
  cd "$ROOT"
}

local_start() {
  cd "${ROOT}/erp" || { fail "erp folder not found"; return; }
  if [[ ! -x .venv/bin/python ]]; then
    fail "venv missing — run Local Install first"
    return
  fi
  fuser -k 8000/tcp 2>/dev/null || true
  # shellcheck disable=SC1091
  source .venv/bin/activate
  info "URL: http://127.0.0.1:8000/login"
  info "Press Ctrl+C to stop."
  if [[ -x .venv/bin/gunicorn && -f wsgi.py ]]; then
    exec .venv/bin/gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 180 wsgi:app
  elif [[ -f run.py ]]; then
    exec python run.py
  else
    fail "Neither gunicorn/wsgi.py nor run.py found"
  fi
}

local_stop() {
  info "Stopping listeners on :8000"
  fuser -k 8000/tcp 2>/dev/null || true
  pkill -f 'gunicorn.*wsgi:app' 2>/dev/null || true
  pass "Done"
}

local_test() {
  cd "${ROOT}/erp" || return
  [[ -x .venv/bin/python ]] || { fail "venv missing"; return; }
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python scripts/test_auth.py
  cd "$ROOT"
}

local_browser() {
  if command -v xdg-open >/dev/null; then
    xdg-open "http://127.0.0.1:8000/login" >/dev/null 2>&1 &
  else
    info "Open in browser: http://127.0.0.1:8000/login"
  fi
}

local_env() {
  local f="${ROOT}/erp/.env"
  [[ ! -f "$f" && -f "${ROOT}/erp/.env.example" ]] && cp "${ROOT}/erp/.env.example" "$f"
  "${EDITOR:-nano}" "$f"
}

local_schema() {
  info "Schema-only DB update (DATA safe)…"
  cd "${ROOT}/erp" || return
  [[ -x .venv/bin/python ]] || { fail "venv missing"; return; }
  .venv/bin/python scripts/apply_schema_migrations.py \
    && pass "Schema update OK" \
    || fail "Schema update failed — data not overwritten"
  cd "$ROOT"
}

# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------
main_menu() {
  load_vps_env
  init_branch
  detect_on_vps
  while true; do
    clear
    echo
    echo "  ${C_CYAN}========================================${C_RESET}"
    echo "  ${C_BOLD}JTCS ERP Deployment Console (Ubuntu)${C_RESET}"
    echo "  ${C_CYAN}========================================${C_RESET}"
    echo "  Host   : ${VPS_USER}@${VPS_HOST}:${VPS_PORT}"
    echo "  Path   : ${VPS_PATH}"
    echo "  Branch : ${C_YELLOW}${LOCAL_BRANCH}${C_RESET}"
    echo "  Health : ${PUBLIC_HEALTH_URL}"
    if [[ "$ON_VPS" -eq 1 ]]; then
      echo "  Mode   : ${C_GREEN}ON VPS (local deploy)${C_RESET}"
    else
      echo "  Mode   : ${C_YELLOW}SSH → VPS${C_RESET}"
    fi
    echo "  ${C_CYAN}========================================${C_RESET}"
    echo
    echo "   1. Git Status"
    echo "   2. Git Add All"
    echo "   3. Commit Changes"
    echo "   4. Push Current Branch"
    echo "   5. Pull Latest"
    echo "   6. Deploy to VPS"
    echo "   7. Restart Application"
    echo "   8. Health Check"
    echo "   9. One Click Push + Deploy"
    echo "  10. Install/Repair VPS Service"
    echo "  11. Show Current VPS Status"
    echo "  12. Show Current Git Branch"
    echo "  13. Show Latest Commit"
    echo "  14. Open Deployment Logs"
    echo "  15. Rollback Previous Version"
    echo "  16. Repair Deployment"
    echo "  17. Full Diagnostics"
    echo "  18. Local Tools (install / start / stop / test / env / schema)"
    echo "  19. Check DB structure Local vs VPS + Update VPS"
    echo "   0. Exit"
    echo
    local choice
    read -r -p "Select option (0-19): " choice
    choice="${choice// /}"
    case "$choice" in
      1) git_status; pause ;;
      2) git_add; pause ;;
      3) git_commit; pause ;;
      4) git_push; pause ;;
      5) git_pull; pause ;;
      6) deploy_vps; pause ;;
      7) restart_app; pause ;;
      8) health_check; pause ;;
      9) oneclick; pause ;;
      10) install_service; pause ;;
      11) vps_status; pause ;;
      12) show_branch; pause ;;
      13) show_commit; pause ;;
      14) open_logs; pause ;;
      15) rollback; pause ;;
      16) repair; pause ;;
      17) diagnostics; pause ;;
      18|L|l) local_menu ;;
      19) db_structure_sync; pause ;;
      0) echo "Bye."; exit 0 ;;
      *) fail "Invalid option: ${choice}"; pause ;;
    esac
    init_branch
    detect_on_vps
  done
}

main_menu
