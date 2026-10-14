import "server-only";

import { createHash } from "node:crypto";

import { isAdminConfigured } from "@/lib/admin";
import { envNameFor, isPublicSecret, resolveSecret, type SecretKey } from "@/lib/secrets";
import type { CredentialFlag, IntegrationCheck, PublicWhatsAppStatus } from "@/lib/types";
import { probeAccessToken } from "@/lib/whatsapp/client";
import { idsAreDistinct } from "@/lib/whatsapp/subscribe-plan";

function flag(key: SecretKey, canEdit: boolean): CredentialFlag {
  const value = resolveSecret(key);
  const configured = typeof value === "string" && value.trim().length > 0;
  return {
    env: envNameFor(key),
    configured,
    preview: canEdit && isPublicSecret(key) && configured ? value : null,
  };
}

export function mailboxReady() {
  return Boolean(resolveSecret("phoneNumberId") && resolveSecret("accessToken"));
}

const probeCache = new Map<
  string,
  { at: number; ok: boolean; tokenInvalid: boolean; detail: string; checks: IntegrationCheck[] }
>();

export async function getPublicWhatsAppStatus(input: { canEdit: boolean }): Promise<PublicWhatsAppStatus> {
  const phoneNumberId = resolveSecret("phoneNumberId");
  const accessToken = resolveSecret("accessToken");
  const businessAccountId = resolveSecret("businessAccountId");
  const appId = resolveSecret("appId");
  const businessId = resolveSecret("businessId");
  const graphApiVersion = resolveSecret("graphApiVersion");
  const probeKey = createHash("sha256")
    .update(`v3\n${phoneNumberId ?? ""}\n${accessToken ?? ""}\n${businessAccountId ?? ""}\n${appId ?? ""}\n${businessId ?? ""}\n${graphApiVersion ?? ""}`)
    .digest("hex");
  const cached = probeCache.get(probeKey);
  let probe = cached && Date.now() - cached.at < 45_000 ? cached : null;
  if (!probe) {
    const result = await probeAccessToken({ phoneNumberId, accessToken, businessAccountId, appId, businessId, graphApiVersion });
    probe = {
      at: Date.now(),
      ok: result.ok,
      tokenInvalid: result.tokenInvalid,
      detail: result.detail,
      checks: result.checks.map((item) => ({
        id: item.id as IntegrationCheck["id"],
        label: item.label,
        state: item.state === "skipped" ? "not_checked" : item.state,
        badge: item.badge ?? item.state,
        detail: item.detail,
      })),
    };
    probeCache.set(probeKey, probe);
  }
  const ready = mailboxReady();
  const live = probe.ok;
  const credentials = {
    businessAccountId: flag("businessAccountId", input.canEdit),
    phoneNumberId: flag("phoneNumberId", input.canEdit),
    displayPhone: flag("displayPhone", input.canEdit),
    appId: flag("appId", input.canEdit),
    accessToken: flag("accessToken", input.canEdit),
    verifyToken: flag("verifyToken", input.canEdit),
    appSecret: flag("appSecret", input.canEdit),
    webhookUrl: flag("webhookUrl", input.canEdit),
    businessId: flag("businessId", input.canEdit),
    graphApiVersion: flag("graphApiVersion", input.canEdit),
  };
  return {
    connection: live ? "connected" : "not_connected",
    demoMode: !ready,
    integrationEnabled: live,
    webhookPath: "/api/whatsapp/webhook",
    productionWebhookUrl: resolveSecret("webhookUrl"),
    adminConfigured: isAdminConfigured(),
    canEdit: input.canEdit,
    credentials,
    tokenInvalid: probe.tokenInvalid,
    detail: probe.detail,
    checks: probe.checks,
    idsDistinct: idsAreDistinct(phoneNumberId, businessAccountId, businessId),
  };
}
