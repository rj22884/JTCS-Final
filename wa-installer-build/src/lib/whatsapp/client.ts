import "server-only";

import { localGraphFailure, parseGraphError, redactSecrets, type GraphFailure } from "@/lib/whatsapp/meta-errors";
import { graphVersion } from "@/lib/whatsapp/cloud-form";
import { liveReady, planSubscribe } from "@/lib/whatsapp/subscribe-plan";

export type SendTextResult = {
  ok: false;
  reason: "not_connected";
  detail: string;
};

const GRAPH_TIMEOUT_MS = 15_000;
const GRAPH_PATH = /^\d{5,64}(\/(subscribed_apps|phone_numbers|messages|media|message_templates))?$/;

export type CloudMediaKind = "image" | "document" | "audio" | "video";

export type CloudTemplateSummary = {
  id: string;
  name: string;
  language: string;
  status: string;
  category: string;
  /** HEADER text (if any). */
  headerText: string;
  /** BODY text with {{n}} placeholders left as-is. */
  bodyText: string;
  footerText: string;
  buttonLabels: string[];
  /** Multi-line preview for the inbox bubble. */
  preview: string;
};

export { redactSecrets };

export type ConnectionCheckState = "verified" | "not_verified" | "skipped" | "not_checked";

export type ConnectionCheck = {
  id: string;
  label: string;
  group: "meta" | "saved";
  state: ConnectionCheckState;
  detail: string;
  badge?: string;
};

export type AccessReport = {
  tokenInvalid: boolean;
  displayPhoneNumber: string | null;
  verifiedName: string | null;
  checks: ConnectionCheck[];
};

export type ConnectionTest = {
  ok: boolean;
  live: boolean;
  detail: string;
  displayPhoneNumber: string | null;
  verifiedName: string | null;
  checks: ConnectionCheck[];
};

export type SubscribeResult = {
  ok: boolean;
  posted: boolean;
  detail: string;
  httpStatus: number | null;
  code: number | null;
  subcode: number | null;
  traceId: string | null;
  cause: string | null;
};

type GraphNode = {
  id?: string;
  url?: string;
  mime_type?: string;
  sha256?: string;
  file_size?: number;
  display_phone_number?: string;
  verified_name?: string;
  name?: string;
  messages?: { id?: string }[];
  data?: Array<{
    id?: string;
    name?: string;
    status?: string;
    category?: string;
    language?: string | { code?: string };
    components?: Array<{
      type?: string;
      format?: string;
      text?: string;
      buttons?: Array<{ type?: string; text?: string; url?: string }>;
    }>;
    whatsapp_business_api_data?: { id?: string; name?: string };
  }>;
};

function templatePreviewFromComponents(
  name: string,
  components: Array<{
    type?: string;
    format?: string;
    text?: string;
    buttons?: Array<{ type?: string; text?: string; url?: string }>;
  }>,
) {
  let headerText = "";
  let bodyText = "";
  let footerText = "";
  const buttonLabels: string[] = [];
  for (const part of components) {
    const type = (part.type || "").toUpperCase();
    if (type === "HEADER" && typeof part.text === "string" && part.text.trim()) {
      headerText = part.text.trim();
    }
    if (type === "BODY" && typeof part.text === "string" && part.text.trim()) {
      bodyText = part.text.trim();
    }
    if (type === "FOOTER" && typeof part.text === "string" && part.text.trim()) {
      footerText = part.text.trim();
    }
    if (type === "BUTTONS" && Array.isArray(part.buttons)) {
      for (const button of part.buttons) {
        const label = typeof button.text === "string" ? button.text.trim() : "";
        if (label) buttonLabels.push(label);
      }
    }
  }
  const lines = [`Template: ${name}`];
  if (headerText) lines.push(headerText);
  if (bodyText) lines.push(bodyText);
  if (footerText) lines.push(footerText);
  if (buttonLabels.length) lines.push(buttonLabels.map((label) => `[${label}]`).join(" · "));
  return {
    headerText,
    bodyText,
    footerText,
    buttonLabels,
    preview: lines.join("\n\n"),
  };
}

type GraphOk = { ok: true; status: number; node: GraphNode };
type GraphErr = { ok: false; failure: GraphFailure };

function check(
  id: string,
  label: string,
  group: ConnectionCheck["group"],
  state: ConnectionCheckState,
  detail: string,
  badge?: string,
): ConnectionCheck {
  return { id, label, group, state, detail, badge };
}

function subscribedAppIds(node: GraphNode) {
  const rows = Array.isArray(node.data) ? node.data : [];
  const ids: string[] = [];
  for (const row of rows) {
    const id = row.whatsapp_business_api_data?.id || row.id;
    if (id) ids.push(id);
  }
  return ids;
}

function listedPhoneIds(node: GraphNode) {
  const rows = Array.isArray(node.data) ? node.data : [];
  return rows.map((row) => row.id).filter((id): id is string => Boolean(id));
}

function refused(failure: GraphFailure): SubscribeResult {
  return {
    ok: false,
    posted: false,
    detail: `${failure.detail} No subscribe request was sent.`,
    httpStatus: failure.httpStatus,
    code: failure.code,
    subcode: failure.subcode,
    traceId: failure.traceId,
    cause: failure.cause,
  };
}

