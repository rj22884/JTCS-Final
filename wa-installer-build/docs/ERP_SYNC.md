# ERP CustomerMaster sync

This WhatsApp app pulls **customer name + mobile only** from JTCS ERP (`app.jtcsxpert.com`) into the local `customer_master` / Contacts store.

## What the ERP sync token authorizes

- **Direction:** outbound from this app → ERP.
- **Header:** `X-WhatsApp-Sync-Token`
- **ERP endpoint:** `GET {ERP_BASE_URL}/api/crm/whatsapp/customer-directory`
- **Scope:** read-only CustomerMaster directory (name + mobile). It does **not** authorize Meta WhatsApp APIs, admin login, or contact delete.

The token is a shared client credential (same idea as storing a Meta access token locally). It must be sent in plaintext to ERP, so it is stored in the local `secrets` table (or env) and **never returned** by status APIs after save/generate. Generate shows the value **once**.

## Generate / configure / revoke (this app)

1. Sign in as **admin** on Settings (`/settings`).
2. Under **Customer Master sync**:
   - **Generate token** — creates a cryptographically random token, shows it once, stores it locally.
   - Or **paste + Save token** if ERP already issued a value.
   - **Revoke token** — clears the local DB value (env vars on the server are unchanged).
3. Copy the token into ERP environment as `WHATSAPP_CUSTOMER_SYNC_TOKEN` (same string).
4. Optional: `ERP_BASE_URL=https://app.jtcsxpert.com` on this app.
5. Click **Sync customers**.

Env aliases on this app:

| Variable | Purpose |
| --- | --- |
| `WHATSAPP_CUSTOMER_SYNC_TOKEN` | Preferred env name for the outbound token |
| `ERP_CUSTOMER_SYNC_TOKEN` | Accepted fallback |
| `ERP_BASE_URL` | HTTPS origin of ERP (default `https://app.jtcsxpert.com`) |

## Sync rules

- Rows **without a valid mobile** (after stripping spaces/punctuation; 8–15 digits) are **skipped**.
- Mobile uniqueness uses a normalized **phone key** (last 10 digits when longer, e.g. `91…`).
- Database enforces `UNIQUE(phone_key)`.
- Re-sync of the same ERP id is **idempotent** (create / update / unchanged counts).
- Same mobile on a **different** contact id is a **conflict** (reported, not merged/deleted).
- Manual contacts (`source=manual`) are not deleted by sync.
- Linked WhatsApp chats block contact **delete** until unlinked.

## Contacts UI

- Route: `/contacts` (desktop + mobile nav).
- Admin can add / edit / delete; list is searchable by name or mobile.
