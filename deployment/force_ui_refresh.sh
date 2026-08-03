#!/usr/bin/env bash
# =============================================================================
# JTCS ERP — Force live UI refresh on VPS
# Pull current branch, migrate, ensure menus, HARD restart gunicorn.
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
REMOTE="${GIT_REMOTE:-origin}"
BRANCH="${BRANCH:-${GIT_BRANCH:-}}"

cd "${APP_DIR}"

if [[ -z "${BRANCH}" || "${BRANCH}" == "HEAD" ]]; then
  BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
fi
if [[ -z "${BRANCH}" || "${BRANCH}" == "HEAD" ]]; then
  log_error "BRANCH required"
  exit 1
fi

log_info "=== FORCE UI REFRESH ==="
log_info "Branch: ${BRANCH}"
log_info "App   : ${APP_DIR}"

ENV_BAK="/tmp/jtcs.env.bak.$$"
if [[ -f "${ERP_DIR}/.env" ]]; then
  cp "${ERP_DIR}/.env" "${ENV_BAK}"
fi

git fetch "${REMOTE}" "${BRANCH}"
git checkout -B "${BRANCH}" "${REMOTE}/${BRANCH}"
git reset --hard "${REMOTE}/${BRANCH}"

if [[ -f "${ENV_BAK}" ]]; then
  cp "${ENV_BAK}" "${ERP_DIR}/.env"
  rm -f "${ENV_BAK}"
fi

log_ok "Code: $(git rev-parse --short HEAD) on $(git branch --show-current)"

# Prove new menu code is on disk
if ! grep -q "CORE_TOP_LEVEL_MENUS" "${ERP_DIR}/app/services/menu_service.py"; then
  log_error "menu_service.py missing CORE_TOP_LEVEL_MENUS — wrong code on disk"
  exit 1
fi
log_ok "menu_service.py has CORE_TOP_LEVEL_MENUS filter"

# Migrations
if [[ -f "${SCRIPT_DIR}/apply_migrations.sh" ]]; then
  bash "${SCRIPT_DIR}/apply_migrations.sh" || log_warn "migrations returned non-zero"
fi

# Menu ensure (fast, no torch)
PY="${VENV}/bin/python"
if [[ ! -x "${PY}" ]]; then
  PY="python3"
fi
log_info "Ensuring live nav menus in SQL…"
(cd "${ERP_DIR}" && "${PY}" scripts/ensure_live_nav.py)

# Hard stop old workers (stale code)
log_info "Hard restart ${SERVICE}…"
systemctl stop "${SERVICE}" || true
pkill -9 -f 'gunicorn.*wsgi:app' 2>/dev/null || true
if command -v fuser >/dev/null 2>&1; then
  fuser -k 8000/tcp 2>/dev/null || true
fi
sleep 1
# Clear bytecode caches so old .pyc cannot stick
find "${ERP_DIR}" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "${ERP_DIR}" -type f -name '*.pyc' -delete 2>/dev/null || true

bash "${SCRIPT_DIR}/install_service.sh"

# Verify unit uses wsgi
if systemctl cat "${SERVICE}" 2>/dev/null | grep -q 'run.py'; then
  log_error "Unit still references run.py"
  exit 1
fi

export HEALTH_WAIT_SECONDS="${HEALTH_WAIT_SECONDS:-180}"
bash "${SCRIPT_DIR}/healthcheck.sh"

log_ok "FORCE UI REFRESH COMPLETE"
echo "===UI_REFRESH:SUCCESS==="
echo "===DEPLOY_COMMIT:$(git rev-parse HEAD)==="
echo "===DEPLOY_BRANCH:$(git branch --show-current)==="
exit 0
