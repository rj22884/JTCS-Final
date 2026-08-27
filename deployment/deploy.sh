#!/usr/bin/env bash
# =============================================================================
# JTCS ERP — CANONICAL production deploy (Ubuntu VPS)
# ONLY deployment path. Do not use scripts/vps_pull_update.sh.
#
# Entry: Flask WSGI via Gunicorn (wsgi:app) — NEVER run.py
# Branch: BRANCH / GIT_BRANCH / current branch — NEVER hardcode main
#
# Usage:
#   export BRANCH="$(git branch --show-current)"   # from Windows SSH caller
#   bash deployment/deploy.sh
#   bash deployment/deploy.sh --skip-backup
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"
load_deploy_env

VERSION=""
RELEASE_NOTES=""
DEVELOPER="${DEFAULT_DEVELOPER:-}"
WHATS_NEW=""
BUG_FIXES=""
FEATURES=""
DB_CHANGES=""
SECURITY_UPDATES=""
PERFORMANCE=""
SKIP_BACKUP=0
SKIP_ROLLBACK=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    --notes) RELEASE_NOTES="$2"; shift 2 ;;
    --developer) DEVELOPER="$2"; shift 2 ;;
    --whats-new) WHATS_NEW="$2"; shift 2 ;;
    --bug-fixes) BUG_FIXES="$2"; shift 2 ;;
    --features) FEATURES="$2"; shift 2 ;;
    --db-changes) DB_CHANGES="$2"; shift 2 ;;
    --security) SECURITY_UPDATES="$2"; shift 2 ;;
    --performance) PERFORMANCE="$2"; shift 2 ;;
    --skip-backup) SKIP_BACKUP=1; shift ;;
    --skip-rollback) SKIP_ROLLBACK=1; shift ;;
    *) log_error "Unknown arg: $1"; echo "===DEPLOY_RESULT:FAILED==="; exit 2 ;;
  esac
done

APP_DIR="${VPS_APP_DIR:-${REPO_ROOT}}"
export DEPLOY_GIT_ROOT="${APP_DIR}"
ERP_DIR="${APP_DIR}/${VPS_ERP_DIR:-erp}"
VENV="${VPS_VENV_DIR:-${ERP_DIR}/.venv}"
SERVICE="${VPS_SYSTEMD_SERVICE:-jtcs-erp}"
REMOTE="${GIT_REMOTE:-origin}"
LOG_DIR="${VPS_LOG_DIR:-/var/log/jtcs-erp}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"
PUBLIC_HEALTH="${PUBLIC_HEALTH_URL:-https://app.jtcsxpert.com/health}"
REPORT_DIR="${LOG_DIR}/reports"
ensure_dir "${LOG_DIR}"
ensure_dir "${REPORT_DIR}"
LOG_FILE="${LOG_DIR}/deploy_$(timestamp_now).log"
REPORT_FILE="${REPORT_DIR}/deploy_report_$(timestamp_now).txt"
STATUS="Failed"
BACKUP_PATH=""
PREV_COMMIT=""
AFTER_COMMIT=""
START_EPOCH="$(date +%s)"
ROLLED=0
DASH_INDEX_SHA=""
BASE_HTML_SHA=""
DASH_JS_SHA=""

# Resolve branch — never hardcode main
BRANCH="${BRANCH:-${GIT_BRANCH:-}}"
if [[ -z "${BRANCH}" || "${BRANCH}" == "HEAD" ]]; then
  BRANCH="$(git -C "${APP_DIR}" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
fi
if [[ -z "${BRANCH}" || "${BRANCH}" == "HEAD" ]]; then
  log_error "Cannot determine git branch. Export BRANCH=<name> before deploy."
  echo "===DEPLOY_RESULT:FAILED==="
  exit 1
fi

exec > >(tee -a "${LOG_FILE}") 2>&1

