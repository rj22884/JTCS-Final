import "server-only";

import { getDb } from "@/lib/db";

export const SECRET_KEYS = [
  "businessAccountId",
  "phoneNumberId",
  "displayPhone",
  "appId",
  "accessToken",
  "verifyToken",
  "appSecret",
  "webhookUrl",
  "businessId",
  "graphApiVersion",
  "erpBaseUrl",
  "erpSyncToken",
] as const;

export type SecretKey = (typeof SECRET_KEYS)[number];

const ENV_NAMES: Record<SecretKey, string> = {
  businessAccountId: "WHATSAPP_BUSINESS_ACCOUNT_ID",
  phoneNumberId: "WHATSAPP_PHONE_NUMBER_ID",
  displayPhone: "WHATSAPP_DISPLAY_PHONE",
  appId: "WHATSAPP_APP_ID",
  accessToken: "WHATSAPP_ACCESS_TOKEN",
  verifyToken: "WHATSAPP_VERIFY_TOKEN",
  appSecret: "WHATSAPP_APP_SECRET",
  webhookUrl: "WHATSAPP_WEBHOOK_URL",
  businessId: "WHATSAPP_BUSINESS_ID",
  graphApiVersion: "WHATSAPP_GRAPH_API_VERSION",
  erpBaseUrl: "ERP_BASE_URL",
  erpSyncToken: "WHATSAPP_CUSTOMER_SYNC_TOKEN",
};

const PUBLIC_KEYS = new Set<SecretKey>([
  "businessAccountId",
  "displayPhone",
  "appId",
  "webhookUrl",
  "businessId",
  "graphApiVersion",
  "phoneNumberId",
  "erpBaseUrl",
]);

const BLOCKED_HOSTS = new Set(["localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"]);

export function isSecretKey(value: string): value is SecretKey {
  return (SECRET_KEYS as readonly string[]).includes(value);
}

export function envNameFor(key: SecretKey) {
  return ENV_NAMES[key];
}

export function normalizeWebhookUrl(input: string) {
  const trimmed = input.trim();
  if (!trimmed || trimmed.length > 300) return null;
  let url: URL;
  try {
    url = new URL(trimmed);
  } catch {
    return null;
  }
  if (url.username || url.password || url.search || url.hash) return null;
  if (url.protocol !== "https:") return null;
  const host = url.hostname.toLowerCase();
  if (BLOCKED_HOSTS.has(host) || host.endsWith(".localhost") || host.endsWith(".local")) return null;
  if (isPrivateHost(host)) return null;
  const pathname = url.pathname.replace(/\/+$/, "");
  return `${url.origin}${pathname}`;
}

function isPrivateHost(host: string) {
  if (/^10\./.test(host)) return true;
  if (/^192\.168\./.test(host)) return true;
  if (/^172\.(1[6-9]|2\d|3[0-1])\./.test(host)) return true;
  if (host.startsWith("169.254.")) return true;
  const mapped = host.replace(/^\[|\]$/g, "");
  if (mapped === "::1" || mapped.startsWith("fc") || mapped.startsWith("fd") || mapped.startsWith("fe80:")) return true;
  return false;
}

export function validateSecretInput(key: SecretKey, input: string) {
  const trimmed = input.trim();
  if (key === "businessAccountId" || key === "phoneNumberId" || key === "appId" || key === "businessId") {
    return /^\d{5,32}$/.test(trimmed) ? trimmed : null;
  }
  if (key === "graphApiVersion") return /^v\d{1,3}\.\d{1,3}$/.test(trimmed) ? trimmed : null;
  if (key === "displayPhone") return normalizeDisplayPhone(trimmed);
  if (key === "webhookUrl") return normalizeWebhookUrl(trimmed);
  if (key === "erpBaseUrl") return normalizeErpBaseUrl(trimmed);
  if (key === "erpSyncToken") return plainSecret(trimmed, 16, 256);
  if (key === "accessToken") return plainSecret(trimmed, 20, 4096);
  if (key === "appSecret") return plainSecret(trimmed, 8, 256);
  return plainSecret(trimmed, 8, 128);
}

function normalizeErpBaseUrl(input: string) {
  const trimmed = input.trim().replace(/\/+$/, "");
  let url: URL;
  try {
    url = new URL(trimmed);
  } catch {
    return null;
  }
  if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash) return null;
  const host = url.hostname.toLowerCase();
  if (BLOCKED_HOSTS.has(host) || host.endsWith(".localhost") || host.endsWith(".local") || isPrivateHost(host)) {
    return null;
  }
  return url.origin;
}

function normalizeDisplayPhone(input: string) {
  const compact = input.replace(/[\s-]/g, "");
  if (!/^\+\d{8,15}$/.test(compact)) return null;
  return compact;
}

function plainSecret(value: string, min: number, max: number) {
  if (value.length < min || value.length > max) return null;
  if (/[\u0000-\u001F\u007F\s]/.test(value)) return null;
  return value;
}

type SecretRow = {
  value: string | null;
  cleared: number | bigint;
};

export function resolveSecret(key: SecretKey) {
  const row = getDb().prepare("SELECT value, cleared FROM secrets WHERE key = ?").get(key) as SecretRow | undefined;
  // Prefer a non-cleared DB value. Empty/cleared rows fall through to env so
  // .env.local can restore Cloud API after Settings "delete credentials".
  if (row && Number(row.cleared) !== 1) {
    const stored = typeof row.value === "string" ? row.value.trim() : "";
    if (stored) {
      if (key === "webhookUrl") return normalizeWebhookUrl(stored);
      if (key === "erpBaseUrl") return normalizeErpBaseUrl(stored);
      return stored;
    }
  }
  const fromEnv =
    process.env[ENV_NAMES[key]]?.trim() ||
    (key === "erpSyncToken" ? process.env.ERP_CUSTOMER_SYNC_TOKEN?.trim() : "") ||
    "";
  if (!fromEnv) return null;
  if (key === "webhookUrl") return normalizeWebhookUrl(fromEnv);
  if (key === "erpBaseUrl") return normalizeErpBaseUrl(fromEnv);
  return fromEnv;
}

export function saveSecret(key: SecretKey, input: string) {
  const value = validateSecretInput(key, input);
  if (!value) return false;
  getDb()
    .prepare(
      `INSERT INTO secrets (key, value, cleared, updated_at)
       VALUES (?, ?, 0, ?)
       ON CONFLICT(key) DO UPDATE SET value = excluded.value, cleared = 0, updated_at = excluded.updated_at`,
    )
    .run(key, value, new Date().toISOString());
  return true;
}

export function isPublicSecret(key: SecretKey) {
  return PUBLIC_KEYS.has(key);
}

export function clearSecret(key: SecretKey) {
  getDb()
    .prepare(
      `INSERT INTO secrets (key, value, cleared, updated_at)
       VALUES (?, NULL, 1, ?)
       ON CONFLICT(key) DO UPDATE SET value = NULL, cleared = 1, updated_at = excluded.updated_at`,
    )
    .run(key, new Date().toISOString());
}
