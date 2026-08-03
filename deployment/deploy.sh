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
ERP_DIR="${APP_DIR}/${VPS_ERP_DIR:-erp}"
VENV="${VPS_VENV_DIR:-${ERP_DIR}/.venv}"
SERVICE="${VPS_SYSTEMD_SERVICE:-jtcs-erp}"
REMOTE="${GIT_REMOTE:-origin}"
LOG_DIR="${VPS_LOG_DIR:-/var/log/jtcs-erp}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"
PUBLIC_HEALTH="${PUBLIC_HEALTH_URL:-https://app.jtcsxpert.com/health}"
ensure_dir "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/deploy_$(timestamp_now).log"
STATUS="Failed"
BACKUP_PATH=""
PREV_COMMIT=""
START_EPOCH="$(date +%s)"
ROLLED=0

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
  echo "===DEPLOY_HEALTH:${HEALTH_URL}==="
  echo "===DEPLOY_PUBLIC_HEALTH:${PUBLIC_HEALTH}==="
}

rollback_on_fail() {
  local reason="$1"
  log_error "Deployment failed: ${reason}"
  STATUS="Failed"
  if [[ ${SKIP_ROLLBACK} -eq 1 ]]; then
    log_warn "Auto-rollback disabled (--skip-rollback)"
    return 0
  fi
  if [[ -x "${SCRIPT_DIR}/rollback.sh" ]]; then
    log_warn "Invoking automatic rollback…"
    if [[ -n "${BACKUP_PATH}" ]]; then
      bash "${SCRIPT_DIR}/rollback.sh" --backup "${BACKUP_PATH}" --reason "${reason}" || true
    else
      bash "${SCRIPT_DIR}/rollback.sh" --latest --reason "${reason}" || true
    fi
    STATUS="RolledBack"
    ROLLED=1
  fi
}

