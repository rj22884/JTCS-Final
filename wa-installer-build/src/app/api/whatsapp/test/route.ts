import { requireAdmin } from "@/lib/admin";
import { ensureRequestTime, json } from "@/lib/http";
import { resolveSecret } from "@/lib/secrets";
import { sendCloudText, testCloudConnection } from "@/lib/whatsapp/client";
import { testSendDecision } from "@/lib/whatsapp/cloud-form";
import type { NextRequest } from "next/server";

const MAX_BODY = 4_000;

export async function POST(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireAdmin(request);
  if (gate.error) return gate.error;
  let send = false;
  let confirm = false;
  let mobile = "";
  const raw = await request.text();
  if (raw.length > MAX_BODY) return json({ ok: false, detail: "The request is too large. No message was sent." }, 400);
  if (raw.trim()) {
    try {
      const parsed = JSON.parse(raw) as { send_test_message?: unknown; confirm_send?: unknown; test_to_number?: unknown };
      send = parsed.send_test_message === true;
      confirm = parsed.confirm_send === true;
      if (typeof parsed.test_to_number === "string") mobile = parsed.test_to_number;
    } catch {
      return json({ ok: false, detail: "The request could not be read. No message was sent." }, 400);
    }
  }
  const decision = testSendDecision({ send, confirm, mobile });
  if ("error" in decision && decision.error) {
    return json({ ok: false, live: false, detail: decision.error, checks: [] }, 400);
  }
  try {
    const result = await testCloudConnection({
      accessToken: resolveSecret("accessToken"),
      phoneNumberId: resolveSecret("phoneNumberId"),
      businessAccountId: resolveSecret("businessAccountId"),
      businessId: resolveSecret("businessId"),
      appId: resolveSecret("appId"),
      graphApiVersion: resolveSecret("graphApiVersion"),
      appSecretSet: Boolean(resolveSecret("appSecret")),
      verifyTokenSet: Boolean(resolveSecret("verifyToken")),
      webhookUrlSet: Boolean(resolveSecret("webhookUrl")),
    });
    if (!decision.send) return json(result);
    const sent = await sendCloudText({
      to: decision.to,
      body: "WhatsApp Cloud API test message.",
      phoneNumberId: resolveSecret("phoneNumberId") || "",
      accessToken: resolveSecret("accessToken") || "",
      graphApiVersion: resolveSecret("graphApiVersion"),
    });
    result.checks.push({
      id: "testMessage",
      label: "Optional test message",
      group: "meta",
      state: sent.ok ? "verified" : "not_verified",
      badge: sent.ok ? "Sent" : "Not sent",
      detail: sent.ok ? "Meta accepted the test message." : sent.detail,
    });
    if (!sent.ok) {
      result.ok = false;
      result.live = false;
      result.detail = sent.detail;
    }
    return json(result, sent.ok ? 200 : 502);
  } catch {
    return json(
      {
        ok: false,
        live: false,
        detail: "Test failed. No message was sent.",
        displayPhoneNumber: null,
        verifiedName: null,
        checks: [],
      },
      500,
    );
  }
}
