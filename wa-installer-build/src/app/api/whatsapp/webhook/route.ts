import { ensureRequestTime, json } from "@/lib/http";
import { resolveSecret } from "@/lib/secrets";
import { notifyPushSubscribers } from "@/lib/web-push-server";
import { eventIdsForPayload, isWhatsAppPayload, rememberEvents } from "@/lib/whatsapp/events";
import { applyWhatsAppPayload } from "@/lib/whatsapp/inbox";
import { mailboxReady } from "@/lib/whatsapp/status";
import { verifyMetaSignature, webhookChallengeMatches } from "@/lib/whatsapp/signature";
import type { NextRequest } from "next/server";

const MAX_BODY = 1_000_000;

export async function GET(request: NextRequest) {
  await ensureRequestTime();
  let verifyToken: string | null = null;
  try {
    verifyToken = resolveSecret("verifyToken");
  } catch {
    return json({ ok: false, live: false, error: "storage_unavailable" }, 500);
  }
  if (!verifyToken) {
    return json(
      {
        ok: false,
        live: false,
        error: "not_configured",
        detail:
          "Webhook verification is not configured. Set the verify token on this server. This endpoint is not live.",
      },
      503,
    );
  }

  const mode = request.nextUrl.searchParams.get("hub.mode");
  const token = request.nextUrl.searchParams.get("hub.verify_token") ?? "";
  const challenge = request.nextUrl.searchParams.get("hub.challenge");
  if (webhookChallengeMatches({ mode, verifyToken, provided: token, challenge })) {
    return new Response(challenge, {
      status: 200,
      headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" },
    });
  }

  return new Response("Forbidden", {
    status: 403,
    headers: { "Cache-Control": "no-store" },
  });
}

export async function POST(request: NextRequest) {
  await ensureRequestTime();
  let appSecret: string | null = null;
  try {
    appSecret = resolveSecret("appSecret");
  } catch {
    return json({ ok: false, live: false, applied: false, error: "storage_unavailable" }, 500);
  }
  if (!appSecret) {
    return json(
      {
        ok: false,
        live: false,
        applied: false,
        error: "not_configured",
        detail:
          "Webhook signature verification is not configured. Set the app secret on this server. Unsigned events are refused.",
      },
      503,
    );
  }

  const declaredLength = Number(request.headers.get("content-length") ?? "0");
  if (Number.isFinite(declaredLength) && declaredLength > MAX_BODY) {
    return json({ ok: false, applied: false, error: "payload_too_large" }, 413);
  }

  const rawBody = await request.text();
  if (rawBody.length > MAX_BODY) return json({ ok: false, applied: false, error: "payload_too_large" }, 413);
  if (!rawBody) return json({ ok: false, applied: false, error: "empty_body" }, 400);

  const valid = verifyMetaSignature(rawBody, request.headers.get("x-hub-signature-256"), appSecret);
  if (!valid) return json({ ok: false, applied: false, error: "invalid_signature" }, 401);

  let payload: unknown;
  try {
    payload = JSON.parse(rawBody) as unknown;
  } catch {
    return json({ ok: false, applied: false, error: "invalid_json" }, 400);
  }
  if (!isWhatsAppPayload(payload)) return json({ ok: false, applied: false, error: "unexpected_object" }, 400);

  const ids = eventIdsForPayload(rawBody, payload);
  try {
    const { applied: appliedCount, notifications } = applyWhatsAppPayload(payload);
    const receipt = rememberEvents(ids);
    const live = mailboxReady();
    let pushSent = 0;
    if (notifications.length) {
      try {
        const push = await notifyPushSubscribers(notifications);
        pushSent = push.sent;
      } catch {
        pushSent = 0;
      }
    }
    return json({
      ok: true,
      live,
      applied: appliedCount > 0,
      pushSent,
      duplicate: receipt.duplicate,
      accepted: receipt.accepted,
      detail:
        appliedCount > 0
          ? "The message was saved in this inbox."
          : receipt.duplicate
            ? "These event ids were already recorded."
            : "Signature checked. No new text message was in this event.",
    });
  } catch {
    return json({ ok: false, live: false, applied: false, error: "storage_unavailable" }, 500);
  }
}
