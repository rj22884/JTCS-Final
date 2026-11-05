import "server-only";

import { mkdirSync, unlinkSync, writeFileSync, existsSync, readFileSync } from "node:fs";
import path from "node:path";

import { getDb } from "@/lib/db";

const MAX_BYTES = 2 * 1024 * 1024;
const ALLOWED = new Map([
  ["image/jpeg", "jpg"],
  ["image/jpg", "jpg"],
  ["image/png", "png"],
  ["image/webp", "webp"],
]);

function avatarsDir() {
  const dir = path.join(process.cwd(), "data", "avatars");
  mkdirSync(dir, { recursive: true });
  return dir;
}

export function publicAvatarUrl(hasAvatar: boolean, cacheKey?: string | null) {
  if (!hasAvatar) return null;
  const version = cacheKey ? encodeURIComponent(cacheKey) : "1";
  return `/api/auth/profile/avatar?v=${version}`;
}

export function avatarFilePath(relativePath: string | null | undefined) {
  if (!relativePath) return null;
  const base = path.resolve(avatarsDir());
  const full = path.resolve(process.cwd(), relativePath);
  if (!full.startsWith(base + path.sep) && full !== base) return null;
  return full;
}

export function saveUserAvatar(userId: string, bytes: Buffer, mimeType: string) {
  const ext = ALLOWED.get(mimeType.toLowerCase());
  if (!ext) {
    return { ok: false as const, error: "invalid_type" as const, detail: "Use a JPG, PNG, or WebP photo (max 2 MB)." };
  }
  if (bytes.byteLength === 0 || bytes.byteLength > MAX_BYTES) {
    return { ok: false as const, error: "invalid_size" as const, detail: "Photo must be under 2 MB." };
  }
  const relative = path.join("data", "avatars", `${userId}.${ext}`);
  const absolute = path.join(process.cwd(), relative);
  mkdirSync(path.dirname(absolute), { recursive: true });
  // Remove previous avatar files for this user (any extension).
  for (const oldExt of ["jpg", "png", "webp"]) {
    const oldPath = path.join(avatarsDir(), `${userId}.${oldExt}`);
    if (oldPath !== absolute && existsSync(oldPath)) {
      try {
        unlinkSync(oldPath);
      } catch {
        /* ignore */
      }
    }
  }
  writeFileSync(absolute, bytes);
  getDb().prepare("UPDATE users SET avatar_path = ? WHERE id = ?").run(relative.replace(/\\/g, "/"), userId);
  return { ok: true as const, path: relative.replace(/\\/g, "/") };
}

export function clearUserAvatar(userId: string) {
  const row = getDb().prepare("SELECT avatar_path FROM users WHERE id = ?").get(userId) as
    | { avatar_path: string | null }
    | undefined;
  const full = avatarFilePath(row?.avatar_path);
  if (full && existsSync(full)) {
    try {
      unlinkSync(full);
    } catch {
      /* ignore */
    }
  }
  for (const ext of ["jpg", "png", "webp"]) {
    const loose = path.join(avatarsDir(), `${userId}.${ext}`);
    if (existsSync(loose)) {
      try {
        unlinkSync(loose);
      } catch {
        /* ignore */
      }
    }
  }
  getDb().prepare("UPDATE users SET avatar_path = NULL WHERE id = ?").run(userId);
  return { ok: true as const };
}

export function readUserAvatar(userId: string) {
  const row = getDb().prepare("SELECT avatar_path FROM users WHERE id = ?").get(userId) as
    | { avatar_path: string | null }
    | undefined;
  const full = avatarFilePath(row?.avatar_path);
  if (!full || !existsSync(full)) return null;
  const ext = path.extname(full).toLowerCase();
  const mime =
    ext === ".png" ? "image/png" : ext === ".webp" ? "image/webp" : "image/jpeg";
  return { bytes: readFileSync(full), mimeType: mime };
}
