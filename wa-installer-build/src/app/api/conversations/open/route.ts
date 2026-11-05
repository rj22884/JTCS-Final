import { requireSession } from "@/lib/admin";
import { ensureRequestTime, json } from "@/lib/http";
import { openDemoConversationForPhone } from "@/lib/store";
import { openConversationForPhone } from "@/lib/whatsapp/inbox";
import { mailboxReady } from "@/lib/whatsapp/status";
import type { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireSession(request);
  if (gate.error) return gate.error;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return json({ error: "invalid_json" }, 400);
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return json({ error: "invalid_body" }, 400);
  }
  const phone = (body as { phone?: unknown }).phone;
  const name = (body as { name?: unknown }).name;
  if (typeof phone !== "string" || !phone.trim()) {
    return json({ error: "invalid_phone", detail: "Phone is required." }, 400);
  }
  const label = typeof name === "string" ? name : null;
  const opened = mailboxReady()
    ? openConversationForPhone(phone, label)
    : openDemoConversationForPhone(phone, label);
  if (!opened) {
    return json({ error: "invalid_phone", detail: "Could not open a chat for this mobile number." }, 400);
  }
  return json({
    ok: true,
    conversationId: opened.id,
    conversation: opened.detail,
    summary: opened.summary,
    demo: !mailboxReady(),
  });
}
