import "server-only";

import { mkdirSync } from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

const globalDb = globalThis as typeof globalThis & {
  __waDb?: DatabaseSync;
};

function databasePath() {
  const override = process.env.WHATSAPP_SQLITE_PATH?.trim();
  if (override) return override;
  return path.join(process.cwd(), "data", "app.sqlite");
}

function migrate(db: DatabaseSync) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS secrets (
      key TEXT PRIMARY KEY,
      value TEXT,
      cleared INTEGER NOT NULL DEFAULT 0,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS webhook_events (
      id TEXT PRIMARY KEY,
      received_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS admin_sessions (
      id TEXT PRIMARY KEY,
      csrf TEXT NOT NULL,
      expires_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS login_attempts (
      ip_hash TEXT NOT NULL,
      at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS users (
      id TEXT PRIMARY KEY,
      email TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      role TEXT NOT NULL,
      verified INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS email_codes (
      id TEXT PRIMARY KEY,
      email TEXT NOT NULL,
      purpose TEXT NOT NULL,
      code_hash TEXT NOT NULL,
      payload TEXT,
      expires_at INTEGER NOT NULL,
      created_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS email_sends (
      email TEXT NOT NULL,
      at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS conversations (
      id TEXT PRIMARY KEY,
      phone TEXT NOT NULL UNIQUE,
      name TEXT NOT NULL,
      status TEXT NOT NULL,
      labels TEXT NOT NULL,
      assignee TEXT NOT NULL,
      unread_count INTEGER NOT NULL,
      notes TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS messages (
      id TEXT PRIMARY KEY,
      conversation_id TEXT NOT NULL,
      direction TEXT NOT NULL,
      body TEXT NOT NULL,
      at TEXT NOT NULL,
      delivery TEXT,
      wa_id TEXT
    );
    CREATE INDEX IF NOT EXISTS messages_conversation ON messages (conversation_id, at);
    CREATE TABLE IF NOT EXISTS customer_master (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      mobile TEXT NOT NULL,
      phone_key TEXT NOT NULL,
      synced_at TEXT
    );
    CREATE INDEX IF NOT EXISTS customer_master_phone ON customer_master (phone_key);
    CREATE TABLE IF NOT EXISTS app_meta (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    );
  `);
  const columns = db.prepare("PRAGMA table_info(admin_sessions)").all() as { name: string }[];
  if (!columns.some((column) => column.name === "user_id")) {
    db.exec("ALTER TABLE admin_sessions ADD COLUMN user_id TEXT");
  }
  const messageColumns = db.prepare("PRAGMA table_info(messages)").all() as { name: string }[];
  const messageNames = new Set(messageColumns.map((column) => column.name));
  if (!messageNames.has("kind")) db.exec("ALTER TABLE messages ADD COLUMN kind TEXT");
  if (!messageNames.has("filename")) db.exec("ALTER TABLE messages ADD COLUMN filename TEXT");
  if (!messageNames.has("media_id")) db.exec("ALTER TABLE messages ADD COLUMN media_id TEXT");
  if (!messageNames.has("attachments_json")) db.exec("ALTER TABLE messages ADD COLUMN attachments_json TEXT");
  if (!messageNames.has("deleted_for_me")) db.exec("ALTER TABLE messages ADD COLUMN deleted_for_me INTEGER NOT NULL DEFAULT 0");
  if (!messageNames.has("referral_json")) db.exec("ALTER TABLE messages ADD COLUMN referral_json TEXT");
  if (!messageNames.has("delivery_error")) db.exec("ALTER TABLE messages ADD COLUMN delivery_error TEXT");

  const customerColumns = db.prepare("PRAGMA table_info(customer_master)").all() as { name: string }[];
  const customerNames = new Set(customerColumns.map((column) => column.name));
  if (!customerNames.has("source")) db.exec("ALTER TABLE customer_master ADD COLUMN source TEXT NOT NULL DEFAULT 'erp'");
  if (!customerNames.has("notes")) db.exec("ALTER TABLE customer_master ADD COLUMN notes TEXT NOT NULL DEFAULT ''");
  if (!customerNames.has("created_at")) db.exec("ALTER TABLE customer_master ADD COLUMN created_at TEXT");
  if (!customerNames.has("updated_at")) db.exec("ALTER TABLE customer_master ADD COLUMN updated_at TEXT");
  if (!customerNames.has("deleted_at")) db.exec("ALTER TABLE customer_master ADD COLUMN deleted_at TEXT");
  if (!customerNames.has("country_code")) {
    db.exec("ALTER TABLE customer_master ADD COLUMN country_code TEXT NOT NULL DEFAULT '91'");
  }
  if (!customerNames.has("labels")) {
    db.exec("ALTER TABLE customer_master ADD COLUMN labels TEXT NOT NULL DEFAULT '[]'");
  }
  const stamp = new Date().toISOString();
  db.prepare(
    `UPDATE customer_master
     SET created_at = COALESCE(created_at, synced_at, ?),
         updated_at = COALESCE(updated_at, synced_at, ?),
         source = COALESCE(NULLIF(source, ''), 'erp'),
         notes = COALESCE(notes, ''),
         country_code = COALESCE(NULLIF(country_code, ''), '91')`,
  ).run(stamp, stamp);
  // Split legacy full India numbers (91 + 10 digits) into country_code + national mobile.
  const legacyFull = db
    .prepare(
      `SELECT id, mobile FROM customer_master
       WHERE IFNULL(country_code, '91') = '91'
         AND length(REPLACE(mobile, '+', '')) >= 12
         AND REPLACE(mobile, '+', '') LIKE '91%'`,
    )
    .all() as { id: string; mobile: string }[];
  for (const row of legacyFull) {
    const digits = row.mobile.replace(/\D/g, "");
    const national = digits.slice(2);
    if (national.length >= 8) {
      db.prepare(`UPDATE customer_master SET country_code = '91', mobile = ? WHERE id = ?`).run(national, row.id);
    }
  }
  // Preserve uniqueness: if duplicate phone_key rows exist, isolate extras without deleting data.
  const dupes = db
    .prepare(
      `SELECT phone_key FROM customer_master
       GROUP BY phone_key HAVING COUNT(*) > 1`,
    )
    .all() as { phone_key: string }[];
  for (const dupe of dupes) {
    const rows = db
      .prepare(`SELECT id FROM customer_master WHERE phone_key = ? ORDER BY id ASC`)
      .all(dupe.phone_key) as { id: string }[];
    for (const row of rows.slice(1)) {
      db.prepare(`UPDATE customer_master SET phone_key = ? WHERE id = ?`).run(`conflict:${dupe.phone_key}:${row.id}`, row.id);
    }
  }
  db.exec(`CREATE UNIQUE INDEX IF NOT EXISTS customer_master_phone_key_unique ON customer_master (phone_key)`);

  const userColumns = db.prepare("PRAGMA table_info(users)").all() as { name: string }[];
  const userNames = new Set(userColumns.map((column) => column.name));
  if (!userNames.has("name")) db.exec("ALTER TABLE users ADD COLUMN name TEXT NOT NULL DEFAULT ''");
  if (!userNames.has("mobile")) db.exec("ALTER TABLE users ADD COLUMN mobile TEXT");
  if (!userNames.has("mobile_key")) db.exec("ALTER TABLE users ADD COLUMN mobile_key TEXT");
  if (!userNames.has("status")) db.exec("ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'");
  if (!userNames.has("deleted_at")) db.exec("ALTER TABLE users ADD COLUMN deleted_at TEXT");
  if (!userNames.has("approved_at")) db.exec("ALTER TABLE users ADD COLUMN approved_at TEXT");
  if (!userNames.has("approved_by")) db.exec("ALTER TABLE users ADD COLUMN approved_by TEXT");
  if (!userNames.has("avatar_path")) db.exec("ALTER TABLE users ADD COLUMN avatar_path TEXT");

  const conversationColumns = db.prepare("PRAGMA table_info(conversations)").all() as { name: string }[];
  const conversationNames = new Set(conversationColumns.map((column) => column.name));
  if (!conversationNames.has("avatar_path")) {
    db.exec("ALTER TABLE conversations ADD COLUMN avatar_path TEXT");
  }
  if (!conversationNames.has("archived")) {
    db.exec("ALTER TABLE conversations ADD COLUMN archived INTEGER NOT NULL DEFAULT 0");
  }
  if (!conversationNames.has("pinned")) {
    db.exec("ALTER TABLE conversations ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0");
  }
  if (!conversationNames.has("muted_until")) {
    db.exec("ALTER TABLE conversations ADD COLUMN muted_until TEXT");
  }
  if (!conversationNames.has("favourite")) {
    db.exec("ALTER TABLE conversations ADD COLUMN favourite INTEGER NOT NULL DEFAULT 0");
  }
  if (!conversationNames.has("blocked")) {
    db.exec("ALTER TABLE conversations ADD COLUMN blocked INTEGER NOT NULL DEFAULT 0");
  }
  // Existing verified users stay active; unverified legacy rows stay blocked until mobile OTP flow replaces them.
  db.prepare(
    `UPDATE users
     SET status = CASE
       WHEN IFNULL(status, '') = '' AND verified = 1 THEN 'active'
       WHEN IFNULL(status, '') = '' THEN 'pending_approval'
       ELSE status
     END,
     name = COALESCE(name, '')`,
  ).run();
  db.exec(`
    CREATE UNIQUE INDEX IF NOT EXISTS users_mobile_key_live
      ON users (mobile_key)
      WHERE mobile_key IS NOT NULL AND status IN ('active', 'pending_approval');
    CREATE TABLE IF NOT EXISTS mobile_otps (
      id TEXT PRIMARY KEY,
      mobile_key TEXT NOT NULL,
      purpose TEXT NOT NULL,
      code_hash TEXT NOT NULL,
      payload TEXT,
      expires_at INTEGER NOT NULL,
      created_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS mobile_otps_lookup ON mobile_otps (mobile_key, purpose, created_at);
    CREATE TABLE IF NOT EXISTS mobile_otp_sends (
      mobile_key TEXT NOT NULL,
      at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS mobile_otp_sends_lookup ON mobile_otp_sends (mobile_key, at);
    CREATE TABLE IF NOT EXISTS approval_tokens (
      id TEXT PRIMARY KEY,
      token_hash TEXT NOT NULL UNIQUE,
      user_id TEXT NOT NULL,
      action TEXT NOT NULL,
      expires_at INTEGER NOT NULL,
      used_at INTEGER,
      created_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS approval_tokens_user ON approval_tokens (user_id, created_at);
    CREATE TABLE IF NOT EXISTS auth_audit (
      id TEXT PRIMARY KEY,
      at TEXT NOT NULL,
      actor_user_id TEXT,
      action TEXT NOT NULL,
      target_user_id TEXT,
      detail TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS approval_notify_failures (
      user_id TEXT PRIMARY KEY,
      last_error TEXT NOT NULL,
      failed_at TEXT NOT NULL,
      attempts INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS push_subscriptions (
      endpoint TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      p256dh TEXT NOT NULL,
      auth TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS push_subscriptions_user ON push_subscriptions (user_id);
  `);
}

export function getDb() {
  if (!globalDb.__waDb) {
    const file = databasePath();
    mkdirSync(path.dirname(file), { recursive: true });
    const db = new DatabaseSync(file);
    db.exec("PRAGMA journal_mode = WAL");
    db.exec("PRAGMA busy_timeout = 3000");
    globalDb.__waDb = db;
  }
  migrate(globalDb.__waDb);
  return globalDb.__waDb;
}
