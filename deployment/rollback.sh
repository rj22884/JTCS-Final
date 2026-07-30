#!/usr/bin/env bash
# =============================================================================
# JTCS ERP — rollback.sh
# Restore a previous backup (by path, latest, or Version_X.Y.Z).
#
# Usage:
#   ./rollback.sh --latest
#   ./rollback.sh --backup /var/backups/jtcs-erp/Version_1.0.0_2026-07-29_103000
#   ./rollback.sh --version 1.0.0
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"
load_deploy_env

BACKUP_PATH=""
VERSION=""
USE_LATEST=0
REASON="manual rollback"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup) BACKUP_PATH="$2"; shift 2 ;;
    --version) VERSION="$2"; shift 2 ;;
    --latest) USE_LATEST=1; shift ;;
    --reason) REASON="$2"; shift 2 ;;
    *) log_error "Unknown arg: $1"; exit 2 ;;
  esac
done

APP_DIR="${VPS_APP_DIR:-${REPO_ROOT}}"
BACKUP_ROOT="${VPS_BACKUP_ROOT:-/var/backups/jtcs-erp}"
SERVICE="${VPS_SYSTEMD_SERVICE:-jtcs-erp}"
LOG_DIR="${VPS_LOG_DIR:-/var/log/jtcs-erp}"
ensure_dir "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/rollback_$(timestamp_now).log"

exec > >(tee -a "${LOG_FILE}") 2>&1

if [[ ${USE_LATEST} -eq 1 ]]; then
  BACKUP_PATH="$(readlink -f "${BACKUP_ROOT}/latest" 2>/dev/null || true)"
fi

if [[ -z "${BACKUP_PATH}" && -n "${VERSION}" ]]; then
  # Prefer newest matching Version_X.Y.Z_* folder
  BACKUP_PATH="$(ls -1dt "${BACKUP_ROOT}/Version_${VERSION}_"* 2>/dev/null | head -n 1 || true)"
fi

if [[ -z "${BACKUP_PATH}" || ! -d "${BACKUP_PATH}" ]]; then
  log_error "Backup not found. Pass --backup, --latest, or --version"
  exit 1
fi

log_info "=== ROLLBACK start ==="
log_info "Reason: ${REASON}"
log_info "Restoring from: ${BACKUP_PATH}"

# Safety snapshot of current state before overwrite
SAFETY="$(bash "${SCRIPT_DIR}/backup.sh" --version "pre-rollback")"
SAFETY="$(echo "${SAFETY}" | tail -n 1)"
log_info "Safety backup: ${SAFETY}"

if [[ -d "${BACKUP_PATH}/app" ]]; then
  log_info "Restoring application files…"
  rsync -a --delete \
    --exclude '.git' \
    --exclude '**/__pycache__' \
    --exclude '**/.venv' \
    --exclude '**/venv' \
    "${BACKUP_PATH}/app/" "${APP_DIR}/"
fi

if [[ -f "${BACKUP_PATH}/config/erp.env" ]]; then
  DEST_ENV="${VPS_FLASK_ENV_FILE:-${APP_DIR}/erp/.env}"
  cp -a "${BACKUP_PATH}/config/erp.env" "${DEST_ENV}"
  chmod 600 "${DEST_ENV}" || true
fi

if [[ -d "${BACKUP_PATH}/uploads" ]]; then
  DEST_UP="${APP_DIR}/erp/app/static/uploads"
  ensure_dir "${DEST_UP}"
  rsync -a "${BACKUP_PATH}/uploads/" "${DEST_UP}/"
fi

# Restore SQL .bak if present and sqlcmd available
BAK="$(ls -1 "${BACKUP_PATH}/sql/"*.bak 2>/dev/null | head -n 1 || true)"
if [[ -n "${BAK}" && -n "${MSSQL_SERVER:-}" && -n "${MSSQL_DATABASE:-}" ]] && command -v sqlcmd >/dev/null 2>&1; then
  log_info "Restoring database from ${BAK}…"
  SQL_AUTH=()
  if [[ -n "${MSSQL_USER:-}" ]]; then
    SQL_AUTH=(-U "${MSSQL_USER}" -P "${MSSQL_PASSWORD:-}")
  else
    SQL_AUTH=(-E)
  fi
  sqlcmd -S "${MSSQL_SERVER}" "${SQL_AUTH[@]}" -Q \
    "ALTER DATABASE [${MSSQL_DATABASE}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
     RESTORE DATABASE [${MSSQL_DATABASE}] FROM DISK = N'${BAK}' WITH REPLACE;
     ALTER DATABASE [${MSSQL_DATABASE}] SET MULTI_USER;"
else
  log_warn "Skipping DB restore (no .bak or sqlcmd/MSSQL not configured)"
fi

log_info "Restarting services…"
systemctl restart "${SERVICE}"
if [[ "${VPS_NGINX_RELOAD:-1}" == "1" ]]; then
  nginx -t && systemctl reload nginx || true
fi

sleep 2
if bash "${SCRIPT_DIR}/healthcheck.sh"; then
  log_ok "ROLLBACK SUCCESS from ${BACKUP_PATH}"
  if [[ -f "${SCRIPT_DIR}/record_version.py" ]]; then
    # Mark rollback in version history (best-effort)
    ERP_DIR="${APP_DIR}/${VPS_ERP_DIR:-erp}"
    VENV="${VPS_VENV_DIR:-${ERP_DIR}/.venv}"
    if [[ -x "${VENV}/bin/python" ]]; then
      # shellcheck disable=SC1091
      source "${VENV}/bin/activate"
      python "${SCRIPT_DIR}/record_version.py" \
        --status "RolledBack" \
        --notes "Rollback: ${REASON}" \
        --backup "${BACKUP_PATH}" \
        --commit "$(git_full_commit)" \
        --branch "$(git_branch_name)" || true
    fi
  fi
  exit 0
fi

log_error "ROLLBACK completed but health check failed — inspect ${LOG_FILE}"
exit 1
