(function () {
  "use strict";

  const page = document.getElementById("crmCalendarPage");
  if (!page) return;

  const apiEvents = page.dataset.apiEvents;
  const listEl = document.getElementById("crmCalEventList");
  const emptyEl = document.getElementById("crmCalEmpty");
  const fromInput = document.getElementById("crmCalFrom");
  const toInput = document.getElementById("crmCalTo");

  function isoDate(d) {
    return d.toISOString().slice(0, 10);
  }

  function initDates() {
    const today = new Date();
    const start = new Date(today.getFullYear(), today.getMonth(), 1);
    const end = new Date(today.getFullYear(), today.getMonth() + 1, 0);
    if (fromInput && !fromInput.value) fromInput.value = isoDate(start);
    if (toInput && !toInput.value) toInput.value = isoDate(end);
  }

  function renderEvents(rows) {
    if (!rows.length) {
      listEl.innerHTML = "";
      emptyEl.classList.remove("d-none");
      return;
    }
    emptyEl.classList.add("d-none");
    listEl.innerHTML = rows
      .map(function (ev) {
        return (
          '<div class="crm-calendar-event">' +
          '<div class="fw-semibold">' + CrmCommon.escapeHtml(ev.title || ev.Title || ev.Subject || ev.event_type || ev.EventType || "Event") + "</div>" +
          '<div class="small text-muted">' + CrmCommon.formatDate(ev.starts_at || ev.StartAt || ev.DueAt || ev.EventDate) + "</div>" +
          (ev.Description ? '<div class="small mt-1">' + CrmCommon.escapeHtml(ev.Description) + "</div>" : "") +
          "</div>"
        );
      })
      .join("");
  }

  async function loadEvents() {
    const params = new URLSearchParams();
    if (fromInput && fromInput.value) params.set("from", fromInput.value);
    if (toInput && toInput.value) params.set("to", toInput.value);
    const data = await CrmCommon.apiFetch(apiEvents + "?" + params.toString());
    renderEvents(data.rows || []);
  }

  document.getElementById("crmCalLoadBtn").addEventListener("click", function () {
    loadEvents().catch(function (err) {
      CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
    });
  });

  initDates();
  loadEvents().catch(function () { /* ignore */ });
})();
