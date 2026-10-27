import { requireUser } from "@/lib/admin";
import { ensureRequestTime, json } from "@/lib/http";
import { hashPassword, isAcceptablePassword, verifyPassword } from "@/lib/passwords";
import { findUser, updatePassword } from "@/lib/users";
import type { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireUser(request);
  if (gate.error) return gate.error;
  if (!gate.session.email) return json({ ok: false, error: "unauthorized" }, 401);
  const raw = await request.text();
  if (raw.length > 2000) return json({ ok: false, error: "invalid_value" }, 400);
  let current = "";
  let next = "";
  try {
    const body = JSON.parse(raw) as { current?: unknown; next?: unknown };
    current = typeof body.current === "string" ? body.current : "";
    next = typeof body.next === "string" ? body.next : "";
  } catch {
    return json({ ok: false, error: "invalid_json" }, 400);
  }
  if (!isAcceptablePassword(next)) return json({ ok: false, error: "invalid_value" }, 400);
  const user = findUser(gate.session.email);
  if (!user || !verifyPassword(current, user.password_hash)) return json({ ok: false, error: "sign_in_failed" }, 401);
  try {
    updatePassword(user.id, hashPassword(next), gate.session.id);
    return json({ ok: true });
  } catch {
    return json({ ok: false, error: "storage_unavailable" }, 500);
  }
}
