import type { MessageReferral } from "@/lib/types";

function asTrimmedString(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/** Parse Click-to-WhatsApp / Facebook ad `referral` from a Cloud API inbound message. */
export function parseMessageReferral(message: Record<string, unknown>): MessageReferral | null {
  const raw = message.referral;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const referral = raw as Record<string, unknown>;
  const parsed: MessageReferral = {
    sourceType: asTrimmedString(referral.source_type),
    sourceId: asTrimmedString(referral.source_id),
    sourceUrl: asTrimmedString(referral.source_url),
    headline: asTrimmedString(referral.headline),
    body: asTrimmedString(referral.body),
    mediaType: asTrimmedString(referral.media_type),
    imageUrl: asTrimmedString(referral.image_url),
    videoUrl: asTrimmedString(referral.video_url),
    thumbnailUrl: asTrimmedString(referral.thumbnail_url),
    ctwaClid: asTrimmedString(referral.ctwa_clid),
  };
  const hasContent = Boolean(
    parsed.headline ||
      parsed.body ||
      parsed.imageUrl ||
      parsed.videoUrl ||
      parsed.thumbnailUrl ||
      parsed.sourceUrl ||
      parsed.sourceId ||
      parsed.ctwaClid,
  );
  return hasContent ? parsed : null;
}

export function parseStoredReferral(value: string | null | undefined): MessageReferral | null {
  if (!value) return null;
  try {
    const parsed = JSON.parse(value) as MessageReferral;
    if (!parsed || typeof parsed !== "object") return null;
    return parsed;
  } catch {
    return null;
  }
}
