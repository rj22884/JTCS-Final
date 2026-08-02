(function () {
  "use strict";

  const page = document.getElementById("crmNotificationsPage");
  if (!page) return;

  const api = {
    list: page.dataset.apiList,
    read: page.dataset.apiRead,
    readAll: page.dataset.apiReadAll,
    archive: page.dataset.apiArchive,
  };

  const listEl = document.getElementById("crmNotifList");
  const emptyEl = document.getElementById("crmNotifEmpty");
  const countEl = document.getElementById("crmNotifCount");
  const filterEl = document.getElementById("crmNotifFilter");

  function renderRows(rows) {
    if (!rows.length) {
      listEl.innerHTML = "";
      emptyEl.classList.remove("d-none");
      return;
    }
    emptyEl.classList.add("d-none");
    listEl.innerHTML = rows
      .map(function (row) {
        const id = row.NotificationID;
        const unread = !row.IsRead ? " list-group-item-primary" : "";
        const href = row.LinkURL || "#";
        return (
          '<div class="list-group-item' + unread + '">' +
          '<div class="d-flex justify-content-between align-items-start gap-2">' +
          '<div class="flex-grow-1">' +
          (href !== "#" ? '<a href="' + CrmCommon.escapeHtml(href) + '" class="fw-semibold text-decoration-none">' : "<strong>") +
          CrmCommon.escapeHtml(row.Title || "Notification") +
          (href !== "#" ? "</a>" : "</strong>") +
          (row.Message ? '<div class="small text-muted mt-1">' + CrmCommon.escapeHtml(row.Message) + "</div>" : "") +
          '<div class="small text-muted">' + CrmCommon.formatDate(row.CreatedDate) + "</div>" +
          "</div>" +
          '<div class="btn-group btn-group-sm">' +
          (!row.IsRead ? '<button type="button" class="btn btn-outline-primary crm-notif-read" data-id="' + id + '">Read</button>' : "") +
          (!row.IsArchived ? '<button type="button" class="btn btn-outline-secondary crm-notif-archive" data-id="' + id + '">Archive</button>' : "") +
          "</div></div></div>"
        );
      })
      .join("");
  }

  async function loadNotifications() {
    const params = new URLSearchParams();
    const filter = filterEl ? filterEl.value : "";
    if (filter === "unread") params.set("unread", "1");
    if (filter === "archived") params.set("archived", "1");
    const data = await CrmCommon.apiFetch(api.list + "?" + params.toString());
    renderRows(data.rows || []);
    if (countEl) countEl.textContent = (data.total || 0) + " notification(s)";
  }

  document.getElementById("crmNotifRefreshBtn").addEventListener("click", loadNotifications);
  if (filterEl) filterEl.addEventListener("change", loadNotifications);

  document.getElementById("crmNotifMarkAllBtn").addEventListener("click", async function () {
    try {
      await CrmCommon.apiFetch(api.readAll, { method: "POST", body: {} });
      loadNotifications();
    } catch (err) {
      CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
    }
  });

  listEl.addEventListener("click", async function (e) {
    const readBtn = e.target.closest(".crm-notif-read");
    const archiveBtn = e.target.closest(".crm-notif-archive");
    if (readBtn) {
      try {
        await CrmCommon.apiFetch(CrmCommon.urlTemplate(api.read, readBtn.dataset.id), { method: "POST", body: {} });
        loadNotifications();
      } catch (err) {
        CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
      }
    }
    if (archiveBtn) {
      try {
        await CrmCommon.apiFetch(CrmCommon.urlTemplate(api.archive, archiveBtn.dataset.id), { method: "POST", body: {} });
        loadNotifications();
      } catch (err) {
        CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
      }
    }
  });

  loadNotifications();
})();
