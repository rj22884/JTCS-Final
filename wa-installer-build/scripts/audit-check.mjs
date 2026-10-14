import { createHmac } from "node:crypto";
import {
  composerAppearanceSendable,
  otpExpired,
  recoveryPublicOk,
  registrationPublicOk,
  resendCooldownMs,
  sessionTtlMs,
  SESSION_MS_DEFAULT,
  SESSION_MS_REMEMBER,
} from "../src/lib/auth-policy.ts";
import { matchCustomerMaster } from "../src/lib/customer-master.ts";
import {
  erpSyncConnectionStatus,
  planCustomerSync,
  upsertCustomerRecords,
  writeErpConnectionMeta,
} from "../src/lib/customer-sync.ts";
import {
  conversationIdForContactMobile,
  createContact,
  deleteContact,
  findContactByPhoneKey,
  getContact,
  listContacts,
  sortContacts,
  undeleteContact,
  updateContact,
} from "../src/lib/contacts.ts";
import { erpSyncTokenMatches, generateErpSyncToken, revokeErpSyncToken } from "../src/lib/erp-sync-token.ts";
import { classifyLink } from "../src/lib/link-audit.ts";
import {
  attachmentLooksLikeImage,
  attachmentLooksLikeVideo,
  extractHttpUrls,
  splitTextWithUrls,
} from "../src/lib/links.ts";
import { assertPublicHttpUrl } from "../src/lib/link-preview.ts";
import { mailConfigured, smtpConnectionStatus } from "../src/lib/mail.ts";
import { openDemoConversationForPhone } from "../src/lib/store.ts";
import {
  actionsForMessage,
  attachmentCaptionText,
  buildAttachmentDrafts,
  canSendComposer,
  DELETE_FOR_EVERYONE_SUPPORTED,
  inferMessageKind,
  isAttachmentMessage,
} from "../src/lib/message-actions.ts";
import { COMPOSER_APPEARANCE, wrapWaTextStyle } from "../src/lib/message-format.ts";
import { hashPassword, isAcceptablePassword, normalizeEmail, verifyPassword } from "../src/lib/passwords.ts";
import { DEFAULT_COUNTRY_CODE, normalizeContactMobile, normalizeMobile } from "../src/lib/phone.ts";
import {
  issueApprovalTokens,
  readApprovalToken,
  consumeApprovalToken,
  adminWhatsAppRecipients,
} from "../src/lib/account-approval.ts";
import { consumeMobileOtp, issueMobileOtp } from "../src/lib/mobile-otp.ts";
import {
  approveUser,
  canLogin,
  createPendingUser,
  createVerifiedUser,
  findDeletedConflict,
  findLiveConflict,
  findUser,
  permanentlyDeleteUser,
  publicProfile,
  rejectUser,
  softDeleteUser,
  updateProfileName,
} from "../src/lib/users.ts";
import { applyWhatsAppPayload, getLiveConversation, updateLiveConversation } from "../src/lib/whatsapp/inbox.ts";
import { parseMessageReferral } from "../src/lib/whatsapp/referral.ts";
import { eventIdsForPayload, rememberEvents } from "../src/lib/whatsapp/events.ts";
import { inspectCloudAccess, subscribeAppToBusinessAccount } from "../src/lib/whatsapp/client.ts";
import { accessTokenInvalid, cleanGraphMessage, parseGraphError, redactSecrets, summarizeGraphFailure } from "../src/lib/whatsapp/meta-errors.ts";
import { verifyMetaSignature, webhookChallengeMatches } from "../src/lib/whatsapp/signature.ts";
import { idsAreDistinct, liveReady, planSubscribe } from "../src/lib/whatsapp/subscribe-plan.ts";
import { blankSecretPreserved, emptyCloudValues, testSendDecision, validateCloudValues } from "../src/lib/whatsapp/cloud-form.ts";

const failures = [];

function check(name, ok) {
  if (!ok) failures.push(name);
  console.log(`${ok ? "ok" : "FAIL"} ${name}`);
}

