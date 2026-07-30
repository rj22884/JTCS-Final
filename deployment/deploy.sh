#!/usr/bin/env bash
# =============================================================================
# JTCS ERP — deploy.sh (Ubuntu VPS)
# Pulls latest code, migrates, restarts services, records version, health-checks.
# On critical failure: automatic rollback to previous backup.
#
# Usage:
#   ./deploy.sh
#   ./deploy.sh --version 1.0.1 --notes "Fix SMTP" --developer "Ravi" \
#               --whats-new "..." --bug-fixes "..." --features "..." \
#               --db-changes "..." --security "..." --performance "..."
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
    *) log_error "Unknown arg: $1"; exit 2 ;;
  esac
done

APP_DIR="${VPS_APP_DIR:-${REPO_ROOT}}"
ERP_DIR="${APP_DIR}/${VPS_ERP_DIR:-erp}"
VENV="${VPS_VENV_DIR:-${ERP_DIR}/.venv}"
SERVICE="${VPS_SYSTEMD_SERVICE:-jtcs-erp}"
BRANCH="${GIT_BRANCH:-main}"
REMOTE="${GIT_REMOTE:-origin}"
LOG_DIR="${VPS_LOG_DIR:-/var/log/jtcs-erp}"
ensure_dir "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/deploy_$(timestamp_now).log"
STATUS="Failed"
BACKUP_PATH=""
PREV_COMMIT=""
START_EPOCH="$(date +%s)"

exec > >(tee -a "${LOG_FILE}") 2>&1

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
  fi
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
"
  if [[ "${STATUS}" == "Success" ]]; then
    log_ok "DEPLOYMENT SUCCESS (${duration}s) — version ${VERSION:-unknown}"
    exit 0
  fi
  log_error "DEPLOYMENT ${STATUS} (${duration}s) — see ${LOG_FILE}"
  exit 1
}

trap finish EXIT

log_info "=== JTCS ERP deploy start ==="
log_info "App dir: ${APP_DIR}"
log_info "Log: ${LOG_FILE}"

require_cmd git rsync curl

cd "${APP_DIR}"
PREV_COMMIT="$(git_full_commit)"

# ---------------------------------------------------------------------------
# 1) Backup before changing anything
# ---------------------------------------------------------------------------
if [[ ${SKIP_BACKUP} -eq 0 ]]; then
  BACKUP_PATH="$(bash "${SCRIPT_DIR}/backup.sh" ${VERSION:+--version "${VERSION}"})"
  BACKUP_PATH="$(echo "${BACKUP_PATH}" | tail -n 1)"
  log_info "Backup path: ${BACKUP_PATH}"
else
  log_warn "Skipping backup (--skip-backup)"
fi

# ---------------------------------------------------------------------------
# 2) Pull latest code
# ---------------------------------------------------------------------------
log_info "Fetching ${REMOTE}/${BRANCH}…"
if ! git fetch "${REMOTE}" "${BRANCH}"; then
  rollback_on_fail "git fetch failed"
  exit 1
fi
if ! git checkout "${BRANCH}"; then
  rollback_on_fail "git checkout ${BRANCH} failed"
  exit 1
fi
if ! git pull --ff-only "${REMOTE}" "${BRANCH}"; then
  rollback_on_fail "git pull failed"
  exit 1
fi
log_ok "Code updated to $(git_commit_id) on $(git_branch_name)"

# ---------------------------------------------------------------------------
# 3) Python dependencies
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
  log_info "Installing Python packages (requirements changed)…"
  pip install --upgrade pip
  pip install -r "${REQ_FILE}"
  echo "${NEW_HASH}" > "${REQ_HASH_FILE}"
else
  log_info "requirements.txt unchanged — skipping pip install"
fi

# ---------------------------------------------------------------------------
# 4) Database migrations (numbered SQL under erp/database)
# ---------------------------------------------------------------------------
if [[ -x "${SCRIPT_DIR}/apply_migrations.sh" ]]; then
  log_info "Applying database migrations…"
  if ! bash "${SCRIPT_DIR}/apply_migrations.sh"; then
    rollback_on_fail "database migration failed"
    exit 1
  fi
else
  log_warn "apply_migrations.sh missing — skip SQL migrations"
fi

# ---------------------------------------------------------------------------
# 5) Sync APP_VERSION in .env + record version row
# ---------------------------------------------------------------------------
if [[ -n "${VERSION}" ]]; then
  sync_app_version_env "${VPS_FLASK_ENV_FILE:-${ERP_DIR}/.env}" "${VERSION}"
fi

if [[ -f "${SCRIPT_DIR}/record_version.py" ]]; then
  log_info "Recording version history…"
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
    || log_warn "Version recording failed (non-fatal until health)"
fi

# ---------------------------------------------------------------------------
# 6) Restart Gunicorn + reload Nginx
# ---------------------------------------------------------------------------
log_info "Restarting ${SERVICE}…"
if ! systemctl restart "${SERVICE}"; then
  rollback_on_fail "gunicorn/systemd restart failed"
  exit 1
fi

if [[ "${VPS_NGINX_RELOAD:-1}" == "1" ]]; then
  if nginx -t; then
    systemctl reload nginx || {
      rollback_on_fail "nginx reload failed"
      exit 1
    }
  else
    rollback_on_fail "nginx -t failed"
    exit 1
  fi
fi

# Clear Python caches under erp (safe)
find "${ERP_DIR}" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true

# ---------------------------------------------------------------------------
# 7) Health check
# ---------------------------------------------------------------------------
sleep 2
if ! bash "${SCRIPT_DIR}/healthcheck.sh"; then
  rollback_on_fail "health check failed"
  exit 1
fi

STATUS="Success"
