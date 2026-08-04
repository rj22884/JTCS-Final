#!/usr/bin/env bash
# =============================================================================
# JTCS ERP - Full overwrite on VPS (fresh clone from GitHub)
# Preserves erp/.env (from live tree, prior .old_*, backups, or Windows upload).
# Invoked from JTCS_ERP.bat via scp + ssh.
# =============================================================================
set -euo pipefail

APP_DIR="${1:?APP_DIR required}"
BRANCH="${2:?BRANCH required}"
REPO_URL="${3:?REPO_URL required}"
SERVICE="${VPS_SYSTEMD_SERVICE:-jtcs-erp}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OLD_DIR="${APP_DIR}.old_${STAMP}"
ENV_BAK="/tmp/jtcs.env.overwrite.${STAMP}"
ENV_FROM_WIN="/tmp/jtcs.env.from_windows"
PARENT="$(dirname "${APP_DIR}")"
BASE_NAME="$(basename "${APP_DIR}")"

echo "[INFO] === FULL OVERWRITE START ==="
echo "[INFO] APP_DIR=${APP_DIR}"
echo "[INFO] BRANCH=${BRANCH}"
echo "[INFO] REPO=${REPO_URL}"
echo "[INFO] SERVICE=${SERVICE}"

command -v git >/dev/null || { echo "[ERROR] git missing"; echo "===DEPLOY_RESULT:FAILED==="; exit 1; }

find_env_candidate() {
  local f
  for f in \
    "${APP_DIR}/erp/.env" \
    "${APP_DIR}/.env" \
    "${APP_DIR}/deployment/deploy.env"
  do
    if [[ -f "${f}" ]]; then
      echo "${f}"
      return 0
    fi
  done

  # Newest prior overwrite backups: /root/JTCS-final.old_*
  local newest=""
  newest="$(ls -1dt "${PARENT}/${BASE_NAME}".old_* 2>/dev/null | head -n 1 || true)"
  if [[ -n "${newest}" ]]; then
    for f in "${newest}/erp/.env" "${newest}/.env"; do
      if [[ -f "${f}" ]]; then
        echo "${f}"
        return 0
      fi
    done
  fi

  # Any sibling JTCS* tree
  local d
  while IFS= read -r d; do
    [[ -z "${d}" ]] && continue
    for f in "${d}/erp/.env" "${d}/.env"; do
      if [[ -f "${f}" ]]; then
        echo "${f}"
        return 0
      fi
    done
  done < <(ls -1dt "${PARENT}"/JTCS* "${PARENT}"/jtcs* 2>/dev/null || true)

  # systemd EnvironmentFile=
  if command -v systemctl >/dev/null 2>&1; then
    local ef
    ef="$(systemctl show -p EnvironmentFiles --value "${SERVICE}" 2>/dev/null | tr ' ' '\n' | sed -n 's/^\([^ ]*\.env\).*/\1/p' | head -n 1 || true)"
    if [[ -n "${ef}" && -f "${ef}" ]]; then
      echo "${ef}"
      return 0
    fi
    ef="$(systemctl cat "${SERVICE}" 2>/dev/null | sed -n 's/^EnvironmentFile=-\?\(.*\)/\1/p' | head -n 1 || true)"
    if [[ -n "${ef}" && -f "${ef}" ]]; then
      echo "${ef}"
      return 0
    fi
  fi

  # Deployment backup bundles: .../config/erp.env
  local bak
  bak="$(ls -1dt /root/jtcs-backups/*/config/erp.env /var/backups/jtcs/*/config/erp.env "${PARENT}"/backups/*/config/erp.env 2>/dev/null | head -n 1 || true)"
  if [[ -n "${bak}" && -f "${bak}" ]]; then
    echo "${bak}"
    return 0
  fi

  # Uploaded from Windows by JTCS_ERP.bat (last resort)
  if [[ -f "${ENV_FROM_WIN}" ]]; then
    echo "${ENV_FROM_WIN}"
    return 0
  fi

  return 1
}

backup_env() {
  local src=""
  src="$(find_env_candidate || true)"
  if [[ -n "${src}" && -f "${src}" ]]; then
    cp "${src}" "${ENV_BAK}"
    chmod 600 "${ENV_BAK}" 2>/dev/null || true
    echo "[OK] Backed up env from ${src} -> ${ENV_BAK}"
    return 0
  fi
  echo "[WARN] No .env found before overwrite (will try again after move / Windows upload)"
  return 1
}

