import "server-only";

import { existsSync, mkdirSync, readFileSync, unlinkSync, writeFileSync } from "node:fs";
import path from "node:path";

import { getDb } from "@/lib/db";

const MAX_BYTES = 2 * 1024 * 1024;
const ALLOWED = new Map([
  ["image/jpeg", "jpg"],
  ["image/jpg", "jpg"],
  ["image/png", "png"],
  ["image/webp", "webp"],
]);

function contactAvatarsDir() {
  const dir = path.join(process.cwd(), "data", "contact-avatars");
  mkdirSync(dir, { recursive: true });
  return dir;
}

function safeConversationId(id: string) {
  return id.replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 80);
}

export function contactAvatarUrl(avatarPath: string | null | undefined, conversationId: string) {
  if (!avatarPath) return null;
  return `/api/conversations/${encodeURIComponent(conversationId)}/avatar?v=${encodeURIComponent(avatarPath)}`;
}

function resolveAvatarFile(relativePath: string | null | undefined) {
  if (!relativePath) return null;
  const base = path.resolve(contactAvatarsDir());
  const full = path.resolve(process.cwd(), relativePath);
  if (!full.startsWith(base + path.sep) && full !== base) return null;
  return full;
}

export function saveContactAvatar(conversationId: string, bytes: Buffer, mimeType: string) {
  const ext = ALLOWED.get(mimeType.toLowerCase());
  if (!ext) {
    return { ok: false as const, error: "invalid_type" as const, detail: "Use a JPG, PNG, or WebP photo (max 2 MB)." };
  }
  if (bytes.byteLength === 0 || bytes.byteLength > MAX_BYTES) {
    return { ok: false as const, error: "invalid_size" as const, detail: "Photo must be under 2 MB." };
  }
  const id = safeConversationId(conversationId);
  const relative = path.join("data", "contact-avatars", `${id}.${ext}`).replace(/\\/g, "/");
  const absolute = path.join(process.cwd(), relative);
  mkdirSync(path.dirname(absolute), { recursive: true });
  for (const oldExt of ["jpg", "png", "webp"]) {
    const oldPath = path.join(contactAvatarsDir(), `${id}.${oldExt}`);
    if (oldPath !== absolute && existsSync(oldPath)) {
      try {
        unlinkSync(oldPath);
      } catch {
        /* ignore */
      }
    }
  }
  writeFileSync(absolute, bytes);
  getDb().prepare("UPDATE conversations SET avatar_path = ? WHERE id = ?").run(relative, conversationId);
  return { ok: true as const, path: relative };
}

export function clearContactAvatar(conversationId: string) {
  const row = getDb().prepare("SELECT avatar_path FROM conversations WHERE id = ?").get(conversationId) as
    | { avatar_path: string | null }
    | undefined;
  const full = resolveAvatarFile(row?.avatar_path);
  if (full && existsSync(full)) {
    try {
      unlinkSync(full);
    } catch {
      /* ignore */
    }
  }
  const id = safeConversationId(conversationId);
  for (const ext of ["jpg", "png", "webp"]) {
    const loose = path.join(contactAvatarsDir(), `${id}.${ext}`);
    if (existsSync(loose)) {
      try {
        unlinkSync(loose);
      } catch {
        /* ignore */
      }
    }
  }
  getDb().prepare("UPDATE conversations SET avatar_path = NULL WHERE id = ?").run(conversationId);
  return { ok: true as const };
}

export function readContactAvatar(conversationId: string) {
  const row = getDb().prepare("SELECT avatar_path FROM conversations WHERE id = ?").get(conversationId) as
    | { avatar_path: string | null }
    | undefined;
  const full = resolveAvatarFile(row?.avatar_path);
  if (!full || !existsSync(full)) return null;
  const ext = path.extname(full).toLowerCase();
  const mime = ext === ".png" ? "image/png" : ext === ".webp" ? "image/webp" : "image/jpeg";
  return { bytes: readFileSync(full), mimeType: mime };
}
