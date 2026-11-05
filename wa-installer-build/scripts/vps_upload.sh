#!/bin/bash
set -euo pipefail

APP_DIR="${1:-}"
ZIP_PATH="${2:-}"
APP_PORT="${3:-3010}"

echo "=== WhatsApp CRM upload ==="

if [ -z "$APP_DIR" ] || [ -z "$ZIP_PATH" ]; then
  echo "ERROR: app directory and zip path are required."
  exit 1
fi

case "$APP_DIR" in
  /|"/var/www"|"/var/www/"|"/home"|"/home/"|"/root"|"/root/"|"/opt"|"/opt/"|"/usr"|"/usr/"|"/etc"|"/etc/")
    echo "ERROR: remote path is too broad."
    exit 1
    ;;
esac

if printf '%s' "$APP_DIR" | grep -qi 'jtcs'; then
  echo "ERROR: refusing a path that looks like JTCS."
  exit 1
fi

if ! printf '%s' "$APP_PORT" | grep -Eq '^[0-9]+$'; then
  echo "ERROR: app port is not a number."
  exit 1
fi
if [ "$APP_PORT" -lt 1024 ] || [ "$APP_PORT" -gt 65535 ] || [ "$APP_PORT" -eq 8000 ]; then
  echo "ERROR: app port must be 1024-65535 and not 8000."
  exit 1
fi

if [ ! -f "$ZIP_PATH" ]; then
  echo "ERROR: zip missing."
  exit 1
fi

install_packages() {
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y
    apt-get install -y "$@"
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y "$@"
  else
    echo "ERROR: cannot install: $*"
    exit 1
  fi
}

ensure_node() {
  export PATH="/usr/local/bin:${PATH}"
  if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    major="$(node -p "Number(process.versions.node.split('.')[0])")"
    if [ "$major" -ge 22 ]; then
      return
    fi
    echo "Node.js $(node -v) is older than 22."
  fi

  if ! command -v curl >/dev/null 2>&1; then
    install_packages ca-certificates curl
  fi

  case "$(uname -m)" in
    x86_64|amd64) nodearch="x64" ;;
    aarch64|arm64) nodearch="arm64" ;;
    *)
      echo "ERROR: unsupported CPU $(uname -m)."
      exit 1
      ;;
  esac

  ver="v24.18.0"
  url="https://nodejs.org/dist/${ver}/node-${ver}-linux-${nodearch}.tar.gz"
  echo "Installing Node.js ${ver} into /usr/local."
  tmp="$(mktemp -d)"
  curl -fsSL "$url" -o "$tmp/node.tar.gz"
  tar -xzf "$tmp/node.tar.gz" -C /usr/local --strip-components=1
  rm -rf "$tmp"
  hash -r
  export PATH="/usr/local/bin:${PATH}"
  if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    echo "ERROR: Node.js install did not succeed."
    exit 1
  fi
}

ensure_node

mkdir -p "$APP_DIR"
cd "$APP_DIR"

KEEP="$(mktemp -d)"
if [ -f .env ]; then cp -a .env "$KEEP/.env"; fi
if [ -f .env.local ]; then cp -a .env.local "$KEEP/.env.local"; fi
if [ -f .env.production ]; then cp -a .env.production "$KEEP/.env.production"; fi
if [ -d data ]; then cp -a data "$KEEP/data"; fi

if command -v python3 >/dev/null 2>&1; then
  python3 -m zipfile -e "$ZIP_PATH" "$APP_DIR"
elif command -v unzip >/dev/null 2>&1; then
  unzip -qo "$ZIP_PATH" -d "$APP_DIR"
else
  install_packages unzip
  unzip -qo "$ZIP_PATH" -d "$APP_DIR"
fi

if [ -f "$KEEP/.env" ]; then mv "$KEEP/.env" .env; fi
if [ -f "$KEEP/.env.local" ]; then mv "$KEEP/.env.local" .env.local; fi
if [ -f "$KEEP/.env.production" ]; then mv "$KEEP/.env.production" .env.production; fi
if [ -d "$KEEP/data" ]; then rm -rf data && mv "$KEEP/data" data; fi
rm -rf "$KEEP"
rm -f "$ZIP_PATH"

if [ ! -f .env.local ] && [ -f .env.example ]; then
  cp .env.example .env.local
  echo "Created .env.local from the example. Fill it in on the server. No password was generated."
fi

if [ -f /tmp/whatsapp-admin.env ]; then
  touch .env.local
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      ADMIN_EMAIL=*|ADMIN_PASSWORD=*|SMTP_HOST=*|SMTP_PORT=*|SMTP_USER=*|SMTP_PASS=*|SMTP_FROM=*|WHATSAPP_BUSINESS_ACCOUNT_ID=*|WHATSAPP_DISPLAY_PHONE=*|WHATSAPP_APP_ID=*|WHATSAPP_WEBHOOK_URL=*|NEXT_PUBLIC_VAPID_PUBLIC_KEY=*|VAPID_PRIVATE_KEY=*|VAPID_SUBJECT=*)
        key="${line%%=*}"
        value="${line#*=}"
        if [ -n "$value" ]; then
          grep -v "^${key}=" .env.local > .env.local.tmp || true
          printf '%s\n' "$line" >> .env.local.tmp
          mv .env.local.tmp .env.local
        fi
        ;;
    esac
  done < /tmp/whatsapp-admin.env
  rm -f /tmp/whatsapp-admin.env
  echo "Admin sign-in / push (VAPID) settings were stored on the server."
fi

npm ci
npm run build

NODE_BIN="$(command -v node)"
UNIT="/etc/systemd/system/whatsapp-crm.service"
if command -v systemctl >/dev/null 2>&1; then
  cat > "$UNIT" <<EOF
[Unit]
Description=WhatsApp CRM
After=network.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=$NODE_BIN $APP_DIR/node_modules/next/dist/bin/next start -p $APP_PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable whatsapp-crm
  systemctl restart whatsapp-crm
  systemctl --no-pager --lines=15 status whatsapp-crm || true
else
  echo "systemd not found. Files are uploaded. Start is not running."
fi

if [ -f "$APP_DIR/scripts/vps_nginx_wa.sh" ]; then
  bash "$APP_DIR/scripts/vps_nginx_wa.sh" "$APP_PORT"
fi

echo "=== Upload finished ==="
echo "App directory: $APP_DIR"
echo "Port: $APP_PORT"
echo "Site: https://wa.ukdscwala.com"
echo "Other nginx sites, JTCS, and existing server env files were left in place."
