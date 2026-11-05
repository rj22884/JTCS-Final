/** Browser + Web Push notifications (tab open, background, or browser closed). */

export type NotifyPermission = NotificationPermission | "unsupported";

const PREF_KEY = "wa_desktop_notify";

export function notificationSupport(): boolean {
  return typeof window !== "undefined" && "Notification" in window;
}

export function pushSupport(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    notificationSupport()
  );
}

export function getNotifyPermission(): NotifyPermission {
  if (!notificationSupport()) return "unsupported";
  return Notification.permission;
}

export function getNotifyPreference(): "on" | "off" | "unset" {
  if (typeof window === "undefined") return "unset";
  const value = window.localStorage.getItem(PREF_KEY);
  if (value === "on" || value === "off") return value;
  return "unset";
}

export function setNotifyPreference(value: "on" | "off") {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(PREF_KEY, value);
}

function urlBase64ToUint8Array(base64String: string) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) outputArray[i] = rawData.charCodeAt(i);
  return outputArray;
}

export async function registerPushServiceWorker() {
  if (!pushSupport()) return null;
  return navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" });
}

async function fetchVapidPublicKey(authedFetch: typeof fetch) {
  const response = await authedFetch("/api/push/subscribe", { method: "GET", cache: "no-store" });
  if (!response.ok) return "";
  const data = (await response.json()) as { publicKey?: string };
  return data.publicKey?.trim() || "";
}

export async function enablePushNotifications(
  authedFetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>,
) {
  if (!pushSupport()) {
    return { ok: false as const, reason: "unsupported" as const };
  }
  const permission =
    Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
  if (permission !== "granted") {
    setNotifyPreference("off");
    return { ok: false as const, reason: "denied" as const, permission };
  }
  setNotifyPreference("on");

  const registration = await registerPushServiceWorker();
  if (!registration) return { ok: false as const, reason: "unsupported" as const };
  await registration.update().catch(() => undefined);
  await navigator.serviceWorker.ready;

  const publicKey = await fetchVapidPublicKey(authedFetch);
  if (!publicKey) return { ok: false as const, reason: "not_configured" as const, permission: "granted" as const };

  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey),
    });
  }

  const response = await authedFetch("/api/push/subscribe", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(subscription.toJSON()),
  });
  if (!response.ok) {
    return { ok: false as const, reason: "subscribe_failed" as const, permission: "granted" as const };
  }
  return { ok: true as const, permission: "granted" as const };
}

export async function disablePushNotifications(
  authedFetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>,
) {
  setNotifyPreference("off");
  if (!pushSupport()) return;
  try {
    const registration = await navigator.serviceWorker.getRegistration("/");
    const subscription = await registration?.pushManager.getSubscription();
    const endpoint = subscription?.endpoint;
    if (subscription) await subscription.unsubscribe();
    await authedFetch("/api/push/subscribe", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ endpoint: endpoint || null }),
    });
  } catch {
    /* ignore */
  }
}

/** Re-register push if the user previously enabled notifications (after login / reload). */
export async function syncPushSubscription(
  authedFetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>,
) {
  if (getNotifyPreference() !== "on" || getNotifyPermission() !== "granted") return;
  await enablePushNotifications(authedFetch).catch(() => undefined);
}

export async function requestNotifyPermission(
  authedFetch?: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>,
): Promise<NotifyPermission> {
  if (!notificationSupport()) return "unsupported";
  if (authedFetch && pushSupport()) {
    const result = await enablePushNotifications(authedFetch);
    if (result.ok) return "granted";
    if (result.reason === "denied") return "denied";
    if (result.reason === "unsupported") return "unsupported";
    // Fall through to page Notification permission if push config missing.
  }
  if (Notification.permission === "granted") {
    setNotifyPreference("on");
    return "granted";
  }
  if (Notification.permission === "denied") {
    setNotifyPreference("off");
    return "denied";
  }
  const result = await Notification.requestPermission();
  setNotifyPreference(result === "granted" ? "on" : "off");
  return result;
}

export function canShowDesktopNotification() {
  return notificationSupport() && Notification.permission === "granted" && getNotifyPreference() !== "off";
}

export function showDesktopNotification(input: {
  title: string;
  body: string;
  tag?: string;
  conversationId?: string;
}) {
  if (!canShowDesktopNotification()) return null;
  try {
    const notification = new Notification(input.title || "WhatsApp CRM", {
      body: input.body.slice(0, 180),
      tag: input.tag || input.conversationId || "wa-crm",
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
    });
    notification.onclick = () => {
      window.focus();
      if (input.conversationId) {
        window.location.assign(`/?c=${encodeURIComponent(input.conversationId)}`);
      }
      notification.close();
    };
    return notification;
  } catch {
    return null;
  }
}

export function setDocumentUnreadTitle(unread: number, base = "WhatsApp CRM") {
  if (typeof document === "undefined") return;
  document.title = unread > 0 ? `(${unread}) ${base}` : base;
}

/** Home-screen / taskbar unread badge (Badging API + service worker). */
export async function setAppUnreadBadge(unread: number) {
  if (typeof window === "undefined") return;
  const count = Math.max(0, Math.floor(unread));
  try {
    if (count > 0) {
      if ("setAppBadge" in navigator) await navigator.setAppBadge(Math.min(count, 99));
    } else if ("clearAppBadge" in navigator) {
      await navigator.clearAppBadge();
    }
  } catch {
    /* unsupported */
  }
  try {
    const registration = await navigator.serviceWorker?.getRegistration("/");
    registration?.active?.postMessage({ type: "SET_BADGE", count });
  } catch {
    /* ignore */
  }
}

export type UnreadSnapshot = {
  unreadCount: number;
  lastMessageAt: string;
  lastMessage: string;
  lastDirection: "inbound" | "outbound";
  name: string;
};

/** Compare poll results and return conversations that gained new inbound unread mail. */
export function detectNewInboundUnread(
  previous: Map<string, UnreadSnapshot> | null,
  next: Array<{
    id: string;
    name: string;
    unreadCount: number;
    lastMessage: string;
    lastMessageAt: string;
    lastDirection: "inbound" | "outbound";
  }>,
) {
  const map = new Map<string, UnreadSnapshot>();
  const gained: Array<{ id: string; name: string; body: string }> = [];
  for (const item of next) {
    map.set(item.id, {
      unreadCount: item.unreadCount,
      lastMessageAt: item.lastMessageAt,
      lastMessage: item.lastMessage,
      lastDirection: item.lastDirection,
      name: item.name,
    });
    if (!previous) continue;
    const before = previous.get(item.id);
    const unreadGrew = item.unreadCount > (before?.unreadCount ?? 0);
    const newerInbound =
      item.lastDirection === "inbound" &&
      item.unreadCount > 0 &&
      (!before || item.lastMessageAt > before.lastMessageAt);
    if (unreadGrew || newerInbound) {
      gained.push({
        id: item.id,
        name: item.name,
        body: item.lastMessage || "New WhatsApp message",
      });
    }
  }
  return { map, gained };
}
