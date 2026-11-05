export const CLOUD_SECRET_FIELDS = ["app_secret", "access_token", "webhook_verify_token"] as const;

export type CloudSecretField = (typeof CLOUD_SECRET_FIELDS)[number];

export type CloudValues = {
  app_id: string;
  app_secret: string;
  phone_number: string;
  phone_number_id: string;
  waba_id: string;
  business_id: string;
  graph_api_version: string;
  access_token: string;
  webhook_verify_token: string;
};

export const CLOUD_FIELD_KEYS = [
  "app_id",
  "app_secret",
  "phone_number",
  "phone_number_id",
  "waba_id",
  "business_id",
  "graph_api_version",
  "access_token",
  "webhook_verify_token",
] as const;

const REQUIRED: { key: keyof CloudValues; label: string }[] = [
  { key: "app_id", label: "Facebook App ID" },
  { key: "app_secret", label: "Facebook App Secret" },
  { key: "phone_number_id", label: "Phone Number ID" },
  { key: "waba_id", label: "WhatsApp Business Account ID" },
  { key: "business_id", label: "Business ID" },
  { key: "access_token", label: "Access token" },
  { key: "webhook_verify_token", label: "Webhook verify token" },
];

export function emptyCloudValues(): CloudValues {
  return {
    app_id: "",
    app_secret: "",
    phone_number: "",
    phone_number_id: "",
    waba_id: "",
    business_id: "",
    graph_api_version: "v21.0",
    access_token: "",
    webhook_verify_token: "",
  };
}

export function readCloudInput(raw: unknown): { ok: true; values: CloudValues } | { ok: false; error: string } {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return { ok: false, error: "invalid_value" };
  const source = raw as Record<string, unknown>;
  const values = emptyCloudValues();
  for (const key of CLOUD_FIELD_KEYS) {
    const value = source[key];
    if (value == null) continue;
    if (typeof value !== "string") return { ok: false, error: "invalid_value" };
    values[key] = value;
  }
  return { ok: true, values };
}

export function blankSecretPreserved(field: keyof CloudValues, value: string) {
  return (CLOUD_SECRET_FIELDS as readonly string[]).includes(field) && value.trim() === "";
}

export function normalizeGraphVersion(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return "v21.0";
  return /^v\d{1,3}\.\d{1,3}$/.test(trimmed) ? trimmed : null;
}

export function normalizeCloudPhone(value: string) {
  const compact = value.trim().replace(/[\s-]/g, "");
  if (!compact) return "";
  const withPlus = compact.startsWith("+") ? compact : `+${compact}`;
  return /^\+\d{8,15}$/.test(withPlus) ? withPlus : null;
}

function digitId(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return "";
  return /^\d{5,32}$/.test(trimmed) ? trimmed : null;
}

export function validateCloudValues(values: CloudValues) {
  if (digitId(values.app_id) === null) return "Facebook App ID is not a valid id.";
  if (digitId(values.phone_number_id) === null) return "Phone Number ID is not a valid id.";
  if (digitId(values.waba_id) === null) return "WhatsApp Business Account ID is not a valid id.";
  if (digitId(values.business_id) === null) return "Business ID is not a valid id.";
  if (normalizeCloudPhone(values.phone_number) === null) return "WhatsApp phone number is not a valid number.";
  if (normalizeGraphVersion(values.graph_api_version) === null) return "Graph API version must look like v21.0.";
  const ids = [digitId(values.phone_number_id), digitId(values.waba_id), digitId(values.business_id)].filter(Boolean);
  if (new Set(ids).size !== ids.length) {
    return "Phone Number ID, WhatsApp Business Account ID, and Business ID must be different values.";
  }
  if (values.app_secret.trim() && (values.app_secret.trim().length < 8 || /\s/.test(values.app_secret))) {
    return "Facebook App Secret was not accepted.";
  }
  if (values.access_token.trim() && (values.access_token.trim().length < 20 || /\s/.test(values.access_token))) {
    return "Access token was not accepted.";
  }
  if (values.webhook_verify_token.trim() && (values.webhook_verify_token.trim().length < 8 || /\s/.test(values.webhook_verify_token))) {
    return "Webhook verify token was not accepted.";
  }
  return null;
}

export function missingCloudLabels(input: { values: Partial<CloudValues>; secrets: Record<string, boolean> }) {
  return REQUIRED.filter((item) => {
    if ((CLOUD_SECRET_FIELDS as readonly string[]).includes(item.key)) return !input.secrets[item.key];
    return !(input.values[item.key] || "").trim();
  }).map((item) => item.label);
}

export function testSendDecision(input: { send: boolean; confirm: boolean; mobile: string }) {
  if (!input.send) return { send: false as const };
  if (!input.confirm) {
    return { send: false as const, error: "Confirm the test message before it is sent. No message was sent." };
  }
  const digits = input.mobile.replace(/\D/g, "");
  if (!/^\d{8,15}$/.test(digits)) {
    return { send: false as const, error: "Test mobile is not valid. No message was sent." };
  }
  return { send: true as const, to: digits };
}

export function graphVersion(value: string | null | undefined) {
  const trimmed = (value ?? "").trim();
  return /^v\d{1,3}\.\d{1,3}$/.test(trimmed) ? trimmed : "v21.0";
}