systemctl stop "${SERVICE}" 2>/dev/null || true
pkill -9 -f 'gunicorn.*wsgi:app' 2>/dev/null || true
pkill -9 -f 'python.*run.py' 2>/dev/null || true
if command -v fuser >/dev/null 2>&1; then
  fuser -k 8000/tcp 2>/dev/null || true
fi

mkdir -p "${PARENT}"
backup_env || true

if [[ -d "${APP_DIR}" ]]; then
  # Re-try env from live tree right before move (in case first pass missed)
  if [[ ! -f "${ENV_BAK}" ]]; then
    backup_env || true
  fi
  rm -rf "${OLD_DIR}"
  mv "${APP_DIR}" "${OLD_DIR}"
  echo "[OK] Moved old tree to ${OLD_DIR}"
  if [[ ! -f "${ENV_BAK}" ]]; then
    if [[ -f "${OLD_DIR}/erp/.env" ]]; then
      cp "${OLD_DIR}/erp/.env" "${ENV_BAK}"
      echo "[OK] Backed up erp/.env from moved tree"
    elif [[ -f "${OLD_DIR}/.env" ]]; then
      cp "${OLD_DIR}/.env" "${ENV_BAK}"
      echo "[OK] Backed up .env from moved tree"
    fi
  fi
else
  echo "[WARN] ${APP_DIR} did not exist - fresh path (searching siblings / backups for .env)"
  backup_env || true
fi

echo "[INFO] Cloning ${REPO_URL} (branch ${BRANCH})..."
if ! git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"; then
  echo "[WARN] Branch clone failed - cloning default then checking out ${BRANCH}"
  git clone "${REPO_URL}" "${APP_DIR}"
  cd "${APP_DIR}"
  git fetch --all --prune
  git checkout -B "${BRANCH}" "origin/${BRANCH}" 2>/dev/null || git checkout -B "${BRANCH}"
fi

cd "${APP_DIR}"
git remote set-url origin "${REPO_URL}"
git fetch --all --prune
git checkout -B "${BRANCH}" "origin/${BRANCH}" 2>/dev/null || git checkout -B "${BRANCH}"
git reset --hard "origin/${BRANCH}"
git clean -fd
echo "[OK] Fresh tree: $(pwd)"
echo "[OK] Branch=$(git branch --show-current) Commit=$(git rev-parse HEAD)"

mkdir -p "${APP_DIR}/erp"
if [[ ! -f "${ENV_BAK}" ]]; then
  backup_env || true
fi
if [[ -f "${ENV_BAK}" ]]; then
  cp "${ENV_BAK}" "${APP_DIR}/erp/.env"
  chmod 600 "${APP_DIR}/erp/.env" 2>/dev/null || true
  echo "[OK] Restored erp/.env"
elif [[ -f "${ENV_FROM_WIN}" ]]; then
  cp "${ENV_FROM_WIN}" "${APP_DIR}/erp/.env"
  chmod 600 "${APP_DIR}/erp/.env" 2>/dev/null || true
  echo "[OK] Restored erp/.env from Windows upload"
else
  echo "[ERROR] erp/.env missing after overwrite - cannot start app"
  echo "[ERROR] Put secrets on VPS, or ensure local erp/.env exists and re-run option 3"
  echo "[ERROR] Also check ${PARENT}/${BASE_NAME}.old_*/erp/.env"
  echo "===DEPLOY_RESULT:FAILED==="
  exit 1
fi

if [[ ! -f "${APP_DIR}/deployment/deploy.sh" ]]; then
  echo "[ERROR] deployment/deploy.sh missing in fresh clone"
  echo "===DEPLOY_RESULT:FAILED==="
  exit 1
fi

export BRANCH="${BRANCH}"
export GIT_BRANCH="${BRANCH}"
export VPS_APP_DIR="${APP_DIR}"
echo "[INFO] Running deployment/deploy.sh --skip-backup..."
if bash "${APP_DIR}/deployment/deploy.sh" --skip-backup; then
  # Re-emit after deploy.sh: SSH+tee can drop the in-script SUCCESS line.
  echo "===DEPLOY_RESULT:SUCCESS==="
  echo "===FULL_OVERWRITE:SUCCESS==="
  echo "[OK] === FULL OVERWRITE COMPLETE ==="
  exit 0
fi

echo "===DEPLOY_RESULT:FAILED==="
echo "===FULL_OVERWRITE:FAILED==="
echo "[ERROR] deploy.sh failed during full overwrite"
exit 1
