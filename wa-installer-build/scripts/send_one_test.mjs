import { DatabaseSync } from "node:sqlite";

const to = (process.argv[2] || "").replace(/\D/g, "");
const body = process.argv[3] || "";
const dbPath = process.argv[4] || "data/app.sqlite";

function fail(detail) {
  console.log(JSON.stringify({ ok: false, detail }));
  process.exit(1);
}

if (!/^\d{8,15}$/.test(to) || !body.trim() || body.length > 1000) {
  fail("The recipient or message text is not valid. Nothing was sent.");
}

const db = new DatabaseSync(dbPath);
const read = db.prepare("SELECT value, cleared FROM secrets WHERE key = ?");
function secret(key) {
  const row = read.get(key);
  if (!row || Number(row.cleared) === 1) return "";
  return typeof row.value === "string" ? row.value.trim() : "";
}

const phoneNumberId = secret("phoneNumberId");
const accessToken = secret("accessToken");
if (!/^\d{5,32}$/.test(phoneNumberId) || accessToken.length < 20) {
  fail("The phone number ID or access token is missing. Nothing was sent.");
}

const url = new URL(`https://graph.facebook.com/v21.0/${phoneNumberId}/messages`);
let response;
try {
  response = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      messaging_product: "whatsapp",
      recipient_type: "individual",
      to,
      type: "text",
      text: { body },
    }),
    signal: AbortSignal.timeout(15000),
  });
} catch {
  fail("Meta did not answer in time. The message may not have been sent.");
}

const text = await response.text();
const safe = text.split(accessToken).join("[redacted]");
let messageId = "";
try {
  const parsed = JSON.parse(safe);
  messageId = parsed.messages?.[0]?.id || "";
  if (!response.ok) {
    const detail = parsed.error?.message?.replace(/\s+/g, " ").trim().slice(0, 180) || "Meta rejected the message.";
    fail(detail);
  }
} catch {
  fail("Meta rejected the message.");
}

if (!messageId) fail("Meta did not return a message id.");
console.log(JSON.stringify({ ok: true, to, messageId }));