check("missing token is not an invalid session", accessTokenInvalid(null, "") === false);
check(
  "invalidated session is an invalid token",
  accessTokenInvalid(190, "The session has been invalidated because the user changed their password") === true,
);
check(
  "validation wording is an invalid token",
  accessTokenInvalid(null, "Error validating access token") === true,
);
const refused = summarizeGraphFailure({
  code: 100,
  subcode: 33,
  message:
    "Unsupported get request. Object with ID '123456789012345' does not exist, cannot be loaded due to missing permissions, or does not support this operation.",
});
check("code 100 subcode 33 is not an expired token", refused.tokenInvalid === false);
check("code 100 subcode 33 cause stays unknown", refused.cause === "unknown");
check("code 100 subcode 33 does not claim the phone works", !/can use the phone number/i.test(refused.detail));
check("code 100 subcode 33 hides the raw id", !refused.detail.includes("123456789012345"));
check("code 100 subcode 33 names the unknown cause", refused.detail.includes("Cause: unknown"));
check("code 190 stays an expired token", summarizeGraphFailure({ code: 190, subcode: null, message: "Error validating access token" }).tokenInvalid === true);
check(
  "permission-only text is missing permission",
  summarizeGraphFailure({ code: 10, subcode: null, message: "Application does not have permission for this action" }).cause === "missing_permission",
);
check(
  "unsupported-only text is unsupported",
  summarizeGraphFailure({ code: 100, subcode: null, message: "Unsupported post request." }).cause === "unsupported_operation",
);
check(
  "missing object text is not found",
  summarizeGraphFailure({ code: 803, subcode: null, message: "Object does not exist" }).cause === "not_found",
);
const parsed = parseGraphError(
  JSON.stringify({
    error: {
      message: "Unsupported get request. Object with ID '123456789012345' does not exist, cannot be loaded due to missing permissions, or does not support this operation. Bearer local-audit-token-value",
      code: 100,
      error_subcode: 33,
      fbtrace_id: "AbCdEf123456",
    },
  }),
  400,
  ["local-audit-token-value"],
);
check("parsed graph error keeps http status", parsed.httpStatus === 400);
check("parsed graph error keeps meta code", parsed.code === 100 && parsed.subcode === 33);
check("parsed graph error keeps trace", parsed.traceId === "AbCdEf123456");
check("parsed graph error cause is unknown", parsed.cause === "unknown");
check("parsed graph error redacts the token", !parsed.detail.includes("local-audit-token-value"));
check("redact removes bearer secrets", !redactSecrets("Authorization: Bearer local-audit-token-value", ["local-audit-token-value"]).includes("local-audit-token-value"));
check("clean message hides long ids", !cleanGraphMessage("id 123456789012345").includes("123456789012345"));
const windowBlocked = summarizeGraphFailure({
  code: 131047,
  subcode: null,
  message: "Message failed to send because more than 24 hours have passed since the customer last replied to this number.",
});
check("code 131047 explains care window", /24-hour customer care window/i.test(windowBlocked.detail));
check("contacts bracket kind is contact", inferMessageKind("[contacts]") === "contact");
check("location emoji kind is location", inferMessageKind("📍 28.61, 77.20") === "location");
check("same ids are not distinct", idsAreDistinct("111111111111111", "111111111111111") === false);
check("different ids are distinct", idsAreDistinct("111111111111111", "222222222222222") === true);
check("one saved id is not a mismatch", idsAreDistinct(null, "222222222222222") === true);
check("no saved ids are not compared", idsAreDistinct(null, null) === null);
check(
  "phone-only checks are not live",
  liveReady({ phoneVerified: "verified", businessVerified: "verified", wabaAccessible: "not_verified", phoneOnWaba: "not_checked", webhookSubscribed: "not_checked", messageSending: "verified" }) === false,
);
check(
  "all required checks are live",
  liveReady({ phoneVerified: "verified", businessVerified: "verified", wabaAccessible: "verified", phoneOnWaba: "verified", webhookSubscribed: "verified" }) === true,
);
check(
  "closed business account does not post",
  planSubscribe({
    phoneNumberId: "111111111111111",
    businessAccountId: "222222222222222",
    appId: "333333333333333",
    businessId: "555555555555555",
    accessTokenPresent: true,
    businessState: "verified",
    wabaState: "not_verified",
    phoneOnWaba: "not_checked",
    appSubscribed: null,
  }).post === false,
);
check(
  "already subscribed does not post",
  planSubscribe({
    phoneNumberId: "111111111111111",
    businessAccountId: "222222222222222",
    appId: "333333333333333",
    businessId: "555555555555555",
    accessTokenPresent: true,
    businessState: "verified",
    wabaState: "verified",
    phoneOnWaba: "verified",
    appSubscribed: true,
  }).reason === "already_subscribed",
);
check(
  "ready account posts once",
  planSubscribe({
    phoneNumberId: "111111111111111",
    businessAccountId: "222222222222222",
    appId: "333333333333333",
    businessId: "555555555555555",
    accessTokenPresent: true,
    businessState: "verified",
    wabaState: "verified",
    phoneOnWaba: "verified",
    appSubscribed: false,
  }).post === true,
);

const secret = "local-test-secret";
const body = "{\"object\":\"whatsapp_business_account\"}";
const signature = `sha256=${createHmac("sha256", secret).update(body).digest("hex")}`;
check("hmac accepts the matching signature", verifyMetaSignature(body, signature, secret) === true);
check("hmac rejects a changed body", verifyMetaSignature(`${body} `, signature, secret) === false);
check("hmac rejects a missing header", verifyMetaSignature(body, null, secret) === false);
check(
  "webhook challenge matches the verify token",
  webhookChallengeMatches({ mode: "subscribe", verifyToken: "local-verify", provided: "local-verify", challenge: "12345" }) === true,
);
check(
  "webhook challenge rejects a different token",
  webhookChallengeMatches({ mode: "subscribe", verifyToken: "local-verify", provided: "other-verify", challenge: "12345" }) === false,
);

const records = [
  { id: "c1", name: "One", mobile: "+91 99900 00001" },
  { id: "c2", name: "Two", mobile: "919990000002" },
  { id: "c3", name: "Two again", mobile: "+91-99900-00002" },
];
check("sample is not a customer", matchCustomerMaster("+1 631 555 1181", records).state === "sample");
check("no match stays empty", matchCustomerMaster("+91 99900 00009", records).state === "none");
check("one match", matchCustomerMaster("919990000001", records).state === "one");
check("multiple matches", matchCustomerMaster("+919990000002", records).state === "many");
check("one match keeps the ERP number", matchCustomerMaster("919990000001", records).matches[0]?.mobile === "+91 99900 00001");

const links = [
  ["https://wa.ukdscwala.com/settings", "this-app", true],
  ["http://wa.ukdscwala.com/settings", "this-app", false],
  ["https://app.jtcsxpert.com/login", "erp-login", true],
  ["http://localhost:3000", "local-dev", true],
  ["http://127.0.0.1:3010", "loopback", true],
  ["https://whatsapp.jtcsxpert.com", "other", false],
  ["https://ukdscwala.com", "other", false],
  ["https://graph.facebook.com/v21.0", "meta", true],
];
for (const [href, origin, ok] of links) {
  const found = classifyLink(href);
  check(`link ${origin} ${href}`, found.origin === origin && found.ok === ok);
}

