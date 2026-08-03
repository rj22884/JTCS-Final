#!/usr/bin/env bash
# =============================================================================
# DEPRECATED — do not use for production deploys.
# Canonical path: deployment/deploy.sh (Gunicorn + wsgi:app)
# This wrapper only exists so accidental old calls still go to the right script.
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "[WARN] scripts/vps_pull_update.sh is DEPRECATED."
echo "[WARN] Redirecting to deployment/deploy.sh …"
exec bash "${ROOT}/deployment/deploy.sh" "$@"
