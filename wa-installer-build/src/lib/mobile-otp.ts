import "server-only";

import { createHash, randomBytes, randomInt, timingSafeEqual } from "node:crypto";

import {
  EMAIL_SEND_MAX,
  EMAIL_SEND_WINDOW_MS,
  OTP_RESEND_COOLDOWN_MS,
  OTP_TTL_MS,
  resendCooldownMs,
} from "@/lib/auth-policy";
import { getDb } from "@/lib/db";
import { normalizeMobile } from "@/lib/phone";
import { resolveSecret } from "@/lib/secrets";
import { sendCloudTemplate, sendCloudText } from "@/lib/whatsapp/client";

function cloudReady() {
  return Boolean(resolveSecret("phoneNumberId") && resolveSecret("accessToken"));
}

function otpTemplateConfig() {
  const name = (process.env.WHATSAPP_OTP_TEMPLATE || process.env.WHATSAPP_OTP_TEMPLATE_NAME || "").trim();
  const language = (process.env.WHATSAPP_OTP_TEMPLATE_LANG || "en").trim() || "en";
  // off | copy_code (auth templates) | url (one-tap / deep link). Default off = body {{1}} only.
  const button = (process.env.WHATSAPP_OTP_TEMPLATE_BUTTON || "off").trim().toLowerCase();
  const buttonMode =
    button === "copy_code" || button === "copy" ? "copy_code" : button === "url" ? "url" : "off";
  return { name, language, buttonMode };
}

export type MobileOtpPurpose = "register" | "reset" | "recover_id";

function codeHash(purpose: string, mobileKey: string, code: string) {
  return createHash("sha256").update(`${purpose}:${mobileKey}:${code}`).digest("hex");
}

export function tooManyMobileOtps(mobileKey: string) {
  const row = getDb()
    .prepare("SELECT COUNT(*) AS count FROM mobile_otp_sends WHERE mobile_key = ? AND at > ?")
    .get(mobileKey, Date.now() - EMAIL_SEND_WINDOW_MS) as { count: number | bigint } | undefined;
  return Number(row?.count ?? 0) >= EMAIL_SEND_MAX;
}

export function lastMobileOtpSendAt(mobileKey: string) {
  const row = getDb()
    .prepare("SELECT MAX(at) AS at FROM mobile_otp_sends WHERE mobile_key = ?")
    .get(mobileKey) as { at: number | bigint | null } | undefined;
  return row?.at == null ? null : Number(row.at);
}

export function mobileOtpResendCooldownMs(mobileKey: string) {
  return resendCooldownMs(lastMobileOtpSendAt(mobileKey));
}

function rememberSend(mobileKey: string) {
  const db = getDb();
  db.prepare("INSERT INTO mobile_otp_sends (mobile_key, at) VALUES (?, ?)").run(mobileKey, Date.now());
  db.prepare("DELETE FROM mobile_otp_sends WHERE at < ?").run(Date.now() - 60 * 60 * 1000);
}

