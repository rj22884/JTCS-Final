import "server-only";

import { randomBytes } from "node:crypto";

import { writeAuthAudit } from "@/lib/auth-audit";
import { getDb } from "@/lib/db";
import { normalizeMobile } from "@/lib/phone";
import { hashPassword, isAcceptablePassword, isEmail, normalizeEmail } from "@/lib/passwords";

export type UserRole = "admin" | "member";
export type UserStatus = "active" | "pending_approval" | "rejected" | "deleted";

export const USER_ROLES: ReadonlyArray<{ value: UserRole; label: string }> = [
  { value: "member", label: "Member" },
  { value: "admin", label: "Admin" },
];

export function parseUserRole(value: unknown): UserRole | null {
  if (value === "admin" || value === "member") return value;
  return null;
}

export type UserRecord = {
  id: string;
  email: string;
  name: string;
  mobile: string | null;
  mobile_key: string | null;
  password_hash: string;
  role: UserRole;
  verified: number | bigint;
  status: UserStatus;
  deleted_at: string | null;
  approved_at: string | null;
  approved_by: string | null;
  created_at: string;
  avatar_path: string | null;
};

const USER_SELECT = `SELECT id, email, IFNULL(name, '') AS name, mobile, mobile_key, password_hash, role, verified,
  IFNULL(status, 'active') AS status, deleted_at, approved_at, approved_by, created_at,
  avatar_path FROM users`;

function asStatus(value: string): UserStatus {
  if (value === "pending_approval" || value === "rejected" || value === "deleted" || value === "active") return value;
  return "active";
}

function mapUser(row: UserRecord): UserRecord {
  return { ...row, status: asStatus(String(row.status)) };
}

export function seedAdmin() {
  const email = normalizeEmail(process.env.ADMIN_EMAIL ?? "");
  const password = process.env.ADMIN_PASSWORD?.trim() ?? "";
  if (!isEmail(email) || !isAcceptablePassword(password)) return;
  const db = getDb();
  const existing = db.prepare("SELECT id FROM users WHERE email = ?").get(email) as { id: string } | undefined;
  if (existing) return;
  db.prepare(
    `INSERT INTO users (id, email, name, mobile, mobile_key, password_hash, role, verified, status, created_at, approved_at)
     VALUES (?, ?, 'Admin', NULL, NULL, ?, 'admin', 1, 'active', ?, ?)`,
  ).run(randomBytes(16).toString("hex"), email, hashPassword(password), new Date().toISOString(), new Date().toISOString());
}

export function hasVerifiedAdmin() {
  seedAdmin();
  const row = getDb()
    .prepare("SELECT COUNT(*) AS count FROM users WHERE role = 'admin' AND verified = 1 AND status = 'active'")
    .get() as { count: number | bigint } | undefined;
  return Number(row?.count ?? 0) > 0;
}

export function findUser(email: string) {
  seedAdmin();
  const row = getDb().prepare(`${USER_SELECT} WHERE email = ?`).get(normalizeEmail(email)) as UserRecord | undefined;
  return row ? mapUser(row) : undefined;
}

export function findUserById(id: string) {
  seedAdmin();
  const row = getDb().prepare(`${USER_SELECT} WHERE id = ?`).get(id) as UserRecord | undefined;
  return row ? mapUser(row) : undefined;
}

export function findUserByMobileKey(mobileKey: string) {
  seedAdmin();
  const row = getDb().prepare(`${USER_SELECT} WHERE mobile_key = ?`).get(mobileKey) as UserRecord | undefined;
  return row ? mapUser(row) : undefined;
}

/** Login id may be email or mobile digits. */
export function findUserByLogin(login: string) {
  seedAdmin();
  const trimmed = login.trim();
  if (trimmed.includes("@")) return findUser(trimmed);
  const mobile = normalizeMobile(trimmed);
  if (!mobile.valid) return undefined;
  return findUserByMobileKey(mobile.phoneKey);
}

