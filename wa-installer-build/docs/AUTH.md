# Authentication (mobile OTP + WhatsApp admin approval)

WhatsApp inbox, contacts, and conversation APIs require an **active** approved user session. Public registration lets the user choose a **role type** (`member` or `admin`), but the account stays `pending_approval` until an existing admin approves (and can confirm/change the role). First admin can still be seeded via env.

## First admin

Set both on the server (never commit real values):

```bash
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=your-long-password
```

On first boot, if that email is not in `users`, a verified **active admin** row is created. Leave both blank to skip seeding.

## Admin WhatsApp approval recipients

Comma-separated E.164-style mobiles (digits ok). Used after a registrant verifies their mobile OTP:

```bash
ADMIN_WHATSAPP_RECIPIENTS=9198XXXXXXXX,9197XXXXXXXX
# Alias also accepted:
# AUTH_APPROVAL_WHATSAPP_NUMBERS=9198XXXXXXXX

# Origin used in approve/reject links (fallback: WHATSAPP_WEBHOOK_URL origin)
APP_BASE_URL=https://wa.example.com
```

Approval links open `/approvals?token=…` and **require an admin session**. Possession of the link alone is not enough.

## WhatsApp Cloud API (OTP + approval messages)

OTP and approval notifications use the same Cloud credentials as the inbox (`WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`, …), sender number `+918477005566`. If Meta credentials are missing, registration returns `whatsapp_not_configured` and the account is not created until OTP can be delivered.

Credentials resolve from the Settings DB first, then `.env.local`. Empty / cleared Settings rows fall back to env.

For first-time mobiles (no open 24h WhatsApp session), free-form text OTP is blocked by Meta. Set an approved Authentication/Utility template:

```bash
WHATSAPP_OTP_TEMPLATE=your_otp_template_name
WHATSAPP_OTP_TEMPLATE_LANG=en
WHATSAPP_OTP_TEMPLATE_BUTTON=off   # or copy_code / url
```

OTPs and tokens are never written to logs.

## Registration flow

1. `/register` — name, mobile, email, password, role type (`member` / `admin`)  
2. WhatsApp OTP to the mobile (10 minutes, single-use, 60s resend cooldown, max 5 / 15 minutes)  
3. `/verify` — OTP creates `pending_approval` user with the requested role (not logged in)  
4. WhatsApp message to `ADMIN_WHATSAPP_RECIPIENTS` with approve/reject links (includes requested role)  
5. Admin signs in → `/approvals` → choose role → approve or reject (or use the link while signed in as admin)  
6. Only **active** users can sign in

Email is stored as contact/recovery detail only. Email OTP / email verification / email approval notifications are **not** used in auth.

## Deleted accounts

If a soft-deleted account already uses the same mobile or email, registration is blocked until an admin **permanently deletes** that user row on `/approvals`. Permanent purge removes only the `users` row (and related auth tokens/sessions). It does **not** cascade into `customer_master`, conversations, or messages.

## Recovery

- Forgot password: mobile → WhatsApp OTP → `/reset-password`  
- Forgot user id: mobile → WhatsApp OTP → reveal email in the UI (not emailed)

Public responses do not reveal whether an account exists until OTP verification succeeds where required.

## Session policy

| Item | Value |
| --- | --- |
| Cookie | HttpOnly `wa_admin` + `wa_csrf`, `SameSite=Strict`, `Secure` in production |
| Default TTL | 12 hours |
| Remember me | 30 days |
| Login throttle | 8 failures / 10 minutes per client IP hash |
| Login id | Email **or** mobile |
| Roles | `admin` · `member` |
| Profile | `/account` — photo, name, password (email/mobile/role read-only) |
| Access | `status=active` and `verified=1` |

Pending, rejected, and deleted users cannot obtain a session. Existing sessions drop if the user is no longer active.

## Public vs protected

- **Public pages:** `/login`, `/register`, `/verify`, `/forgot-password`, `/forgot-user-id`, `/reset-password`
- **Protected:** `/`, `/contacts`, `/settings`, `/account`, `/approvals`
- **Public APIs:** `/api/admin/session` (GET/POST login), `/api/auth/register|verify|resend|forgot-*|reset-password`, `/api/whatsapp/webhook`
- **Admin APIs:** `/api/auth/approvals`, `/api/admin/users/:id/purge`

## Titan SMTP

SMTP env vars may still be used for non-auth mail checks in Settings. They are **not** required for registration or recovery after this change.
