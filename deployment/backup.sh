#!/usr/bin/env bash
# =============================================================================
# JTCS ERP — backup.sh
# Creates a timestamped / versioned backup of app, config, uploads, and DB.
# Usage:
#   ./backup.sh
#   ./backup.sh --version 1.0.1
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"
load_deploy_env

VERSION_LABEL=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) VERSION_LABEL="$2"; shift 2 ;;
    *) log_error "Unknown arg: $1"; exit 2 ;;
  esac
done

APP_DIR="${VPS_APP_DIR:-${REPO_ROOT}}"
BACKUP_ROOT="${VPS_BACKUP_ROOT:-/var/backups/jtcs-erp}"
TS="$(timestamp_now)"
if [[ -n "${VERSION_LABEL}" ]]; then
  BACKUP_NAME="Version_${VERSION_LABEL}_${TS}"
else
  BACKUP_NAME="${TS}"
fi
BACKUP_DIR="${BACKUP_ROOT}/${BACKUP_NAME}"
LOG_DIR="${VPS_LOG_DIR:-/var/log/jtcs-erp}"
LOG_FILE="${LOG_DIR}/backup.log"

ensure_dir "${BACKUP_DIR}/app" "${BACKUP_DIR}/config" "${BACKUP_DIR}/uploads" "${BACKUP_DIR}/sql" "${LOG_DIR}"

START_EPOCH="$(date +%s)"
log_info "Starting backup → ${BACKUP_DIR}"
append_deploy_log "${LOG_FILE}" "BACKUP START ${BACKUP_NAME} at $(iso_now)"

set +e
# Application tree (exclude venv, caches, huge logs).
rsync -a \
  --exclude '.git' \
  --exclude '**/__pycache__' \
  --exclude '**/.venv' \
  --exclude '**/venv' \
  --exclude '**/*.pyc' \
  --exclude 'deployment/backups' \
  --exclude 'deployment/logs' \
  "${APP_DIR}/" "${BACKUP_DIR}/app/"
RSYNC_APP=$?

# Flask / deploy configuration (no secrets in git; still backup live config).
if [[ -f "${VPS_FLASK_ENV_FILE:-${APP_DIR}/erp/.env}" ]]; then
  cp -a "${VPS_FLASK_ENV_FILE:-${APP_DIR}/erp/.env}" "${BACKUP_DIR}/config/erp.env"
fi
if [[ -f "${DEPLOYMENT_DIR}/deploy.env" ]]; then
  cp -a "${DEPLOYMENT_DIR}/deploy.env" "${BACKUP_DIR}/config/deploy.env"
fi
if [[ -d /etc/nginx/sites-available ]]; then
  cp -a /etc/nginx/sites-available/jtcs* "${BACKUP_DIR}/config/" 2>/dev/null || true
fi
if [[ -f /etc/systemd/system/${VPS_SYSTEMD_SERVICE:-jtcs-erp}.service ]]; then
  cp -a "/etc/systemd/system/${VPS_SYSTEMD_SERVICE:-jtcs-erp}.service" "${BACKUP_DIR}/config/"
fi

# Uploads
UPLOADS_SRC="${APP_DIR}/erp/app/static/uploads"
if [[ -d "${UPLOADS_SRC}" ]]; then
  rsync -a "${UPLOADS_SRC}/" "${BACKUP_DIR}/uploads/"
fi

# SQL Server database backup via sqlcmd (optional).
DB_OK=0
if [[ -n "${MSSQL_SERVER:-}" && -n "${MSSQL_DATABASE:-}" ]] && command -v sqlcmd >/dev/null 2>&1; then
  BAK_FILE="${BACKUP_DIR}/sql/${MSSQL_DATABASE}_${TS}.bak"
  SQL_AUTH=()
  if [[ -n "${MSSQL_USER:-}" ]]; then
    SQL_AUTH=(-U "${MSSQL_USER}" -P "${MSSQL_PASSWORD:-}")
  else
    SQL_AUTH=(-E)
  fi
  sqlcmd -S "${MSSQL_SERVER}" "${SQL_AUTH[@]}" -Q \
    "BACKUP DATABASE [${MSSQL_DATABASE}] TO DISK = N'${BAK_FILE}' WITH INIT, COMPRESSION, STATS = 10"
  DB_OK=$?
else
  log_warn "Skipping SQL backup (MSSQL_SERVER/sqlcmd not configured)."
  echo "SQL backup skipped" > "${BACKUP_DIR}/sql/SKIPPED.txt"
  DB_OK=0
fi

# Metadata
{
  echo "backup_name=${BACKUP_NAME}"
  echo "created_at=$(iso_now)"
  echo "git_commit=$(git_full_commit)"
  echo "git_branch=$(git_branch_name)"
  echo "app_dir=${APP_DIR}"
  echo "version_label=${VERSION_LABEL}"
} > "${BACKUP_DIR}/MANIFEST.txt"

# Pointer to latest backup for quick rollback.
ln -sfn "${BACKUP_DIR}" "${BACKUP_ROOT}/latest"

END_EPOCH="$(date +%s)"
DURATION=$((END_EPOCH - START_EPOCH))
set -e

if [[ ${RSYNC_APP} -ne 0 ]]; then
  log_error "Application rsync failed (exit ${RSYNC_APP})"
  append_deploy_log "${LOG_FILE}" "BACKUP FAILED app_rsync=${RSYNC_APP}"
  exit 1
fi
if [[ ${DB_OK} -ne 0 ]]; then
  log_error "Database backup failed (exit ${DB_OK})"
  append_deploy_log "${LOG_FILE}" "BACKUP FAILED db=${DB_OK}"
  exit 1
fi

log_ok "Backup complete: ${BACKUP_DIR} (${DURATION}s)"
append_deploy_log "${LOG_FILE}" "BACKUP OK ${BACKUP_DIR} duration=${DURATION}s"
echo "${BACKUP_DIR}"