export function listUsersByStatus(status: UserStatus) {
  seedAdmin();
  const rows = getDb()
    .prepare(`${USER_SELECT} WHERE status = ? ORDER BY created_at DESC`)
    .all(status) as UserRecord[];
  return rows.map(mapUser);
}

export function findLiveConflict(email: string, mobileKey: string) {
  const byEmail = findUser(email);
  if (byEmail && (byEmail.status === "active" || byEmail.status === "pending_approval")) {
    return { kind: "email" as const, user: byEmail };
  }
  const byMobile = findUserByMobileKey(mobileKey);
  if (byMobile && (byMobile.status === "active" || byMobile.status === "pending_approval")) {
    return { kind: "mobile" as const, user: byMobile };
  }
  return null;
}

export function findDeletedConflict(email: string, mobileKey: string) {
  const byEmail = findUser(email);
  if (byEmail && byEmail.status === "deleted") return byEmail;
  const byMobile = findUserByMobileKey(mobileKey);
  if (byMobile && byMobile.status === "deleted") return byMobile;
  return null;
}

export type RegisterPayload = {
  name: string;
  email: string;
  mobile: string;
  mobileKey: string;
  passwordHash: string;
  /** Requested role; account stays pending until an admin approves. */
  role?: UserRole;
};

export function createPendingUser(input: RegisterPayload) {
  const id = randomBytes(16).toString("hex");
  const now = new Date().toISOString();
  const role = parseUserRole(input.role) ?? "member";
  getDb()
    .prepare(
      `INSERT INTO users
        (id, email, name, mobile, mobile_key, password_hash, role, verified, status, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'pending_approval', ?)`,
    )
    .run(
      id,
      normalizeEmail(input.email),
      input.name.slice(0, 200),
      input.mobile,
      input.mobileKey,
      input.passwordHash,
      role,
      now,
    );
  writeAuthAudit({
    action: "user_pending_created",
    targetUserId: id,
    detail: `Mobile OTP verified; role ${role}; awaiting admin approval.`,
  });
  return findUserById(id)!;
}

export function approveUser(userId: string, actorUserId: string, role?: UserRole | null) {
  const user = findUserById(userId);
  if (!user) return { ok: false as const, error: "not_found" as const };
  if (user.status !== "pending_approval") return { ok: false as const, error: "not_pending" as const };
  const finalRole = parseUserRole(role) ?? user.role;
  const now = new Date().toISOString();
  getDb()
    .prepare(
      `UPDATE users SET status = 'active', verified = 1, role = ?, approved_at = ?, approved_by = ? WHERE id = ?`,
    )
    .run(finalRole, now, actorUserId, userId);
  writeAuthAudit({
    actorUserId,
    action: "user_approved",
    targetUserId: userId,
    detail: `Admin approved registration as ${finalRole}.`,
  });
  return { ok: true as const, user: findUserById(userId)! };
}

export function rejectUser(userId: string, actorUserId: string) {
  const user = findUserById(userId);
  if (!user) return { ok: false as const, error: "not_found" as const };
  if (user.status !== "pending_approval") return { ok: false as const, error: "not_pending" as const };
  getDb().prepare(`UPDATE users SET status = 'rejected', verified = 0 WHERE id = ?`).run(userId);
  getDb().prepare("DELETE FROM admin_sessions WHERE user_id = ?").run(userId);
  writeAuthAudit({
    actorUserId,
    action: "user_rejected",
    targetUserId: userId,
    detail: "Admin rejected registration.",
  });
  return { ok: true as const, user: findUserById(userId)! };
}

/** Soft-delete: frees login but keeps row until admin permanent purge. */
export function softDeleteUser(userId: string, actorUserId: string) {
  const user = findUserById(userId);
  if (!user) return { ok: false as const, error: "not_found" as const };
  if (user.role === "admin" && user.status === "active") {
    return { ok: false as const, error: "admin_protected" as const };
  }
  const now = new Date().toISOString();
  getDb()
    .prepare(`UPDATE users SET status = 'deleted', verified = 0, deleted_at = ? WHERE id = ?`)
    .run(now, userId);
  getDb().prepare("DELETE FROM admin_sessions WHERE user_id = ?").run(userId);
  writeAuthAudit({
    actorUserId,
    action: "user_soft_deleted",
    targetUserId: userId,
    detail: "User marked deleted; permanent purge required before re-registration.",
  });
  return { ok: true as const, user: findUserById(userId)! };
}

