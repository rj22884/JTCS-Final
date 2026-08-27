#!/usr/bin/env bash
# =============================================================================
# JTCS ERP — fix OCR on Ubuntu VPS
# EasyOCR/PaddleOCR fail without libGL.so.1; Tesseract is the Linux fallback.
#
# Usage (on VPS):
#   sudo bash deployment/fix_vps_ocr.sh
# =============================================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=lib/common.sh
if [[ -f "${SCRIPT_DIR}/lib/common.sh" ]]; then
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/lib/common.sh"
  load_deploy_env 2>/dev/null || true
fi

APP_DIR="${VPS_APP_DIR:-${REPO_ROOT}}"
ERP_DIR="${APP_DIR}/${VPS_ERP_DIR:-erp}"
VENV="${VPS_VENV_DIR:-${ERP_DIR}/.venv}"
SERVICE="${VPS_SYSTEMD_SERVICE:-jtcs-erp}"

if [[ "${EUID}" -ne 0 ]]; then
  SUDO="sudo"
else
  SUDO=""
fi

echo "=== JTCS OCR VPS fix ==="
echo "App: ${APP_DIR}"
echo "Venv: ${VENV}"

${SUDO} apt-get update
if ! ${SUDO} DEBIAN_FRONTEND=noninteractive apt-get install -y \
  libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 \
  tesseract-ocr tesseract-ocr-eng poppler-utils; then
  echo "libgl1 package name not found — trying libgl1-mesa-glx"
  ${SUDO} DEBIAN_FRONTEND=noninteractive apt-get install -y \
    libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 \
    tesseract-ocr tesseract-ocr-eng poppler-utils
fi

if [[ ! -x "${VENV}/bin/pip" ]]; then
  echo "ERROR: venv pip not found at ${VENV}/bin/pip"
  exit 1
fi

"${VENV}/bin/pip" uninstall -y opencv-python opencv-contrib-python || true
"${VENV}/bin/pip" install --disable-pip-version-check "opencv-python-headless>=4.8.0"

echo "--- OpenCV import check ---"
"${VENV}/bin/python" - <<'PY'
import sys
try:
    import cv2
    print("cv2 OK", getattr(cv2, "__version__", ""))
except Exception as exc:
    print("cv2 FAIL", exc)
    sys.exit(1)
try:
    import easyocr
    print("easyocr OK")
except Exception as exc:
    print("easyocr FAIL", exc)
    sys.exit(1)
PY

if command -v tesseract >/dev/null 2>&1; then
  echo "tesseract: $(command -v tesseract) $(tesseract --version 2>/dev/null | head -n 1)"
else
  echo "WARN: tesseract still not on PATH"
fi

if systemctl list-unit-files "${SERVICE}.service" >/dev/null 2>&1; then
  echo "Restarting ${SERVICE}"
  ${SUDO} systemctl restart "${SERVICE}" || true
else
  echo "Service ${SERVICE} not found — restart ERP/gunicorn manually."
fi

echo "=== OCR VPS fix complete ==="