abort_deploy() {
  local reason="$1"
  log_error "ABORT: ${reason}"
  STATUS="Failed"
  write_deploy_report "FAILED" "${reason}"
  if [[ ${SKIP_ROLLBACK} -eq 1 ]]; then
    log_warn "Auto-rollback disabled (--skip-rollback)"
  elif [[ -x "${SCRIPT_DIR}/rollback.sh" ]]; then
    log_warn "Invoking automatic rollback…"
    if [[ -n "${BACKUP_PATH}" ]]; then
      bash "${SCRIPT_DIR}/rollback.sh" --backup "${BACKUP_PATH}" --reason "${reason}" || true
    else
      bash "${SCRIPT_DIR}/rollback.sh" --latest --reason "${reason}" || true
    fi
    STATUS="RolledBack"
    ROLLED=1
  fi
  exit 1
}

file_sha256() {
  local path="$1"
  if [[ -f "${path}" ]]; then
    sha256sum "${path}" | awk '{print $1}'
  else
    echo "MISSING"
  fi
}

write_deploy_report() {
  local result="$1"
  local reason="${2:-}"
  {
    echo "============================================================"
    echo " JTCS ERP — DEPLOYMENT REPORT"
    echo "============================================================"
    echo "Result          : ${result}"
    echo "Reason          : ${reason:-n/a}"
    echo "Timestamp       : $(iso_now)"
    echo "PWD             : $(pwd 2>/dev/null || echo n/a)"
    echo "App dir         : ${APP_DIR}"
    echo "ERP dir         : ${ERP_DIR}"
    echo "Branch          : ${BRANCH}"
    echo "Remote          : ${REMOTE}"
    echo "Commit (before) : ${PREV_COMMIT:-n/a}"
    echo "Commit (after)  : ${AFTER_COMMIT:-$(git_full_commit 2>/dev/null || echo n/a)}"
    echo "Service         : ${SERVICE}"
    echo "Backup          : ${BACKUP_PATH:-n/a}"
    echo "Log             : ${LOG_FILE}"
    echo "dashboard/index.html SHA256 : ${DASH_INDEX_SHA:-n/a}"
    echo "layouts/base.html SHA256    : ${BASE_HTML_SHA:-n/a}"
    echo "static/js/dashboard.js SHA256 : ${DASH_JS_SHA:-n/a}"
    echo "------------------------------------------------------------"
    echo "git status --short:"
    git -C "${APP_DIR}" status --short 2>/dev/null || echo "(git status unavailable)"
    echo "------------------------------------------------------------"
    echo "git rev-parse HEAD:"
    git -C "${APP_DIR}" rev-parse HEAD 2>/dev/null || echo "(unavailable)"
    echo "============================================================"
  } | tee "${REPORT_FILE}"
  log_info "Deployment report: ${REPORT_FILE}"
}

emit_result() {
  local result="$1"
  echo ""
  echo "===DEPLOY_RESULT:${result}==="
  echo "===DEPLOY_BRANCH:$(git_branch_name)==="
  echo "===DEPLOY_COMMIT:$(git_full_commit)==="
  echo "===DEPLOY_SHORT:$(git_commit_id)==="
  echo "===DEPLOY_VERSION:${VERSION:-n/a}==="
  echo "===DEPLOY_TIME:$(iso_now)==="
  echo "===DEPLOY_LOG:${LOG_FILE}==="
  echo "===DEPLOY_REPORT:${REPORT_FILE}==="
  echo "===DEPLOY_HEALTH:${HEALTH_URL}==="
  echo "===DEPLOY_PUBLIC_HEALTH:${PUBLIC_HEALTH}==="
  echo "===DEPLOY_COMMIT_BEFORE:${PREV_COMMIT:-n/a}==="
  echo "===DEPLOY_COMMIT_AFTER:$(git_full_commit)==="
  echo "===DEPLOY_DASH_INDEX_SHA:${DASH_INDEX_SHA:-n/a}==="
  echo "===DEPLOY_BASE_HTML_SHA:${BASE_HTML_SHA:-n/a}==="
  echo "===DEPLOY_DASH_JS_SHA:${DASH_JS_SHA:-n/a}==="
}

