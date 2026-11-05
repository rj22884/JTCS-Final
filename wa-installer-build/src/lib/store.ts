import "server-only";

import { sortSummaries } from "@/lib/filter-conversations";
import { sanitizeLabels as sanitizeLabelSet } from "@/lib/labels";
import { createSeedConversations, type StoredConversation } from "@/lib/mock-data";
import {
  CONVERSATION_STATUSES,
  type ActivityEntry,
  type ConversationDetail,
  type ConversationStatus,
  type ConversationSummary,
  type Label,
  type Message,
} from "@/lib/types";

type Store = {
  version: number;
  conversations: StoredConversation[];
};

const STORE_VERSION = 2;
const globalStore = globalThis as typeof globalThis & { __waCrmStore?: Store };

function store(): Store {
  if (!globalStore.__waCrmStore || globalStore.__waCrmStore.version !== STORE_VERSION) {
    globalStore.__waCrmStore = {
      version: STORE_VERSION,
      conversations: createSeedConversations(),
    };
  }
  return globalStore.__waCrmStore;
}

function lastMessage(conversation: StoredConversation) {
  return conversation.messages[conversation.messages.length - 1];
}

export function toSummary(conversation: StoredConversation): ConversationSummary {
  const latest = lastMessage(conversation);
  return {
    id: conversation.id,
    name: conversation.name,
    phone: conversation.phone,
    status: conversation.status,
    labels: [...conversation.labels],
    assignee: conversation.assignee,
    unreadCount: conversation.unreadCount,
    lastMessage: latest?.body ?? "",
    lastMessageAt: latest?.at ?? new Date(0).toISOString(),
    lastDirection: latest?.direction ?? "inbound",
    archived: Boolean(conversation.archived),
    pinned: Boolean(conversation.pinned),
    mutedUntil: conversation.mutedUntil ?? null,
    favourite: Boolean(conversation.favourite),
    blocked: Boolean(conversation.blocked),
  };
}

export function toDetail(conversation: StoredConversation): ConversationDetail {
  return {
    ...toSummary(conversation),
    notes: conversation.notes,
    messages: conversation.messages.map((message) => ({ ...message })),
    activity: conversation.activity.map((entry) => ({ ...entry })),
  };
}

export function listConversations(): ConversationSummary[] {
  return sortSummaries(store().conversations.map(toSummary));
}

export function getConversation(id: string) {
  return store().conversations.find((conversation) => conversation.id === id) ?? null;
}

/** Open or create a demo chat for Send message from Contacts (no WhatsApp send). */
export function openDemoConversationForPhone(phoneRaw: string, name: string | null = null) {
  const digits = phoneRaw.replace(/\D/g, "");
  if (digits.length < 8) return null;
  const id = `p-${digits}`;
  const phone = `+${digits}`;
  const existing = getConversation(id);
  if (existing) {
    return { id, detail: toDetail(existing), summary: toSummary(existing) };
  }
  const now = new Date().toISOString();
  const conversation: StoredConversation = {
    id,
    name: name?.trim() || phone,
    phone,
    status: "open",
    labels: [],
    assignee: "Unassigned",
    unreadCount: 0,
    notes: "",
    messages: [],
    activity: [{ id: `act-${crypto.randomUUID()}`, at: now, label: "Chat opened from Contacts (demo)" }],
  };
  store().conversations.unshift(conversation);
  return { id, detail: toDetail(conversation), summary: toSummary(conversation) };
}

function pushActivity(conversation: StoredConversation, label: string) {
  const entry: ActivityEntry = {
    id: `act-${crypto.randomUUID()}`,
    at: new Date().toISOString(),
    label,
  };
  conversation.activity.unshift(entry);
  conversation.activity = conversation.activity.slice(0, 50);
}

export function isConversationStatus(value: string): value is ConversationStatus {
  return (CONVERSATION_STATUSES as readonly string[]).includes(value);
}

export function sanitizeLabels(values: unknown): Label[] | null {
  const result = sanitizeLabelSet(values);
  return result.ok ? result.labels : null;
}

export function sanitizeLabelsDetailed(values: unknown) {
  return sanitizeLabelSet(values);
}

export function updateConversation(
  id: string,
  patch: {
    notes?: string;
    labels?: Label[];
    status?: ConversationStatus;
    markRead?: boolean;
    markUnread?: boolean;
    archived?: boolean;
    pinned?: boolean;
    favourite?: boolean;
    blocked?: boolean;
    mutedUntil?: string | null;
    clearChat?: boolean;
  },
) {
  const conversation = getConversation(id);
  if (!conversation) return null;

  if (patch.notes !== undefined && patch.notes !== conversation.notes) {
    conversation.notes = patch.notes;
    pushActivity(conversation, "Note updated in demo");
  }

  if (patch.labels !== undefined && patch.labels.join("|") !== conversation.labels.join("|")) {
    conversation.labels = patch.labels;
    pushActivity(conversation, "Labels updated in demo");
  }

  if (patch.status !== undefined && patch.status !== conversation.status) {
    conversation.status = patch.status;
    const statusLabel = patch.status[0].toUpperCase() + patch.status.slice(1);
    pushActivity(conversation, `Status set to ${statusLabel}`);
  }

  if (patch.markRead && conversation.unreadCount !== 0) {
    conversation.unreadCount = 0;
  }
  if (patch.markUnread) {
    conversation.unreadCount = Math.max(1, conversation.unreadCount);
  }
  if (patch.archived !== undefined) conversation.archived = patch.archived;
  if (patch.pinned !== undefined) conversation.pinned = patch.pinned;
  if (patch.favourite !== undefined) conversation.favourite = patch.favourite;
  if (patch.blocked !== undefined) {
    conversation.blocked = patch.blocked;
    if (patch.blocked) conversation.unreadCount = 0;
    pushActivity(conversation, patch.blocked ? "Contact blocked" : "Contact unblocked");
  }
  if (patch.mutedUntil !== undefined) conversation.mutedUntil = patch.mutedUntil;
  if (patch.clearChat) {
    conversation.messages = [];
    pushActivity(conversation, "Chat cleared in demo");
  }

  return toDetail(conversation);
}

export function deleteConversation(id: string) {
  const list = store().conversations;
  const index = list.findIndex((item) => item.id === id);
  if (index < 0) return false;
  list.splice(index, 1);
  return true;
}

export function addDemoMessage(id: string, body: string): { message: Message; detail: ConversationDetail } | null {
  const conversation = getConversation(id);
  if (!conversation) return null;

  const message: Message = {
    id: `m-${crypto.randomUUID()}`,
    direction: "outbound",
    body,
    at: new Date().toISOString(),
    delivery: "not_sent",
    kind: "text",
  };
  conversation.messages.push(message);
  conversation.messages = conversation.messages.slice(-500);
  pushActivity(conversation, "Message kept in demo. Not sent to WhatsApp.");
  return { message, detail: toDetail(conversation) };
}

export function deleteDemoMessage(id: string, messageId: string) {
  const conversation = getConversation(id);
  if (!conversation) return null;
  const before = conversation.messages.length;
  conversation.messages = conversation.messages.filter((message) => message.id !== messageId);
  if (conversation.messages.length === before) return null;
  pushActivity(conversation, "Message deleted for you in demo.");
  return conversation;
}
