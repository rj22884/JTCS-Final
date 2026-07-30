#!/usr/bin/env bash
# First-time VPS setup for JTCS ERP (Ubuntu/Debian).
# Usage (on VPS):
#   cd ~/JTCS-final
#   bash scripts/vps_first_setup.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ERP="$ROOT/erp"

echo "========================================"
echo "  JTCS ERP - VPS first-time setup"
echo "========================================"
echo "  Repo : $ROOT"
echo

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root (or with sudo)."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y git python3 python3-venv python3-pip curl

cd "$ROOT"

if [[ ! -d .git ]]; then
  echo "ERROR: $ROOT is not a git repo."
  echo "Clone first, e.g.:"
  echo "  git clone https://github.com/rj22884/JTCS-final.git ~/JTCS-final"
  exit 1
fi

cd "$ERP"

if [[ ! -d .venv ]]; then
  echo "Creating Python venv..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo
  echo "Created erp/.env from .env.example"
  echo "EDIT these values now:"
  echo "  MAIL_PASSWORD=..."
  echo "  APP_BASE_URL=http://YOUR_PUBLIC_IP:8000"
  echo "  DB_* settings for your SQL Server"
  echo
  "${EDITOR:-nano}" .env || true
fi

UNIT_SRC="$ROOT/scripts/jtcs-erp.service"
UNIT_DST="/etc/systemd/system/jtcs-erp.service"

# Rewrite WorkingDirectory to this machine's path
sed "s|/root/JTCS-final/erp|$ERP|g" "$UNIT_SRC" > "$UNIT_DST"
systemctl daemon-reload
systemctl enable jtcs-erp
systemctl restart jtcs-erp

sleep 2
systemctl --no-pager --full status jtcs-erp | head -25 || true

echo
echo "========================================"
echo "  Setup done"
echo "========================================"
echo "  App URL : http://$(hostname -I | awk '{print $1}'):8000/login"
echo "  Status  : systemctl status jtcs-erp"
echo "  Logs    : journalctl -u jtcs-erp -f"
echo "  Mail    : cd $ERP && python3 scripts/test_smtp_health.py"
echo "========================================"
