#!/usr/bin/env bash
# =============================================================================
# JTCS ERP — VPS status snapshot
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
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"
PUBLIC_HEALTH="${PUBLIC_HEALTH_URL:-https://app.jtcsxpert.com/health}"

cd "${APP_DIR}"

echo "========================================"
echo " JTCS ERP — VPS Status"
echo "========================================"
echo " App dir     : ${APP_DIR}"
echo " Branch      : $(git_branch_name)"
echo " Commit      : $(git_full_commit)"
echo " Short       : $(git_commit_id)"
echo " Service     : ${SERVICE}"
if systemctl is-active --quiet "${SERVICE}" 2>/dev/null; then
  echo " Service     : ACTIVE"
else
  echo " Service     : INACTIVE / MISSING"
fi
echo " Health local: ${HEALTH_URL}"
echo " Health public: ${PUBLIC_HEALTH}"
echo " Port 8000   :"
ss -ltnp 2>/dev/null | grep ':8000' || netstat -ltnp 2>/dev/null | grep ':8000' || echo "  (not listening)"
echo " Nginx       :"
if systemctl is-active --quiet nginx 2>/dev/null; then
  echo "  ACTIVE"
else
  echo "  inactive/missing"
fi
echo " Python/venv :"
if [[ -x "${VENV}/bin/python" ]]; then
  "${VENV}/bin/python" -V
  "${VENV}/bin/python" -c "import gunicorn; print('gunicorn', gunicorn.__version__)" 2>/dev/null || echo "  gunicorn MISSING"
else
  echo "  venv MISSING"
fi
echo " Process     :"
ps aux | grep -E '[g]unicorn|[w]sgi:app' | head -5 || echo "  (no gunicorn process)"
echo " Unit ExecStart:"
systemctl cat "${SERVICE}" 2>/dev/null | grep -E '^ExecStart=' || echo "  (unit missing)"
echo "========================================"
