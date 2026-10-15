import "server-only";

import { contactAvatarUrl } from "@/lib/contact-avatars";
import { resolveCustomerName } from "@/lib/customer-sync";
import { getDb } from "@/lib/db";
import { isMuted, sortSummaries } from "@/lib/filter-conversations";
import { syncContactLabelsForPhone } from "@/lib/contacts";
import { normalizeLabelList } from "@/lib/labels";
import { inferMessageKind } from "@/lib/message-actions";
import type {
  ConversationDetail,
  ConversationStatus,
  ConversationSummary,
  Label,
  Message,
  MessageAttachment,
  MessageKind,
} from "@/lib/types";
import { parseMessageReferral, parseStoredReferral } from "@/lib/whatsapp/referral";

export type InboundPushItem = {
  conversationId: string;
  title: string;
  body: string;
};

export type ApplyWhatsAppResult = {
  applied: number;
  notifications: InboundPushItem[];
};

type ConversationRow = {
  id: string;
  phone: string;
  name: string;
  status: ConversationStatus;
  labels: string;
  assignee: string;
  unread_count: number | bigint;
  notes: string;
  updated_at: string;
  avatar_path?: string | null;
  archived?: number | bigint | null;
  pinned?: number | bigint | null;
  muted_until?: string | null;
  favourite?: number | bigint | null;
  blocked?: number | bigint | null;
};

export type LiveConversationPatch = {
  notes?: string;
  labels?: Label[];
  status?: ConversationStatus;
  markRead?: boolean;
  markUnread?: boolean;
  archived?: boolean;
  pinned?: boolean;
  favourite?: boolean;
  blocked?: boolean;
  /** ISO timestamp, "always", or null to unmute. */
  mutedUntil?: string | null;
  clearChat?: boolean;
};

type MessageRow = {
  id: string;
  conversation_id: string;
  direction: "inbound" | "outbound";
  body: string;
  at: string;
  delivery: Message["delivery"];
  delivery_error?: string | null;
  kind?: string | null;
  filename?: string | null;
  media_id?: string | null;
  attachments_json?: string | null;
  referral_json?: string | null;
  deleted_for_me?: number | bigint | null;
};

export type OutboundMessageMeta = {
  kind?: MessageKind;
  filename?: string | null;
  mediaId?: string | null;
  attachments?: MessageAttachment[];
  deliveryError?: string | null;
};

function displayPhone(raw: string) {
  const digits = raw.replace(/\D/g, "");
  return digits ? `+${digits}` : raw.trim();
}

function conversationId(phone: string) {
  return `p-${phone.replace(/\D/g, "")}`;
}

function parseLabels(value: string): Label[] {
  try {
    return normalizeLabelList(JSON.parse(value) as unknown);
  } catch {
    return [];
  }
}

function parseAttachments(value: string | null | undefined): MessageAttachment[] | undefined {
  if (!value) return undefined;
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!Array.isArray(parsed) || parsed.length === 0) return undefined;
    return parsed.filter((item) => item && typeof item === "object") as MessageAttachment[];
  } catch {
    return undefined;
  }
}

function rowsFor(id: string) {
  return getDb()
    .prepare(
      `SELECT id, direction, body, at, delivery, delivery_error, kind, filename, media_id, attachments_json, referral_json, deleted_for_me
       FROM messages
       WHERE conversation_id = ? AND IFNULL(deleted_for_me, 0) = 0
       ORDER BY at ASC`,
    )
    .all(id) as MessageRow[];
}

function toMessage(row: MessageRow): Message {
  let attachments = parseAttachments(row.attachments_json);
  const kind = (row.kind as MessageKind | null) || inferMessageKind(row.body);
  // Recover media from columns when attachments_json was not stored (older rows).
  if ((!attachments || attachments.length === 0) && row.media_id) {
    const fileKind =
      kind === "image" || kind === "audio" || kind === "video" || kind === "document" ? kind : "document";
    attachments = [
      {
        id: `${row.id}-0`,
        kind: fileKind,
        filename: (row.filename && row.filename.trim()) || fileKind,
        mediaId: row.media_id,
        mimeType: null,
      },
    ];
  }
  return {
    id: row.id,
    direction: row.direction,
    body: row.body,
    at: row.at,
    delivery: row.delivery,
    deliveryError: row.delivery_error ?? null,
    kind,
    attachments,
    referral: parseStoredReferral(row.referral_json),
  };
}

