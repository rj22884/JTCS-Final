#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${VPS_APP_DIR:-/root/JTCS-final}"
ERP_DIR="${APP_DIR}/erp"
VENV_PY="${ERP_DIR}/.venv/bin/python"
RUNNER="/tmp/jtcs_stampmaster_update/update_stampmaster_nulls.py"
OPTION="${1:-}"

if [[ ! -f "${ERP_DIR}/.env" ]]; then
  echo "[FAIL] Live app config not found: ${ERP_DIR}/.env"
  exit 1
fi
if [[ ! -x "${VENV_PY}" ]]; then
  echo "[FAIL] App Python environment not found: ${VENV_PY}"
  exit 1
fi
if [[ ! -f "${RUNNER}" ]]; then
  echo "[FAIL] Update runner not found: ${RUNNER}"
  exit 1
fi
if [[ "${OPTION}" != "1" && "${OPTION}" != "2" ]]; then
  echo "[FAIL] Invalid update option."
  exit 2
fi

cd "${ERP_DIR}"
"${VENV_PY}" "${RUNNER}" "${OPTION}"
