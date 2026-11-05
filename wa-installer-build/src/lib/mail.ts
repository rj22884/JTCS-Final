import "server-only";

import nodemailer from "nodemailer";

import { getDb } from "@/lib/db";

/**
 * Titan SMTP (official): smtp.titan.email
 * - Port 465 + SSL, or
 * - Port 587 + STARTTLS
 * @see https://support.titan.email/hc/en-us/articles/4405162224665-Configuring-Titan-on-Email-Scripts
 */

const SMTP_CONNECTION_META_KEY = "smtp_connection_meta";

export type MailConfigStatus = {
  configured: boolean;
  host: string | null;
  port: number | null;
  secure: boolean | null;
  from: string | null;
  userSet: boolean;
  passSet: boolean;
};

export type SmtpConnectionMeta = {
  ok: boolean;
  checkedAt: string;
  detail: string;
};

function smtpPort() {
  const port = Number(process.env.SMTP_PORT ?? "465");
  return Number.isFinite(port) ? port : 465;
}

function smtpSecure(port: number) {
  const raw = process.env.SMTP_SECURE?.trim().toLowerCase();
  if (raw === "true" || raw === "1") return true;
  if (raw === "false" || raw === "0") return false;
  return port === 465;
}

export function mailConfigured() {
  return Boolean(
    process.env.SMTP_HOST?.trim() &&
      process.env.SMTP_FROM?.trim() &&
      process.env.SMTP_USER?.trim() &&
      process.env.SMTP_PASS?.trim(),
  );
}

export function mailConfigStatus(): MailConfigStatus {
  const port = smtpPort();
  return {
    configured: mailConfigured(),
    host: process.env.SMTP_HOST?.trim() || null,
    port,
    secure: smtpSecure(port),
    from: process.env.SMTP_FROM?.trim() || null,
    userSet: Boolean(process.env.SMTP_USER?.trim()),
    passSet: Boolean(process.env.SMTP_PASS?.trim()),
  };
}

function createTransport() {
  const port = smtpPort();
  const secure = smtpSecure(port);
  return nodemailer.createTransport({
    host: process.env.SMTP_HOST?.trim(),
    port,
    secure,
    auth: {
      user: process.env.SMTP_USER?.trim(),
      pass: process.env.SMTP_PASS,
    },
  });
}

function logMailFailure(stage: string, error: unknown) {
  const message = error instanceof Error ? error.message : "unknown_error";
  const safe = message
    .replace(process.env.SMTP_PASS ?? "", "[redacted]")
    .replace(process.env.SMTP_USER ?? "", "[redacted]");
  console.error(`[mail] ${stage}: ${safe.slice(0, 240)}`);
}

export async function sendMail(to: string, subject: string, text: string) {
  if (!mailConfigured()) return false;
  try {
    const transporter = createTransport();
    await transporter.sendMail({
      from: process.env.SMTP_FROM?.trim(),
      to,
      subject,
      text,
    });
    return true;
  } catch (error) {
    logMailFailure("send", error);
    throw error;
  }
}

function readSmtpConnectionMeta(): SmtpConnectionMeta | null {
  const row = getDb().prepare("SELECT value FROM app_meta WHERE key = ?").get(SMTP_CONNECTION_META_KEY) as
    | { value: string }
    | undefined;
  if (!row?.value) return null;
  try {
    const parsed = JSON.parse(row.value) as SmtpConnectionMeta;
    if (typeof parsed.ok !== "boolean" || typeof parsed.checkedAt !== "string") return null;
    return {
      ok: parsed.ok,
      checkedAt: parsed.checkedAt,
      detail: typeof parsed.detail === "string" ? parsed.detail : "",
    };
  } catch {
    return null;
  }
}

function writeSmtpConnectionMeta(meta: SmtpConnectionMeta) {
  getDb()
    .prepare(
      `INSERT INTO app_meta (key, value) VALUES (?, ?)
       ON CONFLICT(key) DO UPDATE SET value = excluded.value`,
    )
    .run(SMTP_CONNECTION_META_KEY, JSON.stringify(meta));
}

/** Connected only after a successful verify while SMTP env is fully configured. */
export function smtpConnectionStatus() {
  const configured = mailConfigured();
  const last = readSmtpConnectionMeta();
  if (!configured) {
    return {
      connection: "disconnected" as const,
      configured: false,
      lastCheckedAt: last?.checkedAt ?? null,
      lastOk: false,
      detail: "SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, and SMTP_FROM are required.",
    };
  }
  if (!last) {
    return {
      connection: "disconnected" as const,
      configured: true,
      lastCheckedAt: null,
      lastOk: false,
      detail: "SMTP env is set. Run Verify SMTP connection to confirm.",
    };
  }
  return {
    connection: last.ok ? ("connected" as const) : ("disconnected" as const),
    configured: true,
    lastCheckedAt: last.checkedAt,
    lastOk: last.ok,
    detail: last.detail,
  };
}

/** Verify SMTP credentials without sending a message body to a user. Never returns secrets. */
export async function verifyMailConnection() {
  const checkedAt = new Date().toISOString();
  if (!mailConfigured()) {
    const detail = "SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, and SMTP_FROM are required.";
    writeSmtpConnectionMeta({ ok: false, checkedAt, detail });
    return {
      ok: false as const,
      connection: "disconnected" as const,
      checkedAt,
      detail,
    };
  }
  try {
    const transporter = createTransport();
    await transporter.verify();
    const detail = "SMTP connection verified.";
    writeSmtpConnectionMeta({ ok: true, checkedAt, detail });
    return { ok: true as const, connection: "connected" as const, checkedAt, detail };
  } catch (error) {
    logMailFailure("verify", error);
    const detail = "SMTP connection failed. Check host, port, encryption, and credentials.";
    writeSmtpConnectionMeta({ ok: false, checkedAt, detail });
    return { ok: false as const, connection: "disconnected" as const, checkedAt, detail };
  }
}