export function isMetaSamplePhone(phone: string) {
  return phone.replace(/\D/g, "") === "16315551181";
}

function previewLabel(row: MessageRow | undefined) {
  if (!row) return "";
  const referral = parseStoredReferral(row.referral_json);
  if (referral?.headline || referral?.body) {
    const ad = referral.headline || referral.body || "Ad";
    const text = row.body.trim();
    if (text && text !== ad) return `${ad} · ${text}`;
    return ad;
  }
  const kind = (row.kind as MessageKind | null) || inferMessageKind(row.body);
  const name = row.filename?.trim();
  if (kind === "template" || /^Template:\s+/i.test(row.body.trim())) {
    const lines = row.body
      .split(/\n+/)
      .map((line) => line.trim())
      .filter(Boolean);
    const bodyLine = lines.find((line) => !/^Template:\s+/i.test(line) && !/^\[.+\]/.test(line));
    const title = lines[0]?.replace(/^Template:\s+/i, "") || "Template";
    return bodyLine ? `${title}: ${bodyLine}` : `Template: ${title}`;
  }
  if (kind === "document" || kind === "image" || kind === "audio" || kind === "video") {
    const body = row.body.trim();
    const isLabelOnly =
      !body ||
      /^\[(image|document|audio|video)\]$/i.test(body) ||
      /^(image|document|audio|video):\s+/i.test(body);
    if (name && isLabelOnly) {
      if (kind === "image") return "Photo";
      if (kind === "video") return "Video";
      if (kind === "audio") return "Audio";
      return name;
    }
    if (name && body && !isLabelOnly) return `${name} · ${body}`;
  }
  if (kind === "location") {
    const body = row.body.trim();
    if (!body || /^\[location\]$/i.test(body)) return "📍 Location";
    return body.startsWith("📍") ? body.split("\n")[0] : `📍 ${body.split("\n")[0]}`;
  }
  if (kind === "contact") {
    const body = row.body.trim();
    if (!body || /^\[contacts?\]$/i.test(body)) return "👤 Contact";
    return body.startsWith("👤") ? body.split("\n")[0] : `👤 ${body.split("\n")[0]}`;
  }
  return row.body;
}

function summaryFrom(row: ConversationRow, messages: MessageRow[]): ConversationSummary {
  const latest = messages[messages.length - 1];
  return {
    id: row.id,
    name: row.name,
    phone: row.phone,
    status: row.status,
    labels: parseLabels(row.labels),
    assignee: row.assignee,
    unreadCount: Number(row.unread_count),
    lastMessage: previewLabel(latest),
    lastMessageAt: latest?.at ?? row.updated_at,
    lastDirection: latest?.direction ?? "inbound",
    avatarUrl: contactAvatarUrl(row.avatar_path, row.id),
    sample: isMetaSamplePhone(row.phone),
    archived: Number(row.archived ?? 0) === 1,
    pinned: Number(row.pinned ?? 0) === 1,
    mutedUntil: row.muted_until ?? null,
    favourite: Number(row.favourite ?? 0) === 1,
    blocked: Number(row.blocked ?? 0) === 1,
  };
}

function readConversation(id: string) {
  return getDb().prepare("SELECT * FROM conversations WHERE id = ?").get(id) as ConversationRow | undefined;
}

export function listLiveConversations(): ConversationSummary[] {
  const rows = getDb().prepare("SELECT * FROM conversations").all() as ConversationRow[];
  return sortSummaries(rows.map((row) => summaryFrom(row, rowsFor(row.id))));
}

export function getLiveConversation(id: string): ConversationDetail | null {
  const row = readConversation(id);
  if (!row) return null;
  const messages = rowsFor(id);
  return {
    ...summaryFrom(row, messages),
    notes: row.notes,
    messages: messages.map(toMessage),
    activity: [],
  };
}

