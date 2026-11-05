import { requireUser } from "@/lib/admin";
import { sendCloudTemplate } from "@/lib/whatsapp/client";
import { ensureRequestTime, json } from "@/lib/http";
import { resolveSecret } from "@/lib/secrets";
import { addLiveOutbound, getLiveConversation } from "@/lib/whatsapp/inbox";
import { mailboxReady } from "@/lib/whatsapp/status";
import type { NextRequest } from "next/server";

export async function POST(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  await ensureRequestTime();
  const gate = requireUser(request);
  if (gate.error) return gate.error;
  const { id } = await context.params;

  if (!mailboxReady()) {
    return json({ error: "not_connected", detail: "Template messages need a connected WhatsApp Business account." }, 409);
  }

  const conversation = getLiveConversation(id);
  if (!conversation) return json({ error: "not_found" }, 404);
  if (conversation.blocked) {
    return json({ error: "blocked", detail: "This contact is blocked. Unblock to send messages." }, 403);
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return json({ error: "invalid_json" }, 400);
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return json({ error: "invalid_body" }, 400);
  }
  const name = (body as { name?: unknown }).name;
  const language = (body as { language?: unknown }).language;
  const previewRaw = (body as { preview?: unknown }).preview;
  if (typeof name !== "string" || typeof language !== "string") {
    return json({ error: "invalid_template", detail: "Choose an approved template." }, 400);
  }
  const preview = typeof previewRaw === "string" && previewRaw.trim() ? previewRaw.trim().slice(0, 4096) : "";

  const phoneNumberId = resolveSecret("phoneNumberId");
  const accessToken = resolveSecret("accessToken");
  if (!phoneNumberId || !accessToken) {
    return json({ error: "not_connected", detail: "The phone number is not ready. Nothing was sent." }, 409);
  }

  const result = await sendCloudTemplate({
    to: conversation.phone,
    phoneNumberId,
    accessToken,
    graphApiVersion: resolveSecret("graphApiVersion"),
    name,
    language,
    preview: preview || `Template: ${name.trim()}`,
  });
  const inboxBody = result.ok ? result.body : preview || `Template: ${name.trim()}`;
  const saved = addLiveOutbound(id, inboxBody, result.ok ? result.messageId : null, result.ok ? "sent" : "failed", {
    kind: "template",
  });
  if (!saved) return json({ error: "not_found" }, 404);
  return json({
    demo: false,
    delivery: result.ok ? "sent" : "failed",
    detail: result.ok ? "Meta accepted the message." : result.detail,
    message: saved.message,
    conversation: saved.detail,
    summary: saved.summary,
  });
}
