import "server-only";

import { createHash, randomBytes } from "node:crypto";

import { writeAuthAudit } from "@/lib/auth-audit";
import { getDb } from "@/lib/db";
import { normalizeMobile } from "@/lib/phone";
import { resolveSecret } from "@/lib/secrets";
import type { UserRecord } from "@/lib/users";
import { sendCloudText } from "@/lib/whatsapp/client";

function cloudReady() {
  return Boolean(resolveSecret("phoneNumberId") && resolveSecret("accessToken"));
}

const APPROVAL_TTL_MS = 48 * 60 * 60 * 1000;

function tokenHash(token: string) {
  return createHash("sha256").update(token).digest("hex");
}

export function adminWhatsAppRecipients() {
  const raw =
    process.env.ADMIN_WHATSAPP_RECIPIENTS?.trim() ||
    process.env.AUTH_APPROVAL_WHATSAPP_NUMBERS?.trim() ||
    "";
  if (!raw) return [] as string[];
  const out: string[] = [];
  for (const part of raw.split(/[,;\s]+/)) {
    const mobile = normalizeMobile(part);
    if (mobile.valid) out.push(mobile.digits);
  }
  return [...new Set(out)];
}

export function publicAppBaseUrl() {
  const webhook = process.env.WHATSAPP_WEBHOOK_URL?.trim();
  if (webhook) {
    try {
      return new URL(webhook).origin;
    } catch {
      /* fall through */
    }
  }
  return process.env.APP_BASE_URL?.trim().replace(/\/+$/, "") || "";
}

export function issueApprovalTokens(userId: string) {
  const db = getDb();
  db.prepare("DELETE FROM approval_tokens WHERE user_id = ? AND used_at IS NULL").run(userId);
  const approveToken = randomBytes(32).toString("base64url");
  const rejectToken = randomBytes(32).toString("base64url");
  const expiresAt = Date.now() + APPROVAL_TTL_MS;
  const createdAt = Date.now();
  for (const [action, token] of [
    ["approve", approveToken],
    ["reject", rejectToken],
  ] as const) {
    db.prepare(
      `INSERT INTO approval_tokens (id, token_hash, user_id, action, expires_at, used_at, created_at)
       VALUES (?, ?, ?, ?, ?, NULL, ?)`,
    ).run(randomBytes(16).toString("hex"), tokenHash(token), userId, action, expiresAt, createdAt);
  }
  return { approveToken, rejectToken, expiresAt };
}

export function readApprovalToken(token: string) {
  if (!token || token.length < 20) return null;
  const row = getDb()
    .prepare(
      `SELECT id, user_id, action, expires_at, used_at FROM approval_tokens WHERE token_hash = ?`,
    )
    .get(tokenHash(token)) as
    | { id: string; user_id: string; action: string; expires_at: number | bigint; used_at: number | bigint | null }
    | undefined;
  if (!row) return null;
  if (row.used_at != null) return { ok: false as const, error: "used" as const };
  if (Number(row.expires_at) <= Date.now()) return { ok: false as const, error: "expired" as const };
  if (row.action !== "approve" && row.action !== "reject") return { ok: false as const, error: "invalid" as const };
  return {
    ok: true as const,
    id: row.id,
    userId: row.user_id,
    action: row.action as "approve" | "reject",
  };
}

export function consumeApprovalToken(tokenId: string) {
  getDb().prepare("UPDATE approval_tokens SET used_at = ? WHERE id = ? AND used_at IS NULL").run(Date.now(), tokenId);
}

export function recordApprovalNotifyFailure(userId: string, detail: string) {
  const now = new Date().toISOString();
  getDb()
    .prepare(
      `INSERT INTO approval_notify_failures (user_id, last_error, failed_at, attempts)
       VALUES (?, ?, ?, 1)
       ON CONFLICT(user_id) DO UPDATE SET
         last_error = excluded.last_error,
         failed_at = excluded.failed_at,
         attempts = approval_notify_failures.attempts + 1`,
    )
    .run(userId, detail.slice(0, 500), now);
}

export function clearApprovalNotifyFailure(userId: string) {
  getDb().prepare("DELETE FROM approval_notify_failures WHERE user_id = ?").run(userId);
}

export async function notifyAdminsOfPendingUser(user: UserRecord, baseUrl: string) {
  const recipients = adminWhatsAppRecipients();
  if (recipients.length === 0) {
    const detail = "ADMIN_WHATSAPP_RECIPIENTS is not configured.";
    recordApprovalNotifyFailure(user.id, detail);
    return { ok: false as const, detail, sent: 0 };
  }
  if (!cloudReady()) {
    const detail = "WhatsApp Cloud API is not connected.";
    recordApprovalNotifyFailure(user.id, detail);
    return { ok: false as const, detail, sent: 0 };
  }
  const phoneNumberId = resolveSecret("phoneNumberId");
  const accessToken = resolveSecret("accessToken");
  if (!phoneNumberId || !accessToken) {
    const detail = "WhatsApp Cloud API credentials are missing.";
    recordApprovalNotifyFailure(user.id, detail);
    return { ok: false as const, detail, sent: 0 };
  }
  const origin = baseUrl || publicAppBaseUrl();
  if (!origin) {
    const detail = "APP_BASE_URL or WHATSAPP_WEBHOOK_URL is required for approval links.";
    recordApprovalNotifyFailure(user.id, detail);
    return { ok: false as const, detail, sent: 0 };
  }
  const tokens = issueApprovalTokens(user.id);
  const approveUrl = `${origin}/approvals?token=${encodeURIComponent(tokens.approveToken)}`;
  const rejectUrl = `${origin}/approvals?token=${encodeURIComponent(tokens.rejectToken)}`;
  const body = [
    "WhatsApp CRM — new account pending approval",
    `Name: ${user.name || "(none)"}`,
    `Mobile: +${user.mobile || ""}`,
    `Email: ${user.email}`,
    `Requested role: ${user.role}`,
    "",
    "Admin sign-in required to complete the action.",
    `Approve: ${approveUrl}`,
    `Reject: ${rejectUrl}`,
    "",
    "Links expire in 48 hours and work once.",
  ].join("\n");

  let sent = 0;
  let lastError = "";
  for (const to of recipients) {
    const result = await sendCloudText({
      to,
      body,
      phoneNumberId,
      accessToken,
      graphApiVersion: resolveSecret("graphApiVersion"),
    });
    if (result.ok) sent += 1;
    else lastError = result.detail;
  }
  if (sent === 0) {
    const detail = lastError || "WhatsApp notification failed for all admin recipients.";
    recordApprovalNotifyFailure(user.id, detail);
    writeAuthAudit({
      action: "approval_notify_failed",
      targetUserId: user.id,
      detail,
    });
    return { ok: false as const, detail, sent: 0 };
  }
  clearApprovalNotifyFailure(user.id);
  writeAuthAudit({
    action: "approval_notify_sent",
    targetUserId: user.id,
    detail: `Notified ${sent} admin recipient(s).`,
  });
  return { ok: true as const, detail: `Notified ${sent} admin recipient(s).`, sent };
}
