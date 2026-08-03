#!/usr/bin/env bash
# =============================================================================
# JTCS ERP — healthcheck.sh
# Verifies systemd (Gunicorn/WSGI), HTTP /health (with wait), optional Nginx + DB.
# Exit 0 = healthy, non-zero = unhealthy.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"
load_deploy_env

SERVICE="${VPS_SYSTEMD_SERVICE:-jtcs-erp}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"
API_HEALTH_URL="${API_HEALTH_URL:-${HEALTH_URL}}"
HEALTH_WAIT_SECONDS="${HEALTH_WAIT_SECONDS:-180}"
FAILS=0

check() {
  local name="$1"
  shift
  if "$@"; then
    log_ok "${name}"
  else
    log_error "${name} FAILED"
    FAILS=$((FAILS + 1))
  fi
}

log_info "Running health checks…"

if command -v systemctl >/dev/null 2>&1; then
  check "systemd ${SERVICE} active" service_is_active "${SERVICE}"
  if systemctl cat "${SERVICE}" 2>/dev/null | grep -q 'run.py'; then
    log_error "systemd unit still references run.py"
    FAILS=$((FAILS + 1))
  else
    log_ok "systemd unit uses WSGI (no run.py)"
  fi
  if command -v nginx >/dev/null 2>&1 && systemctl is-enabled nginx >/dev/null 2>&1; then
    check "Nginx active" service_is_active nginx
  else
    log_info "Nginx not required / not enabled — skip"
  fi
else
  log_warn "systemctl not available — skipping service checks"
fi

# Wait for gunicorn workers (torch/OCR boot can exceed 60s)
if wait_for_http "${HEALTH_URL}" "${HEALTH_WAIT_SECONDS}" 3; then
  log_ok "Application URL (${HEALTH_URL})"
else
  log_error "Application URL (${HEALTH_URL}) FAILED"
  FAILS=$((FAILS + 1))
  log_info "Recent service logs:"
  journalctl -u "${SERVICE}" -n 40 --no-pager 2>/dev/null || true
fi

if [[ "${API_HEALTH_URL}" != "${HEALTH_URL}" ]]; then
  check "API health (${API_HEALTH_URL})" http_ok "${API_HEALTH_URL}"
fi

APP_DIR="${VPS_APP_DIR:-${REPO_ROOT}}"
ERP_DIR="${APP_DIR}/${VPS_ERP_DIR:-erp}"
VENV="${VPS_VENV_DIR:-${ERP_DIR}/.venv}"
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
print("db_ok")
PY
  ); then
    log_ok "Database connection"
  else
    log_error "Database connection FAILED"
    FAILS=$((FAILS + 1))
  fi
else
  log_warn "Skipping DB Python check (venv/wsgi not found)"
fi

if [[ ${FAILS} -gt 0 ]]; then
  log_error "Health check failed (${FAILS} issue(s))"
  exit 1
fi

log_ok "All health checks passed"
exit 0
