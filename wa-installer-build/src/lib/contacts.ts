import "server-only";

import { sortContacts, type ContactSort } from "@/lib/contact-sort";
import { getDb } from "@/lib/db";
import { normalizeLabelList, sanitizeLabels } from "@/lib/labels";
import {
  coerceContactNameMobile,
  DEFAULT_COUNTRY_CODE,
  formatContactDisplay,
  normalizeContactMobile,
  normalizeCountryCode,
  splitStoredMobile,
} from "@/lib/phone";
import type { Label } from "@/lib/types";

export type { ContactSort };
export { sortContacts };

export type ContactSource = "erp" | "manual";

export type Contact = {
  id: string;
  name: string;
  /** National / local mobile (ERP sync value or form field). */
  mobile: string;
  countryCode: string;
  /** Full international digits without + (countryCode + mobile). */
  fullMobile: string;
  displayMobile: string;
  phoneKey: string;
  source: ContactSource;
  notes: string;
  labels: Label[];
  deletedAt: string | null;
  syncedAt: string | null;
  createdAt: string;
  updatedAt: string;
};

type ContactRow = {
  id: string;
  name: string;
  mobile: string;
  country_code: string | null;
  phone_key: string;
  source: string;
  notes: string | null;
  labels: string | null;
  deleted_at: string | null;
  synced_at: string | null;
  created_at: string;
  updated_at: string;
};

function parseContactLabels(raw: string | null | undefined): Label[] {
  if (!raw) return [];
  try {
    return normalizeLabelList(JSON.parse(raw) as unknown);
  } catch {
    return [];
  }
}

