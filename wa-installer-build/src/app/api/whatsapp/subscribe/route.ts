import { requireAdmin } from "@/lib/admin";
import { ensureRequestTime, json } from "@/lib/http";
import { resolveSecret } from "@/lib/secrets";
import { subscribeAppToBusinessAccount } from "@/lib/whatsapp/client";
import type { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireAdmin(request);
  if (gate.error) return gate.error;
  try {
    const result = await subscribeAppToBusinessAccount({
      businessAccountId: resolveSecret("businessAccountId"),
      phoneNumberId: resolveSecret("phoneNumberId"),
      businessId: resolveSecret("businessId"),
      appId: resolveSecret("appId"),
      accessToken: resolveSecret("accessToken"),
      graphApiVersion: resolveSecret("graphApiVersion"),
    });
    const status = result.ok ? 200 : result.posted ? 502 : 409;
    return json(result, status);
  } catch {
    return json(
      {
        ok: false,
        posted: false,
        detail: "Meta did not finish subscribing this app. Nothing else was changed.",
        httpStatus: null,
        code: null,
        subcode: null,
        traceId: null,
        cause: "unknown",
      },
      500,
    );
  }
}
