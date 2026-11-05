import "server-only";

import {
  CUSTOMER_MASTER_BASE_URL,
  erpBaseUrl,
  matchCustomerMaster,
  type CustomerMasterRecord,
} from "@/lib/customer-master";
import { getDb } from "@/lib/db";
import { resolveOutboundErpSyncToken } from "@/lib/erp-sync-token";
import { DEFAULT_COUNTRY_CODE, normalizeContactMobile } from "@/lib/phone";
import { resolveSecret, saveSecret } from "@/lib/secrets";

export type SyncConflict = {
  erpId: string;
  name: string;
  mobile: string;
  phoneKey: string;
  existingId: string;
  existingName: string;
  detail: string;
};

export type SyncSummary = {
  created: number;
  updated: number;
  unchanged: number;
  skippedInvalidMobile: number;
  duplicateInFeed: number;
  conflicts: SyncConflict[];
  renamedChats: number;
};

type CustomerRow = {
  id: string;
  name: string;
  mobile: string;
  country_code?: string | null;
  phone_key: string;
  source?: string | null;
};

function listCached(): CustomerMasterRecord[] {
  const rows = getDb().prepare("SELECT id, name, mobile FROM customer_master ORDER BY name ASC").all() as CustomerRow[];
  return rows.map((row) => ({ id: row.id, name: row.name, mobile: row.mobile }));
}

const ERP_CONNECTION_META_KEY = "erp_sync_connection_meta";

export type ErpConnectionMeta = {
  ok: boolean;
  checkedAt: string;
  detail: string;
};

export function customerMasterCount(activeOnly = true) {
  const row = activeOnly
    ? (getDb()
        .prepare("SELECT COUNT(*) AS count FROM customer_master WHERE deleted_at IS NULL")
        .get() as { count: number | bigint })
    : (getDb().prepare("SELECT COUNT(*) AS count FROM customer_master").get() as { count: number | bigint });
  return Number(row.count);
}

