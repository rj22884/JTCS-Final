#!/usr/bin/env bash
# =============================================================================
# JTCS ERP - Fix 502: restore erp/.env + redeploy/restart
# Usage: bash vps_repair_502.sh APP_DIR BRANCH REPO_URL
# Expects Windows-uploaded secrets at /tmp/jtcs.env.from_windows
# =============================================================================
set -euo pipefail

APP_DIR="${1:?APP_DIR required}"
BRANCH="${2:?BRANCH required}"
REPO_URL="${3:?REPO_URL required}"
ENV_SRC="/tmp/jtcs.env.from_windows"
SERVICE="${VPS_SYSTEMD_SERVICE:-jtcs-erp}"
PARENT="$(dirname "${APP_DIR}")"
BASE_NAME="$(basename "${APP_DIR}")"

echo "[INFO] === 502 REPAIR START ==="
echo "[INFO] APP_DIR=${APP_DIR}"
echo "[INFO] BRANCH=${BRANCH}"

if [[ ! -f "${ENV_SRC}" ]]; then
  echo "[ERROR] ${ENV_SRC} missing - upload local erp/.env first"
  echo "===DEPLOY_RESULT:FAILED==="
  exit 1
fi

# If live tree missing after bad overwrite, restore newest .old_* backup
if [[ ! -d "${APP_DIR}/.git" ]]; then
  NEWEST="$(ls -1dt "${PARENT}/${BASE_NAME}".old_* 2>/dev/null | head -n 1 || true)"
  if [[ -n "${NEWEST}" && -d "${NEWEST}/.git" ]]; then
    echo "[INFO] Restoring app tree from ${NEWEST}"
    rm -rf "${APP_DIR}"
    mv "${NEWEST}" "${APP_DIR}"
    echo "[OK] Restored ${APP_DIR}"
  fi
fi

if [[ ! -d "${APP_DIR}/.git" ]]; then
  echo "[ERROR] App tree missing at ${APP_DIR}"
  echo "[ERROR] Run JTCS_ERP.bat option 3 (Full overwrite)"
  echo "===DEPLOY_RESULT:FAILED==="
  exit 1
fi

mkdir -p "${APP_DIR}/erp"
cp "${ENV_SRC}" "${APP_DIR}/erp/.env"
chmod 600 "${APP_DIR}/erp/.env"
echo "[OK] erp/.env restored from Windows upload"

cd "${APP_DIR}"
git remote set-url origin "${REPO_URL}" || true
export BRANCH="${BRANCH}"
export GIT_BRANCH="${BRANCH}"
export VPS_APP_DIR="${APP_DIR}"

systemctl stop "${SERVICE}" 2>/dev/null || true
pkill -9 -f 'gunicorn.*wsgi:app' 2>/dev/null || true
if command -v fuser >/dev/null 2>&1; then
  fuser -k 8000/tcp 2>/dev/null || true
fi

if [[ -f "${APP_DIR}/deployment/deploy.sh" ]]; then
  echo "[INFO] Running deployment/deploy.sh --skip-backup..."
  if bash "${APP_DIR}/deployment/deploy.sh" --skip-backup; then
    echo "===DEPLOY_RESULT:SUCCESS==="
    echo "[OK] === 502 REPAIR COMPLETE ==="
    exit 0
  fi
  echo "[WARN] deploy.sh failed - trying repair.sh"
fi

if [[ -f "${APP_DIR}/deployment/repair.sh" ]]; then
  if bash "${APP_DIR}/deployment/repair.sh"; then
    echo "===DEPLOY_RESULT:SUCCESS==="
    echo "[OK] === 502 REPAIR COMPLETE ==="
    exit 0
  fi
fi

echo "===DEPLOY_RESULT:FAILED==="
echo "[ERROR] Repair failed"
exit 1
