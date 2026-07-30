#!/usr/bin/env bash
# =============================================================================
# JTCS ERP — setup_deployment.sh (Ubuntu VPS bootstrap)
# Installs packages, creates dirs, example systemd/nginx, venv, permissions.
# Run once as a sudo-capable deploy user.
# =============================================================================

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"
load_deploy_env

APP_DIR="${VPS_APP_DIR:-/var/www/jtcs-erp}"
ERP_DIR="${APP_DIR}/${VPS_ERP_DIR:-erp}"
VENV="${VPS_VENV_DIR:-${ERP_DIR}/.venv}"
SERVICE="${VPS_SYSTEMD_SERVICE:-jtcs-erp}"
BACKUP_ROOT="${VPS_BACKUP_ROOT:-/var/backups/jtcs-erp}"
LOG_DIR="${VPS_LOG_DIR:-/var/log/jtcs-erp}"

log_info "=== JTCS ERP VPS setup ==="
log_info "App dir: ${APP_DIR}"

if [[ "${EUID}" -ne 0 ]]; then
  log_warn "Not root — some steps may need sudo"
  SUDO="sudo"
else
  SUDO=""
fi

${SUDO} apt-get update
${SUDO} DEBIAN_FRONTEND=noninteractive apt-get install -y \
  git curl rsync python3 python3-venv python3-pip \
  nginx supervisor 2>/dev/null || true

# Prefer systemd unit for gunicorn (supervisor optional).
${SUDO} apt-get install -y gunicorn 2>/dev/null || true

ensure_dir "${APP_DIR}" "${BACKUP_ROOT}" "${LOG_DIR}"
${SUDO} chown -R "${SUDO_USER:-$USER}:${SUDO_USER:-$USER}" "${APP_DIR}" "${BACKUP_ROOT}" "${LOG_DIR}" 2>/dev/null || true

if [[ ! -d "${APP_DIR}/.git" ]]; then
  log_warn "${APP_DIR} is not a git clone yet."
  log_info "Clone with: git clone git@github.com:YOUR/JTCS-final.git ${APP_DIR}"
fi

if [[ -f "${SCRIPT_DIR}/config/deploy.env.example" && ! -f "${SCRIPT_DIR}/deploy.env" ]]; then
  cp "${SCRIPT_DIR}/config/deploy.env.example" "${SCRIPT_DIR}/deploy.env"
  chmod 600 "${SCRIPT_DIR}/deploy.env"
  log_info "Created ${SCRIPT_DIR}/deploy.env — edit secrets there"
fi

if [[ -d "${ERP_DIR}" && ! -x "${VENV}/bin/python" ]]; then
  python3 -m venv "${VENV}"
  # shellcheck disable=SC1091
  source "${VENV}/bin/activate"
  pip install --upgrade pip
  pip install -r "${ERP_DIR}/requirements.txt"
  pip install gunicorn
fi

# Install example systemd unit if missing
UNIT_SRC="${SCRIPT_DIR}/config/jtcs-erp.service.example"
UNIT_DST="/etc/systemd/system/${SERVICE}.service"
if [[ -f "${UNIT_SRC}" && ! -f "${UNIT_DST}" ]]; then
  log_info "Installing systemd unit ${UNIT_DST}"
  ${SUDO} cp "${UNIT_SRC}" "${UNIT_DST}"
  ${SUDO} sed -i "s|/var/www/jtcs-erp|${APP_DIR}|g" "${UNIT_DST}"
  ${SUDO} systemctl daemon-reload
  ${SUDO} systemctl enable "${SERVICE}" || true
fi

# Nginx site example
NGX_SRC="${SCRIPT_DIR}/config/nginx-jtcs-erp.conf.example"
NGX_DST="/etc/nginx/sites-available/jtcs-erp"
if [[ -f "${NGX_SRC}" && ! -f "${NGX_DST}" ]]; then
  log_info "Installing nginx site ${NGX_DST}"
  ${SUDO} cp "${NGX_SRC}" "${NGX_DST}"
  ${SUDO} ln -sfn "${NGX_DST}" /etc/nginx/sites-enabled/jtcs-erp
  ${SUDO} nginx -t && ${SUDO} systemctl reload nginx || true
fi

chmod +x "${SCRIPT_DIR}"/*.sh "${SCRIPT_DIR}/lib/"*.sh 2>/dev/null || true

log_ok "VPS setup complete"
log_info "1) Edit ${SCRIPT_DIR}/deploy.env and ${ERP_DIR}/.env"
log_info "2) systemctl start ${SERVICE}"
log_info "3) From Windows: double-click deployment\\deploy.bat"