export function updateLiveConversation(id: string, patch: LiveConversationPatch) {
  const row = readConversation(id);
  if (!row) return null;
  const notes = patch.notes ?? row.notes;
  const labels = JSON.stringify(patch.labels ?? parseLabels(row.labels));
  const status = patch.status ?? row.status;
  let unread = Number(row.unread_count);
  if (patch.markRead) unread = 0;
  if (patch.markUnread) unread = Math.max(1, unread);
  const archived = patch.archived === undefined ? Number(row.archived ?? 0) : patch.archived ? 1 : 0;
  const pinned = patch.pinned === undefined ? Number(row.pinned ?? 0) : patch.pinned ? 1 : 0;
  const favourite = patch.favourite === undefined ? Number(row.favourite ?? 0) : patch.favourite ? 1 : 0;
  const blocked = patch.blocked === undefined ? Number(row.blocked ?? 0) : patch.blocked ? 1 : 0;
  // Blocking clears unread so the chat does not keep a badge while silenced.
  if (patch.blocked === true) unread = 0;
  const mutedUntil = patch.mutedUntil === undefined ? row.muted_until ?? null : patch.mutedUntil;
  const now = new Date().toISOString();
  getDb()
    .prepare(
      `UPDATE conversations
       SET notes = ?, labels = ?, status = ?, unread_count = ?, archived = ?, pinned = ?, favourite = ?, blocked = ?, muted_until = ?, updated_at = ?
       WHERE id = ?`,
    )
    .run(notes, labels, status, unread, archived, pinned, favourite, blocked, mutedUntil, now, id);

  if (patch.clearChat) {
    getDb().prepare("UPDATE messages SET deleted_for_me = 1 WHERE conversation_id = ?").run(id);
  }

  if (patch.labels) {
    const phone = (readConversation(id) as ConversationRow | undefined)?.phone ?? "";
    syncContactLabelsForPhone(phone.replace(/\D/g, ""), patch.labels);
  }
  const detail = getLiveConversation(id);
  if (!detail) return null;
  return { detail, summary: summaryFrom(readConversation(id) as ConversationRow, rowsFor(id)) };
}

export function deleteLiveConversation(id: string) {
  const row = readConversation(id);
  if (!row) return false;
  const db = getDb();
  db.prepare("DELETE FROM messages WHERE conversation_id = ?").run(id);
  db.prepare("DELETE FROM conversations WHERE id = ?").run(id);
  return true;
}

export function muteUntilFromDuration(duration: "8h" | "1w" | "always") {
  if (duration === "always") return "always";
  const ms = duration === "8h" ? 8 * 60 * 60 * 1000 : 7 * 24 * 60 * 60 * 1000;
  return new Date(Date.now() + ms).toISOString();
}

function ensureConversation(phoneRaw: string, name: string | null) {
  const phone = displayPhone(phoneRaw);
  const id = conversationId(phone);
  const existing = readConversation(id);
  const now = new Date().toISOString();
  const resolved = resolveCustomerName(phone, name) || name?.trim() || phone;
  if (!existing) {
    getDb()
      .prepare(
        `INSERT INTO conversations (id, phone, name, status, labels, assignee, unread_count, notes, updated_at)
         VALUES (?, ?, ?, 'open', '[]', 'Unassigned', 0, '', ?)`,
      )
      .run(id, phone, resolved, now);
  } else if (resolved && (existing.name === existing.phone || existing.name === phone)) {
    getDb().prepare("UPDATE conversations SET name = ?, updated_at = ? WHERE id = ?").run(resolved, now, id);
  }
  return id;
}

/** Open or create a chat thread for a contact mobile without sending a message. */
export function openConversationForPhone(phoneRaw: string, name: string | null = null) {
  const digits = phoneRaw.replace(/\D/g, "");
  if (digits.length < 8) return null;
  const id = ensureConversation(digits, name);
  const detail = getLiveConversation(id);
  if (!detail) return null;
  return {
    id,
    detail,
    summary: summaryFrom(readConversation(id) as ConversationRow, rowsFor(id)),
  };
}

