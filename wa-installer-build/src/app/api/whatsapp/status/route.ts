import { hasAdminSession, requireSession } from "@/lib/admin";
import { ensureRequestTime, json } from "@/lib/http";
import { getPublicWhatsAppStatus } from "@/lib/whatsapp/status";
import type { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireSession(request);
  if (gate.error) return gate.error;
  try {
    return json(await getPublicWhatsAppStatus({ canEdit: hasAdminSession(request) }));
  } catch {
    return json({ ok: false, error: "storage_unavailable" }, 500);
  }
}