export function issueMobileOtp(mobileRaw: string, purpose: MobileOtpPurpose, payload: string | null) {
  const mobile = normalizeMobile(mobileRaw);
  if (!mobile.valid) return { ok: false as const, error: "invalid_mobile" as const, detail: mobile.reason || "Invalid mobile." };
  const cooldown = mobileOtpResendCooldownMs(mobile.phoneKey);
  if (cooldown > 0) return { ok: false as const, error: "resend_cooldown" as const, retryAfterMs: cooldown };
  if (tooManyMobileOtps(mobile.phoneKey)) {
    return { ok: false as const, error: "sign_in_unavailable" as const, retryAfterMs: null };
  }
  const code = String(randomInt(100000, 1000000));
  const db = getDb();
  db.prepare("DELETE FROM mobile_otps WHERE mobile_key = ? AND purpose = ?").run(mobile.phoneKey, purpose);
  db.prepare(
    `INSERT INTO mobile_otps (id, mobile_key, purpose, code_hash, payload, expires_at, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
  ).run(
    randomBytes(16).toString("hex"),
    mobile.phoneKey,
    purpose,
    codeHash(purpose, mobile.phoneKey, code),
    payload,
    Date.now() + OTP_TTL_MS,
    Date.now(),
  );
  rememberSend(mobile.phoneKey);
  return {
    ok: true as const,
    code,
    mobile,
    ttlMs: OTP_TTL_MS,
    cooldownMs: OTP_RESEND_COOLDOWN_MS,
  };
}

export function consumeMobileOtp(mobileRaw: string, purpose: MobileOtpPurpose, code: string) {
  const mobile = normalizeMobile(mobileRaw);
  if (!mobile.valid || !/^\d{6}$/.test(code)) return null;
  const row = getDb()
    .prepare(
      `SELECT id, code_hash, payload, expires_at FROM mobile_otps
       WHERE mobile_key = ? AND purpose = ? ORDER BY created_at DESC LIMIT 1`,
    )
    .get(mobile.phoneKey, purpose) as
    | { id: string; code_hash: string; payload: string | null; expires_at: number | bigint }
    | undefined;
  if (!row) return null;
  if (Number(row.expires_at) <= Date.now()) {
    getDb().prepare("DELETE FROM mobile_otps WHERE id = ?").run(row.id);
    return null;
  }
  const actual = Buffer.from(codeHash(purpose, mobile.phoneKey, code), "hex");
  const expected = Buffer.from(row.code_hash, "hex");
  if (actual.length !== expected.length || !timingSafeEqual(actual, expected)) return null;
  getDb().prepare("DELETE FROM mobile_otps WHERE id = ?").run(row.id);
  return { payload: row.payload, mobile };
}

export function peekMobileOtpPayload(mobileRaw: string, purpose: MobileOtpPurpose) {
  const mobile = normalizeMobile(mobileRaw);
  if (!mobile.valid) return null;
  const row = getDb()
    .prepare(
      `SELECT payload FROM mobile_otps WHERE mobile_key = ? AND purpose = ? ORDER BY created_at DESC LIMIT 1`,
    )
    .get(mobile.phoneKey, purpose) as { payload: string | null } | undefined;
  return row?.payload ?? null;
}

/** Send OTP over WhatsApp Cloud API. Never logs the code. */
export async function deliverMobileOtp(toDigits: string, code: string, purpose: MobileOtpPurpose) {
  if (!cloudReady()) {
    return { ok: false as const, error: "whatsapp_not_configured" as const, detail: "WhatsApp Cloud API is not connected." };
  }
  const phoneNumberId = resolveSecret("phoneNumberId");
  const accessToken = resolveSecret("accessToken");
  if (!phoneNumberId || !accessToken) {
    return { ok: false as const, error: "whatsapp_not_configured" as const, detail: "WhatsApp Cloud API is not connected." };
  }
  const graphApiVersion = resolveSecret("graphApiVersion");
  const template = otpTemplateConfig();

  // Prefer an approved Authentication/Utility template so OTP works for first-time
  // recipients (free-form text is blocked outside the 24h customer window).
  if (template.name) {
    const templated = await sendCloudTemplate({
      to: toDigits,
      phoneNumberId,
      accessToken,
      graphApiVersion,
      name: template.name,
      language: template.language,
      bodyParams: [code],
      buttonParams: template.buttonMode === "off" ? undefined : [code],
      buttonSubType: template.buttonMode === "copy_code" ? "copy_code" : "url",
    });
    if (templated.ok) return { ok: true as const };
    console.error("[mobile-otp] template delivery failed (code redacted); trying free-form text");
  }

  const label =
    purpose === "register"
      ? "registration"
      : purpose === "reset"
        ? "password reset"
        : "account recovery";
  const body = `Your WhatsApp CRM ${label} code is ${code}. It expires in 10 minutes. Do not share this code.`;
  const sent = await sendCloudText({
    to: toDigits,
    body,
    phoneNumberId,
    accessToken,
    graphApiVersion,
  });
  if (!sent.ok) {
    console.error("[mobile-otp] delivery failed (code redacted)");
    return {
      ok: false as const,
      error: "otp_delivery_failed" as const,
      detail:
        "Could not send the OTP by WhatsApp. Connect Cloud API (+918477005566) and use an approved OTP template for new numbers.",
    };
  }
  return { ok: true as const };
}

export function clearMobileOtp(mobileRaw: string, purpose: MobileOtpPurpose) {
  const mobile = normalizeMobile(mobileRaw);
  if (!mobile.valid) return;
  getDb().prepare("DELETE FROM mobile_otps WHERE mobile_key = ? AND purpose = ?").run(mobile.phoneKey, purpose);
}