async function graphRequest(
  method: "GET" | "POST",
  path: string,
  token: string,
  body?: unknown,
  version?: string | null,
): Promise<GraphOk | GraphErr> {
  if (!GRAPH_PATH.test(path)) {
    return { ok: false, failure: localGraphFailure("unknown", "The Graph path was rejected before Meta was called.") };
  }
  const url = new URL(`https://graph.facebook.com/${graphVersion(version)}/${path}`);
  if (url.username || url.password) {
    return { ok: false, failure: localGraphFailure("unknown", "The Graph URL was rejected before Meta was called.") };
  }
  if (path.endsWith("/phone_numbers") || path.endsWith("/message_templates")) url.searchParams.set("limit", "100");
  try {
    const response = await fetch(url, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(method === "POST" ? { "Content-Type": "application/json" } : {}),
      },
      body: method === "POST" ? JSON.stringify(body ?? {}) : undefined,
      signal: AbortSignal.timeout(GRAPH_TIMEOUT_MS),
    });
    const text = await response.text();
    if (!response.ok) return { ok: false, failure: parseGraphError(text, response.status, [token]) };
    try {
      return { ok: true, status: response.status, node: JSON.parse(text) as GraphNode };
    } catch {
      return { ok: false, failure: parseGraphError(text, response.status, [token]) };
    }
  } catch (error) {
    const message = redactSecrets(error instanceof Error ? error.message : "request_failed", [token]);
    const timeout = /timeout|aborted/i.test(message);
    return {
      ok: false,
      failure: timeout
        ? parseGraphError("timeout", null, [token])
        : localGraphFailure("unknown", "Meta did not return a readable response."),
    };
  }
}

export async function postCloudMessage(path: string, body: unknown, token: string) {
  const result = await graphRequest("POST", path, token, body);
  if (!result.ok) throw new Error(result.failure.detail);
  return result.node;
}

