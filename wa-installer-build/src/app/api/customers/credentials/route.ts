import { requireAdmin } from "@/lib/admin";
import { customerMasterMeta, saveErpBaseUrl, saveErpSyncToken, writeErpConnectionMeta } from "@/lib/customer-sync";
import { erpSyncTokenStatus } from "@/lib/erp-sync-token";
import { ensureRequestTime, json } from "@/lib/http";
import { getDb } from "@/lib/db";
import type { NextRequest } from "next/server";

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
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return json({ error: "invalid_body" }, 400);
  }

  const syncToken = (body as { syncToken?: unknown }).syncToken;
  const baseUrl = (body as { baseUrl?: unknown }).baseUrl;
  let saved = false;
  if (typeof syncToken === "string" && syncToken.trim()) {
    if (!saveErpSyncToken(syncToken)) {
      return json({ error: "invalid_value", detail: "Sync token must be at least 16 characters." }, 400);
    }
    const createdAt = new Date().toISOString();
    getDb()
      .prepare(
        `INSERT INTO app_meta (key, value) VALUES (?, ?)
         ON CONFLICT(key) DO UPDATE SET value = excluded.value`,
      )
      .run("erp_sync_token_meta", JSON.stringify({ createdAt, prefix: "saved" }));
    writeErpConnectionMeta({
      ok: false,
      checkedAt: createdAt,
      detail: "Token saved locally. Run Test connection to verify ERP accepts it.",
    });
    saved = true;
  }
  if (typeof baseUrl === "string" && baseUrl.trim()) {
    if (!saveErpBaseUrl(baseUrl)) {
      return json({ error: "invalid_value", detail: "ERP base URL must be a public https origin." }, 400);
    }
    saved = true;
  }
  if (!saved) return json({ error: "invalid_value", detail: "Enter a sync token or base URL to save." }, 400);
  return json({
    ok: true,
    detail: "ERP sync credentials saved. The token value is not returned again.",
    ...customerMasterMeta(),
    ...erpSyncTokenStatus(),
  });
}
