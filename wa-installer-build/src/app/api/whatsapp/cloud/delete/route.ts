import { requireAdmin } from "@/lib/admin";
import { ensureRequestTime, json } from "@/lib/http";
import { deleteCloudValues } from "@/lib/whatsapp/cloud-state";
import type { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireAdmin(request);
  if (gate.error) return gate.error;
  try {
    return json({ ok: true, ...deleteCloudValues() });
  } catch {
    return json({ ok: false, error: "storage_unavailable" }, 500);
  }
}
