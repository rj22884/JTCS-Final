(function () {
  "use strict";

  const page = document.getElementById("crmTimelinePage");
  if (!page) return;

  const apiList = page.dataset.apiList;
  const listEl = document.getElementById("crmTimelineList");
  const emptyEl = document.getElementById("crmTimelineEmpty");

  function renderRows(rows) {
    if (!rows.length) {
      listEl.innerHTML = "";
      emptyEl.classList.remove("d-none");
      return;
    }
    emptyEl.classList.add("d-none");
    listEl.innerHTML = rows
      .map(function (ev) {
        return (
          '<li class="crm-timeline-item">' +
          '<div class="crm-timeline-title">' + CrmCommon.escapeHtml(ev.Title || ev.EventType || "Event") + "</div>" +
          '<div class="crm-timeline-meta">' +
          CrmCommon.formatDate(ev.CreatedDate) +
          (ev.UserName ? " · " + CrmCommon.escapeHtml(ev.UserName) : "") +
          "</div>" +
          (ev.Description ? '<div class="crm-timeline-desc">' + CrmCommon.escapeHtml(ev.Description) + "</div>" : "") +
          "</li>"
        );
      })
      .join("");
  }

  async function loadTimeline() {
    const params = new URLSearchParams();
    const cid = document.getElementById("crmTimelineCustomerId").value;
    const lid = document.getElementById("crmTimelineLeadId").value;
    if (cid) params.set("customer_id", cid);
    if (lid) params.set("lead_id", lid);
    const data = await CrmCommon.apiFetch(apiList + "?" + params.toString());
    renderRows(data.rows || []);
  }

  document.getElementById("crmTimelineLoadBtn").addEventListener("click", function () {
    loadTimeline().catch(function (err) {
      CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
    });
  });

  loadTimeline().catch(function () { /* ignore */ });
})();
