# WhatsApp CRM

A WhatsApp Business inbox for a team. The app uses WhatsApp’s green, white, and neutral palette and is meant for daily conversation work on desktop and mobile.

It is **not connected** to Meta until a Cloud API client is enabled. The inbox shows sample conversations marked **Demo**. Composed messages are marked **Not sent** and are not delivered. Settings reports each credential as configured or not configured and never returns a saved secret to the browser.

Older notes for the JTCS ERP host are in [deploy/DEPLOYMENT.md](deploy/DEPLOYMENT.md). `deploy/nginx-whatsapp.conf.example` still describes that ERP proxy. It is not the config for this Next.js app.

## Run locally

Requires Node.js 22 or newer. Webhook event ids and saved credentials use the built-in `node:sqlite` module.

```bash
npm install
```

Windows (PowerShell):

```powershell
Copy-Item .env.example .env.local
npm run dev
```

macOS or Linux:

```bash
cp .env.example .env.local
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

Leave the values in `.env.local` empty to stay in demo mode. Real tokens and `ADMIN_PASSWORD` belong only in that file or the server environment. `.env.local` is gitignored. Do not prefix secrets with `NEXT_PUBLIC_`.

Open [http://localhost:3000/login](http://localhost:3000/login) first — the inbox requires a signed-in session.

`data/` holds this app’s SQLite file and is gitignored. Clearing a credential writes a local tombstone, so the field stays “Not configured” even if an environment variable is still set. That change does not affect any other system.

## Environment

| Name | Purpose |
| --- | --- |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Seeds the first verified admin on boot (scrypt hash). No default password. |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_SECURE` / `SMTP_USER` / `SMTP_PASS` / `SMTP_FROM` | Titan (or other) SMTP for OTP and recovery. See [docs/AUTH.md](docs/AUTH.md). |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | WhatsApp Business Account ID. |
| `WHATSAPP_PHONE_NUMBER_ID` | Cloud API phone number id. |
| `WHATSAPP_ACCESS_TOKEN` | Access token. Never returned to the browser. |
| `WHATSAPP_APP_SECRET` | Verifies `X-Hub-Signature-256`. |
| `WHATSAPP_VERIFY_TOKEN` | Answers the Meta webhook challenge. |
| `WHATSAPP_WEBHOOK_URL` | Production https webhook URL, if you already have one. Localhost is ignored. |
| `ERP_BASE_URL` | HTTPS origin of JTCS ERP (default `https://app.jtcsxpert.com`). |
| `WHATSAPP_CUSTOMER_SYNC_TOKEN` | Outbound token for CustomerMaster sync. Prefer generating it in Settings. |

A saved value in the local database overrides the matching environment variable. Delete on Settings clears the local value and does not rewrite another machine.

Auth + Titan email: [docs/AUTH.md](docs/AUTH.md). CustomerMaster sync and Contacts: [docs/ERP_SYNC.md](docs/ERP_SYNC.md).

## Scripts

- `npm run dev` — development server
- `npm run build` — production build
- `npm run start` — production server
- `npm run lint` — lint

## What the demo does

- Conversations, notes, labels, and new messages live in server memory and reset when the process restarts.
- Opening a conversation clears its unread count in that demo store.
- Sample transcripts include sent, delivered, read, and failed marks so the layout can be reviewed. Those marks are not receipts from Meta.
- `GET /api/whatsapp/status` reports whether each credential is configured. It does not return secret values. The connection stays `not_connected` and demo mode stays on. The production webhook URL is included only when a real https URL is configured.
- An admin session is an HttpOnly cookie. Credential replace and clear require that session, a matching CSRF token, and a same-origin request.
- `GET /api/whatsapp/webhook` answers Meta’s verify challenge only when the verify token is configured. Otherwise it returns 503.
- `POST /api/whatsapp/webhook` checks `X-Hub-Signature-256` when the app secret is configured, stores event ids in SQLite so retries are ignored, and does not write those events into the inbox. Without the app secret it refuses the body.

Sending through the official Cloud API is intentionally not implemented. The server boundary for that later work is `src/lib/whatsapp/client.ts`.