function extractMediaMeta(message: Record<string, unknown>) {
  const kindRaw = typeof message.type === "string" ? message.type : "message";
  const media = message[kindRaw];
  let mediaId: string | null = null;
  let filename: string | null = null;
  let mimeType: string | null = null;
  if (media && typeof media === "object" && !Array.isArray(media)) {
    const id = (media as { id?: unknown }).id;
    const name = (media as { filename?: unknown }).filename;
    const mime = (media as { mime_type?: unknown }).mime_type;
    if (typeof id === "string") mediaId = id;
    if (typeof name === "string") filename = name;
    if (typeof mime === "string") mimeType = mime;
  }
  // Button / interactive / reaction replies are stored as normal text bubbles.
  const kind = (
    ["image", "document", "audio", "video", "text", "template", "location"].includes(kindRaw)
      ? kindRaw
      : kindRaw === "contacts" || kindRaw === "contact"
        ? "contact"
        : kindRaw === "button" || kindRaw === "interactive" || kindRaw === "reaction"
          ? "text"
          : inferMessageKind(messageBody(message))
  ) as MessageKind;
  const mediaKinds = kind === "image" || kind === "document" || kind === "audio" || kind === "video";
  const attachments =
    mediaId && mediaKinds
      ? [
          {
            id: `${typeof message.id === "string" ? message.id : "media"}-0`,
            kind: kind as MessageAttachment["kind"],
            filename: filename || kind,
            mediaId,
            mimeType,
          },
        ]
      : undefined;
  return { kind, filename: mediaKinds ? filename : null, mediaId: mediaKinds ? mediaId : null, attachments };
}