function toContact(row: ContactRow): Contact {
  const split = splitStoredMobile(row.mobile, row.country_code || DEFAULT_COUNTRY_CODE);
  return {
    id: row.id,
    name: row.name,
    mobile: split.national || row.mobile,
    countryCode: split.countryCode,
    fullMobile: split.fullDigits,
    displayMobile: formatContactDisplay(split.countryCode, split.national || row.mobile),
    phoneKey: row.phone_key,
    source: row.source === "erp" ? "erp" : "manual",
    notes: row.notes ?? "",
    labels: parseContactLabels(row.labels),
    deletedAt: row.deleted_at,
    syncedAt: row.synced_at,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

const CONTACT_SELECT = `SELECT id, name, mobile, IFNULL(country_code, '91') AS country_code, phone_key,
       IFNULL(source, 'erp') AS source, IFNULL(notes, '') AS notes, IFNULL(labels, '[]') AS labels,
       deleted_at, synced_at, IFNULL(created_at, synced_at) AS created_at, IFNULL(updated_at, synced_at) AS updated_at
       FROM customer_master`;

/** Keep matching chat thread groups in sync with the CRM contact. */
export function syncConversationLabelsForPhone(fullMobileDigits: string, labels: Label[]) {
  const digits = fullMobileDigits.replace(/\D/g, "");
  if (digits.length < 8) return;
  const id = `p-${digits}`;
  const now = new Date().toISOString();
  getDb()
    .prepare(`UPDATE conversations SET labels = ?, updated_at = ? WHERE id = ? OR REPLACE(REPLACE(REPLACE(phone, '+', ''), '-', ''), ' ', '') = ?`)
    .run(JSON.stringify(labels), now, id, digits);
}

export function syncContactLabelsForPhone(fullMobileDigits: string, labels: Label[]) {
  const digits = fullMobileDigits.replace(/\D/g, "");
  if (digits.length < 8) return;
  const key = digits.length > 10 ? digits.slice(-10) : digits;
  const contact = findContactByPhoneKey(key);
  if (!contact || contact.deletedAt) return;
  const now = new Date().toISOString();
  getDb()
    .prepare(`UPDATE customer_master SET labels = ?, updated_at = ? WHERE id = ?`)
    .run(JSON.stringify(labels), now, contact.id);
}

function matchesQuery(contact: Contact, query: string) {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const digits = q.replace(/\D/g, "");
  return (
    contact.name.toLowerCase().includes(q) ||
    (digits.length > 0 &&
      (contact.mobile.includes(digits) ||
        contact.fullMobile.includes(digits) ||
        contact.phoneKey.includes(digits) ||
        contact.countryCode.includes(digits)))
  );
}

export function listContacts(query = "") {
  const rows = getDb()
    .prepare(
      `${CONTACT_SELECT}
       ORDER BY CASE WHEN deleted_at IS NULL THEN 0 ELSE 1 END, name COLLATE NOCASE ASC, id ASC`,
    )
    .all() as ContactRow[];
  const contacts = rows.map(toContact);
  if (!query.trim()) return contacts;
  return sortContacts(contacts.filter((item) => matchesQuery(item, query)));
}

export function getContact(id: string) {
  const row = getDb().prepare(`${CONTACT_SELECT} WHERE id = ?`).get(id) as ContactRow | undefined;
  return row ? toContact(row) : null;
}

export function findContactByPhoneKey(phoneKey: string, exceptId?: string) {
  const row = exceptId
    ? (getDb()
        .prepare(`${CONTACT_SELECT} WHERE phone_key = ? AND id != ?`)
        .get(phoneKey, exceptId) as ContactRow | undefined)
    : (getDb().prepare(`${CONTACT_SELECT} WHERE phone_key = ?`).get(phoneKey) as ContactRow | undefined);
  return row ? toContact(row) : null;
}

export function contactLinkedConversationCount(phoneDigitsOrKey: string) {
  const digits = phoneDigitsOrKey.replace(/\D/g, "");
  if (!digits) return 0;
  const key = digits.length > 10 ? digits.slice(-10) : digits;
  const row = getDb()
    .prepare(
      `SELECT COUNT(*) AS count FROM conversations
       WHERE REPLACE(REPLACE(REPLACE(phone, '+', ''), '-', ''), ' ', '') LIKE ?`,
    )
    .get(`%${key}`) as { count: number | bigint };
  return Number(row.count);
}

export function createContact(input: {
  name: string;
  mobile: string;
  countryCode?: string;
  notes?: string;
  labels?: Label[];
}) {
  const coerced = coerceContactNameMobile(input.name, input.mobile);
  const name = coerced.name.slice(0, 200);
  if (!name) return { ok: false as const, error: "invalid_name", detail: "Name is required." };
  const mobile = normalizeContactMobile(input.countryCode ?? DEFAULT_COUNTRY_CODE, coerced.mobile);
  if (!mobile.valid) return { ok: false as const, error: "invalid_mobile", detail: mobile.reason || "Mobile is invalid." };
  const existing = findContactByPhoneKey(mobile.phoneKey);
  if (existing && !existing.deletedAt) {
    return {
      ok: false as const,
      error: "duplicate_mobile",
      detail: `Mobile already used by contact “${existing.name}”.`,
    };
  }
  let labels: Label[] = [];
  if (input.labels !== undefined) {
    const checked = sanitizeLabels(input.labels);
    if (!checked.ok) return { ok: false as const, error: "invalid_labels", detail: checked.error };
    labels = checked.labels;
  }
  const now = new Date().toISOString();
  const id = existing?.deletedAt ? existing.id : `manual-${crypto.randomUUID()}`;
  try {
    if (existing?.deletedAt) {
      getDb()
        .prepare(
          `UPDATE customer_master
           SET name = ?, mobile = ?, country_code = ?, phone_key = ?, source = 'manual', notes = ?, labels = ?,
               deleted_at = NULL, synced_at = ?, created_at = COALESCE(created_at, ?), updated_at = ?
           WHERE id = ?`,
        )
        .run(
          name,
          mobile.national,
          mobile.countryCode,
          mobile.phoneKey,
          (input.notes ?? "").trim().slice(0, 2000),
          JSON.stringify(labels),
          now,
          now,
          now,
          id,
        );
    } else {
      getDb()
        .prepare(
          `INSERT INTO customer_master
            (id, name, mobile, country_code, phone_key, source, notes, labels, deleted_at, synced_at, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'manual', ?, ?, NULL, ?, ?, ?)`,
        )
        .run(
          id,
          name,
          mobile.national,
          mobile.countryCode,
          mobile.phoneKey,
          (input.notes ?? "").trim().slice(0, 2000),
          JSON.stringify(labels),
          now,
          now,
          now,
        );
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (/UNIQUE/i.test(message)) {
      return { ok: false as const, error: "duplicate_mobile", detail: "Mobile number already exists." };
    }
    throw error;
  }
  const contact = getContact(id)!;
  syncConversationLabelsForPhone(contact.fullMobile, contact.labels);
  return { ok: true as const, contact };
}

export function updateContact(
  id: string,
  input: { name: string; mobile: string; countryCode?: string; notes?: string; labels?: Label[] },
) {
  const current = getContact(id);
  if (!current) return { ok: false as const, error: "not_found", detail: "Contact not found." };
  if (current.deletedAt) {
    return { ok: false as const, error: "deleted", detail: "Restore this contact before editing." };
  }
  const coerced = coerceContactNameMobile(input.name, input.mobile);
  const name = coerced.name.slice(0, 200);
  if (!name) return { ok: false as const, error: "invalid_name", detail: "Name is required." };
  const mobile = normalizeContactMobile(input.countryCode ?? current.countryCode, coerced.mobile);
  if (!mobile.valid) return { ok: false as const, error: "invalid_mobile", detail: mobile.reason || "Mobile is invalid." };
  const conflict = findContactByPhoneKey(mobile.phoneKey, id);
  if (conflict && !conflict.deletedAt) {
    return {
      ok: false as const,
      error: "duplicate_mobile",
      detail: `Mobile already used by contact “${conflict.name}”.`,
    };
  }
  let labels = current.labels;
  if (input.labels !== undefined) {
    const checked = sanitizeLabels(input.labels);
    if (!checked.ok) return { ok: false as const, error: "invalid_labels", detail: checked.error };
    labels = checked.labels;
  }
  const now = new Date().toISOString();
  try {
    getDb()
      .prepare(
        `UPDATE customer_master
         SET name = ?, mobile = ?, country_code = ?, phone_key = ?, notes = ?, labels = ?, updated_at = ?
         WHERE id = ?`,
      )
      .run(
        name,
        mobile.national,
        mobile.countryCode,
        mobile.phoneKey,
        (input.notes ?? current.notes).trim().slice(0, 2000),
        JSON.stringify(labels),
        now,
        id,
      );
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (/UNIQUE/i.test(message)) {
      return { ok: false as const, error: "duplicate_mobile", detail: "Mobile number already exists." };
    }
    throw error;
  }
  const contact = getContact(id)!;
  syncConversationLabelsForPhone(contact.fullMobile, contact.labels);
  return { ok: true as const, contact };
}

/** Soft-delete in this app only. Never mutates ERP CustomerMaster. Preserves chats/messages. */
export function deleteContact(id: string) {
  const current = getContact(id);
  if (!current) return { ok: false as const, error: "not_found", detail: "Contact not found." };
  if (current.deletedAt) {
    return { ok: false as const, error: "already_deleted", detail: "Contact is already deleted.", contact: current };
  }
  const now = new Date().toISOString();
  getDb()
    .prepare(`UPDATE customer_master SET deleted_at = ?, updated_at = ? WHERE id = ?`)
    .run(now, now, id);
  return { ok: true as const, contact: getContact(id)! };
}

export function undeleteContact(id: string) {
  const current = getContact(id);
  if (!current) return { ok: false as const, error: "not_found", detail: "Contact not found." };
  if (!current.deletedAt) {
    return { ok: false as const, error: "not_deleted", detail: "Contact is already active.", contact: current };
  }
  const conflict = findContactByPhoneKey(current.phoneKey, id);
  if (conflict && !conflict.deletedAt) {
    return {
      ok: false as const,
      error: "duplicate_mobile",
      detail: `Cannot restore: mobile already used by active contact “${conflict.name}”.`,
    };
  }
  const now = new Date().toISOString();
  getDb()
    .prepare(`UPDATE customer_master SET deleted_at = NULL, updated_at = ? WHERE id = ?`)
    .run(now, id);
  return { ok: true as const, contact: getContact(id)! };
}

/** Conversation id used by the live inbox (`p-{fullInternationalDigits}`). */
export function conversationIdForContactMobile(mobile: string, countryCode = DEFAULT_COUNTRY_CODE) {
  const parsed = normalizeContactMobile(countryCode, mobile);
  return parsed.valid ? `p-${parsed.digits}` : null;
}

export function contactDialDigits(contact: Pick<Contact, "countryCode" | "mobile" | "fullMobile">) {
  if (contact.fullMobile) return contact.fullMobile;
  return normalizeContactMobile(normalizeCountryCode(contact.countryCode), contact.mobile).digits;
}