finish() {
  local end duration ec
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
log_info "App dir : ${APP_DIR}"
log_info "Branch  : ${BRANCH} (auto / exported — not hardcoded)"
log_info "Service : ${SERVICE}"
log_info "Log     : ${LOG_FILE}"

require_cmd git curl
command -v rsync >/dev/null 2>&1 || log_warn "rsync missing — backup may be limited"

cd "${APP_DIR}"
PREV_COMMIT="$(git_full_commit)"
log_info "Previous commit: ${PREV_COMMIT}"

# ---------------------------------------------------------------------------
# 1) Backup
# ---------------------------------------------------------------------------
if [[ ${SKIP_BACKUP} -eq 0 && -x "${SCRIPT_DIR}/backup.sh" ]] && command -v rsync >/dev/null 2>&1; then
  if BACKUP_PATH="$(bash "${SCRIPT_DIR}/backup.sh" ${VERSION:+--version "${VERSION}"} | tail -n 1)"; then
    log_info "Backup path: ${BACKUP_PATH}"
  else
    log_warn "Backup failed — continuing with --no hard stop (set SKIP to force). Using skip."
    BACKUP_PATH=""
  fi
else
  log_warn "Skipping full backup (rsync/backup.sh unavailable or --skip-backup)"
fi

# ---------------------------------------------------------------------------
# 2) Preserve .env + pull CURRENT branch
# ---------------------------------------------------------------------------
ENV_BAK="/tmp/jtcs.env.bak.$$"
if [[ -f "${ERP_DIR}/.env" ]]; then
  cp "${ERP_DIR}/.env" "${ENV_BAK}"
  log_info "Backed up erp/.env"
fi

log_info "Fetching ${REMOTE}/${BRANCH}…"
if ! git fetch "${REMOTE}" "${BRANCH}"; then
  rollback_on_fail "git fetch failed for ${BRANCH}"
  exit 1
fi

if ! git show-ref --verify --quiet "refs/remotes/${REMOTE}/${BRANCH}"; then
  rollback_on_fail "remote branch ${REMOTE}/${BRANCH} not found"
  exit 1
fi

log_info "Hard reset to ${REMOTE}/${BRANCH} (deploy clean)…"
if ! git checkout -B "${BRANCH}" "${REMOTE}/${BRANCH}"; then
  rollback_on_fail "git checkout ${BRANCH} failed"
  exit 1
fi
if ! git reset --hard "${REMOTE}/${BRANCH}"; then
  rollback_on_fail "git reset --hard failed"
  exit 1
fi

if [[ -f "${ENV_BAK}" ]]; then
  mkdir -p "${ERP_DIR}"
  cp "${ENV_BAK}" "${ERP_DIR}/.env"
  rm -f "${ENV_BAK}"
  log_ok "Restored erp/.env"
fi

if [[ ! -f "${ERP_DIR}/.env" ]]; then
  rollback_on_fail "erp/.env missing after deploy"
  exit 1
fi

log_ok "Code updated: branch=$(git_branch_name) commit=$(git_full_commit)"

if [[ ! -f "${ERP_DIR}/wsgi.py" ]]; then
  rollback_on_fail "wsgi.py missing — refusing run.py fallback"
  exit 1
fi

# ---------------------------------------------------------------------------
# 3) Python deps + gunicorn
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
  python3 -m venv "${VENV}"
fi
# shellcheck disable=SC1091
source "${VENV}/bin/activate"

if [[ "${NEW_HASH}" != "${OLD_HASH}" ]]; then
  log_info "Installing Python packages…"
  pip install --upgrade pip
  pip install -r "${REQ_FILE}"
  echo "${NEW_HASH}" > "${REQ_HASH_FILE}"
else
  log_info "requirements.txt unchanged — ensuring gunicorn"
fi
pip install -q "gunicorn>=22.0.0"

# ---------------------------------------------------------------------------
# 4) Schema-only migrations
# ---------------------------------------------------------------------------
# Use -f (not -x): git on Windows often drops the executable bit.
if [[ -f "${SCRIPT_DIR}/apply_migrations.sh" ]]; then
  chmod +x "${SCRIPT_DIR}/apply_migrations.sh" 2>/dev/null || true
  log_info "Applying SCHEMA-ONLY migrations…"
  if ! bash "${SCRIPT_DIR}/apply_migrations.sh"; then
    rollback_on_fail "database migration failed"
    exit 1
  fi
else
  log_warn "apply_migrations.sh missing — skip SQL migrations"
fi

# ---------------------------------------------------------------------------
# 5) Version record (best-effort)
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
# 6) Ensure systemd uses gunicorn/wsgi + restart (HARD FAIL if restart fails)
# ---------------------------------------------------------------------------
find "${ERP_DIR}" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
if command -v fuser >/dev/null 2>&1; then
  fuser -k 8000/tcp 2>/dev/null || true
fi
pkill -f 'python.*run.py' 2>/dev/null || true

log_info "Installing/repairing systemd unit (gunicorn wsgi:app)…"
if ! bash "${SCRIPT_DIR}/install_service.sh"; then
  rollback_on_fail "systemd install/restart failed"
  exit 1
fi

if ! systemctl is-active --quiet "${SERVICE}"; then
  rollback_on_fail "service ${SERVICE} not active after restart"
  exit 1
fi
log_ok "Service ${SERVICE} active"

if [[ "${VPS_NGINX_RELOAD:-1}" == "1" ]] && command -v nginx >/dev/null 2>&1; then
  if systemctl is-active --quiet nginx; then
    if nginx -t; then
      systemctl reload nginx || log_warn "nginx reload failed (non-fatal if direct :8000 works)"
    else
      log_warn "nginx -t failed — skipped reload"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# 7) Health checks (local required; public best-effort then required from bat)
# ---------------------------------------------------------------------------
# Do NOT use a short sleep — gunicorn + torch/OCR needs a long warm-up.
log_info "Health check: ${HEALTH_URL} (waiting for workers to accept connections)"
export HEALTH_WAIT_SECONDS="${HEALTH_WAIT_SECONDS:-180}"
if ! bash "${SCRIPT_DIR}/healthcheck.sh"; then
  rollback_on_fail "health check failed after restart"
  exit 1
fi

# Public URL from VPS (may fail if DNS/outbound blocked — Windows bat also checks)
if http_ok "${PUBLIC_HEALTH}"; then
  log_ok "Public health OK: ${PUBLIC_HEALTH}"
else
  log_warn "Public health not reachable from VPS: ${PUBLIC_HEALTH} (Windows will re-check)"
fi

STATUS="Success"
