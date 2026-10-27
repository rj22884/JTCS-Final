import { requireAdmin } from "@/lib/admin";
import { ensureRequestTime, json } from "@/lib/http";
import { generateVerifyToken } from "@/lib/whatsapp/cloud-state";
import type { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireAdmin(request);
  if (gate.error) return gate.error;
  try {
    const created = generateVerifyToken();
    if (!created.ok) return json({ ok: false, error: created.error }, 400);
    return json(created);
  } catch {
    return json({ ok: false, error: "storage_unavailable" }, 500);
  }
}
