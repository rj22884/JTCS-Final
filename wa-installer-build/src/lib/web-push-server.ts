import "server-only";

import { getDb } from "@/lib/db";
import type { InboundPushItem } from "@/lib/whatsapp/inbox";
import webpush from "web-push";

export type PushSubscriptionJSON = {
  endpoint: string;
  expirationTime?: number | null;
  keys: { p256dh: string; auth: string };
};

export type { InboundPushItem };

function vapidConfigured() {
  const publicKey = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY?.trim();
  const privateKey = process.env.VAPID_PRIVATE_KEY?.trim();
  return Boolean(publicKey && privateKey);
}

function ensureVapid() {
  const publicKey = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY?.trim();
  const privateKey = process.env.VAPID_PRIVATE_KEY?.trim();
  if (!publicKey || !privateKey) return false;
  const subject =
    process.env.VAPID_SUBJECT?.trim() ||
    process.env.SMTP_FROM?.trim() ||
    process.env.ADMIN_EMAIL?.trim() ||
    "mailto:admin@ukdscwala.com";
  const contact = subject.includes("@") && !subject.startsWith("mailto:") ? `mailto:${subject}` : subject;
  webpush.setVapidDetails(contact.startsWith("mailto:") ? contact : `mailto:${contact}`, publicKey, privateKey);
  return true;
}

export function pushPublicKey() {
  return process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY?.trim() || "";
}

export function savePushSubscription(userId: string, subscription: PushSubscriptionJSON) {
  const endpoint = subscription.endpoint?.trim();
  const p256dh = subscription.keys?.p256dh?.trim();
  const auth = subscription.keys?.auth?.trim();
  if (!endpoint || !p256dh || !auth) throw new Error("invalid_subscription");
  const now = new Date().toISOString();
  getDb()
    .prepare(
      `INSERT INTO push_subscriptions (endpoint, user_id, p256dh, auth, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?)
       ON CONFLICT(endpoint) DO UPDATE SET
         user_id = excluded.user_id,
         p256dh = excluded.p256dh,
         auth = excluded.auth,
         updated_at = excluded.updated_at`,
    )
    .run(endpoint, userId, p256dh, auth, now, now);
}

export function deletePushSubscription(userId: string, endpoint?: string | null) {
  if (endpoint?.trim()) {
    getDb().prepare("DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?").run(userId, endpoint.trim());
    return;
  }
  getDb().prepare("DELETE FROM push_subscriptions WHERE user_id = ?").run(userId);
}

/** Total unread across open chats (for home-screen / PWA badge). */
export function totalUnreadForBadge() {
  const row = getDb()
    .prepare(
      `SELECT COALESCE(SUM(unread_count), 0) AS total
       FROM conversations
       WHERE IFNULL(archived, 0) = 0 AND IFNULL(blocked, 0) = 0`,
    )
    .get() as { total: number | bigint } | undefined;
  return Math.max(0, Number(row?.total ?? 0));
}

export async function notifyPushSubscribers(items: InboundPushItem[]) {
  if (!items.length || !vapidConfigured() || !ensureVapid()) return { sent: 0, removed: 0 };
  const rows = getDb()
    .prepare("SELECT endpoint, p256dh, auth FROM push_subscriptions")
    .all() as { endpoint: string; p256dh: string; auth: string }[];
  if (!rows.length) return { sent: 0, removed: 0 };

  let sent = 0;
  let removed = 0;
  const stale: string[] = [];
  const unreadBadge = totalUnreadForBadge();

  for (const item of items) {
    const payload = JSON.stringify({
      title: item.title || "WhatsApp CRM",
      body: (item.body || "New WhatsApp message").slice(0, 180),
      conversationId: item.conversationId,
      tag: `wa-msg-${item.conversationId}`,
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      unreadBadge,
    });
    await Promise.all(
      rows.map(async (row) => {
        try {
          await webpush.sendNotification(
            { endpoint: row.endpoint, keys: { p256dh: row.p256dh, auth: row.auth } },
            payload,
            { urgency: "high", TTL: 60 * 60 },
          );
          sent += 1;
        } catch (error) {
          const status = typeof error === "object" && error && "statusCode" in error ? Number((error as { statusCode?: number }).statusCode) : 0;
          if (status === 404 || status === 410) stale.push(row.endpoint);
        }
      }),
    );
  }

  if (stale.length) {
    const del = getDb().prepare("DELETE FROM push_subscriptions WHERE endpoint = ?");
    for (const endpoint of new Set(stale)) {
      del.run(endpoint);
      removed += 1;
    }
  }
  return { sent, removed };
}
