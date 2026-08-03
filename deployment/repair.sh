#!/usr/bin/env bash
# =============================================================================
# JTCS ERP — repair common VPS deployment issues
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"
load_deploy_env

APP_DIR="${VPS_APP_DIR:-${REPO_ROOT}}"
ERP_DIR="${APP_DIR}/${VPS_ERP_DIR:-erp}"
VENV="${VPS_VENV_DIR:-${ERP_DIR}/.venv}"
SERVICE="${VPS_SYSTEMD_SERVICE:-jtcs-erp}"
BRANCH="${BRANCH:-${GIT_BRANCH:-}}"

cd "${APP_DIR}"

log_info "=== REPAIR start ==="

# .env
if [[ ! -f "${ERP_DIR}/.env" ]]; then
  if [[ -f "${ERP_DIR}/.env.example" ]]; then
    cp "${ERP_DIR}/.env.example" "${ERP_DIR}/.env"
    log_warn "Created erp/.env from .env.example — edit secrets on VPS"
  else
    log_error "Missing erp/.env and no .env.example"
    exit 1
  fi
else
  log_ok "erp/.env present"
fi

# Branch sync (current requested branch only)
if [[ -z "${BRANCH}" || "${BRANCH}" == "HEAD" ]]; then
  BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
fi
if [[ -n "${BRANCH}" && "${BRANCH}" != "HEAD" ]]; then
  log_info "Aligning to origin/${BRANCH}"
  git fetch origin "${BRANCH}"
  git checkout -B "${BRANCH}" "origin/${BRANCH}" 2>/dev/null || git checkout "${BRANCH}"
  git reset --hard "origin/${BRANCH}"
  log_ok "Branch $(git_branch_name) @ $(git_commit_id)"
fi

# Permissions
chmod +x "${SCRIPT_DIR}"/*.sh 2>/dev/null || true
chmod 600 "${ERP_DIR}/.env" 2>/dev/null || true

# Kill stale run.py / old listeners
if command -v fuser >/dev/null 2>&1; then
  fuser -k 8000/tcp 2>/dev/null || true
fi
pkill -f 'python.*run.py' 2>/dev/null || true

# Service + gunicorn
bash "${SCRIPT_DIR}/install_service.sh"

# Nginx soft repair
if command -v nginx >/dev/null 2>&1; then
  if nginx -t 2>/dev/null; then
    systemctl reload nginx 2>/dev/null || systemctl restart nginx 2>/dev/null || true
    log_ok "Nginx reloaded"
  else
    log_warn "nginx -t failed — left unchanged"
  fi
fi

sleep 2
if bash "${SCRIPT_DIR}/healthcheck.sh"; then
  log_ok "REPAIR SUCCESS"
  exit 0
fi
log_error "REPAIR finished but health check failed"
exit 1
