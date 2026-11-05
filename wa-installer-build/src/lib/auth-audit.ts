import "server-only";

import { randomBytes } from "node:crypto";

import { getDb } from "@/lib/db";

export function writeAuthAudit(input: {
  actorUserId?: string | null;
  action: string;
  targetUserId?: string | null;
  detail: string;
}) {
  getDb()
    .prepare(
      `INSERT INTO auth_audit (id, at, actor_user_id, action, target_user_id, detail)
       VALUES (?, ?, ?, ?, ?, ?)`,
    )
    .run(
      randomBytes(16).toString("hex"),
      new Date().toISOString(),
      input.actorUserId ?? null,
      input.action,
      input.targetUserId ?? null,
      input.detail.slice(0, 2000),
    );
}
