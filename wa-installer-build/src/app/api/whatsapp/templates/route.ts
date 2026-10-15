import { requireSession } from "@/lib/admin";
import { listCloudTemplates } from "@/lib/whatsapp/client";
import { ensureRequestTime, json } from "@/lib/http";
import { resolveSecret } from "@/lib/secrets";
import { mailboxReady } from "@/lib/whatsapp/status";
import type { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireSession(request);
  if (gate.error) return gate.error;
  if (!mailboxReady()) {
    return json({ error: "not_connected", detail: "Template messages need a connected WhatsApp Business account." }, 409);
  }
  const businessAccountId = resolveSecret("businessAccountId");
  const accessToken = resolveSecret("accessToken");
  if (!businessAccountId || !accessToken) {
    return json({ error: "not_connected", detail: "The WhatsApp Business account is not ready." }, 409);
  }
  const result = await listCloudTemplates({
    businessAccountId,
    accessToken,
    graphApiVersion: resolveSecret("graphApiVersion"),
  });
  if (!result.ok) return json({ error: "list_failed", detail: result.detail }, 502);
  const templates = result.templates.filter((item) => item.status.toUpperCase() === "APPROVED");
  return json({ templates });
}
