import { requireUser } from "@/lib/admin";
import { normalizeAttachmentFile } from "@/lib/clipboard-files";
import { mediaPreviewBody, sendCloudMedia, uploadCloudMedia } from "@/lib/whatsapp/client";
import { ensureRequestTime, json } from "@/lib/http";
import { resolveSecret } from "@/lib/secrets";
import type { MessageAttachment } from "@/lib/types";
import { addLiveOutbound, getLiveConversation } from "@/lib/whatsapp/inbox";
import { saveLocalMedia } from "@/lib/whatsapp/media-store";
import { mailboxReady } from "@/lib/whatsapp/status";
import type { NextRequest } from "next/server";

const MAX_BYTES = 100 * 1024 * 1024;
const MAX_FILES = 10;

export async function POST(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  await ensureRequestTime();
  const gate = requireUser(request);
  if (gate.error) return gate.error;
  const { id } = await context.params;

  if (!mailboxReady()) {
    return json({ error: "not_connected", detail: "Attachments need a connected WhatsApp Business account." }, 409);
  }

  const conversation = getLiveConversation(id);
  if (!conversation) return json({ error: "not_found" }, 404);
  if (conversation.blocked) {
    return json({ error: "blocked", detail: "This contact is blocked. Unblock to send messages." }, 403);
  }

  const phoneNumberId = resolveSecret("phoneNumberId");
  const accessToken = resolveSecret("accessToken");
  if (!phoneNumberId || !accessToken) {
    return json({ error: "not_connected", detail: "The phone number is not ready. Nothing was sent." }, 409);
  }

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return json({ error: "invalid_body", detail: "Expected multipart form data with files." }, 400);
  }

  const files = form.getAll("file").filter((item): item is File => item instanceof File);
  if (files.length === 0) {
    const single = form.get("file");
    if (single instanceof File) files.push(single);
  }
  if (files.length === 0) return json({ error: "invalid_file", detail: "Choose an image or document to send." }, 400);
  if (files.length > MAX_FILES) return json({ error: "invalid_file", detail: `You can send up to ${MAX_FILES} files at once.` }, 400);

  const captionValue = form.get("caption");
  const caption = typeof captionValue === "string" ? captionValue : "";
  const graphApiVersion = resolveSecret("graphApiVersion");

  let lastSaved: ReturnType<typeof addLiveOutbound> = null;
  let failedDetail = "";
  const sentAttachments: MessageAttachment[] = [];

  for (let index = 0; index < files.length; index += 1) {
    const file = normalizeAttachmentFile(files[index], index);
    if (file.size <= 0 || file.size > MAX_BYTES) {
      return json({ error: "invalid_file", detail: `${file.name || "File"} size is not allowed.` }, 400);
    }
    const bytes = await file.arrayBuffer();
    const mimeType = file.type || "application/octet-stream";
    const uploaded = await uploadCloudMedia({
      phoneNumberId,
      accessToken,
      graphApiVersion,
      bytes,
      filename: file.name || `attachment-${index + 1}`,
      mimeType,
    });
    if (!uploaded.ok) return json({ error: "upload_failed", detail: uploaded.detail }, 502);

    // Keep a local copy so the chat thumbnail works even if Meta media download fails.
    saveLocalMedia(uploaded.mediaId, bytes, mimeType);

    const fileCaption = index === 0 ? caption : "";
    const sent = await sendCloudMedia({
      to: conversation.phone,
      phoneNumberId,
      accessToken,
      graphApiVersion,
      kind: uploaded.kind,
      mediaId: uploaded.mediaId,
      filename: uploaded.filename,
      caption: fileCaption,
    });
    const body = sent.ok ? sent.body : mediaPreviewBody(uploaded.kind, uploaded.filename, fileCaption);
    const attachment: MessageAttachment = {
      id: `${sent.ok ? sent.messageId : uploaded.mediaId}-${index}`,
      kind: uploaded.kind,
      filename: uploaded.filename,
      mediaId: uploaded.mediaId,
      mimeType,
    };
    sentAttachments.push(attachment);
    lastSaved = addLiveOutbound(id, body, sent.ok ? sent.messageId : null, sent.ok ? "sent" : "failed", {
      kind: uploaded.kind,
      filename: uploaded.filename,
      mediaId: uploaded.mediaId,
      attachments: [attachment],
    });
    if (!sent.ok) failedDetail = sent.detail;
    if (!lastSaved) return json({ error: "not_found" }, 404);
  }

  const multiBody =
    sentAttachments.length > 1
      ? `${sentAttachments.length} files: ${sentAttachments.map((item) => item.filename).join(", ")}`
      : lastSaved?.message.body || "";

  if (sentAttachments.length > 1 && lastSaved) {
    // Keep individual bubbles; summary uses last message already.
    void multiBody;
  }

  return json({
    demo: false,
    delivery: failedDetail ? "failed" : "sent",
    detail: failedDetail || "Meta accepted the message.",
    message: lastSaved?.message,
    conversation: lastSaved?.detail,
    summary: lastSaved?.summary,
    attachments: sentAttachments,
  });
}