check(
  "webhook challenge rejects a missing challenge",
  webhookChallengeMatches({ mode: "subscribe", verifyToken: "local-verify", provided: "local-verify", challenge: null }) === false,
);
check(
  "webhook challenge rejects the wrong mode",
  webhookChallengeMatches({ mode: "unsubscribe", verifyToken: "local-verify", provided: "local-verify", challenge: "12345" }) === false,
);
check("hmac rejects a different secret", verifyMetaSignature(body, signature, "other-secret") === false);

const inbound = {
  object: "whatsapp_business_account",
  entry: [
    {
      changes: [
        {
          value: {
            contacts: [{ wa_id: "15550001111", profile: { name: "Audit" } }],
            messages: [
              {
                id: "wamid.AUDIT1",
                from: "15550001111",
                timestamp: "1710000000",
                type: "text",
                text: { body: "audit hello" },
              },
            ],
          },
        },
      ],
    },
  ],
};
check("webhook apply saves the first event", applyWhatsAppPayload(inbound).applied === 1);
check("webhook apply ignores the duplicate message", applyWhatsAppPayload(inbound).applied === 0);

const ctwaReferral = parseMessageReferral({
  type: "text",
  text: { body: "नमस्ते! क्या मुझे इस बारे में और पता चल सकता है?" },
  referral: {
    source_type: "ad",
    source_id: "120212345678901234",
    source_url: "https://fb.me/example",
    headline: "Joshi Tax Consultancy and Services",
    body: "JTCS Xpert is hiring: Sales Executive",
    media_type: "image",
    image_url: "https://scontent.xx.fbcdn.net/example.jpg",
    ctwa_clid: "ARAkLkA8rmlFeiCktEJQ",
  },
});
check("ctwa referral parses headline and image", Boolean(ctwaReferral?.headline && ctwaReferral.imageUrl));
const ctwaInbound = {
  object: "whatsapp_business_account",
  entry: [
    {
      changes: [
        {
          value: {
            contacts: [{ wa_id: "15550002222", profile: { name: "CTWA Lead" } }],
            messages: [
              {
                id: "wamid.CTWA1",
                from: "15550002222",
                timestamp: "1710000100",
                type: "text",
                text: { body: "नमस्ते! क्या मुझे इस बारे में और पता चल सकता है?" },
                referral: {
                  source_type: "ad",
                  source_id: "120212345678901234",
                  source_url: "https://fb.me/example",
                  headline: "Joshi Tax Consultancy and Services",
                  body: "JTCS Xpert is hiring: Sales Executive",
                  media_type: "image",
                  image_url: "https://scontent.xx.fbcdn.net/example.jpg",
                  ctwa_clid: "ARAkLkA8rmlFeiCktEJQ",
                },
              },
            ],
          },
        },
      ],
    },
  ],
};
check("ctwa webhook stores referral with message", applyWhatsAppPayload(ctwaInbound).applied === 1);
const ctwaConversation = getLiveConversation("p-15550002222");
const ctwaMessage = ctwaConversation?.messages.find((item) => item.id === "wamid.CTWA1");
check(
  "ctwa inbox message keeps user text and ad preview fields",
  Boolean(
    ctwaMessage?.body.includes("नमस्ते") &&
      ctwaMessage.referral?.headline === "Joshi Tax Consultancy and Services" &&
      ctwaMessage.referral?.imageUrl,
  ),
);
const eventIds = eventIdsForPayload(JSON.stringify(inbound), inbound);
const firstReceipt = rememberEvents(eventIds);
const secondReceipt = rememberEvents(eventIds);
check("event id is accepted once", firstReceipt.accepted === 1 && firstReceipt.duplicate === false);
check("repeat event id is a duplicate", secondReceipt.accepted === 0 && secondReceipt.duplicate === true);
check(
  "status event moves delivery to delivered",
  applyWhatsAppPayload({
    object: "whatsapp_business_account",
    entry: [
      {
        changes: [
          {
            value: {
              statuses: [{ id: "wamid.AUDIT1", status: "delivered", timestamp: "1710000001", recipient_id: "15550001111" }],
            },
          },
        ],
      },
    ],
  }).applied === 0,
);
const saved = getLiveConversation("p-15550001111");
check("saved delivery is delivered", saved?.messages[0]?.delivery === "delivered");
check("saved conversation starts open", saved?.status === "open");
check("status can move to pending", updateLiveConversation("p-15550001111", { status: "pending" })?.detail.status === "pending");
check("status can move to resolved", updateLiveConversation("p-15550001111", { status: "resolved" })?.detail.status === "resolved");

const contactShareInbound = {
  object: "whatsapp_business_account",
  entry: [
    {
      changes: [
        {
          value: {
            contacts: [{ wa_id: "15550003333", profile: { name: "Share Contact" } }],
            messages: [
              {
                id: "wamid.CONTACT1",
                from: "15550003333",
                timestamp: "1710000200",
                type: "contacts",
                contacts: [
                  {
                    name: { formatted_name: "Demo Person" },
                    phones: [{ phone: "+919876543210", wa_id: "919876543210" }],
                  },
                ],
              },
            ],
          },
        },
      ],
    },
  ],
};
check("webhook stores shared contact card", applyWhatsAppPayload(contactShareInbound).applied === 1);
const contactShare = getLiveConversation("p-15550003333")?.messages.find((item) => item.id === "wamid.CONTACT1");
check(
  "shared contact body is readable",
  Boolean(contactShare?.kind === "contact" && contactShare.body.includes("Demo Person") && contactShare.body.includes("9876543210")),
);

const locationShareInbound = {
  object: "whatsapp_business_account",
  entry: [
    {
      changes: [
        {
          value: {
            contacts: [{ wa_id: "15550004444", profile: { name: "Share Location" } }],
            messages: [
              {
                id: "wamid.LOC1",
                from: "15550004444",
                timestamp: "1710000300",
                type: "location",
                location: { latitude: 29.2183, longitude: 79.512, name: "Haldwani", address: "Nainital Rd" },
              },
            ],
          },
        },
      ],
    },
  ],
};
check("webhook stores shared location", applyWhatsAppPayload(locationShareInbound).applied === 1);
const locationShare = getLiveConversation("p-15550004444")?.messages.find((item) => item.id === "wamid.LOC1");
check(
  "shared location body is readable",
  Boolean(locationShare?.kind === "location" && locationShare.body.includes("Haldwani") && locationShare.body.includes("Nainital")),
);