export async function inspectCloudAccess(input: {
  accessToken: string | null;
  phoneNumberId: string | null;
  businessAccountId: string | null;
  businessId: string | null;
  appId: string | null;
  graphApiVersion: string | null;
}): Promise<AccessReport> {
  const checks: ConnectionCheck[] = [];
  if (!input.accessToken || !input.phoneNumberId) {
    const missing = [input.phoneNumberId ? null : "phone number ID", input.accessToken ? null : "access token"].filter(Boolean).join(" and ");
    checks.push(
      check("phoneVerified", "Phone number", "meta", "not_checked", `Not checked. Missing ${missing}.`, "Not checked"),
      check("businessVerified", "Business ID", "meta", "not_checked", "Not checked. Nothing was sent to Meta.", "Not checked"),
      check("wabaAccessible", "Business account", "meta", "not_checked", "Not checked. Nothing was sent to Meta.", "Not checked"),
      check("phoneOnWaba", "Phone on this account", "meta", "not_checked", "Not checked. Nothing was sent to Meta.", "Not checked"),
      check("webhookSubscribed", "Webhook subscription", "meta", "not_checked", "Not checked. Nothing was sent to Meta.", "Not checked"),
      check("messageSending", "Message sending", "meta", "not_checked", "Not checked. No message was sent.", "Not checked"),
    );
    return { tokenInvalid: false, displayPhoneNumber: null, verifiedName: null, checks };
  }

  let phoneOk = false;
  let tokenInvalid = false;
  let displayPhoneNumber: string | null = null;
  let verifiedName: string | null = null;
  const version = graphVersion(input.graphApiVersion);
  const phone = await graphRequest("GET", input.phoneNumberId, input.accessToken, undefined, version);
  if (!phone.ok) {
    tokenInvalid = phone.failure.tokenInvalid;
    checks.push(check("phoneVerified", "Phone number", "meta", "not_verified", phone.failure.detail, "Not verified"));
  } else if (phone.node.id !== input.phoneNumberId) {
    checks.push(check("phoneVerified", "Phone number", "meta", "not_verified", "Meta answered, but the phone number ID did not match.", "Not verified"));
  } else {
    phoneOk = true;
    displayPhoneNumber = phone.node.display_phone_number ?? null;
    verifiedName = phone.node.verified_name ?? null;
    const found = [displayPhoneNumber, verifiedName].filter(Boolean).join(" · ");
    checks.push(check("phoneVerified", "Phone number", "meta", "verified", found || "Meta accepted this phone number ID.", "Verified"));
  }

  const businessSame =
    Boolean(input.businessId) && (input.businessId === input.phoneNumberId || input.businessId === input.businessAccountId);
  if (!input.businessId) {
    checks.push(check("businessVerified", "Business ID", "meta", "not_checked", "Not checked because no Business ID is saved.", "Not checked"));
  } else if (businessSame) {
    checks.push(
      check(
        "businessVerified",
        "Business ID",
        "meta",
        "not_verified",
        "Business ID matches the Phone Number ID or WhatsApp Business Account ID. These are different Meta values. Meta was not asked to open it. Cause: id_mismatch.",
        "Not verified",
      ),
    );
  } else {
    const business = await graphRequest("GET", input.businessId, input.accessToken, undefined, version);
    if (!business.ok) {
      tokenInvalid = tokenInvalid || business.failure.tokenInvalid;
      checks.push(check("businessVerified", "Business ID", "meta", "not_verified", business.failure.detail, "Not verified"));
    } else if (business.node.id !== input.businessId) {
      checks.push(check("businessVerified", "Business ID", "meta", "not_verified", "Meta answered, but the Business ID did not match.", "Not verified"));
    } else {
      checks.push(
        check(
          "businessVerified",
          "Business ID",
          "meta",
          "verified",
          business.node.name ? `Meta accepted ${business.node.name}.` : "Meta accepted this Business ID.",
          "Verified",
        ),
      );
    }
  }

  let accountOk = false;
  const sameIds = Boolean(input.businessAccountId && input.businessAccountId === input.phoneNumberId);
  if (!input.businessAccountId) {
    checks.push(check("wabaAccessible", "Business account", "meta", "not_checked", "Not checked because no business account ID is saved.", "Not checked"));
  } else if (sameIds) {
    checks.push(
      check(
        "wabaAccessible",
        "Business account",
        "meta",
        "not_verified",
        "The saved business account ID is the same as the phone number ID. These are different Meta values. Meta was not asked to open the business account. Cause: id_mismatch.",
        "Not accessible",
      ),
    );
  } else if (!phoneOk) {
    checks.push(check("wabaAccessible", "Business account", "meta", "not_checked", "Not checked because the phone number was not accepted.", "Not checked"));
  } else {
    const account = await graphRequest("GET", input.businessAccountId, input.accessToken, undefined, version);
    if (!account.ok) {
      tokenInvalid = tokenInvalid || account.failure.tokenInvalid;
      checks.push(check("wabaAccessible", "Business account", "meta", "not_verified", account.failure.detail, "Not accessible"));
    } else if (account.node.id !== input.businessAccountId) {
      checks.push(check("wabaAccessible", "Business account", "meta", "not_verified", "Meta answered, but the business account ID did not match.", "Not accessible"));
    } else {
      accountOk = true;
      checks.push(
        check(
          "wabaAccessible",
          "Business account",
          "meta",
          "verified",
          account.node.name ? `Meta accepted ${account.node.name}.` : "Meta accepted this business account ID.",
          "Accessible",
        ),
      );
    }
  }

  if (!accountOk) {
    checks.push(
      check(
        "phoneOnWaba",
        "Phone on this account",
        "meta",
        "not_checked",
        "Not checked because the business account is not accessible. No phone list was requested.",
        "Not checked",
      ),
    );
  } else {
    const listed = await graphRequest("GET", `${input.businessAccountId}/phone_numbers`, input.accessToken, undefined, version);
    if (!listed.ok) {
      tokenInvalid = tokenInvalid || listed.failure.tokenInvalid;
      checks.push(check("phoneOnWaba", "Phone on this account", "meta", "not_checked", listed.failure.detail, "Not checked"));
    } else if (listedPhoneIds(listed.node).includes(input.phoneNumberId)) {
      checks.push(
        check(
          "phoneOnWaba",
          "Phone on this account",
          "meta",
          "verified",
          "The saved phone number ID is in this business account. The saved ID was not changed.",
          "Same account",
        ),
      );
    } else {
      checks.push(
        check(
          "phoneOnWaba",
          "Phone on this account",
          "meta",
          "not_verified",
          "Meta opened the business account, but the saved phone number ID is not one of its phone numbers. Cause: wrong_waba. The saved ID was not changed.",
          "Different account",
        ),
      );
    }
  }

  if (!accountOk) {
    checks.push(
      check(
        "webhookSubscribed",
        "Webhook subscription",
        "meta",
        "not_checked",
        "Not checked. Subscription was not read because the business account is not accessible. No subscribe request was sent.",
        "Not checked",
      ),
    );
  } else if (!input.appId) {
    checks.push(
      check(
        "webhookSubscribed",
        "Webhook subscription",
        "meta",
        "not_checked",
        "Not checked. Save the Meta App ID before this app can be matched to the subscription list.",
        "Not checked",
      ),
    );
  } else {
    const subscribed = await graphRequest("GET", `${input.businessAccountId}/subscribed_apps`, input.accessToken, undefined, version);
    if (!subscribed.ok) {
      tokenInvalid = tokenInvalid || subscribed.failure.tokenInvalid;
      checks.push(check("webhookSubscribed", "Webhook subscription", "meta", "not_verified", subscribed.failure.detail, "Not subscribed"));
    } else {
      const appSubscribed = subscribedAppIds(subscribed.node).includes(input.appId);
      checks.push(
        appSubscribed
          ? check("webhookSubscribed", "Webhook subscription", "meta", "verified", "This app is in the business account subscription list.", "Subscribed")
          : check(
              "webhookSubscribed",
              "Webhook subscription",
              "meta",
              "not_verified",
              "This app is not in the business account subscription list. No subscribe request was sent.",
              "Not subscribed",
            ),
      );
    }
  }

  checks.push(
    phoneOk
      ? check("messageSending", "Message sending", "meta", "verified", "The phone number can accept a reply. No message was sent by this check.", "Ready")
      : check("messageSending", "Message sending", "meta", "not_verified", "A reply cannot be sent until Meta accepts the phone number. No message was sent.", "Not ready"),
  );

  return { tokenInvalid, displayPhoneNumber, verifiedName, checks };
}

