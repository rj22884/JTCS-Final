#!/usr/bin/env bash
# =============================================================================
# JTCS ERP — full diagnostics (PASS/FAIL per check)
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
FAILS=0

pass() { echo "[PASS] $*"; }
fail() { echo "[FAIL] $*"; FAILS=$((FAILS + 1)); }

cd "${APP_DIR}"

echo "========================================"
echo " JTCS ERP — Full Diagnostics"
echo "========================================"

command -v git >/dev/null && pass "Git installed" || fail "Git missing"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 && pass "Git repo: ${APP_DIR}" || fail "Not a git repo"

BR="$(git_branch_name)"
CM="$(git_full_commit)"
[[ -n "${BR}" && "${BR}" != "unknown" ]] && pass "Branch: ${BR}" || fail "Branch unknown"
[[ -n "${CM}" && "${CM}" != "unknown" ]] && pass "Commit: ${CM}" || fail "Commit unknown"

[[ -f "${ERP_DIR}/.env" ]] && pass "erp/.env present" || fail "erp/.env missing"
[[ -f "${ERP_DIR}/wsgi.py" ]] && pass "wsgi.py present" || fail "wsgi.py missing"
[[ -x "${VENV}/bin/python" ]] && pass "venv python" || fail "venv python missing"
if [[ -x "${VENV}/bin/gunicorn" ]]; then
  pass "gunicorn binary"
else
  fail "gunicorn binary missing"
fi

if systemctl is-active --quiet "${SERVICE}" 2>/dev/null; then
  pass "systemd ${SERVICE} active"
else
  fail "systemd ${SERVICE} not active"
fi

if systemctl cat "${SERVICE}" 2>/dev/null | grep -q 'wsgi:app'; then
  pass "unit uses wsgi:app"
else
  fail "unit does not use wsgi:app (stale run.py unit?)"
fi

if systemctl cat "${SERVICE}" 2>/dev/null | grep -q 'run.py'; then
  fail "unit still references run.py"
else
  pass "unit has no run.py reference"
fi

ss -ltn 2>/dev/null | grep -q ':8000' && pass "Port 8000 listening" || fail "Port 8000 not listening"

if command -v nginx >/dev/null 2>&1; then
  systemctl is-active --quiet nginx && pass "Nginx active" || fail "Nginx inactive"
  nginx -t >/dev/null 2>&1 && pass "Nginx config" || fail "Nginx config invalid"
else
  echo "[SKIP] Nginx not installed"
fi

if http_ok "${HEALTH_URL}"; then
  pass "Local health ${HEALTH_URL}"
else
  fail "Local health ${HEALTH_URL}"
fi

if http_ok "${PUBLIC_HEALTH}"; then
  pass "Public health ${PUBLIC_HEALTH}"
else
  fail "Public health ${PUBLIC_HEALTH}"
fi

if [[ -x "${VENV}/bin/python" && -f "${ERP_DIR}/wsgi.py" ]]; then
  if (
    cd "${ERP_DIR}"
    # shellcheck disable=SC1091
    source "${VENV}/bin/activate"
    python - <<'PY'
from wsgi import app
with app.app_context():
    from app.extensions import db
    db.session.execute(db.text("SELECT 1"))
print("ok")
PY
  ); then
    pass "Database connectivity"
  else
    fail "Database connectivity"
  fi
else
  fail "Cannot test database (venv/wsgi)"
fi

echo "========================================"
if [[ ${FAILS} -gt 0 ]]; then
  echo "RESULT: FAIL (${FAILS} issue(s))"
  exit 1
fi
echo "RESULT: PASS"
exit 0