const phoneId = "111111111111111";
const wabaId = "222222222222222";
const appId = "333333333333333";
const businessId = "555555555555555";
const auditToken = "local-audit-token-value";

function graphRefusal() {
  return new Response(
    JSON.stringify({
      error: {
        message:
          "Unsupported get request. Object with ID '333333333333333' does not exist, cannot be loaded due to missing permissions, or does not support this operation.",
        type: "GraphMethodException",
        code: 100,
        error_subcode: 33,
        fbtrace_id: "AbCdEf123456",
      },
    }),
    { status: 400, headers: { "Content-Type": "application/json" } },
  );
}

async function withFetch(handler, run) {
  const previous = globalThis.fetch;
  globalThis.fetch = handler;
  try {
    await run();
  } finally {
    globalThis.fetch = previous;
  }
}

let blockedPosts = 0;
await withFetch(async (url, init) => {
  const href = String(url);
  if (init?.method === "POST") blockedPosts += 1;
  if (href.endsWith(`/${businessId}`)) return new Response(JSON.stringify({ id: businessId, name: "Audit Business" }), { status: 200 });
  if (href.endsWith(`/${phoneId}`)) {
    return new Response(JSON.stringify({ id: phoneId, display_phone_number: "+1 555 000 1111", verified_name: "Audit" }), { status: 200 });
  }
  return graphRefusal();
}, async () => {
  const report = await inspectCloudAccess({
    accessToken: auditToken,
    phoneNumberId: phoneId,
    businessAccountId: wabaId,
    businessId,
    appId,
    graphApiVersion: "v21.0",
  });
  const byId = Object.fromEntries(report.checks.map((item) => [item.id, item]));
  check("mocked phone lookup is verified", byId.phoneVerified.state === "verified");
  check("mocked business account cause is unknown", byId.wabaAccessible.state === "not_verified" && byId.wabaAccessible.detail.includes("Cause: unknown"));
  check("mocked phone list stays unread", byId.phoneOnWaba.state === "not_checked");
  check("mocked subscription stays unread", byId.webhookSubscribed.state === "not_checked");
  check("mocked message check sends nothing", byId.messageSending.badge === "Ready" && byId.messageSending.detail.includes("No message was sent"));
  check("mocked phone-only result is not live", liveReady(Object.fromEntries(report.checks.map((item) => [item.id, item.state]))) === false);
  const blocked = await subscribeAppToBusinessAccount({
    businessAccountId: wabaId,
    phoneNumberId: phoneId,
    businessId,
    appId,
    accessToken: auditToken,
    graphApiVersion: "v21.0",
  });
  check("blocked subscribe keeps meta fields", blocked.httpStatus === 400 && blocked.code === 100 && blocked.subcode === 33 && blocked.traceId === "AbCdEf123456");
  check("blocked subscribe does not post", blocked.ok === false && blocked.posted === false && blocked.cause === "unknown");
});
check("blocked account created no subscribe post", blockedPosts === 0);

let sameIdCalls = 0;
await withFetch(async () => {
  sameIdCalls += 1;
  return graphRefusal();
}, async () => {
  const same = await subscribeAppToBusinessAccount({
    businessAccountId: phoneId,
    phoneNumberId: phoneId,
    appId,
    accessToken: auditToken,
  });
  check("same saved ids are an id mismatch", same.cause === "id_mismatch" && same.posted === false);
});
check("same saved ids do not call meta", sameIdCalls === 0);

let successPosts = 0;
let nowSubscribed = false;
await withFetch(async (url, init) => {
  const href = String(url);
  if (init?.method === "POST" && href.includes("/subscribed_apps")) {
    successPosts += 1;
    nowSubscribed = true;
    return new Response(JSON.stringify({ success: true }), { status: 200 });
  }
  if (href.includes("/phone_numbers")) {
    return new Response(JSON.stringify({ data: [{ id: phoneId }] }), { status: 200 });
  }
  if (href.includes("/subscribed_apps")) {
    const data = nowSubscribed ? [{ whatsapp_business_api_data: { id: appId, name: "Audit" } }] : [];
    return new Response(JSON.stringify({ data }), { status: 200 });
  }
  if (href.endsWith(`/${businessId}`)) return new Response(JSON.stringify({ id: businessId, name: "Audit Business" }), { status: 200 });
  if (href.endsWith(`/${wabaId}`)) return new Response(JSON.stringify({ id: wabaId, name: "Audit WABA" }), { status: 200 });
  if (href.endsWith(`/${phoneId}`)) {
    return new Response(JSON.stringify({ id: phoneId, display_phone_number: "+1 555 000 1111", verified_name: "Audit" }), { status: 200 });
  }
  return graphRefusal();
}, async () => {
  const created = await subscribeAppToBusinessAccount({
    businessAccountId: wabaId,
    phoneNumberId: phoneId,
    businessId,
    appId,
    accessToken: auditToken,
    graphApiVersion: "v21.0",
  });
  check("open account posts once", created.ok === true && created.posted === true && successPosts === 1);
  const repeat = await subscribeAppToBusinessAccount({
    businessAccountId: wabaId,
    phoneNumberId: phoneId,
    businessId,
    appId,
    accessToken: auditToken,
    graphApiVersion: "v21.0",
  });
  check("subscribed account does not post again", repeat.ok === true && repeat.posted === false && successPosts === 1);
});

