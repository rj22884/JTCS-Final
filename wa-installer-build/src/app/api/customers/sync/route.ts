import { requireAdmin } from "@/lib/admin";
import { syncCustomerMasterFromErp } from "@/lib/customer-sync";
import { ensureRequestTime, json } from "@/lib/http";
import type { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireAdmin(request);
  if (gate.error) return gate.error;
  const result = await syncCustomerMasterFromErp();
  if (!result.ok) return json({ error: "sync_failed", detail: result.detail }, 502);
  return json({
    ok: true,
    created: result.created,
    updated: result.updated,
    unchanged: result.unchanged,
    skippedInvalidMobile: result.skippedInvalidMobile,
    duplicateInFeed: result.duplicateInFeed,
    conflicts: result.conflicts,
    renamed: result.renamedChats,
    detail: result.detail,
  });
}
