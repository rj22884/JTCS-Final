import { requireAdmin } from "@/lib/admin";
import { erpSyncConnectionStatus, testErpSyncConnection } from "@/lib/customer-sync";
import { ensureRequestTime, json } from "@/lib/http";
import type { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireAdmin(request);
  if (gate.error) return gate.error;
  const result = await testErpSyncConnection();
  const status = erpSyncConnectionStatus();
  return json(
    {
      ok: result.ok,
      connection: result.connection,
      checkedAt: result.checkedAt,
      detail: result.detail,
      tokenConfigured: status.tokenConfigured,
    },
    result.ok ? 200 : 502,
  );
}
