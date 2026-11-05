/* WhatsApp CRM service worker — Web Push when tab/browser/PWA is closed or backgrounded. */
async function applyAppBadge(count) {
  try {
    if (typeof count !== "number" || !Number.isFinite(count)) return;
    if (count > 0) {
      if (self.registration.setAppBadge) await self.registration.setAppBadge(Math.min(count, 99));
    } else if (self.registration.clearAppBadge) {
      await self.registration.clearAppBadge();
    }
  } catch {
    /* Badging API unsupported on this device */
  }
}

self.addEventListener("push", (event) => {
  let data = {
    title: "WhatsApp CRM",
    body: "New WhatsApp message",
    conversationId: "",
    tag: "wa-crm",
    unreadBadge: undefined,
  };
  try {
    if (event.data) data = { ...data, ...event.data.json() };
  } catch {
    try {
      const text = event.data?.text();
      if (text) data.body = text;
    } catch {
      /* keep defaults */
    }
  }
  const conversationId = typeof data.conversationId === "string" ? data.conversationId : "";
  const tag = typeof data.tag === "string" && data.tag ? data.tag : conversationId ? `wa-msg-${conversationId}` : "wa-crm";
  const url = conversationId ? `/?c=${encodeURIComponent(conversationId)}` : "/";
  const unreadBadge = typeof data.unreadBadge === "number" ? data.unreadBadge : undefined;

  event.waitUntil(
    (async () => {
      await applyAppBadge(typeof unreadBadge === "number" ? unreadBadge : 1);

      const windowClients = await clients.matchAll({ type: "window", includeUncontrolled: true });
      // Only suppress the system notification when the CRM is visibly focused.
      // Background / closed PWA must always notify.
      const hasFocusedVisible = windowClients.some(
        (client) => client.focused && client.visibilityState === "visible",
      );
      if (hasFocusedVisible) return;

      await self.registration.showNotification(data.title || "WhatsApp CRM", {
        body: String(data.body || "New WhatsApp message").slice(0, 180),
        icon: data.icon || "/icons/icon-192.png",
        badge: data.badge || "/icons/icon-192.png",
        tag,
        renotify: true,
        requireInteraction: false,
        data: { conversationId, url, unreadBadge },
      });
    })(),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target =
    (event.notification.data && event.notification.data.url) ||
    (event.notification.data && event.notification.data.conversationId
      ? `/?c=${encodeURIComponent(event.notification.data.conversationId)}`
      : "/");
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((windowClients) => {
      for (const client of windowClients) {
        if ("focus" in client) {
          return client.focus().then((focused) => {
            if (focused && "navigate" in focused) {
              return focused.navigate(target).catch(() => clients.openWindow(target));
            }
            return clients.openWindow(target);
          });
        }
      }
      return clients.openWindow(target);
    }),
  );
});

self.addEventListener("message", (event) => {
  const data = event.data;
  if (!data || typeof data !== "object") return;
  if (data.type === "SET_BADGE") {
    event.waitUntil(applyAppBadge(Number(data.count) || 0));
  }
  if (data.type === "CLEAR_BADGE") {
    event.waitUntil(applyAppBadge(0));
  }
});
