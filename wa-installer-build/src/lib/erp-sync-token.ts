import "server-only";

import { createHash, randomBytes, timingSafeEqual } from "node:crypto";

import { clearSecret, resolveSecret, saveSecret } from "@/lib/secrets";
import { getDb } from "@/lib/db";

/**
 * Outbound client credential sent to ERP as X-WhatsApp-Sync-Token.
 * Plaintext must be retained to call ERP (same pattern as Meta access tokens).
 * APIs never return the saved value after the one-time generate response.
 */

const META_KEY = "erp_sync_token_meta";

export type ErpSyncTokenStatus = {
  configured: boolean;
  preview: string | null;
  createdAt: string | null;
  source: "database" | "environment" | null;
};

function sha256Prefix(token: string) {
  return createHash("sha256").update(token).digest("hex").slice(0, 12);
}

function readMeta() {
  const row = getDb().prepare("SELECT value FROM app_meta WHERE key = ?").get(META_KEY) as { value: string } | undefined;
  if (!row?.value) return null;
  try {
    return JSON.parse(row.value) as { createdAt?: string; prefix?: string };
  } catch {
    return null;
  }
}

function writeMeta(createdAt: string, prefix: string) {
  getDb()
    .prepare(
      `INSERT INTO app_meta (key, value) VALUES (?, ?)
       ON CONFLICT(key) DO UPDATE SET value = excluded.value`,
    )
    .run(META_KEY, JSON.stringify({ createdAt, prefix }));
}

function clearMeta() {
  getDb().prepare("DELETE FROM app_meta WHERE key = ?").run(META_KEY);
}

export function erpSyncTokenStatus(): ErpSyncTokenStatus {
  const dbValue = (() => {
    const row = getDb().prepare("SELECT value, cleared FROM secrets WHERE key = ?").get("erpSyncToken") as
      | { value: string | null; cleared: number | bigint }
      | undefined;
    if (!row || Number(row.cleared) === 1) return null;
    return typeof row.value === "string" && row.value.trim() ? row.value.trim() : null;
  })();
  const envValue = process.env.WHATSAPP_CUSTOMER_SYNC_TOKEN?.trim() || process.env.ERP_CUSTOMER_SYNC_TOKEN?.trim() || "";
  const token = dbValue || envValue || null;
  const meta = readMeta();
  if (!token) {
    return { configured: false, preview: null, createdAt: null, source: null };
  }
  const prefix = meta?.prefix || sha256Prefix(token).slice(0, 8);
  return {
    configured: true,
    preview: `${prefix}…`,
    createdAt: meta?.createdAt ?? null,
    source: dbValue ? "database" : "environment",
  };
}

export function generateErpSyncToken() {
  const token = randomBytes(32).toString("base64url");
  if (!saveSecret("erpSyncToken", token)) {
    return { ok: false as const, detail: "Generated token failed validation." };
  }
  const createdAt = new Date().toISOString();
  writeMeta(createdAt, sha256Prefix(token).slice(0, 8));
  return {
    ok: true as const,
    token,
    createdAt,
    detail:
      "Copy this token now. It is shown once. Set the same value on app.jtcsxpert.com as WHATSAPP_CUSTOMER_SYNC_TOKEN.",
  };
}

export function revokeErpSyncToken() {
  clearSecret("erpSyncToken");
  clearMeta();
  return { ok: true as const, detail: "Local ERP sync token revoked. Environment variables are unchanged." };
}

/** Compare candidate to configured outbound token without logging secrets. */
export function erpSyncTokenMatches(candidate: string) {
  const expected = resolveSecret("erpSyncToken");
  if (!expected || !candidate) return false;
  const left = Buffer.from(candidate);
  const right = Buffer.from(expected);
  if (left.length !== right.length) return false;
  return timingSafeEqual(left, right);
}

export function resolveOutboundErpSyncToken() {
  return resolveSecret("erpSyncToken");
}