function trimmedString(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/** Human-readable body for Cloud API inbound messages (text, media, template button clicks, etc.). */
function messageBody(message: Record<string, unknown>) {
  const text = message.text as { body?: unknown } | undefined;
  if (message.type === "text" && typeof text?.body === "string" && text.body.trim()) return text.body.trim();

  // Template quick-reply / URL button tap (type: "button")
  if (message.type === "button") {
    const button = message.button as { text?: unknown; payload?: unknown } | undefined;
    const label = trimmedString(button?.text) || trimmedString(button?.payload);
    if (label) return label;
  }

  // Interactive reply (button_reply / list_reply / nfm_reply)
  if (message.type === "interactive") {
    const interactive = message.interactive as
      | {
          type?: unknown;
          button_reply?: { title?: unknown; id?: unknown };
          list_reply?: { title?: unknown; description?: unknown; id?: unknown };
          nfm_reply?: { body?: unknown; name?: unknown };
        }
      | undefined;
    const buttonTitle = trimmedString(interactive?.button_reply?.title);
    if (buttonTitle) return buttonTitle;
    const listTitle = trimmedString(interactive?.list_reply?.title);
    if (listTitle) {
      const description = trimmedString(interactive?.list_reply?.description);
      return description ? `${listTitle} — ${description}` : listTitle;
    }
    const nfmBody = trimmedString(interactive?.nfm_reply?.body);
    if (nfmBody) return nfmBody;
  }

  // Emoji reaction on a prior message
  if (message.type === "reaction") {
    const reaction = message.reaction as { emoji?: unknown } | undefined;
    const emoji = trimmedString(reaction?.emoji);
    if (emoji) return emoji;
  }

  // Shared contact card(s)
  if (message.type === "contacts") {
    const cards = Array.isArray(message.contacts) ? message.contacts : [];
    const lines: string[] = [];
    for (const card of cards) {
      if (!card || typeof card !== "object") continue;
      const nameObj = (card as { name?: { formatted_name?: unknown; first_name?: unknown } }).name;
      const formatted =
        trimmedString(nameObj?.formatted_name) ||
        trimmedString(nameObj?.first_name) ||
        "Contact";
      const phones = Array.isArray((card as { phones?: unknown }).phones)
        ? ((card as { phones: { phone?: unknown; wa_id?: unknown }[] }).phones
            .map((item) => trimmedString(item?.phone) || trimmedString(item?.wa_id))
            .filter(Boolean) as string[])
        : [];
      lines.push(phones.length ? `👤 ${formatted} · ${phones.join(", ")}` : `👤 ${formatted}`);
    }
    if (lines.length) return lines.join("\n");
    return "👤 Contact";
  }

  // Location pin
  if (message.type === "location") {
    const location = message.location as
      | { latitude?: unknown; longitude?: unknown; name?: unknown; address?: unknown }
      | undefined;
    const name = trimmedString(location?.name);
    const address = trimmedString(location?.address);
    const lat = typeof location?.latitude === "number" ? location.latitude : Number(location?.latitude);
    const lng = typeof location?.longitude === "number" ? location.longitude : Number(location?.longitude);
    const coords =
      Number.isFinite(lat) && Number.isFinite(lng) ? `${lat.toFixed(5)}, ${lng.toFixed(5)}` : null;
    if (name && address) return `📍 ${name}\n${address}`;
    if (name) return coords ? `📍 ${name}\n${coords}` : `📍 ${name}`;
    if (address) return `📍 ${address}`;
    if (coords) return `📍 ${coords}`;
    return "📍 Location";
  }

  const kind = typeof message.type === "string" ? message.type : "message";
  const media = message[kind];
  if (media && typeof media === "object" && !Array.isArray(media)) {
    const caption = (media as { caption?: unknown }).caption;
    const filename = (media as { filename?: unknown }).filename;
    // Some payloads put reply text on `.text` even when type is not "text"
    const nestedText = trimmedString((media as { text?: unknown }).text);
    if (nestedText) return nestedText;
    if (typeof caption === "string" && caption.trim()) return caption.trim();
    if (typeof filename === "string" && filename.trim()) return `${kind}: ${filename.trim()}`;
  }
  return `[${kind}]`;
}

function messageTime(message: Record<string, unknown>) {
  const stamp = typeof message.timestamp === "string" ? Number(message.timestamp) : Number.NaN;
  if (Number.isFinite(stamp) && stamp > 0) return new Date(stamp * 1000).toISOString();
  return new Date().toISOString();
}

export function applyWhatsAppPayload(payload: unknown): ApplyWhatsAppResult {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { applied: 0, notifications: [] };
  }
  const entries = (payload as { entry?: unknown }).entry;
  if (!Array.isArray(entries)) return { applied: 0, notifications: [] };
  let applied = 0;
  const notifications: InboundPushItem[] = [];
  const db = getDb();
  const insertMessage = db.prepare(
    `INSERT OR IGNORE INTO messages
      (id, conversation_id, direction, body, at, delivery, wa_id, kind, filename, media_id, attachments_json, referral_json, deleted_for_me)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)`,
  );
  const bumpUnread = db.prepare(
    "UPDATE conversations SET unread_count = unread_count + 1, updated_at = ? WHERE id = ?",
  );
  const markDelivery = db.prepare("UPDATE messages SET delivery = ? WHERE id = ? OR wa_id = ?");

  for (const entry of entries) {
    const changes = (entry as { changes?: unknown }).changes;
    if (!Array.isArray(changes)) continue;
    for (const change of changes) {
      const value = (change as { value?: unknown }).value as
        | {
            contacts?: { wa_id?: string; profile?: { name?: string } }[];
            messages?: Record<string, unknown>[];
            statuses?: Record<string, unknown>[];
          }
        | undefined;
      if (!value) continue;
      const names = new Map<string, string>();
      for (const contact of value.contacts ?? []) {
        if (contact.wa_id && contact.profile?.name) names.set(contact.wa_id, contact.profile.name);
      }
      for (const message of value.messages ?? []) {
        const id = typeof message.id === "string" ? message.id : "";
        const from = typeof message.from === "string" ? message.from : "";
        if (!id || !from) continue;
        const conversation = ensureConversation(from, names.get(from) ?? null);
        const existing = readConversation(conversation);
        // Blocked contacts: drop inbound entirely (no store, unread, or push).
        if (existing && Number(existing.blocked ?? 0) === 1) continue;
        const at = messageTime(message);
        const body = messageBody(message).slice(0, 4096);
        const meta = extractMediaMeta(message);
        const referral = parseMessageReferral(message);
        const result = insertMessage.run(
          id,
          conversation,
          "inbound",
          body,
          at,
          null,
          id,
          meta.kind,
          meta.filename,
          meta.mediaId,
          meta.attachments ? JSON.stringify(meta.attachments) : null,
          referral ? JSON.stringify(referral) : null,
        );
        if (result.changes > 0) {
          bumpUnread.run(at, conversation);
          applied += 1;
          const row = readConversation(conversation);
          if (row && !isMuted(row.muted_until ?? null)) {
            notifications.push({
              conversationId: conversation,
              title: row.name || "WhatsApp",
              body: body || "New WhatsApp message",
            });
          }
        }
      }
      for (const status of value.statuses ?? []) {
        const id = typeof status.id === "string" ? status.id : "";
        const name = typeof status.status === "string" ? status.status : "";
        if (!id || !["sent", "delivered", "read", "failed"].includes(name)) continue;
        markDelivery.run(name, id, id);
        if (name === "failed") {
          const errors = Array.isArray((status as { errors?: unknown }).errors)
            ? ((status as {
                errors: {
                  code?: unknown;
                  title?: unknown;
                  message?: unknown;
                  error_data?: { details?: unknown };
                }[];
              }).errors)
            : [];
          const first = errors[0];
          const code = typeof first?.code === "number" ? first.code : null;
          let detail =
            trimmedString(first?.error_data?.details) ||
            trimmedString(first?.message) ||
            trimmedString(first?.title) ||
            "Meta reported delivery failed.";
          if (
            code === 131047 ||
            code === 131026 ||
            /re-engagement|outside.*allowed window|24.?hour|customer care window/i.test(detail)
          ) {
            detail =
              "Meta blocked this free-form text: the 24-hour customer care window is closed. Ask the customer to message first, or send an approved template.";
          }
          getDb()
            .prepare("UPDATE messages SET delivery_error = ? WHERE id = ? OR wa_id = ?")
            .run(detail.slice(0, 500), id, id);
        }
      }
    }
  }
  return { applied, notifications };
}