/**
 * Permanently remove a deleted/rejected user account row only.
 * Does not touch customer_master, conversations, or messages.
 */
export function permanentlyDeleteUser(userId: string, actorUserId: string) {
  const user = findUserById(userId);
  if (!user) return { ok: false as const, error: "not_found" as const, detail: "User not found." };
  if (user.status !== "deleted" && user.status !== "rejected") {
    return {
      ok: false as const,
      error: "not_deletable" as const,
      detail: "Only deleted or rejected accounts can be permanently removed.",
    };
  }
  if (user.role === "admin") {
    return { ok: false as const, error: "admin_protected" as const, detail: "Admin accounts cannot be permanently deleted here." };
  }
  const db = getDb();
  db.prepare("DELETE FROM admin_sessions WHERE user_id = ?").run(userId);
  db.prepare("DELETE FROM approval_tokens WHERE user_id = ?").run(userId);
  db.prepare("DELETE FROM approval_notify_failures WHERE user_id = ?").run(userId);
  if (user.mobile_key) {
    db.prepare("DELETE FROM mobile_otps WHERE mobile_key = ?").run(user.mobile_key);
  }
  db.prepare("DELETE FROM users WHERE id = ?").run(userId);
  writeAuthAudit({
    actorUserId,
    action: "user_purged",
    targetUserId: userId,
    detail: `Permanently deleted account ${user.email}. Customer/chat/ERP data untouched.`,
  });
  return { ok: true as const, detail: "Account permanently deleted. Customer and chat records were not modified." };
}

export function canLogin(user: UserRecord) {
  if (user.status === "pending_approval") return { ok: false as const, error: "pending_approval" as const };
  if (user.status === "rejected") return { ok: false as const, error: "rejected" as const };
  if (user.status === "deleted") return { ok: false as const, error: "sign_in_failed" as const };
  if (user.status !== "active" || Number(user.verified) !== 1) {
    return { ok: false as const, error: "verify_required" as const };
  }
  return { ok: true as const };
}

export function updatePassword(userId: string, passwordHash: string, keepSessionId?: string) {
  getDb().prepare("UPDATE users SET password_hash = ? WHERE id = ?").run(passwordHash, userId);
  if (keepSessionId) {
    getDb()
      .prepare("DELETE FROM admin_sessions WHERE user_id = ? AND id != ?")
      .run(userId, keepSessionId);
  } else {
    getDb().prepare("DELETE FROM admin_sessions WHERE user_id = ?").run(userId);
  }
}

export function updateProfileName(userId: string, name: string) {
  const trimmed = name.trim().slice(0, 200);
  if (!trimmed) return { ok: false as const, error: "invalid_name" as const, detail: "Name is required." };
  getDb().prepare("UPDATE users SET name = ? WHERE id = ?").run(trimmed, userId);
  return { ok: true as const, user: findUserById(userId)! };
}

export function publicProfile(user: UserRecord) {
  return {
    id: user.id,
    name: user.name,
    email: user.email,
    mobile: user.mobile,
    role: user.role,
    hasAvatar: Boolean(user.avatar_path),
    avatarUrl: user.avatar_path ? `/api/auth/profile/avatar?v=${encodeURIComponent(user.avatar_path)}` : null,
  };
}

/** @deprecated Email OTP removed from auth; kept for temporary audit cleanup only. */
export function createVerifiedUser(email: string, passwordHash: string, role: UserRole) {
  const id = randomBytes(16).toString("hex");
  const now = new Date().toISOString();
  getDb()
    .prepare(
      `INSERT INTO users (id, email, name, password_hash, role, verified, status, created_at, approved_at)
       VALUES (?, ?, '', ?, ?, 1, 'active', ?, ?)`,
    )
    .run(id, normalizeEmail(email), passwordHash, role, now, now);
  return id;
}