let mismatchPosts = 0;
await withFetch(async (url, init) => {
  const href = String(url);
  if (init?.method === "POST") mismatchPosts += 1;
  if (href.includes("/phone_numbers")) return new Response(JSON.stringify({ data: [{ id: "444444444444444" }] }), { status: 200 });
  if (href.endsWith(`/${businessId}`)) return new Response(JSON.stringify({ id: businessId, name: "Audit Business" }), { status: 200 });
  if (href.endsWith(`/${wabaId}`)) return new Response(JSON.stringify({ id: wabaId, name: "Other WABA" }), { status: 200 });
  return graphRefusal();
}, async () => {
  const mismatch = await subscribeAppToBusinessAccount({
    businessAccountId: wabaId,
    phoneNumberId: phoneId,
    businessId,
    appId,
    accessToken: auditToken,
    graphApiVersion: "v21.0",
  });
  check("phone outside the account is wrong waba", mismatch.cause === "wrong_waba" && mismatch.posted === false);
});
check("wrong account created no subscribe post", mismatchPosts === 0);

const duplicateIds = emptyCloudValues();
duplicateIds.phone_number_id = "111111111111111";
duplicateIds.waba_id = "111111111111111";
duplicateIds.business_id = "555555555555555";
check("equal phone and account ids are rejected", (validateCloudValues(duplicateIds) || "").includes("different"));
check("blank access token is preserved", blankSecretPreserved("access_token", " ") === true);
check("blank app id is not preserved as a secret", blankSecretPreserved("app_id", "") === false);
check("unchecked test sends no message", testSendDecision({ send: false, confirm: false, mobile: "" }).send === false);
check("unconfirmed checkbox sends no message", "error" in testSendDecision({ send: true, confirm: false, mobile: "919999999999" }));
check("confirmed test mobile can be sent", testSendDecision({ send: true, confirm: true, mobile: "91 99999 99999" }).to === "919999999999");

const draftFiles = [new File(["a"], "a.pdf", { type: "application/pdf" }), new File(["b"], "b.png", { type: "image/png" })];
const drafts = buildAttachmentDrafts(draftFiles, 0);
check("attachment drafts stay local until send", drafts.drafts.length === 2 && drafts.error === null);
check("composer cannot send while empty", canSendComposer("", 0, false) === false);
check("composer can send with drafts only", canSendComposer("", 2, false) === true);
check("composer cannot send while sending", canSendComposer("hi", 1, true) === false);
const tooMany = buildAttachmentDrafts(draftFiles, 9, 10);
check("attachment draft enforces max files", tooMany.error !== null && tooMany.drafts.length === 0);
const bold = wrapWaTextStyle("hello", 0, 5, "bold");
check("whatsapp bold markers wrap selection", bold.body === "*hello*");
const boldTyped = wrapWaTextStyle("hi", 2, 2, "bold");
check("whatsapp bold wraps typed body without placeholder", boldTyped.body === "*hi*" && boldTyped.body !== "hi*text*");
const italicEmpty = wrapWaTextStyle("", 0, 0, "italic");
check("whatsapp italic empty inserts markers", italicEmpty.body === "__" && italicEmpty.selectionStart === 1);
const textActions = actionsForMessage({
  id: "m1",
  direction: "outbound",
  body: "hello",
  at: new Date().toISOString(),
  delivery: "sent",
  kind: "text",
});
check("text message offers copy and delete for me", textActions.some((item) => item.id === "copy" && item.enabled) && textActions.some((item) => item.id === "delete_for_me" && item.enabled));
check("delete for everyone is not claimed as supported", DELETE_FOR_EVERYONE_SUPPORTED === false);
check(
  "delete for everyone stays disabled in menu",
  textActions.some((item) => item.id === "delete_for_everyone" && item.enabled === false && /Cloud API/i.test(item.detail || "")),
);
const attachmentMessage = {
  id: "m2",
  direction: "outbound",
  body: "document: invoice.pdf",
  at: new Date().toISOString(),
  delivery: "sent",
  kind: "document",
  attachments: [
    { id: "a1", kind: "document", filename: "invoice.pdf", mediaId: "123456789012345", mimeType: "application/pdf" },
    { id: "a2", kind: "document", filename: "note.pdf", mediaId: "123456789012346", mimeType: "application/pdf" },
  ],
};
const attachmentActions = actionsForMessage(attachmentMessage);
check("attachment message is detected", isAttachmentMessage(attachmentMessage));
check(
  "attachment menu includes reply forward copy",
  attachmentActions.some((item) => item.id === "reply" && item.enabled) &&
    attachmentActions.some((item) => item.id === "forward" && item.enabled) &&
    attachmentActions.some((item) => item.id === "copy" && item.enabled),
);
check("multi attachment offers save all", attachmentActions.some((item) => item.id === "save_all" && item.enabled));
check(
  "document label body is not shown as caption",
  attachmentCaptionText({
    id: "m3",
    direction: "inbound",
    body: "document: Invoice-HVVGZTRP-0010.pdf",
    at: new Date().toISOString(),
    kind: "document",
    attachments: [
      { id: "a1", kind: "document", filename: "Invoice-HVVGZTRP-0010.pdf", mediaId: "1", mimeType: "application/pdf" },
    ],
  }) === "",
);
check(
  "real caption under attachment is kept",
  attachmentCaptionText({
    id: "m4",
    direction: "outbound",
    body: "Please review this invoice",
    at: new Date().toISOString(),
    kind: "document",
    attachments: [
      { id: "a1", kind: "document", filename: "Invoice-HVVGZTRP-0010.pdf", mediaId: "1", mimeType: "application/pdf" },
    ],
  }) === "Please review this invoice",
);

