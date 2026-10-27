import { requireAdmin } from "@/lib/admin";
import { erpSyncConnectionStatus, writeErpConnectionMeta } from "@/lib/customer-sync";
import { erpSyncTokenStatus, generateErpSyncToken, revokeErpSyncToken } from "@/lib/erp-sync-token";
import { ensureRequestTime, json } from "@/lib/http";
import type { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireAdmin(request);
  if (gate.error) return gate.error;
  const connection = erpSyncConnectionStatus();
  return json({
    ok: true,
    ...erpSyncTokenStatus(),
    connection: connection.connection,
    connectionCheckedAt: connection.lastCheckedAt,
    connectionDetail: connection.detail,
    detail:
      "This outbound token authenticates Sync customers calls to app.jtcsxpert.com (/api/crm/whatsapp/customer-directory). Plaintext is never returned after generate.",
  });
}

export async function POST(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireAdmin(request);
  if (gate.error) return gate.error;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return json({ error: "invalid_json" }, 400);
  }
  const action = body && typeof body === "object" && !Array.isArray(body) ? (body as { action?: unknown }).action : null;
  if (action === "generate") {
    const result = generateErpSyncToken();
    if (!result.ok) return json({ error: "generate_failed", detail: result.detail }, 500);
    writeErpConnectionMeta({
      ok: false,
      checkedAt: new Date().toISOString(),
      detail: "New token generated. Run Test connection after updating ERP.",
    });
    const status = erpSyncTokenStatus();
    const connection = erpSyncConnectionStatus();
    return json({
      ok: true,
      token: result.token,
      detail: result.detail,
      ...status,
      createdAt: result.createdAt,
      connection: connection.connection,
      connectionCheckedAt: connection.lastCheckedAt,
      connectionDetail: connection.detail,
    });
  }
  if (action === "revoke") {
    const result = revokeErpSyncToken();
    writeErpConnectionMeta({
      ok: false,
      checkedAt: new Date().toISOString(),
      detail: "Token revoked. Sync is disconnected until a new token is configured and tested.",
    });
    const connection = erpSyncConnectionStatus();
    return json({
      ok: true,
      detail: result.detail,
      ...erpSyncTokenStatus(),
      connection: connection.connection,
      connectionCheckedAt: connection.lastCheckedAt,
      connectionDetail: connection.detail,
    });
  }
  return json({ error: "invalid_action", detail: "Use action generate or revoke." }, 400);
}