function readErpConnectionMeta(): ErpConnectionMeta | null {
  const row = getDb().prepare("SELECT value FROM app_meta WHERE key = ?").get(ERP_CONNECTION_META_KEY) as
    | { value: string }
    | undefined;
  if (!row?.value) return null;
  try {
    const parsed = JSON.parse(row.value) as ErpConnectionMeta;
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

export function writeErpConnectionMeta(meta: ErpConnectionMeta | null) {
  if (!meta) {
    getDb().prepare("DELETE FROM app_meta WHERE key = ?").run(ERP_CONNECTION_META_KEY);
    return;
  }
  getDb()
    .prepare(
      `INSERT INTO app_meta (key, value) VALUES (?, ?)
       ON CONFLICT(key) DO UPDATE SET value = excluded.value`,
    )
    .run(ERP_CONNECTION_META_KEY, JSON.stringify(meta));
}

/** Connected only after a successful live ERP check while a token is configured. */
export function erpSyncConnectionStatus() {
  const tokenConfigured = Boolean(resolveOutboundErpSyncToken());
  const last = readErpConnectionMeta();
  if (!tokenConfigured) {
    return {
      connection: "disconnected" as const,
      tokenConfigured: false,
      lastCheckedAt: last?.checkedAt ?? null,
      lastOk: false,
      detail: "No sync token configured.",
    };
  }
  if (!last) {
    return {
      connection: "disconnected" as const,
      tokenConfigured: true,
      lastCheckedAt: null,
      lastOk: false,
      detail: "Token saved locally. Run Test connection to verify ERP accepts it.",
    };
  }
  return {
    connection: last.ok ? ("connected" as const) : ("disconnected" as const),
    tokenConfigured: true,
    lastCheckedAt: last.checkedAt,
    lastOk: last.ok,
    detail: last.detail,
  };
}

export function customerMasterMeta() {
  const row = getDb().prepare("SELECT value FROM app_meta WHERE key = ?").get("customer_master_last_sync") as
    | { value: string }
    | undefined;
  const connection = erpSyncConnectionStatus();
  return {
    count: customerMasterCount(true),
    lastSyncAt: row?.value ?? null,
    tokenConfigured: connection.tokenConfigured,
    baseUrl: erpBaseUrl(resolveSecret("erpBaseUrl")),
    loginUrl: `${erpBaseUrl(resolveSecret("erpBaseUrl"))}/login`,
    connection: connection.connection,
    connectionCheckedAt: connection.lastCheckedAt,
    connectionDetail: connection.detail,
  };
}

export function lookupCachedCustomer(phone: string) {
  return matchCustomerMaster(phone, listCached());
}

export function saveErpSyncToken(token: string) {
  return saveSecret("erpSyncToken", token);
}

export function saveErpBaseUrl(value: string) {
  return saveSecret("erpBaseUrl", value);
}

function parseDirectoryPayload(payload: unknown): CustomerMasterRecord[] {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return [];
  const rows =
    (payload as { customers?: unknown }).customers ??
    (payload as { rows?: unknown }).rows ??
    (payload as { data?: unknown }).data;
  if (!Array.isArray(rows)) return [];
  const out: CustomerMasterRecord[] = [];
  for (const row of rows) {
    if (!row || typeof row !== "object" || Array.isArray(row)) continue;
    const id = String(
      (row as { id?: unknown }).id ??
        (row as { customer_id?: unknown }).customer_id ??
        (row as { CustomerID?: unknown }).CustomerID ??
        "",
    ).trim();
    const name = String(
      (row as { name?: unknown }).name ??
        (row as { customer_name?: unknown }).customer_name ??
        (row as { CustomerName?: unknown }).CustomerName ??
        "",
    ).trim();
    const mobile = String(
      (row as { mobile?: unknown }).mobile ??
        (row as { mobile_number?: unknown }).mobile_number ??
        (row as { MobileNumber?: unknown }).MobileNumber ??
        (row as { whatsapp_number?: unknown }).whatsapp_number ??
        "",
    ).trim();
    if (!id || !name) continue;
    out.push({ id, name, mobile });
  }
  return out;
}

/** Pure sync planner for tests and upsert. */
export function planCustomerSync(records: readonly CustomerMasterRecord[], existing: readonly CustomerRow[]) {
  const summary: SyncSummary = {
    created: 0,
    updated: 0,
    unchanged: 0,
    skippedInvalidMobile: 0,
    duplicateInFeed: 0,
    conflicts: [],
    renamedChats: 0,
  };
  const byId = new Map(existing.map((row) => [row.id, row]));
  const byPhone = new Map(existing.map((row) => [row.phone_key, row]));
  const seenPhoneInFeed = new Map<string, CustomerMasterRecord>();
  const upserts: Array<{
    id: string;
    name: string;
    mobile: string;
    countryCode: string;
    phoneKey: string;
    mode: "create" | "update" | "unchanged";
  }> = [];

  const sorted = [...records].sort((a, b) => a.id.localeCompare(b.id));
  for (const record of sorted) {
    const name = record.name.trim().slice(0, 200);
    if (!name) {
      summary.skippedInvalidMobile += 1;
      continue;
    }
    // ERP local mobiles default to +91 India; full E.164 from ERP is split into country + national.
    const mobile = normalizeContactMobile(DEFAULT_COUNTRY_CODE, record.mobile);
    if (!mobile.valid) {
      summary.skippedInvalidMobile += 1;
      continue;
    }
    const priorInFeed = seenPhoneInFeed.get(mobile.phoneKey);
    if (priorInFeed && priorInFeed.id !== record.id) {
      summary.duplicateInFeed += 1;
      summary.conflicts.push({
        erpId: record.id,
        name,
        mobile: mobile.national,
        phoneKey: mobile.phoneKey,
        existingId: priorInFeed.id,
        existingName: priorInFeed.name,
        detail: `Duplicate mobile in ERP feed; kept ERP id ${priorInFeed.id}, skipped ${record.id}.`,
      });
      continue;
    }
    seenPhoneInFeed.set(mobile.phoneKey, { id: record.id, name, mobile: mobile.national });

    const sameId = byId.get(record.id);
    const samePhone = byPhone.get(mobile.phoneKey);
    if (samePhone && samePhone.id !== record.id) {
      summary.conflicts.push({
        erpId: record.id,
        name,
        mobile: mobile.national,
        phoneKey: mobile.phoneKey,
        existingId: samePhone.id,
        existingName: samePhone.name,
        detail: `Mobile already belongs to contact ${samePhone.id}. Not merged or overwritten.`,
      });
      continue;
    }
    if (!sameId) {
      summary.created += 1;
      upserts.push({
        id: record.id,
        name,
        mobile: mobile.national,
        countryCode: mobile.countryCode,
        phoneKey: mobile.phoneKey,
        mode: "create",
      });
      continue;
    }
    const sameCountry = sameId.country_code || DEFAULT_COUNTRY_CODE;
    if (
      sameId.name === name &&
      sameId.mobile === mobile.national &&
      sameCountry === mobile.countryCode &&
      sameId.phone_key === mobile.phoneKey
    ) {
      summary.unchanged += 1;
      upserts.push({
        id: record.id,
        name,
        mobile: mobile.national,
        countryCode: mobile.countryCode,
        phoneKey: mobile.phoneKey,
        mode: "unchanged",
      });
      continue;
    }
    summary.updated += 1;
    upserts.push({
      id: record.id,
      name,
      mobile: mobile.national,
      countryCode: mobile.countryCode,
      phoneKey: mobile.phoneKey,
      mode: "update",
    });
  }

  return { summary, upserts };
}

function applyUpserts(upserts: ReturnType<typeof planCustomerSync>["upserts"]) {
  const db = getDb();
  const now = new Date().toISOString();
  const insert = db.prepare(
    `INSERT INTO customer_master
      (id, name, mobile, country_code, phone_key, source, notes, synced_at, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, 'erp', '', ?, ?, ?)`,
  );
  const update = db.prepare(
    `UPDATE customer_master
     SET name = ?, mobile = ?, country_code = ?, phone_key = ?, source = 'erp', synced_at = ?, updated_at = ?
     WHERE id = ?`,
  );
  const touch = db.prepare(`UPDATE customer_master SET synced_at = ?, source = 'erp' WHERE id = ?`);
  db.exec("BEGIN");
  try {
    for (const row of upserts) {
      if (row.mode === "create") {
        insert.run(row.id, row.name, row.mobile, row.countryCode, row.phoneKey, now, now, now);
      } else if (row.mode === "update") {
        update.run(row.name, row.mobile, row.countryCode, row.phoneKey, now, now, row.id);
      } else {
        touch.run(now, row.id);
      }
    }
    db.prepare(
      `INSERT INTO app_meta (key, value) VALUES (?, ?)
       ON CONFLICT(key) DO UPDATE SET value = excluded.value`,
    ).run("customer_master_last_sync", now);
    db.exec("COMMIT");
  } catch (error) {
    db.exec("ROLLBACK");
    throw error;
  }
}

export function applyCustomerNamesToConversations() {
  const records = listCached();
  if (records.length === 0) return 0;
  const db = getDb();
  const conversations = db.prepare("SELECT id, phone, name FROM conversations").all() as {
    id: string;
    phone: string;
    name: string;
  }[];
  const update = db.prepare("UPDATE conversations SET name = ?, updated_at = ? WHERE id = ?");
  const now = new Date().toISOString();
  let renamed = 0;
  db.exec("BEGIN");
  try {
    for (const conversation of conversations) {
      const match = matchCustomerMaster(conversation.phone, records);
      if (match.state !== "one") continue;
      const nextName = match.matches[0].name.trim();
      if (!nextName || nextName === conversation.name) continue;
      update.run(nextName, now, conversation.id);
      renamed += 1;
    }
    db.exec("COMMIT");
  } catch (error) {
    db.exec("ROLLBACK");
    throw error;
  }
  return renamed;
}

export function resolveCustomerName(phone: string, fallback: string | null) {
  const match = lookupCachedCustomer(phone);
  if (match.state === "one") return match.matches[0].name;
  return fallback?.trim() || null;
}

export function upsertCustomerRecords(records: readonly CustomerMasterRecord[]) {
  const existing = getDb()
    .prepare(
      `SELECT id, name, mobile, IFNULL(country_code, '91') AS country_code, phone_key, IFNULL(source, 'erp') AS source FROM customer_master`,
    )
    .all() as CustomerRow[];
  const planned = planCustomerSync(records, existing);
  applyUpserts(planned.upserts);
  planned.summary.renamedChats = applyCustomerNamesToConversations();
  return planned.summary;
}

async function fetchErpCustomerDirectory() {
  const token = resolveOutboundErpSyncToken();
  if (!token) {
    return {
      ok: false as const,
      unauthorized: false,
      detail: "ERP sync token missing. Generate or save WHATSAPP_CUSTOMER_SYNC_TOKEN, and set the same value on app.jtcsxpert.com.",
      payload: null as unknown,
      base: erpBaseUrl(resolveSecret("erpBaseUrl") || CUSTOMER_MASTER_BASE_URL),
    };
  }
  const base = erpBaseUrl(resolveSecret("erpBaseUrl") || CUSTOMER_MASTER_BASE_URL);
  const url = `${base}/api/crm/whatsapp/customer-directory`;
  let response: Response;
  try {
    response = await fetch(url, {
      method: "GET",
      headers: {
        Accept: "application/json",
        "X-WhatsApp-Sync-Token": token,
      },
      signal: AbortSignal.timeout(30_000),
      cache: "no-store",
    });
  } catch {
    return {
      ok: false as const,
      unauthorized: false,
      detail: `Could not reach ${base}. Check ERP_BASE_URL and network.`,
      payload: null as unknown,
      base,
    };
  }
  const text = await response.text();
  let payload: unknown = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    return {
      ok: false as const,
      unauthorized: false,
      detail: "ERP did not return JSON for the customer directory.",
      payload: null,
      base,
    };
  }
  if (response.status === 401 || response.status === 403) {
    return {
      ok: false as const,
      unauthorized: true,
      detail: "ERP rejected the sync token (unauthorized).",
      payload,
      base,
    };
  }
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && typeof (payload as { error?: unknown }).error === "string"
        ? (payload as { error: string }).error
        : `ERP returned HTTP ${response.status}.`;
    return { ok: false as const, unauthorized: false, detail, payload, base };
  }
  return { ok: true as const, unauthorized: false, detail: "ERP accepted the sync token.", payload, base };
}