export function addLiveOutbound(
  conversationIdValue: string,
  body: string,
  waId: string | null,
  delivery: Message["delivery"],
  meta: OutboundMessageMeta = {},
) {
  const row = readConversation(conversationIdValue);
  if (!row) return null;
  const at = new Date().toISOString();
  const id = waId || `local-${crypto.randomUUID()}`;
  const kind = meta.kind || inferMessageKind(body);
  getDb()
    .prepare(
      `INSERT OR REPLACE INTO messages
        (id, conversation_id, direction, body, at, delivery, delivery_error, wa_id, kind, filename, media_id, attachments_json, referral_json, deleted_for_me)
       VALUES (?, ?, 'outbound', ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0)`,
    )
    .run(
      id,
      conversationIdValue,
      body,
      at,
      delivery,
      delivery === "failed" ? (meta.deliveryError ?? "Meta did not accept this message.").slice(0, 500) : null,
      waId,
      kind,
      meta.filename ?? null,
      meta.mediaId ?? null,
      meta.attachments ? JSON.stringify(meta.attachments) : null,
    );
  getDb().prepare("UPDATE conversations SET updated_at = ? WHERE id = ?").run(at, conversationIdValue);
  const detail = getLiveConversation(conversationIdValue);
  const message = detail?.messages.find((item) => item.id === id) ?? null;
  if (!detail || !message) return null;
  return { message, detail, summary: summaryFrom(readConversation(conversationIdValue) as ConversationRow, rowsFor(conversationIdValue)) };
}

export function getLiveMessage(conversationIdValue: string, messageId: string) {
  const row = getDb()
    .prepare(
      `SELECT id, direction, body, at, delivery, kind, filename, media_id, attachments_json, referral_json, deleted_for_me
       FROM messages
       WHERE conversation_id = ? AND id = ? AND IFNULL(deleted_for_me, 0) = 0`,
    )
    .get(conversationIdValue, messageId) as MessageRow | undefined;
  return row ? toMessage(row) : null;
}

export function deleteLiveMessageForMe(conversationIdValue: string, messageId: string) {
  if (!readConversation(conversationIdValue)) return null;
  const result = getDb()
    .prepare("UPDATE messages SET deleted_for_me = 1 WHERE conversation_id = ? AND id = ? AND IFNULL(deleted_for_me, 0) = 0")
    .run(conversationIdValue, messageId);
  if (result.changes === 0) return null;
  getDb().prepare("UPDATE conversations SET updated_at = ? WHERE id = ?").run(new Date().toISOString(), conversationIdValue);
  const detail = getLiveConversation(conversationIdValue);
  if (!detail) return null;
  return { detail, summary: summaryFrom(readConversation(conversationIdValue) as ConversationRow, rowsFor(conversationIdValue)) };
}
