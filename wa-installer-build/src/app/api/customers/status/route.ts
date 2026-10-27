import { hasAdminSession, requireSession } from "@/lib/admin";
import { customerMasterMeta, erpSyncConnectionStatus } from "@/lib/customer-sync";
import { erpSyncTokenStatus } from "@/lib/erp-sync-token";
import { ensureRequestTime, json } from "@/lib/http";
import type { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireSession(request);
  if (gate.error) return gate.error;
  const meta = customerMasterMeta();
  const token = erpSyncTokenStatus();
  const connection = erpSyncConnectionStatus();
  if (!hasAdminSession(request)) {
    return json({
      count: meta.count,
      lastSyncAt: meta.lastSyncAt,
      tokenConfigured: false,
      connection: "disconnected",
      loginUrl: meta.loginUrl,
      detail: "Sign in as admin to manage the ERP sync token or run Sync.",
    });
  }
  return json({
    ...meta,
    tokenConfigured: token.configured,
    tokenPreview: token.preview,
    tokenSource: token.source,
    tokenCreatedAt: token.createdAt,
    connection: connection.connection,
    connectionCheckedAt: connection.lastCheckedAt,
    connectionDetail: connection.detail,
    detail: token.configured
      ? connection.connection === "connected"
        ? "ERP sync connected. Sync pulls CustomerMaster name/phone for valid mobiles only."
        : connection.detail ||
          "Token saved locally. Run Test connection to verify ERP accepts it before relying on Sync."
      : "Generate an ERP sync token, copy it once, and set the same value on app.jtcsxpert.com as WHATSAPP_CUSTOMER_SYNC_TOKEN.",
  });
}
