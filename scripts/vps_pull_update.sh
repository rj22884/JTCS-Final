#!/usr/bin/env bash
# Run on the VPS to pull latest code from GitHub and restart JTCS ERP.
# Usage:
#   cd ~/JTCS-final
#   bash scripts/vps_pull_update.sh
#
# Safe for dirty VPS trees: backs up erp/.env, hard-resets to origin, restores .env.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "========================================"
echo "  JTCS ERP - VPS pull + update"
echo "========================================"
echo "  Folder : $ROOT"
echo

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is not installed. Run: apt update && apt install -y git"
  exit 1
fi

ENV_BAK="/tmp/jtcs.env.bak.$$"
if [[ -f erp/.env ]]; then
  cp erp/.env "$ENV_BAK"
  echo "Backed up erp/.env"
fi

echo "Fetching from origin..."
git fetch origin

CURRENT="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
TARGET="${BRANCH:-$CURRENT}"

if [[ -n "${BRANCH:-}" ]]; then
  echo "Switching to requested branch: $TARGET"
  git checkout -B "$TARGET" "origin/$TARGET" 2>/dev/null || git checkout "$TARGET" || git checkout main
fi

CURRENT="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
echo "Current branch: $CURRENT"

if git show-ref --verify --quiet "refs/remotes/origin/$CURRENT"; then
  echo "Hard reset to origin/$CURRENT (keeps deploy clean; .env restored after)..."
  git reset --hard "origin/$CURRENT"
else
  echo "Remote branch missing — hard reset to origin/main"
  git checkout main 2>/dev/null || true
  git reset --hard origin/main
fi

if [[ -f "$ENV_BAK" ]]; then
  mkdir -p erp
  cp "$ENV_BAK" erp/.env
  rm -f "$ENV_BAK"
  echo "Restored erp/.env"
fi

echo
echo "Latest commit:"
git log -1 --oneline
echo

ERP_DIR="$ROOT/erp"
if [[ -d "$ERP_DIR" ]]; then
  cd "$ERP_DIR"

  if [[ ! -f .env ]]; then
    echo "WARNING: erp/.env missing on VPS."
    echo "  cp .env.example .env && nano .env"
    echo "  Set MAIL_PASSWORD and APP_BASE_URL=http://200.141.5.68:8000"
  else
    echo "erp/.env found (not overwritten from git)."
  fi

  PY=""
  if [[ -x .venv/bin/python ]]; then
    PY=".venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PY="python3"
  elif command -v python >/dev/null 2>&1; then
    PY="python"
  fi

  if [[ -n "$PY" && -f requirements.txt ]]; then
    echo "Installing/updating Python deps with: $PY"
    "$PY" -m pip install -r requirements.txt -q || true
  fi

  # SCHEMA ONLY — never RESTORE / never wipe transaction data.
  if [[ -n "$PY" && -f scripts/apply_schema_migrations.py ]]; then
    echo
    echo "Applying SCHEMA-ONLY SQL migrations (data preserved)..."
    "$PY" scripts/apply_schema_migrations.py || {
      echo "WARNING: schema migration failed — app code updated, DATA left untouched."
    }
  elif [[ -x "$ROOT/deployment/apply_migrations.sh" ]]; then
    echo
    echo "Applying SCHEMA-ONLY SQL migrations via deployment/apply_migrations.sh..."
    bash "$ROOT/deployment/apply_migrations.sh" || {
      echo "WARNING: schema migration failed — DATA left untouched."
    }
  else
    echo "No schema migrator found — skipping DB schema update (DATA untouched)."
  fi

  UNIT_SRC="$ROOT/scripts/jtcs-erp.service"
  UNIT_DST="/etc/systemd/system/jtcs-erp.service"

  if command -v systemctl >/dev/null 2>&1 && [[ -f "$UNIT_SRC" ]]; then
    if [[ ! -f "$UNIT_DST" ]]; then
      echo "Installing systemd unit jtcs-erp..."
      sed "s|/root/JTCS-final/erp|$ERP_DIR|g" "$UNIT_SRC" > /tmp/jtcs-erp.service
      if [[ "$(id -u)" -eq 0 ]]; then
        cp /tmp/jtcs-erp.service "$UNIT_DST"
        systemctl daemon-reload
        systemctl enable jtcs-erp
      else
        sudo cp /tmp/jtcs-erp.service "$UNIT_DST"
        sudo systemctl daemon-reload
        sudo systemctl enable jtcs-erp
      fi
    fi

    echo "Restarting systemd service jtcs-erp..."
    if [[ "$(id -u)" -eq 0 ]]; then
      systemctl restart jtcs-erp || true
      systemctl --no-pager --full status jtcs-erp | head -20 || true
    else
      sudo systemctl restart jtcs-erp || true
      sudo systemctl --no-pager --full status jtcs-erp | head -20 || true
    fi
  else
    echo
    echo "No jtcs-erp systemd service (optional)."
    echo "App restart manually if needed:"
    echo "  cd $ERP_DIR && fuser -k 8000/tcp 2>/dev/null; ${PY:-python3} run.py"
  fi
fi

echo
echo "========================================"
echo "  VPS update finished"
echo "========================================"
echo "  Mail test:"
echo "    cd $ERP_DIR"
echo "    python3 scripts/check_vps_mail.py"
echo "========================================"