check(
  "chat text extracts http urls",
  extractHttpUrls("See https://wa.ukdscwala.com/ and also https://jtcsxpert.com/path.").length === 2,
);
check(
  "chat text splits urls for clickable links",
  splitTextWithUrls("Go https://example.com/now.").some((part) => part.type === "url" && part.value === "https://example.com/now"),
);
check(
  "png attachment is treated as image preview",
  attachmentLooksLikeImage({ kind: "document", filename: "access token (1).png", mimeType: null }) === true,
);
check(
  "mp4 attachment is treated as video preview",
  attachmentLooksLikeVideo({ kind: "video", filename: "clip.mp4", mimeType: "video/mp4" }) === true,
);
check("localhost link preview is blocked", assertPublicHttpUrl("http://127.0.0.1/secret").ok === false);
check("public https link preview is allowed", assertPublicHttpUrl("https://wa.ukdscwala.com/").ok === true);

check("mobile without digits is invalid", normalizeMobile("").valid === false);
check("formatted mobile normalizes", normalizeMobile("+91 (98765) 43210").digits === "919876543210");
check("formatted mobile shares phone key with local 10-digit", normalizeMobile("+91-98765-43210").phoneKey === normalizeMobile("98765 43210").phoneKey);
check("default country code is India 91", DEFAULT_COUNTRY_CODE === "91");
check(
  "contact mobile composes country code + national",
  normalizeContactMobile("91", "7819840614").digits === "917819840614" &&
    normalizeContactMobile("91", "7819840614").national === "7819840614" &&
    normalizeContactMobile("91", "7819840614").display === "+91 7819840614",
);

const syncPlan = planCustomerSync(
  [
    { id: "1", name: "A", mobile: "" },
    { id: "2", name: "B", mobile: "9876543210" },
    { id: "2", name: "B Updated", mobile: "9876543210" },
    { id: "3", name: "C", mobile: "+91 98765-43210" },
    { id: "4", name: "D", mobile: "9876543210" },
  ],
  [{ id: "2", name: "B", mobile: "9876543210", country_code: "91", phone_key: "9876543210", source: "erp" }],
);
check("erp row without mobile is skipped", syncPlan.summary.skippedInvalidMobile >= 1);
check("same erp id re-sync updates or stays unchanged without duplicate create", syncPlan.summary.created === 0 || syncPlan.upserts.filter((row) => row.mode === "create").every((row) => row.id !== "2"));
check("same normalized mobile in feed is duplicate/conflict", syncPlan.summary.duplicateInFeed + syncPlan.summary.conflicts.length >= 1);
check(
  "erp sync upserts include country code 91",
  syncPlan.upserts.every((row) => row.countryCode === "91"),
);
const secondPass = planCustomerSync(
  [{ id: "2", name: "B", mobile: "9876543210" }],
  [{ id: "2", name: "B", mobile: "9876543210", country_code: "91", phone_key: "9876543210", source: "erp" }],
);
check("identical re-sync is unchanged not created", secondPass.summary.unchanged === 1 && secondPass.summary.created === 0);

const uniqueMobile = `98${String(Date.now()).slice(-8)}`;
const created = createContact({ name: "Audit Contact", mobile: uniqueMobile, countryCode: "91" });
check("contact create succeeds", created.ok === true);
if (created.ok) {
  check(
    "contact create stores country code and national mobile",
    created.contact.countryCode === "91" &&
      created.contact.mobile === uniqueMobile &&
      created.contact.fullMobile === `91${uniqueMobile}` &&
      created.contact.displayMobile === `+91 ${uniqueMobile}`,
  );
}
const dupCreate = createContact({ name: "Other", mobile: `+91 ${uniqueMobile}` });
check("duplicate normalized mobile is rejected on create", dupCreate.ok === false && dupCreate.error === "duplicate_mobile");
if (created.ok) {
  const dupUpdate = updateContact(created.contact.id, { name: "Audit Contact", mobile: uniqueMobile });
  check("contact update with same mobile is allowed", dupUpdate.ok === true);
  const otherMobile = `97${String(Date.now()).slice(-8)}`;
  const other = createContact({ name: "Other Contact", mobile: otherMobile });
  check("second distinct contact creates", other.ok === true);
  if (other.ok) {
    const steal = updateContact(created.contact.id, { name: "Audit Contact", mobile: otherMobile });
    check("contact update cannot steal another mobile", steal.ok === false && steal.error === "duplicate_mobile");
    check("lookup by phone key finds contact", Boolean(findContactByPhoneKey(normalizeMobile(uniqueMobile).phoneKey)));
    const removedOther = deleteContact(other.contact.id);
    check(
      "unlinked contact can be soft-deleted",
      removedOther.ok === true && Boolean(removedOther.contact?.deletedAt),
    );
    const restoredOther = undeleteContact(other.contact.id);
    check("soft-deleted contact can be undeleted", restoredOther.ok === true && !restoredOther.contact?.deletedAt);
    deleteContact(other.contact.id);
  }
  const removed = deleteContact(created.contact.id);
  check("created audit contact cleanup soft-delete", removed.ok === true && Boolean(removed.contact?.deletedAt));
  check("deleted contact remains in list for restore", Boolean(getContact(created.contact.id)?.deletedAt));
}

const erpSoftMobile = `96${String(Date.now()).slice(-8)}`;
const erpSoftId = `erp-soft-${Date.now()}`;
upsertCustomerRecords([{ id: erpSoftId, name: "ERP Soft", mobile: erpSoftMobile }]);
const erpSoft = getContact(erpSoftId);
check("erp sync creates contact", Boolean(erpSoft) && !erpSoft?.deletedAt);
check(
  "erp sync defaults country code to India and keeps national mobile",
  erpSoft?.countryCode === "91" && erpSoft?.mobile === erpSoftMobile && erpSoft?.fullMobile === `91${erpSoftMobile}`,
);
if (erpSoft) {
  const soft = deleteContact(erpSoft.id);
  check("erp contact soft-delete does not remove row", soft.ok === true && Boolean(getContact(erpSoft.id)));
  upsertCustomerRecords([{ id: erpSoftId, name: "ERP Soft Updated", mobile: erpSoftMobile }]);
  const afterSync = getContact(erpSoftId);
  check(
    "erp sync preserves soft-delete state",
    Boolean(afterSync?.deletedAt) && afterSync?.name === "ERP Soft Updated",
  );
  undeleteContact(erpSoftId);
  deleteContact(erpSoftId);
}

