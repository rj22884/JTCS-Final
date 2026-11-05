import { requireAdmin } from "@/lib/admin";
import { ensureRequestTime, json } from "@/lib/http";
import { permanentlyDeleteUser } from "@/lib/users";
import type { NextRequest } from "next/server";

export async function POST(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  await ensureRequestTime();
  const gate = requireAdmin(request);
  if (gate.error) return gate.error;
  const { id } = await context.params;
  const result = permanentlyDeleteUser(id, gate.session!.userId!);
  if (!result.ok) {
    const status = result.error === "not_found" ? 404 : 409;
    return json({ ok: false, error: result.error, detail: result.detail }, status);
  }
  return json({ ok: true, detail: result.detail });
}