function savedCheck(id: string, label: string, present: boolean, missing: string): ConnectionCheck {
  return check(id, label, "saved", present ? "verified" : "not_verified", present ? "Saved on this server." : missing);
}

export async function testCloudConnection(input: {
  accessToken: string | null;
  phoneNumberId: string | null;
  businessAccountId: string | null;
  businessId: string | null;
  appId: string | null;
  graphApiVersion: string | null;
  appSecretSet: boolean;
  verifyTokenSet: boolean;
  webhookUrlSet: boolean;
}): Promise<ConnectionTest> {
  const checks: ConnectionCheck[] = [
    savedCheck("phoneNumberId", "Phone number ID", Boolean(input.phoneNumberId), "Add the Cloud API phone number ID."),
    savedCheck("accessToken", "Access token", Boolean(input.accessToken), "Add the access token."),
    savedCheck("businessAccountId", "Business account ID", Boolean(input.businessAccountId), "Add the WhatsApp Business Account ID."),
    savedCheck("appSecret", "App secret", input.appSecretSet, "Add the app secret."),
    savedCheck("verifyToken", "Verify token", input.verifyTokenSet, "Add the verify token you will also enter in Meta."),
    savedCheck("webhookUrl", "Webhook URL", input.webhookUrlSet, "Add the production webhook URL."),
  ];

  const access = await inspectCloudAccess(input);
  checks.push(...access.checks);
  const states = Object.fromEntries(access.checks.map((item) => [item.id, item.state]));
  const phoneOk = states.phoneVerified === "verified";
  const accountOk = states.wabaAccessible === "verified";
  const ok = liveReady(states);
  return {
    ok,
    live: ok,
    detail: ok
      ? "Phone, business account, phone membership, and webhook subscription all passed. No message was sent by this test."
      : phoneOk && !accountOk
        ? "The phone number is verified. Meta did not open the business account, so this app is not connected and new messages will not arrive. No message was sent by this test."
        : phoneOk
          ? "The phone number is verified. The business account link or webhook subscription is not confirmed, so this app is not connected. No message was sent by this test."
          : input.accessToken && input.phoneNumberId
            ? "Test failed. No message was sent."
            : "Test failed. Nothing was sent to Meta.",
    displayPhoneNumber: access.displayPhoneNumber,
    verifiedName: access.verifiedName,
    checks,
  };
}

export async function probeAccessToken(input: {
  phoneNumberId: string | null;
  accessToken: string | null;
  businessAccountId: string | null;
  businessId: string | null;
  appId: string | null;
  graphApiVersion: string | null;
}) {
  const missing: string[] = [];
  if (!input.phoneNumberId) missing.push("phoneNumberId");
  if (!input.accessToken) missing.push("accessToken");
  const access = await inspectCloudAccess(input);
  const phone = access.checks.find((item) => item.id === "phoneVerified");
  const account = access.checks.find((item) => item.id === "wabaAccessible");
  const states = Object.fromEntries(access.checks.map((item) => [item.id, item.state]));
  const connected = liveReady(states);
  const detail = connected
    ? "Phone, business account, phone membership, and webhook subscription are all in place. New WhatsApp messages can arrive."
    : phone?.state === "verified" && account?.state !== "verified"
      ? "The phone number is verified. The business account is not accessible, so new WhatsApp messages will not arrive."
      : missing.length > 0
        ? `Missing ${missing.join(", ")}. WhatsApp is not connected.`
        : (phone?.detail ?? "WhatsApp is not connected.");
  return {
    ok: connected,
    tokenInvalid: access.tokenInvalid,
    missing,
    detail,
    checks: access.checks,
  };
}

