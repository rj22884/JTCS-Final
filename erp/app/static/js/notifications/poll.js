(function () {
  "use strict";

  const header = document.querySelector(".jtcs-app-header");
  if (!header || !header.dataset.pollUrl) return;

  const pollUrl = header.dataset.pollUrl;
  const pollSeconds = Math.max(5, parseInt(header.dataset.pollSeconds, 10) || 15);
  const badgeEl = document.getElementById("jtcsNotifyBadge");
  const crmListEl = document.getElementById("jtcsNotifyCrmList");
  const emptyEl = document.getElementById("jtcsNotifyEmpty");
  let pendingUserCount = parseInt(header.dataset.pendingUserCount, 10) || 0;

  function setBadge(total) {
    if (!badgeEl) return;
    if (total > 0) {
      badgeEl.textContent = String(total);
      badgeEl.classList.remove("d-none");
    } else {
      badgeEl.textContent = "0";
      badgeEl.classList.add("d-none");
    }
  }

  function renderCrmNotifications(rows) {
    if (!crmListEl) return;
    if (!rows || !rows.length) {
      crmListEl.innerHTML = "";
      if (emptyEl) emptyEl.classList.remove("d-none");
      return;
    }
    if (emptyEl) emptyEl.classList.add("d-none");
    crmListEl.innerHTML = rows
      .map(function (item) {
        const href = item.LinkURL || "/crm/notifications";
        const unread = !item.IsRead ? " jtcs-notify-unread" : "";
        const msg = item.Message ? String(item.Message).slice(0, 120) : "";
        return (
          '<a class="dropdown-item jtcs-notify-item' +
          unread +
          '" href="' +
          CrmCommon.escapeHtml(href) +
          '">' +
          '<div class="jtcs-notify-title"><i class="bi bi-bell-fill"></i> ' +
          CrmCommon.escapeHtml(item.Title || "Notification") +
          "</div>" +
          (msg ? '<div class="jtcs-notify-meta">' + CrmCommon.escapeHtml(msg) + "</div>" : "") +
          "</a>"
        );
      })
      .join("");
  }

  async function poll() {
    try {
      const data = await CrmCommon.apiFetch(pollUrl);
      const crmUnread = parseInt(data.unread_count, 10) || 0;
      const adminPending = pendingUserCount;
      setBadge(crmUnread + adminPending);
      renderCrmNotifications(data.rows || []);
    } catch (_err) {
      /* silent */
    }
  }

  setInterval(poll, pollSeconds * 1000);
})();
