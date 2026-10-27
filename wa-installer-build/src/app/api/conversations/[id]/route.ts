import { requireSession, requireUser } from "@/lib/admin";
import { ensureRequestTime, json } from "@/lib/http";
import {
  deleteConversation,
  getConversation,
  isConversationStatus,
  sanitizeLabelsDetailed,
  toDetail,
  updateConversation,
} from "@/lib/store";
import {
  deleteLiveConversation,
  getLiveConversation,
  muteUntilFromDuration,
  updateLiveConversation,
  type LiveConversationPatch,
} from "@/lib/whatsapp/inbox";
import { mailboxReady } from "@/lib/whatsapp/status";
import type { ConversationStatus, Label, MuteDuration } from "@/lib/types";
import type { NextRequest } from "next/server";

const NOTES_LIMIT = 4000;
const MUTE_DURATIONS = new Set<MuteDuration>(["8h", "1w", "always"]);

export async function GET(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  await ensureRequestTime();
  const gate = requireSession(request);
  if (gate.error) return gate.error;
  const { id } = await context.params;
  if (mailboxReady()) {
    const live = getLiveConversation(id);
    if (!live) return json({ error: "not_found" }, 404);
    return json({ conversation: live, demo: false });
  }
  const conversation = getConversation(id);
  if (!conversation) return json({ error: "not_found" }, 404);
  return json({ conversation: toDetail(conversation), demo: true });
}

export async function PATCH(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  await ensureRequestTime();
  const gate = requireUser(request);
  if (gate.error) return gate.error;
  const { id } = await context.params;
  const live = mailboxReady();
  if (live ? !getLiveConversation(id) : !getConversation(id)) return json({ error: "not_found" }, 404);

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return json({ error: "invalid_json" }, 400);
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return json({ error: "invalid_body" }, 400);
  }

  const record = body as Record<string, unknown>;
  const patch: LiveConversationPatch = {};

  if ("notes" in record) {
    if (typeof record.notes !== "string" || record.notes.length > NOTES_LIMIT) {
      return json({ error: "invalid_notes" }, 400);
    }
    patch.notes = record.notes;
  }

  if ("labels" in record) {
    const labelsResult = sanitizeLabelsDetailed(record.labels);
    if (!labelsResult.ok) {
      return json({ error: "invalid_labels", detail: labelsResult.error }, 400);
    }
    patch.labels = labelsResult.labels;
  }

  if ("status" in record) {
    if (typeof record.status !== "string" || !isConversationStatus(record.status)) {
      return json({ error: "invalid_status" }, 400);
    }
    patch.status = record.status as ConversationStatus;
  }

  if ("markRead" in record) {
    if (typeof record.markRead !== "boolean") return json({ error: "invalid_mark_read" }, 400);
    patch.markRead = record.markRead;
  }
  if ("markUnread" in record) {
    if (typeof record.markUnread !== "boolean") return json({ error: "invalid_mark_unread" }, 400);
    patch.markUnread = record.markUnread;
  }
  if ("archived" in record) {
    if (typeof record.archived !== "boolean") return json({ error: "invalid_archived" }, 400);
    patch.archived = record.archived;
  }
  if ("pinned" in record) {
    if (typeof record.pinned !== "boolean") return json({ error: "invalid_pinned" }, 400);
    patch.pinned = record.pinned;
  }
  if ("favourite" in record) {
    if (typeof record.favourite !== "boolean") return json({ error: "invalid_favourite" }, 400);
    patch.favourite = record.favourite;
  }
  if ("blocked" in record) {
    if (typeof record.blocked !== "boolean") return json({ error: "invalid_blocked" }, 400);
    patch.blocked = record.blocked;
  }
  if ("clearChat" in record) {
    if (record.clearChat !== true) return json({ error: "invalid_clear_chat" }, 400);
    patch.clearChat = true;
  }
  if ("mute" in record) {
    if (record.mute === null) {
      patch.mutedUntil = null;
    } else if (typeof record.mute === "string" && MUTE_DURATIONS.has(record.mute as MuteDuration)) {
      patch.mutedUntil = muteUntilFromDuration(record.mute as MuteDuration);
    } else {
      return json({ error: "invalid_mute", detail: "Use 8h, 1w, always, or null." }, 400);
    }
  }

  if (
    !("notes" in patch) &&
    !("labels" in patch) &&
    !("status" in patch) &&
    !("markRead" in patch) &&
    !("markUnread" in patch) &&
    !("archived" in patch) &&
    !("pinned" in patch) &&
    !("favourite" in patch) &&
    !("blocked" in patch) &&
    !("mutedUntil" in patch) &&
    !("clearChat" in patch)
  ) {
    return json({ error: "empty_patch" }, 400);
  }

  if (live) {
    const updated = updateLiveConversation(id, patch);
    if (!updated) return json({ error: "not_found" }, 404);
    return json({ conversation: updated.detail, summary: updated.summary, demo: false });
  }

  const conversation = updateConversation(id, {
    notes: patch.notes,
    labels: patch.labels as Label[] | undefined,
    status: patch.status,
    markRead: patch.markRead,
    markUnread: patch.markUnread,
    archived: patch.archived,
    pinned: patch.pinned,
    favourite: patch.favourite,
    blocked: patch.blocked,
    mutedUntil: patch.mutedUntil,
    clearChat: patch.clearChat,
  });
  if (!conversation) return json({ error: "not_found" }, 404);
  return json({
    conversation,
    summary: {
      id: conversation.id,
      name: conversation.name,
      phone: conversation.phone,
      status: conversation.status,
      labels: conversation.labels,
      assignee: conversation.assignee,
      unreadCount: conversation.unreadCount,
      lastMessage: conversation.lastMessage,
      lastMessageAt: conversation.lastMessageAt,
      lastDirection: conversation.lastDirection,
      archived: conversation.archived,
      pinned: conversation.pinned,
      mutedUntil: conversation.mutedUntil,
      favourite: conversation.favourite,
      blocked: conversation.blocked,
    },
    demo: true,
  });
}

export async function DELETE(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  await ensureRequestTime();
  const gate = requireUser(request);
  if (gate.error) return gate.error;
  const { id } = await context.params;
  const live = mailboxReady();
  const removed = live ? deleteLiveConversation(id) : deleteConversation(id);
  if (!removed) return json({ error: "not_found" }, 404);
  return json({ ok: true, deleted: true, demo: !live });
}
