#!/usr/bin/env bash
# =============================================================================
# JTCS ERP — install / repair systemd unit (Gunicorn + wsgi:app)
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
UNIT_DST="/etc/systemd/system/${SERVICE}.service"
GUNI_CFG="${APP_DIR}/deployment/config/gunicorn.conf.py"

log_info "Installing/repairing systemd unit: ${SERVICE}"
log_info "App dir: ${APP_DIR}"

if [[ ! -d "${ERP_DIR}" ]]; then
  log_error "ERP dir missing: ${ERP_DIR}"
  exit 1
fi

if [[ ! -x "${VENV}/bin/python" ]]; then
  log_info "Creating venv…"
  python3 -m venv "${VENV}"
fi
# shellcheck disable=SC1091
source "${VENV}/bin/activate"
# Only ensure gunicorn here — full requirements install belongs to deploy.sh
if [[ ! -x "${VENV}/bin/gunicorn" ]]; then
  log_info "Installing gunicorn…"
  pip install -q "gunicorn>=22.0.0"
else
  log_info "gunicorn already present"
fi

if [[ ! -f "${ERP_DIR}/wsgi.py" ]]; then
  log_error "wsgi.py missing in ${ERP_DIR} — cannot install WSGI service"
  exit 1
fi

if [[ ! -f "${GUNI_CFG}" ]]; then
  log_warn "gunicorn.conf.py missing — writing default"
  mkdir -p "$(dirname "${GUNI_CFG}")"
  cat > "${GUNI_CFG}" <<'PY'
bind = "0.0.0.0:8000"
workers = 2
threads = 2
worker_class = "gthread"
timeout = 120
accesslog = "-"
errorlog = "-"
preload_app = True
PY
fi

cat > "/tmp/${SERVICE}.service" <<EOF
[Unit]
Description=JTCS ERP (Gunicorn / Flask WSGI)
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=${ERP_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=GUNICORN_BIND=0.0.0.0:8000
EnvironmentFile=-${ERP_DIR}/.env
ExecStart=${VENV}/bin/gunicorn --config ${GUNI_CFG} wsgi:app
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=5
KillMode=mixed
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

cp "/tmp/${SERVICE}.service" "${UNIT_DST}"
systemctl daemon-reload
systemctl enable "${SERVICE}"
# Free stale listeners on 8000 (old run.py leftovers)
if command -v fuser >/dev/null 2>&1; then
  fuser -k 8000/tcp 2>/dev/null || true
fi
systemctl restart "${SERVICE}"
sleep 2

if ! systemctl is-active --quiet "${SERVICE}"; then
  log_error "Service ${SERVICE} failed to start"
  systemctl --no-pager --full status "${SERVICE}" | head -40 || true
  journalctl -u "${SERVICE}" -n 40 --no-pager || true
  exit 1
fi

log_ok "Service ${SERVICE} is active (running)"
systemctl --no-pager --full status "${SERVICE}" | head -20 || true

# Wait until /health answers (workers may still be loading torch/OCR)
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"
if wait_for_http "${HEALTH_URL}" "${HEALTH_WAIT_SECONDS:-180}" 3; then
  log_ok "Service accepting HTTP on ${HEALTH_URL}"
  exit 0
fi

log_error "Service active but /health not ready in time"
journalctl -u "${SERVICE}" -n 50 --no-pager || true
exit 1
