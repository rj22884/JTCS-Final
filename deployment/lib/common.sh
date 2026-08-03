#!/usr/bin/env bash
# =============================================================================
# JTCS ERP — Shared deployment helpers (sourced by other scripts)
# =============================================================================

set -o errexit
set -o pipefail
set -o nounset

# Resolve deployment/ and repo roots even when sourced via symlink.
_COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENT_DIR="$(cd "${_COMMON_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${DEPLOYMENT_DIR}/.." && pwd)"

# Load deploy.env if present (secrets stay out of git).
load_deploy_env() {
  local env_file="${1:-}"
  if [[ -z "${env_file}" ]]; then
    if [[ -f "${DEPLOYMENT_DIR}/deploy.env" ]]; then
      env_file="${DEPLOYMENT_DIR}/deploy.env"
    elif [[ -f "${DEPLOYMENT_DIR}/config/deploy.env" ]]; then
      env_file="${DEPLOYMENT_DIR}/config/deploy.env"
    fi
  fi
  if [[ -n "${env_file}" && -f "${env_file}" ]]; then
    # shellcheck disable=SC1090
    set -a
    source "${env_file}"
    set +a
  fi
}

timestamp_now() {
  date +"%Y-%m-%d_%H%M%S"
}

iso_now() {
  date +"%Y-%m-%d %H:%M:%S %z"
}

log_info()  { echo "[INFO ] $(iso_now) $*"; }
log_warn()  { echo "[WARN ] $(iso_now) $*" >&2; }
log_error() { echo "[ERROR] $(iso_now) $*" >&2; }
log_ok()    { echo "[OK   ] $(iso_now) $*"; }

require_cmd() {
  local c
  for c in "$@"; do
    if ! command -v "${c}" >/dev/null 2>&1; then
      log_error "Required command not found: ${c}"
      return 1
    fi
  done
}

ensure_dir() {
  mkdir -p "$@"
}

# Append a structured log line to deployment log file.
append_deploy_log() {
  local log_file="${1}"
  shift
  ensure_dir "$(dirname "${log_file}")"
  {
    echo "------------------------------------------------------------"
    echo "$*"
  } >> "${log_file}"
}

git_commit_id() {
  git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo "unknown"
}

git_branch_name() {
  git -C "${REPO_ROOT}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown"
}

git_full_commit() {
  git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || echo "unknown"
}

service_is_active() {
  local unit="$1"
  systemctl is-active --quiet "${unit}"
}

http_ok() {
  local url="$1"
  local code
  code="$(curl -fsS -o /dev/null -w "%{http_code}" --max-time 20 "${url}" || true)"
  [[ "${code}" == "200" || "${code}" == "204" ]]
}

# Heavy apps (torch/OCR) can take 1–3 minutes before /health answers.
wait_for_http() {
  local url="$1"
  local timeout_s="${2:-180}"
  local interval_s="${3:-3}"
  local elapsed=0
  local code=""
  log_info "Waiting up to ${timeout_s}s for ${url} …"
  while [[ ${elapsed} -lt ${timeout_s} ]]; do
    code="$(curl -fsS -o /dev/null -w "%{http_code}" --max-time 10 "${url}" 2>/dev/null || true)"
    if [[ "${code}" == "200" || "${code}" == "204" ]]; then
      log_ok "HTTP ${code} from ${url} after ${elapsed}s"
      return 0
    fi
    sleep "${interval_s}"
    elapsed=$((elapsed + interval_s))
    if (( elapsed % 15 == 0 )); then
      log_info "Still waiting for ${url} (${elapsed}s, last=${code:-none})…"
    fi
  done
  log_error "Timed out waiting for ${url} after ${timeout_s}s (last HTTP=${code:-none})"
  return 1
}

# Write APP_VERSION into Flask .env without printing secrets.
sync_app_version_env() {
  local env_file="$1"
  local version="$2"
  [[ -f "${env_file}" ]] || return 0
  if grep -qE '^APP_VERSION=' "${env_file}"; then
    sed -i "s/^APP_VERSION=.*/APP_VERSION=${version}/" "${env_file}"
  else
    printf '\nAPP_VERSION=%s\n' "${version}" >> "${env_file}"
  fi
}