finish() {
  local end duration
  end="$(date +%s)"
  duration=$((end - START_EPOCH))
  append_deploy_log "${LOG_DIR}/deploy_history.log" \
"Deployment Date: $(date +%F)
Time: $(date +%T)
Git Commit ID: $(git_full_commit)
Git Branch: $(git_branch_name)
Version: ${VERSION:-n/a}
Backup: ${BACKUP_PATH:-n/a}
Status: ${STATUS}
Duration: ${duration}s
Log: ${LOG_FILE}
Report: ${REPORT_FILE}
"
  if [[ "${STATUS}" == "Success" ]]; then
    log_ok "DEPLOYMENT SUCCESS (${duration}s) — $(git_branch_name) @ $(git_commit_id)"
    emit_result "SUCCESS"
    exit 0
  fi
  log_error "DEPLOYMENT ${STATUS} (${duration}s) — see ${LOG_FILE}"
  emit_result "${STATUS}"
  exit 1
}

trap finish EXIT

log_info "=== JTCS ERP deploy start ==="
require_cmd git curl
command -v rsync >/dev/null 2>&1 || log_warn "rsync missing — backup may be limited"

# ---------------------------------------------------------------------------
# 1) Current working directory
# ---------------------------------------------------------------------------
cd "${APP_DIR}" || abort_deploy "cannot cd to APP_DIR ${APP_DIR}"
log_info "PWD: $(pwd)"
log_info "App dir : ${APP_DIR}"
log_info "ERP dir : ${ERP_DIR}"
log_info "Service : ${SERVICE}"
log_info "Log     : ${LOG_FILE}"

# ---------------------------------------------------------------------------
# 2) Git branch  /  3) Git commit (before)
# ---------------------------------------------------------------------------
log_info "Git branch: ${BRANCH}"
PREV_COMMIT="$(git rev-parse HEAD 2>/dev/null || true)"
[[ -n "${PREV_COMMIT}" ]] || abort_deploy "cannot read git rev-parse HEAD before deploy"
log_info "Git commit BEFORE deploy: ${PREV_COMMIT}"
log_info "git rev-parse HEAD (before): ${PREV_COMMIT}"

# ---------------------------------------------------------------------------
# Backup (hard-fail if tools exist and backup fails; skip only with flag/tools missing)
# ---------------------------------------------------------------------------
if [[ ${SKIP_BACKUP} -eq 0 ]]; then
  if [[ -x "${SCRIPT_DIR}/backup.sh" ]] && command -v rsync >/dev/null 2>&1; then
    if BACKUP_PATH="$(bash "${SCRIPT_DIR}/backup.sh" ${VERSION:+--version "${VERSION}"} | tail -n 1)"; then
      log_info "Backup path: ${BACKUP_PATH}"
    else
      abort_deploy "backup failed"
    fi
  else
    log_warn "Backup tools unavailable (rsync/backup.sh) — continuing without backup"
  fi
else
  log_warn "Skipping full backup (--skip-backup)"
fi

# ---------------------------------------------------------------------------
# Preserve .env across hard reset / clean
# ---------------------------------------------------------------------------
ENV_BAK="/tmp/jtcs.env.bak.$$"
if [[ -f "${ERP_DIR}/.env" ]]; then
  cp "${ERP_DIR}/.env" "${ENV_BAK}" || abort_deploy "failed to backup erp/.env"
  log_info "Backed up erp/.env"
fi

# ---------------------------------------------------------------------------
# 4) Git fetch --all
# ---------------------------------------------------------------------------
log_info "git fetch --all…"
if ! git fetch --all --prune; then
  abort_deploy "git fetch --all failed"
fi

if ! git show-ref --verify --quiet "refs/remotes/${REMOTE}/${BRANCH}"; then
  abort_deploy "remote branch ${REMOTE}/${BRANCH} not found"
fi

