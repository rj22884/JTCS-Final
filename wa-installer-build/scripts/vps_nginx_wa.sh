#!/bin/bash
set -euo pipefail

# Serve only wa.ukdscwala.com from this app. Do not edit other nginx sites.

APP_PORT="${1:-3010}"
SITE="wa.ukdscwala.com"
AVAIL="/etc/nginx/sites-available/${SITE}"
ENABLED="/etc/nginx/sites-enabled/${SITE}"

if ! printf '%s' "$APP_PORT" | grep -Eq '^[0-9]+$'; then
  echo "ERROR: app port is not a number."
  exit 1
fi

if ! command -v nginx >/dev/null 2>&1; then
  echo "ERROR: nginx is not installed."
  exit 1
fi

echo "Waiting for WhatsApp CRM on 127.0.0.1:${APP_PORT}..."
ready=0
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do
  if curl -fsS --max-time 2 "http://127.0.0.1:${APP_PORT}/" >/dev/null; then
    ready=1
    break
  fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  echo "ERROR: WhatsApp CRM is not answering on 127.0.0.1:${APP_PORT}"
  journalctl -u whatsapp-crm -n 40 --no-pager || true
  exit 1
fi

cat > "$AVAIL" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${SITE};

    client_max_body_size 16m;

    location / {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_redirect off;
        proxy_read_timeout 120s;
    }
}
EOF

ln -sfn "$AVAIL" "$ENABLED"
nginx -t
systemctl reload nginx
echo "HTTP vhost enabled for ${SITE} -> 127.0.0.1:${APP_PORT}"

if command -v certbot >/dev/null 2>&1; then
  certbot --nginx -d "$SITE" \
    --non-interactive --agree-tos --redirect \
    --register-unsafely-without-email \
    || echo "WARN: certificate was not issued. HTTP for ${SITE} is still on."
else
  echo "WARN: certbot is not installed. ${SITE} is on HTTP only."
fi

echo "=== Host check ==="
curl -sI -H "Host: ${SITE}" "http://127.0.0.1/" | head -n 12
echo "=== Nginx site done ==="
