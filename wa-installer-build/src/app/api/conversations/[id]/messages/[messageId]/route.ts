import { requireUser } from "@/lib/admin";
import { DELETE_FOR_EVERYONE_REASON, DELETE_FOR_EVERYONE_SUPPORTED } from "@/lib/message-actions";
import { ensureRequestTime, json } from "@/lib/http";
import { deleteDemoMessage, getConversation, toDetail, toSummary } from "@/lib/store";
import { deleteLiveMessageForMe, getLiveConversation } from "@/lib/whatsapp/inbox";
import { mailboxReady } from "@/lib/whatsapp/status";
import type { NextRequest } from "next/server";

export async function DELETE(request: NextRequest, context: { params: Promise<{ id: string; messageId: string }> }) {
  await ensureRequestTime();
  const gate = requireUser(request);
  if (gate.error) return gate.error;
  const { id, messageId } = await context.params;

  let body: unknown = {};
  try {
    const text = await request.text();
    body = text ? JSON.parse(text) : {};
  } catch {
    return json({ error: "invalid_json" }, 400);
  }
  const scope = body && typeof body === "object" && !Array.isArray(body) ? (body as { scope?: unknown }).scope : "me";
  if (scope !== "me" && scope !== "everyone") return json({ error: "invalid_scope" }, 400);

  if (scope === "everyone") {
    return json(
      {
        error: "unsupported",
        supported: DELETE_FOR_EVERYONE_SUPPORTED,
        detail: DELETE_FOR_EVERYONE_REASON,
      },
      501,
    );
  }

  if (mailboxReady()) {
    if (!getLiveConversation(id)) return json({ error: "not_found" }, 404);
    const deleted = deleteLiveMessageForMe(id, messageId);
    if (!deleted) return json({ error: "not_found", detail: "Message was not found in this chat." }, 404);
    return json({ ok: true, scope: "me", conversation: deleted.detail, summary: deleted.summary });
  }

  const conversation = getConversation(id);
  if (!conversation) return json({ error: "not_found" }, 404);
  const deleted = deleteDemoMessage(id, messageId);
  if (!deleted) return json({ error: "not_found", detail: "Message was not found in this chat." }, 404);
  return json({
    ok: true,
    scope: "me",
    conversation: toDetail(deleted),
    summary: toSummary(deleted),
  });
}