# ---------------------------------------------------------------------------
# 5) Hard reset to origin/$BRANCH
# ---------------------------------------------------------------------------
log_info "Hard reset to ${REMOTE}/${BRANCH}…"
if ! git checkout -B "${BRANCH}" "${REMOTE}/${BRANCH}"; then
  abort_deploy "git checkout ${BRANCH} failed"
fi
if ! git reset --hard "${REMOTE}/${BRANCH}"; then
  abort_deploy "git reset --hard ${REMOTE}/${BRANCH} failed"
fi

# ---------------------------------------------------------------------------
# 6) Git clean — remove every untracked/deleted leftover
# ---------------------------------------------------------------------------
log_info "git clean -fd…"
if ! git clean -fd; then
  abort_deploy "git clean -fd failed"
fi

if [[ -f "${ENV_BAK}" ]]; then
  mkdir -p "${ERP_DIR}"
  cp "${ENV_BAK}" "${ERP_DIR}/.env" || abort_deploy "failed to restore erp/.env"
  rm -f "${ENV_BAK}"
  log_ok "Restored erp/.env"
fi

if [[ ! -f "${ERP_DIR}/.env" ]]; then
  abort_deploy "erp/.env missing after deploy"
fi

AFTER_COMMIT="$(git rev-parse HEAD)"
log_ok "Code updated: branch=$(git rev-parse --abbrev-ref HEAD) commit=${AFTER_COMMIT}"
log_info "git rev-parse HEAD (after): ${AFTER_COMMIT}"

if [[ ! -f "${ERP_DIR}/wsgi.py" ]]; then
  abort_deploy "wsgi.py missing — refusing run.py fallback"
fi

# ---------------------------------------------------------------------------
# 7) Delete bytecode / pytest caches
# ---------------------------------------------------------------------------
# Skip .venv — legacy commits may track bytecode under backend/.venv; wiping
# those makes `git diff HEAD` fail and aborts deploy after a successful reset.
log_info "Clearing __pycache__, *.pyc, *.pyo, .pytest_cache (excluding .venv)…"
find "${APP_DIR}" \
  \( -path '*/.venv' -o -path '*/.venv/*' -o -path '*/venv' -o -path '*/venv/*' \) -prune -o \
  -type d -name '__pycache__' -print0 2>/dev/null \
  | xargs -0 -r rm -rf 2>/dev/null || true
find "${APP_DIR}" \
  \( -path '*/.venv' -o -path '*/.venv/*' -o -path '*/venv' -o -path '*/venv/*' \) -prune -o \
  -type f \( -name '*.pyc' -o -name '*.pyo' \) -print0 2>/dev/null \
  | xargs -0 -r rm -f 2>/dev/null || true
find "${APP_DIR}" \
  \( -path '*/.venv' -o -path '*/.venv/*' -o -path '*/venv' -o -path '*/venv/*' \) -prune -o \
  -type d -name '.pytest_cache' -print0 2>/dev/null \
  | xargs -0 -r rm -rf 2>/dev/null || true
# If anything tracked was still removed, restore from HEAD before the dirty check.
git checkout -f HEAD -- . >/dev/null 2>&1 || true

# ---------------------------------------------------------------------------
# 8) Delete old static / template caches (never leave stale UI assets)
# ---------------------------------------------------------------------------
log_info "Clearing old static / template caches…"
# Preserve uploaded user content; clear generated caches only.
find "${ERP_DIR}" -type d \( \
  -name '.webassets-cache' -o \
  -name '.cache' -o \
  -name '__cache__' -o \
  -name 'flask_cache' -o \
  -name '.mypy_cache' -o \
  -name '.ruff_cache' \
\) -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf \
  "${ERP_DIR}/instance/cache" \
  "${ERP_DIR}/.pytest_cache" \
  "${APP_DIR}/.pytest_cache" \
  2>/dev/null || true
# Nginx proxy/static cache (if present on this host)
if [[ -d /var/cache/nginx ]]; then
  find /var/cache/nginx -type f -delete 2>/dev/null || true
  log_info "Cleared /var/cache/nginx files"
fi