const sortSample = sortContacts([
  { id: "b", name: "Beta", mobile: "1", countryCode: "91", fullMobile: "911", displayMobile: "+91 1", phoneKey: "1", source: "manual", notes: "", deletedAt: "2026-01-01T00:00:00.000Z", syncedAt: null, createdAt: "", updatedAt: "" },
  { id: "a", name: "Alpha", mobile: "2", countryCode: "91", fullMobile: "912", displayMobile: "+91 2", phoneKey: "2", source: "manual", notes: "", deletedAt: null, syncedAt: null, createdAt: "", updatedAt: "" },
  { id: "c", name: "Gamma", mobile: "3", countryCode: "91", fullMobile: "913", displayMobile: "+91 3", phoneKey: "3", source: "erp", notes: "", deletedAt: null, syncedAt: null, createdAt: "", updatedAt: "" },
]);
check(
  "deleted contacts sort after active contacts",
  sortSample[0].id === "a" && sortSample[1].id === "c" && sortSample[2].id === "b",
);
const sortByMobile = sortContacts(
  [
    { id: "b", name: "Beta", mobile: "900", countryCode: "91", fullMobile: "91900", displayMobile: "+91 900", phoneKey: "91900", source: "manual", notes: "", deletedAt: null, syncedAt: null, createdAt: "", updatedAt: "" },
    { id: "a", name: "Alpha", mobile: "800", countryCode: "91", fullMobile: "91800", displayMobile: "+91 800", phoneKey: "91800", source: "manual", notes: "", deletedAt: null, syncedAt: null, createdAt: "", updatedAt: "" },
  ],
  "mobile",
);
check("contacts sort by mobile", sortByMobile[0].id === "a" && sortByMobile[1].id === "b");
const sortByDeleted = sortContacts(
  [
    { id: "a", name: "Alpha", mobile: "1", countryCode: "91", fullMobile: "911", displayMobile: "+91 1", phoneKey: "1", source: "manual", notes: "", deletedAt: null, syncedAt: null, createdAt: "", updatedAt: "" },
    { id: "b", name: "Beta", mobile: "2", countryCode: "91", fullMobile: "912", displayMobile: "+91 2", phoneKey: "2", source: "manual", notes: "", deletedAt: "2026-01-01T00:00:00.000Z", syncedAt: null, createdAt: "", updatedAt: "" },
  ],
  "deleted",
);
check("contacts sort deleted first", sortByDeleted[0].id === "b" && sortByDeleted[1].id === "a");
check(
  "send message conversation id from mobile",
  conversationIdForContactMobile("9876543210", "91") === "p-919876543210",
);
check(
  "send message conversation id from full international",
  conversationIdForContactMobile("919876543210") === "p-919876543210",
);
const openedDemo = openDemoConversationForPhone("919876543210", "Audit Chat");
check(
  "send message opens demo conversation without sending",
  Boolean(openedDemo?.id === "p-919876543210" && openedDemo.detail.messages.length === 0),
);
check("list contacts includes soft-deleted when present", listContacts().some((item) => item.deletedAt));

revokeErpSyncToken();
writeErpConnectionMeta({
  ok: false,
  checkedAt: new Date().toISOString(),
  detail: "Token revoked. Sync is disconnected until a new token is configured and tested.",
});
check("revoked token does not match random value", erpSyncTokenMatches("not-the-token-value-at-all") === false);
check("revoked erp sync status is disconnected", erpSyncConnectionStatus().connection === "disconnected");
const generated = generateErpSyncToken();
check("erp sync token generates", generated.ok === true && typeof generated.token === "string" && generated.token.length >= 32);
if (generated.ok) {
  check("generated token matches itself", erpSyncTokenMatches(generated.token) === true);
  check("invalid token is rejected", erpSyncTokenMatches(`${generated.token}x`) === false);
  writeErpConnectionMeta({
    ok: false,
    checkedAt: new Date().toISOString(),
    detail: "Token saved locally. Run Test connection to verify ERP accepts it.",
  });
  check(
    "token configured alone is not connected",
    erpSyncConnectionStatus().tokenConfigured === true && erpSyncConnectionStatus().connection === "disconnected",
  );
  revokeErpSyncToken();
  writeErpConnectionMeta({
    ok: false,
    checkedAt: new Date().toISOString(),
    detail: "Token revoked. Sync is disconnected until a new token is configured and tested.",
  });
  check("revoked token no longer matches", erpSyncTokenMatches(generated.token) === false);
  check("revoke leaves erp sync disconnected", erpSyncConnectionStatus().connection === "disconnected");
}

