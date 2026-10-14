/** Shared URL helpers for chat text (client + server safe). */

const URL_RE = /https?:\/\/[^\s<>"'`]+/gi;

export function extractHttpUrls(text: string, limit = 3) {
  if (!text) return [] as string[];
  const found: string[] = [];
  const seen = new Set<string>();
  for (const match of text.matchAll(URL_RE)) {
    let raw = match[0] || "";
    raw = raw.replace(/[),.!?;:]+$/g, "");
    if (!raw) continue;
    try {
      const url = new URL(raw);
      if (url.protocol !== "http:" && url.protocol !== "https:") continue;
      const key = url.href;
      if (seen.has(key)) continue;
      seen.add(key);
      found.push(url.href);
      if (found.length >= limit) break;
    } catch {
      /* skip */
    }
  }
  return found;
}

export function splitTextWithUrls(text: string) {
  const parts: Array<{ type: "text" | "url"; value: string }> = [];
  if (!text) return parts;
  let last = 0;
  for (const match of text.matchAll(URL_RE)) {
    const full = match[0] || "";
    const start = match.index ?? 0;
    const trimmed = full.replace(/[),.!?;:]+$/g, "");
    const trail = full.slice(trimmed.length);
    if (start > last) parts.push({ type: "text", value: text.slice(last, start) });
    if (trimmed) parts.push({ type: "url", value: trimmed });
    if (trail) parts.push({ type: "text", value: trail });
    last = start + full.length;
  }
  if (last < text.length) parts.push({ type: "text", value: text.slice(last) });
  return parts.length > 0 ? parts : [{ type: "text" as const, value: text }];
}

export function attachmentLooksLikeImage(input: {
  kind?: string | null;
  mimeType?: string | null;
  filename?: string | null;
}) {
  if (input.kind === "image") return true;
  if (input.mimeType?.startsWith("image/")) return true;
  return /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(input.filename || "");
}

export function attachmentLooksLikeVideo(input: {
  kind?: string | null;
  mimeType?: string | null;
  filename?: string | null;
}) {
  if (input.kind === "video") return true;
  if (input.mimeType?.startsWith("video/")) return true;
  return /\.(mp4|webm|mov|m4v|mkv)$/i.test(input.filename || "");
}

export function attachmentLooksLikeAudio(input: {
  kind?: string | null;
  mimeType?: string | null;
  filename?: string | null;
}) {
  if (input.kind === "audio") return true;
  if (input.mimeType?.startsWith("audio/")) return true;
  return /\.(mp3|ogg|wav|m4a|aac|opus)$/i.test(input.filename || "");
}

export function attachmentLooksLikePdf(input: {
  mimeType?: string | null;
  filename?: string | null;
}) {
  if (input.mimeType?.includes("pdf")) return true;
  return /\.pdf$/i.test(input.filename || "");
}