/** Live check against ERP. Never returns the token. Persists Connected/Disconnected result. */
export async function testErpSyncConnection() {
  const checkedAt = new Date().toISOString();
  const result = await fetchErpCustomerDirectory();
  if (!result.ok) {
    writeErpConnectionMeta({ ok: false, checkedAt, detail: result.detail });
    return {
      ok: false as const,
      connection: "disconnected" as const,
      checkedAt,
      detail: result.detail,
    };
  }
  const records = parseDirectoryPayload(result.payload);
  const detail =
    records.length > 0
      ? `Connected to ERP. Directory reachable (${records.length} row${records.length === 1 ? "" : "s"} evaluated).`
      : "Connected to ERP. Directory reachable (empty list).";
  writeErpConnectionMeta({ ok: true, checkedAt, detail });
  return {
    ok: true as const,
    connection: "connected" as const,
    checkedAt,
    detail,
  };
}

export async function syncCustomerMasterFromErp() {
  const result = await fetchErpCustomerDirectory();
  const checkedAt = new Date().toISOString();
  if (!result.ok) {
    writeErpConnectionMeta({ ok: false, checkedAt, detail: result.detail });
    return { ok: false as const, detail: result.detail };
  }
  writeErpConnectionMeta({
    ok: true,
    checkedAt,
    detail: "Connected to ERP. Directory reachable.",
  });
  const records = parseDirectoryPayload(result.payload);
  if (records.length === 0) {
    return { ok: false as const, detail: "ERP returned no CustomerMaster rows to evaluate." };
  }
  try {
    const summary = upsertCustomerRecords(records);
    const conflictNote =
      summary.conflicts.length > 0 ? ` Conflicts: ${summary.conflicts.length} (not merged).` : "";
    return {
      ok: true as const,
      ...summary,
      detail: `Created ${summary.created}, updated ${summary.updated}, unchanged ${summary.unchanged}, skipped invalid mobile ${summary.skippedInvalidMobile}, duplicate-in-feed ${summary.duplicateInFeed}. Renamed ${summary.renamedChats} chats.${conflictNote}`,
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : "sync_failed";
    if (/UNIQUE/i.test(message)) {
      return {
        ok: false as const,
        detail: "Sync stopped on a mobile uniqueness conflict. No silent merge was applied.",
      };
    }
    return { ok: false as const, detail: "Sync failed while saving contacts." };
  }
}
