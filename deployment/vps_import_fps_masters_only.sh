#!/usr/bin/env bash
# STRICT SCOPE: overwrite ONLY Public Report Ration Card PDS masters
# (State / District / DSO / ARO / FPS) used by:
#   https://app.jtcsxpert.com/public-report/ration-card
# Does NOT touch ERP billing, follow-up, bank, daybook, or other modules.
# Does NOT deploy application code.
set -eu

APP_DIR="${VPS_APP_DIR:-/root/JTCS-final}"
ERP_DIR="${APP_DIR}/erp"
VENV_PY="${ERP_DIR}/.venv/bin/python"
IMPORT_PY="${ERP_DIR}/scripts/import_fps_masters_excel.py"
XLSX="${1:-/tmp/jtcs_fps_import/DistrictWiseFpsDetails_Merged_WithCodes.xlsx}"
REMOTE_STAGING="/tmp/jtcs_fps_import"

echo "========================================"
echo " JTCS - FPS masters import (VPS ONLY)"
echo " Target : https://app.jtcsxpert.com/public-report/ration-card"
echo " Scope  : PdsState/District/DSO/ARO/FPS only"
echo "========================================"

if [[ ! -f "${XLSX}" ]]; then
  echo "[FAIL] Excel not found: ${XLSX}"
  exit 1
fi
if [[ ! -f "${IMPORT_PY}" ]]; then
  echo "[FAIL] Import script missing: ${IMPORT_PY}"
  exit 1
fi
if [[ ! -x "${VENV_PY}" ]]; then
  echo "[FAIL] Venv python missing: ${VENV_PY}"
  exit 1
fi
if [[ ! -f "${ERP_DIR}/.env" ]]; then
  echo "[FAIL] Missing ${ERP_DIR}/.env (live DB config)"
  exit 1
fi

cd "${ERP_DIR}"
export FLASK_APP=wsgi:app
echo "[RUN] ${VENV_PY} ${IMPORT_PY} ${XLSX}"
"${VENV_PY}" "${IMPORT_PY}" "${XLSX}"
echo "[OK] Import finished."

rm -f "${REMOTE_STAGING}/DistrictWiseFpsDetails_Merged_WithCodes.xlsx" \
      "${REMOTE_STAGING}/import_fps_masters_excel.py" \
      "${REMOTE_STAGING}/vps_import_fps_masters_only.sh" 2>/dev/null || true
echo "[OK] Remote staging cleaned: ${REMOTE_STAGING}"
echo
echo "Verify in browser:"
echo "  https://app.jtcsxpert.com/public-report/ration-card/fps-master"
echo "  https://app.jtcsxpert.com/public-report/ration-card/district-master"