check("remember-me session is longer than default", sessionTtlMs(true) === SESSION_MS_REMEMBER && sessionTtlMs(false) === SESSION_MS_DEFAULT);
check("registration public ok does not include exists flag", registrationPublicOk().ok === true && !("exists" in registrationPublicOk()));
check("recovery public ok is generic", recoveryPublicOk().ok === true);
check("otp expiry detects past timestamps", otpExpired(Date.now() - 1) === true && otpExpired(Date.now() + 60_000) === false);
check("resend cooldown is zero when never sent", resendCooldownMs(null) === 0);
check("resend cooldown positive shortly after send", resendCooldownMs(Date.now() - 1000) > 0);
check("password hashing verifies", (() => {
  const stored = hashPassword("audit-pass-123");
  return verifyPassword("audit-pass-123", stored) && !verifyPassword("wrong-pass-123", stored);
})());
check("short passwords rejected", isAcceptablePassword("short") === false);
check("email normalize lowercases", normalizeEmail("  A@B.Com ") === "a@b.com");
check(
  "composer font/size/color enabled locally but not Cloud-sendable",
  COMPOSER_APPEARANCE.fontFamily.supported &&
    COMPOSER_APPEARANCE.fontSize.supported &&
    COMPOSER_APPEARANCE.textColor.supported &&
    COMPOSER_APPEARANCE.fontFamily.options.length > 1 &&
    COMPOSER_APPEARANCE.fontSize.options.length > 1 &&
    COMPOSER_APPEARANCE.textColor.options.length > 1 &&
    !composerAppearanceSendable("fontFamily") &&
    !composerAppearanceSendable("fontSize") &&
    !composerAppearanceSendable("textColor"),
);
check("mail without env is not configured", mailConfigured() === false);
check(
  "smtp without env is disconnected until verify",
  smtpConnectionStatus().connection === "disconnected" && smtpConnectionStatus().configured === false,
);

const otpMobile = `98${String(Date.now()).slice(-8)}`;
const issued = issueMobileOtp(otpMobile, "register", JSON.stringify({ demo: true }));
check("mobile otp issue succeeds", issued.ok === true && typeof issued.code === "string" && issued.code.length === 6);
if (issued.ok) {
  const reusedWrong = consumeMobileOtp(otpMobile, "register", "000000");
  check("wrong mobile otp rejected", reusedWrong === null);
  const consumed = consumeMobileOtp(otpMobile, "register", issued.code);
  check("mobile otp verifies once", Boolean(consumed?.payload));
  const reuse = consumeMobileOtp(otpMobile, "register", issued.code);
  check("mobile otp cannot be reused", reuse === null);
}

const cooldownIssued = issueMobileOtp(otpMobile, "register", "{}");
check(
  "mobile otp resend respects cooldown or rate limit",
  cooldownIssued.ok === false && (cooldownIssued.error === "resend_cooldown" || cooldownIssued.error === "sign_in_unavailable"),
);

const pendingEmail = `pending-${Date.now()}@example.com`;
const pendingMobile = `97${String(Date.now()).slice(-8)}`;
const pendingUser = createPendingUser({
  name: "Pending Member",
  email: pendingEmail,
  mobile: pendingMobile,
  mobileKey: pendingMobile.slice(-10),
  passwordHash: hashPassword("member-pass-123"),
});
check("pending user cannot login", canLogin(pendingUser).ok === false && canLogin(pendingUser).error === "pending_approval");
check("public registration defaults to member role", pendingUser.role === "member");
const renamed = updateProfileName(pendingUser.id, "Profile Name");
check("profile name can be updated", renamed.ok === true && renamed.user?.name === "Profile Name");
check("public profile hides password hash", !("password_hash" in publicProfile(pendingUser)));
const pendingAdmin = createPendingUser({
  name: "Pending Admin",
  email: `pending-admin-${Date.now()}@example.com`,
  mobile: `91${String(Date.now()).slice(-10)}`,
  mobileKey: String(Date.now()).slice(-10),
  passwordHash: hashPassword("member-pass-123"),
  role: "admin",
});
check("registration can request admin while still pending", pendingAdmin.role === "admin" && pendingAdmin.status === "pending_approval");
const approvedAdmin = approveUser(pendingAdmin.id, "audit-actor", "admin");
check("admin approval can activate requested admin role", approvedAdmin.ok === true && approvedAdmin.user?.role === "admin");
const liveConflict = findLiveConflict(pendingEmail, pendingMobile.slice(-10));
check("duplicate live email/mobile is detected", Boolean(liveConflict));

const tokens = issueApprovalTokens(pendingUser.id);
const approveParsed = readApprovalToken(tokens.approveToken);
check("approval token validates", Boolean(approveParsed && approveParsed.ok && approveParsed.action === "approve"));
const actorId = createVerifiedUser(`admin-actor-${Date.now()}@example.com`, hashPassword("admin-pass-123"), "admin");
const approved = approveUser(pendingUser.id, actorId);
check("admin approve activates user", approved.ok === true && approved.user?.status === "active");
consumeApprovalToken(approveParsed && approveParsed.ok ? approveParsed.id : "");
const reuseToken = readApprovalToken(tokens.approveToken);
check("approval token single-use after consume", Boolean(reuseToken && !reuseToken.ok));

const rejectEmail = `reject-${Date.now()}@example.com`;
const rejectMobile = `96${String(Date.now()).slice(-8)}`;
const rejectPending = createPendingUser({
  name: "Reject Me",
  email: rejectEmail,
  mobile: rejectMobile,
  mobileKey: rejectMobile.slice(-10),
  passwordHash: hashPassword("member-pass-123"),
});
const rejected = rejectUser(rejectPending.id, actorId);
check("admin reject blocks login", rejected.ok === true && canLogin(rejected.user).error === "rejected");

const softEmail = `soft-${Date.now()}@example.com`;
const softId = createVerifiedUser(softEmail, hashPassword("member-pass-123"), "member");
const soft = softDeleteUser(softId, actorId);
check("soft delete marks deleted", soft.ok === true && soft.user?.status === "deleted");
check("deleted account blocks re-registration", Boolean(findDeletedConflict(softEmail, "0000000000") || findUser(softEmail)?.status === "deleted"));
const purged = permanentlyDeleteUser(softId, actorId);
check("permanent delete removes user only", purged.ok === true && !findUser(softEmail));
check("admin recipients env helper returns array", Array.isArray(adminWhatsAppRecipients()));

if (failures.length) {
  console.error(`failed ${failures.length}`);
  process.exit(1);
}
console.log("audit checks passed");