export async function subscribeAppToBusinessAccount(input: {
  businessAccountId: string | null;
  phoneNumberId: string | null;
  businessId: string | null;
  appId: string | null;
  accessToken: string | null;
  graphApiVersion: string | null;
}): Promise<SubscribeResult> {
  const businessAccountId = input.businessAccountId && /^\d{5,32}$/.test(input.businessAccountId) ? input.businessAccountId : null;
  const phoneNumberId = input.phoneNumberId && /^\d{5,32}$/.test(input.phoneNumberId) ? input.phoneNumberId : null;
  const businessId = input.businessId && /^\d{5,32}$/.test(input.businessId) ? input.businessId : null;
  const appId = input.appId && /^\d{5,32}$/.test(input.appId) ? input.appId : null;
  const accessToken = input.accessToken;
  const version = graphVersion(input.graphApiVersion);
  const ids = [phoneNumberId, businessAccountId, businessId].filter(Boolean);
  const mismatched = new Set(ids).size !== ids.length;
  if (mismatched) {
    return refused(
      localGraphFailure(
        "id_mismatch",
        "Phone Number ID, WhatsApp Business Account ID, and Business ID must be different values. Nothing was sent to Meta.",
      ),
    );
  }
  if (!accessToken || !businessAccountId || !phoneNumberId || !appId || !businessId) {
    const plan = planSubscribe({
      phoneNumberId,
      businessAccountId,
      businessId,
      appId,
      accessTokenPresent: Boolean(accessToken),
      businessState: "not_checked",
      wabaState: "not_checked",
      phoneOnWaba: "not_checked",
      appSubscribed: null,
    });
    const reason = plan.post ? "missing_token" : plan.reason;
    const detail =
      reason === "id_mismatch"
        ? "Phone Number ID, WhatsApp Business Account ID, and Business ID must be different values. Nothing was sent to Meta."
        : reason === "missing_business"
          ? "Business ID is missing. Nothing was sent to Meta."
        : reason === "missing_phone"
          ? "The phone number ID is missing. Nothing was sent to Meta."
          : reason === "missing_app"
            ? "The Meta App ID is missing, so this app cannot be matched. Nothing was sent to Meta."
            : "The business account ID or access token is missing. Nothing was changed.";
    return { ...refused(localGraphFailure(reason === "id_mismatch" ? "id_mismatch" : "unknown", detail)), detail };
  }

  const business = await graphRequest("GET", businessId, accessToken, undefined, version);
  if (!business.ok || business.node.id !== businessId) {
    return business.ok
      ? refused(localGraphFailure("unknown", "Meta answered, but the Business ID did not match."))
      : refused(business.failure);
  }

  const account = await graphRequest("GET", businessAccountId, accessToken, undefined, version);
  if (!account.ok || account.node.id !== businessAccountId) {
    return account.ok
      ? refused(localGraphFailure("unknown", "Meta answered, but the business account ID did not match."))
      : refused(account.failure);
  }

  const listed = await graphRequest("GET", `${businessAccountId}/phone_numbers`, accessToken, undefined, version);
  const phoneOnWaba = !listed.ok ? "not_checked" : listedPhoneIds(listed.node).includes(phoneNumberId) ? "verified" : "not_verified";
  if (!listed.ok) return refused(listed.failure);
  if (phoneOnWaba !== "verified") {
    return refused(
      localGraphFailure(
        "wrong_waba",
        "Meta opened the business account, but the saved phone number ID is not one of its phone numbers. The saved ID was not changed.",
      ),
    );
  }

  const subscribed = await graphRequest("GET", `${businessAccountId}/subscribed_apps`, accessToken, undefined, version);
  if (!subscribed.ok) return refused(subscribed.failure);
  const already = subscribedAppIds(subscribed.node).includes(appId);
  const plan = planSubscribe({
    phoneNumberId,
    businessAccountId,
    businessId,
    appId,
    accessTokenPresent: true,
    businessState: "verified",
    wabaState: "verified",
    phoneOnWaba,
    appSubscribed: already,
  });
  if (!plan.post) {
    if (plan.reason === "already_subscribed") {
      return {
        ok: true,
        posted: false,
        detail: "This app is already subscribed. No second subscribe request was sent. Other subscribed apps were not removed.",
        httpStatus: subscribed.status,
        code: null,
        subcode: null,
        traceId: null,
        cause: null,
      };
    }
    return refused(localGraphFailure("unknown", "Subscribe was not sent because a required read did not pass."));
  }

  const posted = await graphRequest("POST", `${businessAccountId}/subscribed_apps`, accessToken, {}, version);
  if (!posted.ok) {
    return {
      ok: false,
      posted: true,
      detail: `${posted.failure.detail} One subscribe request was sent. No retry was sent.`,
      httpStatus: posted.failure.httpStatus,
      code: posted.failure.code,
      subcode: posted.failure.subcode,
      traceId: posted.failure.traceId,
      cause: posted.failure.cause,
    };
  }

  const confirm = await graphRequest("GET", `${businessAccountId}/subscribed_apps`, accessToken, undefined, version);
  if (!confirm.ok) {
    return {
      ok: false,
      posted: true,
      detail: `${confirm.failure.detail} One subscribe request was sent. The follow-up read failed. No retry was sent.`,
      httpStatus: confirm.failure.httpStatus,
      code: confirm.failure.code,
      subcode: confirm.failure.subcode,
      traceId: confirm.failure.traceId,
      cause: confirm.failure.cause,
    };
  }
  if (!subscribedAppIds(confirm.node).includes(appId)) {
    return {
      ok: false,
      posted: true,
      detail: "The subscribe request was sent once. A follow-up read did not show this app on the list. No retry was sent.",
      httpStatus: confirm.status,
      code: null,
      subcode: null,
      traceId: null,
      cause: "unknown",
    };
  }
  return {
    ok: true,
    posted: true,
    detail: "This app is subscribed. The subscription was read back from Meta. Other subscribed apps were not removed. No WhatsApp message was sent.",
    httpStatus: posted.status,
    code: null,
    subcode: null,
    traceId: null,
    cause: null,
  };
}

export function normalizeRecipient(input: string) {
  const digits = input.replace(/\D/g, "");
  return /^\d{8,15}$/.test(digits) ? digits : null;
}

