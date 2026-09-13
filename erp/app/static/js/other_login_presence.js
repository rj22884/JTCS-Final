(function () {
  const cfg = window.OTHER_LOGIN_PRESENCE || {};
  if (!cfg.url) return;
  const initial = !!cfg.online;
  async function ping() {
    try {
      const res = await fetch(cfg.url, { headers: { Accept: "application/json" } });
      const data = await res.json();
      if (typeof data.online === "boolean" && data.online !== initial) {
        window.location.reload();
      }
    } catch (_err) {
      /* keep current page */
    }
  }
  window.setInterval(ping, 15000);
})();
