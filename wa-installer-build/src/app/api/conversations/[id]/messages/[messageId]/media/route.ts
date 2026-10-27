import { requireSession } from "@/lib/admin";
import { downloadCloudMedia } from "@/lib/whatsapp/client";
import { ensureRequestTime, json } from "@/lib/http";
import { messageAttachments } from "@/lib/message-actions";
import { resolveSecret } from "@/lib/secrets";
import { getLiveMessage } from "@/lib/whatsapp/inbox";
import { readLocalMedia, saveLocalMedia } from "@/lib/whatsapp/media-store";
import { mailboxReady } from "@/lib/whatsapp/status";
import type { NextRequest } from "next/server";

export async function GET(request: NextRequest, context: { params: Promise<{ id: string; messageId: string }> }) {
  await ensureRequestTime();
  const gate = requireSession(request);
  if (gate.error) return gate.error;
  const { id, messageId } = await context.params;
  const message = getLiveMessage(id, messageId);
  if (!message) return json({ error: "not_found" }, 404);
  const indexValue = Number(request.nextUrl.searchParams.get("index") || "0");
  const attachments = messageAttachments(message);
  const attachment = attachments[Number.isFinite(indexValue) ? indexValue : 0];
  if (!attachment?.mediaId) {
    return json({ error: "no_media", detail: "This message has no downloadable WhatsApp media id." }, 404);
  }

  const filename = attachment.filename || `whatsapp-${attachment.mediaId}`;
  const inline = request.nextUrl.searchParams.get("inline") === "1";
  const safeName = filename.replace(/"/g, "");

  const local = readLocalMedia(attachment.mediaId, attachment.mimeType);
  if (local) {
    return new Response(local.bytes, {
      status: 200,
      headers: {
        "Content-Type": local.mimeType || attachment.mimeType || "application/octet-stream",
        "Content-Disposition": `${inline ? "inline" : "attachment"}; filename="${safeName}"`,
        "Cache-Control": inline ? "private, max-age=300" : "no-store",
      },
    });
  }

  if (!mailboxReady()) {
    return json({ error: "not_connected", detail: "Media download needs a connected WhatsApp Business account." }, 409);
  }
  const accessToken = resolveSecret("accessToken");
  if (!accessToken) return json({ error: "not_connected", detail: "Access token missing." }, 409);
  const downloaded = await downloadCloudMedia({
    mediaId: attachment.mediaId,
    accessToken,
    graphApiVersion: resolveSecret("graphApiVersion"),
  });
  if (!downloaded.ok) return json({ error: "download_failed", detail: downloaded.detail }, 502);
  saveLocalMedia(attachment.mediaId, downloaded.bytes, downloaded.mimeType);
  return new Response(downloaded.bytes, {
    status: 200,
    headers: {
      "Content-Type": downloaded.mimeType,
      "Content-Disposition": `${inline ? "inline" : "attachment"}; filename="${safeName}"`,
      "Cache-Control": inline ? "private, max-age=300" : "no-store",
    },
  });
}
