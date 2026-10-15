import "server-only";

import { createHash } from "node:crypto";
import { getDb } from "@/lib/db";

function stringField(value: unknown, key: string) {
  if (!value || typeof value !== "object") return null;
  const field = (value as Record<string, unknown>)[key];
  return typeof field === "string" && field.trim() ? field : null;
}

export function eventIdsForPayload(rawBody: string, payload: unknown) {
  const ids: string[] = [];
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return ids;
  }

  const entries = (payload as { entry?: unknown }).entry;
  if (Array.isArray(entries)) {
    for (const entry of entries) {
      const changes = (entry as { changes?: unknown }).changes;
      if (!Array.isArray(changes)) continue;
      for (const change of changes) {
        const value = (change as { value?: unknown }).value;
        const messages = (value as { messages?: unknown } | null)?.messages;
        if (Array.isArray(messages)) {
          for (const message of messages) {
            const id = stringField(message, "id");
            if (id) ids.push(`message:${id}`);
          }
        }
        const statuses = (value as { statuses?: unknown } | null)?.statuses;
        if (Array.isArray(statuses)) {
          for (const status of statuses) {
            const id = stringField(status, "id");
            const name = stringField(status, "status") ?? "";
            if (id) ids.push(`status:${id}:${name}`);
          }
        }
      }
    }
  }

  if (ids.length > 0) return ids;
  const hash = createHash("sha256").update(rawBody).digest("hex");
  return [`body:${hash}`];
}

export function rememberEvents(ids: string[]) {
  const db = getDb();
  const insert = db.prepare("INSERT OR IGNORE INTO webhook_events (id, received_at) VALUES (?, ?)");
  const receivedAt = new Date().toISOString();
  let accepted = 0;
  db.exec("BEGIN");
  try {
    for (const id of ids) {
      const result = insert.run(id, receivedAt);
      if (result.changes > 0) accepted += 1;
    }
    db.exec("COMMIT");
  } catch (error) {
    db.exec("ROLLBACK");
    throw error;
  }
  return {
    duplicate: accepted === 0,
    accepted,
  };
}

export function isWhatsAppPayload(payload: unknown) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return false;
  return (payload as { object?: unknown }).object === "whatsapp_business_account";
}
