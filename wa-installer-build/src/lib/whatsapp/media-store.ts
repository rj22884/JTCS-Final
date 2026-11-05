import "server-only";

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const EXT_BY_MIME: Record<string, string> = {
  "image/jpeg": "jpg",
  "image/jpg": "jpg",
  "image/png": "png",
  "image/webp": "webp",
  "audio/aac": "aac",
  "audio/mp4": "m4a",
  "audio/mpeg": "mp3",
  "audio/amr": "amr",
  "audio/ogg": "ogg",
  "video/mp4": "mp4",
  "video/3gpp": "3gp",
  "application/pdf": "pdf",
  "text/plain": "txt",
};

function mediaDir() {
  const dir = path.join(process.cwd(), "data", "whatsapp-media");
  mkdirSync(dir, { recursive: true });
  return dir;
}

function safeMediaId(mediaId: string) {
  return mediaId.replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 120);
}

function resolveStoredPath(mediaId: string, mimeType?: string | null) {
  const id = safeMediaId(mediaId);
  const dir = mediaDir();
  const preferred = EXT_BY_MIME[(mimeType || "").toLowerCase()];
  if (preferred) {
    const candidate = path.join(dir, `${id}.${preferred}`);
    if (existsSync(candidate)) return candidate;
  }
  for (const ext of Object.values(EXT_BY_MIME)) {
    const candidate = path.join(dir, `${id}.${ext}`);
    if (existsSync(candidate)) return candidate;
  }
  const bare = path.join(dir, id);
  if (existsSync(bare)) return bare;
  return null;
}

/** Persist outbound (or cached inbound) media bytes keyed by Meta media id. */
export function saveLocalMedia(mediaId: string, bytes: ArrayBuffer | Buffer, mimeType: string) {
  const id = safeMediaId(mediaId);
  if (!id || !bytes || (bytes as ArrayBuffer).byteLength === 0) return null;
  const mime = (mimeType || "application/octet-stream").toLowerCase();
  const ext = EXT_BY_MIME[mime] || "bin";
  const absolute = path.join(mediaDir(), `${id}.${ext}`);
  const buffer = Buffer.isBuffer(bytes) ? bytes : Buffer.from(bytes);
  writeFileSync(absolute, buffer);
  return absolute;
}

export function readLocalMedia(mediaId: string, mimeType?: string | null) {
  const absolute = resolveStoredPath(mediaId, mimeType);
  if (!absolute) return null;
  try {
    const bytes = readFileSync(absolute);
    const ext = path.extname(absolute).slice(1).toLowerCase();
    const mimeFromExt =
      Object.entries(EXT_BY_MIME).find(([, value]) => value === ext)?.[0] ||
      mimeType ||
      "application/octet-stream";
    return { bytes, mimeType: mimeFromExt, absolute };
  } catch {
    return null;
  }
}