export async function sendCloudText(input: {
  to: string;
  body: string;
  phoneNumberId: string;
  accessToken: string;
  graphApiVersion?: string | null;
  /** WhatsApp message id (wamid…) to reply to, when present. */
  replyToMessageId?: string | null;
}) {
  const to = normalizeRecipient(input.to);
  const body = input.body.trim();
  if (!to || !body || body.length > 4096) {
    return { ok: false as const, detail: "The recipient or message text is not valid. Nothing was sent." };
  }
  if (!/^\d{5,32}$/.test(input.phoneNumberId) || !input.accessToken) {
    return { ok: false as const, detail: "The phone number ID or access token is missing. Nothing was sent." };
  }
  const replyId = input.replyToMessageId?.trim() || "";
  const payload: Record<string, unknown> = {
    messaging_product: "whatsapp",
    recipient_type: "individual",
    to,
    type: "text",
    text: { body },
  };
  if (replyId.startsWith("wamid.")) {
    payload.context = { message_id: replyId };
  }
  const result = await graphRequest(
    "POST",
    `${input.phoneNumberId}/messages`,
    input.accessToken,
    payload,
    input.graphApiVersion,
  );
  if (!result.ok) return { ok: false as const, detail: result.failure.detail };
  const messageId = result.node.messages?.[0]?.id ?? "";
  if (!messageId) return { ok: false as const, detail: "Meta accepted the request but did not return a message id." };
  return { ok: true as const, to, messageId };
}

const MEDIA_LIMITS: Record<CloudMediaKind, number> = {
  image: 5 * 1024 * 1024,
  audio: 16 * 1024 * 1024,
  video: 16 * 1024 * 1024,
  document: 100 * 1024 * 1024,
};

const MEDIA_MIME: Record<string, CloudMediaKind> = {
  "image/jpeg": "image",
  "image/png": "image",
  "image/webp": "image",
  "audio/aac": "audio",
  "audio/mp4": "audio",
  "audio/mpeg": "audio",
  "audio/amr": "audio",
  "audio/ogg": "audio",
  "video/mp4": "video",
  "video/3gpp": "video",
  "application/pdf": "document",
  "application/msword": "document",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "document",
  "application/vnd.ms-excel": "document",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "document",
  "application/vnd.ms-powerpoint": "document",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation": "document",
  "text/plain": "document",
};

export function cloudMediaKind(mimeType: string): CloudMediaKind | null {
  const normalized = mimeType.trim().toLowerCase();
  return MEDIA_MIME[normalized] ?? null;
}

export function mediaPreviewBody(kind: CloudMediaKind, filename?: string | null, caption?: string | null) {
  const trimmedCaption = caption?.trim();
  if (trimmedCaption) return trimmedCaption;
  const trimmedName = filename?.trim();
  if (trimmedName) return `${kind}: ${trimmedName}`;
  if (kind === "image") return "Photo";
  if (kind === "video") return "Video";
  if (kind === "audio") return "Audio";
  return `[${kind}]`;
}

