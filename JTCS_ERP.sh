#!/usr/bin/env bash
# =============================================================================
# JTCS ERP — same 3 options as JTCS_ERP.bat
#   bash JTCS_ERP.sh
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

VPS_HOST="200.234.41.220"
VPS_USER="root"
VPS_PORT="22"
VPS_PATH="/root/JTCS-final"
PUBLIC_HEALTH_URL="https://app.jtcsxpert.com/health"
LOCAL_BRANCH=""
ON_VPS=0

pass() { echo "${C_GREEN}[PASS]${C_RESET} $*"; }
fail() { echo "${C_RED}[FAIL]${C_RESET} $*"; }
info() { echo "${C_CYAN}[INFO]${C_RESET} $*"; }

pause() { read -r -p "Press Enter to continue..." _; }

load_vps_env() {
  local f="${ROOT}/deploy_vps.env"
  if [[ -f "$f" ]]; then
    # shellcheck disable=SC1090
    set -a
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
  if [[ -d /root/JTCS-final/.git && "$ROOT" == "/root/JTCS-final" ]]; then
    ON_VPS=1
  fi
}

require_git() {
  command -v git >/dev/null 2>&1 || { fail "git not found"; return 1; }
}

require_ssh() {
  command -v ssh >/dev/null 2>&1 || { fail "ssh not found"; return 1; }
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

show_deploy_summary() {
  init_branch
  local commit
  commit="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo
  echo "  ${C_BOLD}Deploy Summary${C_RESET}"
  echo "  Branch  : ${LOCAL_BRANCH}"
  echo "  Commit  : ${commit}"
  echo "  Live    : ${PUBLIC_HEALTH_URL}"
  echo "  Time    : $(date '+%Y-%m-%d %H:%M:%S %z')"
  echo
}

run_local() {
  echo "${C_BOLD}[1] Run at local${C_RESET}"
  cd "${ROOT}/erp" || { fail "erp folder not found"; return; }
  if [[ ! -x .venv/bin/python ]]; then
    info "First run — creating venv and installing requirements..."
    command -v python3 >/dev/null 2>&1 || { fail "python3 not found"; return; }
    python3 -m venv .venv || { fail "venv create failed"; return; }
    # shellcheck disable=SC1091
    source .venv/bin/activate
    python -m pip install --upgrade pip
    [[ -f requirements.txt ]] && python -m pip install -r requirements.txt
    [[ ! -f .env && -f .env.example ]] && cp .env.example .env
    pass "Local install done"
  else
    # shellcheck disable=SC1091
    source .venv/bin/activate
  fi
  fuser -k 8000/tcp 2>/dev/null || true
  info "URL: http://127.0.0.1:8000/login"
  info "Press Ctrl+C to stop."
  if [[ -f run.py ]]; then
    python run.py
  elif [[ -x .venv/bin/gunicorn && -f wsgi.py ]]; then
    .venv/bin/gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 180 wsgi:app
  else
    fail "run.py / wsgi.py not found"
  fi
  cd "$ROOT"
}

push_and_deploy() {
  require_git || return
  init_branch
  [[ "$LOCAL_BRANCH" == "DETACHED" ]] && { fail "Detached HEAD — checkout a branch first"; return; }
  echo "${C_BOLD}[2] Push and deploy${C_RESET}"
  echo
  echo "${C_CYAN}Step 1/6${C_RESET} Git status"
  git -C "$ROOT" status -sb
  echo
  echo "${C_CYAN}Step 2/6${C_RESET} Stage all changes"
  git -C "$ROOT" add -A && pass "Staged"
  echo "${C_CYAN}Step 3/6${C_RESET} Commit"
  local msg
  read -r -p "Commit message (Enter = auto): " msg
  [[ -z "$msg" ]] && msg="deploy $(date '+%d-%m-%Y %H%M')"
  if git -C "$ROOT" diff --cached --quiet; then
    info "Nothing new to commit"
  else
    git -C "$ROOT" commit -m "$msg" || { fail "Commit failed — abort"; return; }
    pass "Committed"
  fi
  echo "${C_CYAN}Step 4/6${C_RESET} Push origin/${LOCAL_BRANCH}"
  git -C "$ROOT" push -u origin HEAD || { fail "Push failed — abort"; return; }
  pass "Push OK"
  echo "${C_CYAN}Step 5/6${C_RESET} Deploy on VPS (deployment/deploy.sh)"
  local logf="${LOG_DIR}/deploy_$(date +%Y%m%d_%H%M%S).log"
  if [[ "$ON_VPS" -eq 1 ]]; then
    (
      cd "$VPS_PATH" && export BRANCH="$LOCAL_BRANCH" VPS_APP_DIR="$VPS_PATH" GIT_BRANCH="$LOCAL_BRANCH"
      bash deployment/deploy.sh
    ) 2>&1 | tee "$logf"
  else
    require_ssh || return
    echo "Enter VPS password when asked."
    ssh -p "$VPS_PORT" -o StrictHostKeyChecking=accept-new \
      "${VPS_USER}@${VPS_HOST}" \
      "cd '$VPS_PATH' && export BRANCH='$LOCAL_BRANCH' VPS_APP_DIR='$VPS_PATH' GIT_BRANCH='$LOCAL_BRANCH' && bash deployment/deploy.sh" \
      2>&1 | tee "$logf"
  fi
  if ! grep -q '===DEPLOY_RESULT:SUCCESS===' "$logf"; then
    fail "Deploy FAILED — SUCCESS marker not found"
    echo "--- last 40 lines ---"
    tail -n 40 "$logf"
    echo "Log: $logf"
    return
  fi
  pass "Deploy script SUCCESS"
  echo "${C_CYAN}Step 6/6${C_RESET} Public health check"
  run_public_health || { fail "Health URL not HTTP 200 — deployment FAILED"; return; }
  show_deploy_summary
  pass "PUSH AND DEPLOY COMPLETE"
  echo "Log: $logf"
}

menu() {
  while true; do
    clear 2>/dev/null || true
    init_branch
    echo
    echo "  ${C_CYAN}========================================${C_RESET}"
    echo "  ${C_BOLD}JTCS ERP${C_RESET}"
    echo "  ${C_CYAN}========================================${C_RESET}"
    echo "  Branch : ${C_YELLOW}${LOCAL_BRANCH}${C_RESET}"
    echo "  Live   : ${PUBLIC_HEALTH_URL}"
    echo "  Local  : http://localhost:8000"
    echo "  ${C_CYAN}========================================${C_RESET}"
    echo
    echo "   1. Run at local"
    echo "   2. Push and deploy"
    echo "   0. Exit"
    echo
    local choice
    read -r -p "Select option (0-2): " choice
    choice="${choice// /}"
    case "$choice" in
      1) run_local; pause ;;
      2) push_and_deploy; pause ;;
      0) exit 0 ;;
      *) fail "Invalid option: ${choice}"; pause ;;
    esac
  done
}

load_vps_env
init_branch
detect_on_vps
menu
