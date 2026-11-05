import { requireSession, requireUser } from "@/lib/admin";
import { ensureRequestTime, json } from "@/lib/http";
import {
  deletePushSubscription,
  pushPublicKey,
  savePushSubscription,
  type PushSubscriptionJSON,
} from "@/lib/web-push-server";
import type { NextRequest } from "next/server";

function readSubscription(body: unknown): PushSubscriptionJSON | null {
  if (!body || typeof body !== "object" || Array.isArray(body)) return null;
  const endpoint = typeof (body as { endpoint?: unknown }).endpoint === "string" ? (body as { endpoint: string }).endpoint : "";
  const keys = (body as { keys?: unknown }).keys;
  if (!keys || typeof keys !== "object" || Array.isArray(keys)) return null;
  const p256dh = typeof (keys as { p256dh?: unknown }).p256dh === "string" ? (keys as { p256dh: string }).p256dh : "";
  const auth = typeof (keys as { auth?: unknown }).auth === "string" ? (keys as { auth: string }).auth : "";
  if (!endpoint || !p256dh || !auth) return null;
  return { endpoint, keys: { p256dh, auth } };
}

export async function GET(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireSession(request);
  if (gate.error) return gate.error;
  return json({ ok: true, publicKey: pushPublicKey(), configured: Boolean(pushPublicKey()) });
}

export async function POST(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireUser(request);
  if (gate.error) return gate.error;
  const userId = gate.session?.userId;
  if (!userId) return json({ ok: false, error: "unauthorized" }, 401);
  if (!pushPublicKey()) {
    return json({ ok: false, error: "push_not_configured", detail: "VAPID keys are not set on the server." }, 503);
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return json({ ok: false, error: "invalid_json" }, 400);
  }
  const subscription = readSubscription(body);
  if (!subscription) return json({ ok: false, error: "invalid_subscription" }, 400);
  try {
    savePushSubscription(userId, subscription);
    return json({ ok: true });
  } catch {
    return json({ ok: false, error: "storage_unavailable" }, 500);
  }
}

export async function DELETE(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireUser(request);
  if (gate.error) return gate.error;
  const userId = gate.session?.userId;
  if (!userId) return json({ ok: false, error: "unauthorized" }, 401);
  let endpoint: string | null = null;
  try {
    const body = (await request.json().catch(() => null)) as { endpoint?: string } | null;
    endpoint = typeof body?.endpoint === "string" ? body.endpoint : null;
  } catch {
    endpoint = null;
  }
  try {
    deletePushSubscription(userId, endpoint);
    return json({ ok: true });
  } catch {
    return json({ ok: false, error: "storage_unavailable" }, 500);
  }
}
