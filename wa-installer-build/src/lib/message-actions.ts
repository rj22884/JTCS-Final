import { normalizeAttachmentFile } from "@/lib/clipboard-files";
import type { Message, MessageAttachment, MessageKind } from "@/lib/types";

export const DELETE_FOR_EVERYONE_SUPPORTED = false;
export const DELETE_FOR_EVERYONE_REASON =
  "WhatsApp Cloud API does not support deleting a sent message for everyone. Only Delete for me is available in this inbox.";

export const FORWARD_CLOUD_SUPPORTED = false;
export const FORWARD_CLOUD_REASON =
  "WhatsApp Cloud API has no forward endpoint. Forward copies the content so you can paste it into another chat.";

export type MessageActionId =
  | "reply"
  | "forward"
  | "copy"
  | "view"
  | "save"
  | "save_all"
  | "delete_for_me"
  | "delete_for_everyone";

export type MessageAction = {
  id: MessageActionId;
  label: string;
  enabled: boolean;
  detail?: string;
};

export function isAttachmentMessage(message: Message) {
  if (message.attachments && message.attachments.length > 0) return true;
  const kind = message.kind ?? inferMessageKind(message.body);
  return kind === "image" || kind === "document" || kind === "audio" || kind === "video";
}

export function inferMessageKind(body: string): MessageKind {
  const trimmed = body.trim();
  if (/^📍\s*/.test(trimmed) || /^Location:/i.test(trimmed)) return "location";
  if (/^👤\s*/.test(trimmed) || /^Contact:/i.test(trimmed)) return "contact";
  const bracket = trimmed.match(/^\[([a-z_]+)\]$/i);
  if (bracket) {
    const kind = bracket[1].toLowerCase();
    if (
      kind === "image" ||
      kind === "document" ||
      kind === "audio" ||
      kind === "video" ||
      kind === "template" ||
      kind === "location" ||
      kind === "contacts" ||
      kind === "contact"
    ) {
      if (kind === "contacts") return "contact";
      return kind as MessageKind;
    }
    return "unknown";
  }
  const prefix = trimmed.match(/^(image|document|audio|video|template|location|contact):\s+/i);
  if (prefix) return prefix[1].toLowerCase() as MessageKind;
  return "text";
}

export function messageAttachments(message: Message): MessageAttachment[] {
  if (message.attachments && message.attachments.length > 0) return message.attachments;
  if (!isAttachmentMessage(message)) return [];
  const kind = message.kind ?? inferMessageKind(message.body);
  const filename =
    message.body.match(/^(?:image|document|audio|video):\s+(.+)$/i)?.[1]?.trim() ||
    (kind !== "text" && kind !== "unknown" ? `${kind}` : "attachment");
  const attachmentKind =
    kind === "image" || kind === "document" || kind === "audio" || kind === "video" ? kind : "document";
  return [
    {
      id: `${message.id}-0`,
      kind: attachmentKind,
      filename,
      mediaId: null,
      mimeType: null,
    },
  ];
}

/** Caption text to show under a file card — skips redundant document:/[document] labels. */
export function attachmentCaptionText(message: Message) {
  const body = message.body.trim();
  if (!body) return "";
  if (/^\[(image|document|audio|video|template)\]$/i.test(body)) return "";
  const prefixed = body.match(/^(?:image|document|audio|video|template):\s+(.+)$/i);
  if (prefixed) {
    const label = prefixed[1].trim();
    const attachments = messageAttachments(message);
    if (attachments.some((item) => item.filename === label || item.filename === body)) return "";
    return label;
  }
  return body;
}

export function copyTextForMessage(message: Message) {
  const attachments = messageAttachments(message);
  const caption = attachmentCaptionText(message);
  if (attachments.length > 0) {
    const names = attachments.map((item) => item.filename).join(", ");
    return caption ? `${names}\n${caption}` : names;
  }
  return message.body;
}

export function actionsForMessage(message: Message): MessageAction[] {
  const attachment = isAttachmentMessage(message);
  const attachments = messageAttachments(message);
  const canMedia = attachments.some((item) => Boolean(item.mediaId));
  const actions: MessageAction[] = [
    { id: "reply", label: "Reply", enabled: true },
    {
      id: "forward",
      label: "Forward",
      enabled: true,
      detail: FORWARD_CLOUD_REASON,
    },
    {
      id: "copy",
      label: "Copy",
      enabled: Boolean(copyTextForMessage(message).trim()),
    },
  ];

  if (attachment) {
    actions.push({
      id: "view",
      label: "View / Open",
      enabled: canMedia || Boolean(message.body.trim()),
      detail: canMedia ? undefined : "Open needs a Meta media id from WhatsApp.",
    });
    actions.push({
      id: "save",
      label: "Save / Download",
      enabled: canMedia,
      detail: canMedia ? undefined : "Download needs a Meta media id from WhatsApp.",
    });
    if (attachments.length > 1) {
      actions.push({
        id: "save_all",
        label: "Save all",
        enabled: attachments.every((item) => Boolean(item.mediaId)),
        detail: attachments.every((item) => Boolean(item.mediaId))
          ? undefined
          : "Save all needs media ids for every file.",
      });
    }
  }

  actions.push({ id: "delete_for_me", label: "Delete for me", enabled: true });
  actions.push({
    id: "delete_for_everyone",
    label: "Delete for everyone",
    enabled: false,
    detail: DELETE_FOR_EVERYONE_REASON,
  });

  return actions;
}

export type AttachmentDraft = {
  id: string;
  file: File;
  name: string;
  size: number;
  mimeType: string;
  previewUrl: string | null;
};

export function buildAttachmentDrafts(files: FileList | File[], existingCount = 0, maxFiles = 10): {
  drafts: Omit<AttachmentDraft, "previewUrl">[];
  error: string | null;
} {
  const list = Array.from(files);
  if (list.length === 0) return { drafts: [], error: null };
  if (existingCount + list.length > maxFiles) {
    return { drafts: [], error: `You can attach up to ${maxFiles} files before sending.` };
  }
  const drafts = list.map((raw, index) => {
    const file = normalizeAttachmentFile(raw, index);
    return {
      id: `draft-${Date.now()}-${index}-${file.name}`,
      file,
      name: file.name || `file-${index + 1}`,
      size: file.size,
      mimeType: file.type || "application/octet-stream",
    };
  });
  return { drafts, error: null };
}

export function canSendComposer(body: string, draftCount: number, sending: boolean) {
  if (sending) return false;
  return body.trim().length > 0 || draftCount > 0;
}
