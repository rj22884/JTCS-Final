import { requireUser } from "@/lib/admin";
import { undeleteContact } from "@/lib/contacts";
import { ensureRequestTime, json } from "@/lib/http";
import type { NextRequest } from "next/server";

export async function POST(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  await ensureRequestTime();
  const gate = requireUser(request);
  if (gate.error) return gate.error;
  const { id } = await context.params;
  const result = undeleteContact(id);
  if (!result.ok) {
    const status =
      result.error === "not_found" ? 404 : result.error === "duplicate_mobile" ? 409 : result.error === "not_deleted" ? 400 : 400;
    return json({ error: result.error, detail: result.detail }, status);
  }
  return json({ ok: true, contact: result.contact });
}