export async function uploadCloudMedia(input: {
  phoneNumberId: string;
  accessToken: string;
  graphApiVersion?: string | null;
  bytes: ArrayBuffer;
  filename: string;
  mimeType: string;
}) {
  if (!/^\d{5,32}$/.test(input.phoneNumberId) || !input.accessToken) {
    return { ok: false as const, detail: "The phone number ID or access token is missing. Nothing was uploaded." };
  }
  const kind = cloudMediaKind(input.mimeType);
  if (!kind) return { ok: false as const, detail: "This file type is not supported by WhatsApp Cloud API." };
  if (input.bytes.byteLength <= 0) return { ok: false as const, detail: "The file is empty. Nothing was uploaded." };
  if (input.bytes.byteLength > MEDIA_LIMITS[kind]) {
    return { ok: false as const, detail: `This ${kind} is too large for WhatsApp Cloud API.` };
  }
  const filename = input.filename.trim().slice(0, 240) || `file.${kind}`;
  const form = new FormData();
  form.append("messaging_product", "whatsapp");
  form.append("type", input.mimeType.trim().toLowerCase());
  form.append("file", new Blob([new Uint8Array(input.bytes)], { type: input.mimeType }), filename);
  const url = new URL(`https://graph.facebook.com/${graphVersion(input.graphApiVersion)}/${input.phoneNumberId}/media`);
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${input.accessToken}` },
      body: form,
      signal: AbortSignal.timeout(GRAPH_TIMEOUT_MS),
    });
    const text = await response.text();
    if (!response.ok) return { ok: false as const, detail: parseGraphError(text, response.status, [input.accessToken]).detail };
    let node: GraphNode;
    try {
      node = JSON.parse(text) as GraphNode;
    } catch {
      return { ok: false as const, detail: "Meta did not return a readable media upload response." };
    }
    const mediaId = typeof node.id === "string" ? node.id : "";
    if (!mediaId) return { ok: false as const, detail: "Meta accepted the upload but did not return a media id." };
    return { ok: true as const, mediaId, kind, filename };
  } catch (error) {
    const message = redactSecrets(error instanceof Error ? error.message : "request_failed", [input.accessToken]);
    const timeout = /timeout|aborted/i.test(message);
    return {
      ok: false as const,
      detail: timeout ? "Meta timed out while uploading the file." : "Meta did not accept the media upload.",
    };
  }
}

export async function sendCloudLocation(input: {
  to: string;
  phoneNumberId: string;
  accessToken: string;
  graphApiVersion?: string | null;
  latitude: number;
  longitude: number;
  name?: string | null;
  address?: string | null;
}) {
  const to = normalizeRecipient(input.to);
  if (!to || !Number.isFinite(input.latitude) || !Number.isFinite(input.longitude)) {
    return { ok: false as const, detail: "The recipient or location is not valid. Nothing was sent." };
  }
  if (!/^\d{5,32}$/.test(input.phoneNumberId) || !input.accessToken) {
    return { ok: false as const, detail: "The phone number ID or access token is missing. Nothing was sent." };
  }
  const location: Record<string, unknown> = {
    latitude: input.latitude,
    longitude: input.longitude,
  };
  const name = input.name?.trim();
  const address = input.address?.trim();
  if (name) location.name = name.slice(0, 1000);
  if (address) location.address = address.slice(0, 1000);
  const result = await graphRequest(
    "POST",
    `${input.phoneNumberId}/messages`,
    input.accessToken,
    {
      messaging_product: "whatsapp",
      recipient_type: "individual",
      to,
      type: "location",
      location,
    },
    input.graphApiVersion,
  );
  if (!result.ok) return { ok: false as const, detail: result.failure.detail };
  const messageId = result.node.messages?.[0]?.id ?? "";
  if (!messageId) return { ok: false as const, detail: "Meta accepted the request but did not return a message id." };
  const label = name || address || `${input.latitude.toFixed(5)}, ${input.longitude.toFixed(5)}`;
  return { ok: true as const, to, messageId, body: `📍 ${label}` };
}

export async function sendCloudContact(input: {
  to: string;
  phoneNumberId: string;
  accessToken: string;
  graphApiVersion?: string | null;
  name: string;
  phone: string;
}) {
  const to = normalizeRecipient(input.to);
  const phone = normalizeRecipient(input.phone);
  const name = input.name.trim();
  if (!to || !phone || !name) {
    return { ok: false as const, detail: "The recipient or contact is not valid. Nothing was sent." };
  }
  if (!/^\d{5,32}$/.test(input.phoneNumberId) || !input.accessToken) {
    return { ok: false as const, detail: "The phone number ID or access token is missing. Nothing was sent." };
  }
  const result = await graphRequest(
    "POST",
    `${input.phoneNumberId}/messages`,
    input.accessToken,
    {
      messaging_product: "whatsapp",
      recipient_type: "individual",
      to,
      type: "contacts",
      contacts: [
        {
          name: { formatted_name: name.slice(0, 200), first_name: name.slice(0, 200) },
          phones: [{ phone: `+${phone}`, type: "CELL", wa_id: phone }],
        },
      ],
    },
    input.graphApiVersion,
  );
  if (!result.ok) return { ok: false as const, detail: result.failure.detail };
  const messageId = result.node.messages?.[0]?.id ?? "";
  if (!messageId) return { ok: false as const, detail: "Meta accepted the request but did not return a message id." };
  return { ok: true as const, to, messageId, body: `👤 ${name} · +${phone}` };
}

export async function sendCloudMedia(input: {
  to: string;
  phoneNumberId: string;
  accessToken: string;
  graphApiVersion?: string | null;
  kind: CloudMediaKind;
  mediaId: string;
  filename?: string | null;
  caption?: string | null;
}) {
  const to = normalizeRecipient(input.to);
  if (!to || !input.mediaId) {
    return { ok: false as const, detail: "The recipient or media id is not valid. Nothing was sent." };
  }
  if (!/^\d{5,32}$/.test(input.phoneNumberId) || !input.accessToken) {
    return { ok: false as const, detail: "The phone number ID or access token is missing. Nothing was sent." };
  }
  const caption = input.caption?.trim().slice(0, 1024) || undefined;
  const filename = input.filename?.trim().slice(0, 240) || undefined;
  const mediaPayload: Record<string, string> = { id: input.mediaId };
  if (caption && (input.kind === "image" || input.kind === "document" || input.kind === "video")) {
    mediaPayload.caption = caption;
  }
  if (filename && input.kind === "document") mediaPayload.filename = filename;
  const result = await graphRequest(
    "POST",
    `${input.phoneNumberId}/messages`,
    input.accessToken,
    {
      messaging_product: "whatsapp",
      recipient_type: "individual",
      to,
      type: input.kind,
      [input.kind]: mediaPayload,
    },
    input.graphApiVersion,
  );
  if (!result.ok) return { ok: false as const, detail: result.failure.detail };
  const messageId = result.node.messages?.[0]?.id ?? "";
  if (!messageId) return { ok: false as const, detail: "Meta accepted the request but did not return a message id." };
  return {
    ok: true as const,
    to,
    messageId,
    body: mediaPreviewBody(input.kind, filename, caption),
  };
}

export async function downloadCloudMedia(input: {
  mediaId: string;
  accessToken: string;
  graphApiVersion?: string | null;
}) {
  if (!/^\d{5,64}$/.test(input.mediaId) || !input.accessToken) {
    return { ok: false as const, detail: "The media id or access token is missing." };
  }
  const meta = await graphRequest("GET", input.mediaId, input.accessToken, undefined, input.graphApiVersion);
  if (!meta.ok) return { ok: false as const, detail: meta.failure.detail };
  const url = typeof meta.node.url === "string" ? meta.node.url : "";
  if (!url.startsWith("https://")) return { ok: false as const, detail: "Meta did not return a media download URL." };
  try {
    const response = await fetch(url, {
      headers: { Authorization: `Bearer ${input.accessToken}` },
      signal: AbortSignal.timeout(GRAPH_TIMEOUT_MS),
    });
    if (!response.ok) return { ok: false as const, detail: "Meta did not return the media bytes." };
    const bytes = await response.arrayBuffer();
    const mimeType =
      (typeof meta.node.mime_type === "string" && meta.node.mime_type) ||
      response.headers.get("content-type") ||
      "application/octet-stream";
    return { ok: true as const, bytes, mimeType, filenameHint: input.mediaId };
  } catch {
    return { ok: false as const, detail: "Meta timed out or refused the media download." };
  }
}

export async function listCloudTemplates(input: {
  businessAccountId: string;
  accessToken: string;
  graphApiVersion?: string | null;
}) {
  if (!/^\d{5,32}$/.test(input.businessAccountId) || !input.accessToken) {
    return { ok: false as const, detail: "The business account ID or access token is missing." };
  }
  const result = await graphRequest(
    "GET",
    `${input.businessAccountId}/message_templates`,
    input.accessToken,
    undefined,
    input.graphApiVersion,
  );
  if (!result.ok) return { ok: false as const, detail: result.failure.detail };
  const templates: CloudTemplateSummary[] = [];
  for (const row of result.node.data ?? []) {
    const name = typeof row.name === "string" ? row.name : "";
    const language =
      typeof row.language === "string"
        ? row.language
        : typeof row.language?.code === "string"
          ? row.language.code
          : "";
    const status = typeof row.status === "string" ? row.status : "";
    if (!name || !language) continue;
    const parsed = templatePreviewFromComponents(name, Array.isArray(row.components) ? row.components : []);
    templates.push({
      id: typeof row.id === "string" ? row.id : `${name}:${language}`,
      name,
      language,
      status: status || "UNKNOWN",
      category: typeof row.category === "string" ? row.category : "",
      headerText: parsed.headerText,
      bodyText: parsed.bodyText,
      footerText: parsed.footerText,
      buttonLabels: parsed.buttonLabels,
      preview: parsed.preview,
    });
  }
  return { ok: true as const, templates };
}

export async function sendCloudTemplate(input: {
  to: string;
  phoneNumberId: string;
  accessToken: string;
  graphApiVersion?: string | null;
  name: string;
  language: string;
  /** Optional inbox preview (header/body/buttons). Falls back to Template: name. */
  preview?: string | null;
  /** Body {{1}} / {{2}}… text parameters (OTP authentication templates). */
  bodyParams?: string[];
  /** Button parameter(s), usually the OTP digits. */
  buttonParams?: string[];
  /** Meta button sub_type: url (one-tap) or copy_code (auth copy button). */
  buttonSubType?: "url" | "copy_code";
}) {
  const to = normalizeRecipient(input.to);
  const name = input.name.trim();
  const language = input.language.trim();
  if (!to || !name || !language) {
    return { ok: false as const, detail: "The recipient or template is not valid. Nothing was sent." };
  }
  if (!/^\d{5,32}$/.test(input.phoneNumberId) || !input.accessToken) {
    return { ok: false as const, detail: "The phone number ID or access token is missing. Nothing was sent." };
  }
  const components: Array<Record<string, unknown>> = [];
  const bodyParams = (input.bodyParams || []).map((text) => text.trim()).filter(Boolean);
  if (bodyParams.length) {
    components.push({
      type: "body",
      parameters: bodyParams.map((text) => ({ type: "text", text })),
    });
  }
  const buttonParams = (input.buttonParams || []).map((text) => text.trim()).filter(Boolean);
  const buttonSubType = input.buttonSubType || "url";
  buttonParams.forEach((text, index) => {
    components.push({
      type: "button",
      sub_type: buttonSubType,
      index: String(index),
      parameters:
        buttonSubType === "copy_code"
          ? [{ type: "coupon_code", coupon_code: text }]
          : [{ type: "text", text }],
    });
  });
  const template: Record<string, unknown> = {
    name,
    language: { code: language },
  };
  if (components.length) template.components = components;
  const result = await graphRequest(
    "POST",
    `${input.phoneNumberId}/messages`,
    input.accessToken,
    {
      messaging_product: "whatsapp",
      recipient_type: "individual",
      to,
      type: "template",
      template,
    },
    input.graphApiVersion,
  );
  if (!result.ok) return { ok: false as const, detail: result.failure.detail };
  const messageId = result.node.messages?.[0]?.id ?? "";
  if (!messageId) return { ok: false as const, detail: "Meta accepted the request but did not return a message id." };
  const preview = input.preview?.trim() || `Template: ${name}`;
  return { ok: true as const, to, messageId, body: preview };
}

export async function sendWhatsAppText(input: { to: string; body: string }): Promise<SendTextResult> {
  void input.to;
  void input.body;
  void postCloudMessage;
  return {
    ok: false,
    reason: "not_connected",
    detail: "WhatsApp Cloud API sending is not enabled. The message was not submitted to Meta.",
  };
}