# ---------------------------------------------------------------------------
# 9–10) Verify dashboard widgets — search + print every matching filename
# ---------------------------------------------------------------------------
log_info "Searching for removed CRM dashboard widget labels…"
WIDGET_PATTERN="Today's Leads|Unread Notifications|Unread Messages|Pending Tasks|Upcoming Follow-up|Open Leads"
SEARCH_DIRS=()
for d in \
  "${ERP_DIR}/app/templates" \
  "${ERP_DIR}/app/static" \
  "${ERP_DIR}/app/routes" \
  "${ERP_DIR}/app/modules" \
  "${ERP_DIR}/app/controllers" \
  "${ERP_DIR}/app/blueprints"
do
  [[ -d "${d}" ]] && SEARCH_DIRS+=("${d}")
done
mapfile -t MATCH_FILES < <(
  if [[ ${#SEARCH_DIRS[@]} -gt 0 ]]; then
    grep -RIlE --binary-files=without-match "${WIDGET_PATTERN}" "${SEARCH_DIRS[@]}" 2>/dev/null | sort -u || true
  fi
)

if [[ ${#MATCH_FILES[@]} -eq 0 || -z "${MATCH_FILES[0]:-}" ]]; then
  log_ok "No widget-label matches under templates/static/routes/modules"
else
  log_warn "Widget-label matches (${#MATCH_FILES[@]} file(s)):"
  for f in "${MATCH_FILES[@]}"; do
    [[ -n "${f}" ]] && echo "  MATCH: ${f}"
  done
fi

# Main ERP dashboard must not still ship the removed CRM widget strip.
DASH_INDEX="${ERP_DIR}/app/templates/dashboard/index.html"
if [[ -f "${DASH_INDEX}" ]] && grep -E "${WIDGET_PATTERN}" "${DASH_INDEX}" >/dev/null 2>&1; then
  abort_deploy "erp/app/templates/dashboard/index.html still contains removed CRM widgets — commit/push was not deployed or remote still has old UI"
fi

# ---------------------------------------------------------------------------
# 15–17) Checksums for critical UI files
# ---------------------------------------------------------------------------
DASH_INDEX_SHA="$(file_sha256 "${DASH_INDEX}")"
BASE_HTML_SHA="$(file_sha256 "${ERP_DIR}/app/templates/layouts/base.html")"
DASH_JS_SHA="$(file_sha256 "${ERP_DIR}/app/static/js/dashboard.js")"
log_info "checksum dashboard/index.html = ${DASH_INDEX_SHA}"
log_info "checksum layouts/base.html    = ${BASE_HTML_SHA}"
log_info "checksum static/js/dashboard.js = ${DASH_JS_SHA}"
if [[ "${DASH_INDEX_SHA}" == "MISSING" || "${BASE_HTML_SHA}" == "MISSING" || "${DASH_JS_SHA}" == "MISSING" ]]; then
  abort_deploy "critical UI file missing (dashboard/index.html, base.html, or dashboard.js)"
fi

# ---------------------------------------------------------------------------
# 18) Compare deployed files with Git (working tree must match HEAD)
# ---------------------------------------------------------------------------
log_info "Comparing working tree to Git HEAD…"
if ! git diff --quiet HEAD -- \
  "erp/app/templates/dashboard/index.html" \
  "erp/app/templates/layouts/base.html" \
  "erp/app/static/js/dashboard.js"
then
  abort_deploy "critical UI files differ from Git HEAD"
fi
# Refresh index so stale stat info cannot fake dirtiness.
git update-index --refresh >/dev/null 2>&1 || true
if ! git diff --quiet HEAD; then
  log_warn "Tracked file content differs from HEAD (showing):"
  git diff --stat HEAD || true
  abort_deploy "working tree content does not match Git HEAD after reset/clean"
fi

# ---------------------------------------------------------------------------
# Python deps + gunicorn
# ---------------------------------------------------------------------------
REQ_FILE="${ERP_DIR}/requirements.txt"
REQ_HASH_FILE="${ERP_DIR}/.requirements.sha256"
NEW_HASH=""
OLD_HASH=""
if [[ -f "${REQ_FILE}" ]]; then
  NEW_HASH="$(sha256sum "${REQ_FILE}" | awk '{print $1}')"
  [[ -f "${REQ_HASH_FILE}" ]] && OLD_HASH="$(cat "${REQ_HASH_FILE}")"
fi

if [[ ! -x "${VENV}/bin/python" ]]; then
  log_info "Creating virtualenv at ${VENV}"
  python3 -m venv "${VENV}" || abort_deploy "venv create failed"
fi
# shellcheck disable=SC1091
source "${VENV}/bin/activate"

if [[ "${NEW_HASH}" != "${OLD_HASH}" ]]; then
  log_info "Installing Python packages…"
  pip install --upgrade pip || abort_deploy "pip upgrade failed"
  pip install -r "${REQ_FILE}" || abort_deploy "pip install -r requirements.txt failed"
  echo "${NEW_HASH}" > "${REQ_HASH_FILE}"
else
  log_info "requirements.txt unchanged — ensuring gunicorn"
fi
pip install -q "gunicorn>=22.0.0" || abort_deploy "gunicorn install failed"

# EasyOCR pulls opencv-python (needs libGL). Keep headless OpenCV on Linux VPS.
if [[ "$(uname -s)" == "Linux" ]]; then
  log_info "Ensuring Linux OCR system libraries + opencv-python-headless"
  if [[ "${EUID}" -eq 0 ]]; then SUDO_OCR=""; else SUDO_OCR="sudo"; fi
  ${SUDO_OCR} apt-get install -y libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 tesseract-ocr tesseract-ocr-eng >/dev/null 2>&1 \
    || ${SUDO_OCR} apt-get install -y libgl1-mesa-glx libglib2.0-0 tesseract-ocr tesseract-ocr-eng >/dev/null 2>&1 \
    || log_warn "Could not apt-install libGL/tesseract (run deployment/fix_vps_ocr.sh)"
  pip uninstall -y opencv-python opencv-contrib-python >/dev/null 2>&1 || true
  pip install -q "opencv-python-headless>=4.8.0" || log_warn "opencv-python-headless install failed"
fi

# ---------------------------------------------------------------------------
# Schema-only migrations
# ---------------------------------------------------------------------------
if [[ -f "${SCRIPT_DIR}/apply_migrations.sh" ]]; then
  # Use bash explicitly — do not chmod (avoids dirty filemode in git status).
  log_info "Applying SCHEMA-ONLY migrations…"
  if ! bash "${SCRIPT_DIR}/apply_migrations.sh"; then
    abort_deploy "database migration failed"
  fi
else
  log_warn "apply_migrations.sh missing — skip SQL migrations"
fi

# ---------------------------------------------------------------------------
# Version record (best-effort)
# ---------------------------------------------------------------------------
if [[ -n "${VERSION}" ]]; then
  sync_app_version_env "${VPS_FLASK_ENV_FILE:-${ERP_DIR}/.env}" "${VERSION}"
fi
if [[ -f "${SCRIPT_DIR}/record_version.py" ]]; then
  python "${SCRIPT_DIR}/record_version.py" \
    --version "${VERSION:-}" \
    --notes "${RELEASE_NOTES}" \
    --developer "${DEVELOPER}" \
    --commit "$(git_full_commit)" \
    --branch "$(git_branch_name)" \
    --backup "${BACKUP_PATH}" \
    --status "Success" \
    --whats-new "${WHATS_NEW}" \
    --bug-fixes "${BUG_FIXES}" \
    --features "${FEATURES}" \
    --db-changes "${DB_CHANGES}" \
    --security "${SECURITY_UPDATES}" \
    --performance "${PERFORMANCE}" \
    || log_warn "Version recording failed (non-fatal)"
fi

# ---------------------------------------------------------------------------
# 11) Restart application — completely stop old process, start fresh
# ---------------------------------------------------------------------------
log_info "Hard-stopping old application processes…"
systemctl stop "${SERVICE}" 2>/dev/null || true
pkill -9 -f 'gunicorn.*wsgi:app' 2>/dev/null || true
pkill -9 -f 'python.*run.py' 2>/dev/null || true
if command -v fuser >/dev/null 2>&1; then
  fuser -k 8000/tcp 2>/dev/null || true
fi
sleep 1

# Re-clear bytecode after stop (stale workers may have rewritten .pyc)
find "${ERP_DIR}" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "${ERP_DIR}" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true

log_info "Installing/repairing systemd unit (gunicorn wsgi:app)…"
if ! bash "${SCRIPT_DIR}/install_service.sh"; then
  abort_deploy "systemd install/restart failed"
fi

if ! systemctl is-active --quiet "${SERVICE}"; then
  abort_deploy "service ${SERVICE} not active after restart"
fi
log_ok "Service ${SERVICE} active (fresh start)"

# ---------------------------------------------------------------------------
# 12) Reload nginx
# ---------------------------------------------------------------------------
if command -v nginx >/dev/null 2>&1 && systemctl is-active --quiet nginx; then
  log_info "Reloading nginx…"
  if ! nginx -t; then
    abort_deploy "nginx -t failed"
  fi
  if ! systemctl reload nginx; then
    abort_deploy "nginx reload failed"
  fi
  log_ok "nginx reloaded"
elif [[ "${VPS_NGINX_RELOAD:-1}" == "1" ]]; then
  log_warn "nginx not active — skip reload"
fi

# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------
log_info "Health check: ${HEALTH_URL} (waiting for workers to accept connections)"
export HEALTH_WAIT_SECONDS="${HEALTH_WAIT_SECONDS:-180}"
if ! bash "${SCRIPT_DIR}/healthcheck.sh"; then
  abort_deploy "health check failed after restart"
fi

if http_ok "${PUBLIC_HEALTH}"; then
  log_ok "Public health OK: ${PUBLIC_HEALTH}"
else
  log_warn "Public health not reachable from VPS: ${PUBLIC_HEALTH} (Windows will re-check)"
fi

# ---------------------------------------------------------------------------
# 13) git status must be clean  /  14) print HEAD again
# ---------------------------------------------------------------------------
log_info "Post-deploy git status:"
git status
# Require no content changes to tracked files. Allow only the deploy-side
# requirements hash stamp (not part of the application UI tree).
TRACKED_DIRT="$(git status --porcelain --untracked-files=no | grep -vE '^\s*M\s+erp/\.requirements\.sha256$' | grep -vE '^ M erp/\.requirements\.sha256$' || true)"
if [[ -n "${TRACKED_DIRT}" ]]; then
  echo "${TRACKED_DIRT}"
  abort_deploy "git status not clean after deployment (tracked changes remain)"
fi
# Fail if unexpected untracked app files remain under erp/app (stale templates/static).
UNTRACKED_APP="$(git status --porcelain --untracked-files=normal -- "erp/app" | awk '/^\?\?/ {print $2}' || true)"
if [[ -n "${UNTRACKED_APP}" ]]; then
  echo "${UNTRACKED_APP}"
  abort_deploy "untracked files remain under erp/app after git clean — stale UI risk"
fi
# Re-verify critical UI files still match Git after restart side-effects.
if ! git diff --quiet HEAD -- \
  "erp/app/templates/dashboard/index.html" \
  "erp/app/templates/layouts/base.html" \
  "erp/app/static/js/dashboard.js"
then
  abort_deploy "critical UI files drifted from Git HEAD after restart"
fi
log_ok "git status clean (no tracked dirt; erp/app has no untracked leftovers)"
log_info "git rev-parse HEAD (final): $(git rev-parse HEAD)"
log_info "git rev-parse HEAD (before): ${PREV_COMMIT}"
log_info "git rev-parse HEAD (after) : $(git rev-parse HEAD)"

write_deploy_report "SUCCESS" "all checks passed"
STATUS="Success"
