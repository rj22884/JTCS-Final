import "server-only";

import { randomBytes } from "node:crypto";

import { clearSecret, resolveSecret, saveSecret, type SecretKey } from "@/lib/secrets";
import {
  blankSecretPreserved,
  missingCloudLabels,
  normalizeCloudPhone,
  normalizeGraphVersion,
  validateCloudValues,
  type CloudValues,
} from "@/lib/whatsapp/cloud-form";

const FIELD_TO_SECRET = {
  app_id: "appId",
  app_secret: "appSecret",
  phone_number: "displayPhone",
  phone_number_id: "phoneNumberId",
  waba_id: "businessAccountId",
  business_id: "businessId",
  graph_api_version: "graphApiVersion",
  access_token: "accessToken",
  webhook_verify_token: "verifyToken",
} as const satisfies Record<keyof CloudValues, SecretKey>;

export function cloudFieldState() {
  const values = {
    app_id: resolveSecret("appId") ?? "",
    phone_number: resolveSecret("displayPhone") ?? "",
    phone_number_id: resolveSecret("phoneNumberId") ?? "",
    waba_id: resolveSecret("businessAccountId") ?? "",
    business_id: resolveSecret("businessId") ?? "",
    graph_api_version: resolveSecret("graphApiVersion") || "v21.0",
  };
  const secrets = {
    app_secret: Boolean(resolveSecret("appSecret")),
    access_token: Boolean(resolveSecret("accessToken")),
    webhook_verify_token: Boolean(resolveSecret("verifyToken")),
  };
  const hasSaved = Boolean(
    values.app_id ||
      values.phone_number_id ||
      values.waba_id ||
      values.business_id ||
      secrets.app_secret ||
      secrets.access_token ||
      secrets.webhook_verify_token,
  );
  return {
    field_values: values,
    secret_configured: secrets,
    missing_labels: missingCloudLabels({ values, secrets }),
    has_saved: hasSaved,
    webhook_url: resolveSecret("webhookUrl"),
  };
}

export function saveCloudValues(values: CloudValues) {
  const error = validateCloudValues(values);
  if (error) return { ok: false as const, error };
  for (const [field, key] of Object.entries(FIELD_TO_SECRET) as [keyof CloudValues, SecretKey][]) {
    if (blankSecretPreserved(field, values[field])) continue;
    let next = values[field].trim();
    if (field === "phone_number") next = normalizeCloudPhone(next) ?? "";
    if (field === "graph_api_version") next = normalizeGraphVersion(next) ?? "";
    if (!next) {
      clearSecret(key);
      continue;
    }
    if (!saveSecret(key, next)) return { ok: false as const, error: "invalid_value" };
  }
  return { ok: true as const, ...cloudFieldState(), message: "Credentials saved." };
}

export function deleteCloudValues() {
  for (const key of Object.values(FIELD_TO_SECRET)) clearSecret(key);
  return { ...cloudFieldState(), message: "Credentials deleted." };
}

export function generateVerifyToken() {
  const token = randomBytes(24).toString("hex");
  if (!saveSecret("verifyToken", token)) return { ok: false as const, error: "invalid_value" };
  return {
    ok: true as const,
    webhook_verify_token_plain: token,
    ...cloudFieldState(),
    message: "Verify token generated and saved. Copy it into the Meta webhook form.",
  };
}
