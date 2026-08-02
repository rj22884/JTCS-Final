(function () {
  "use strict";

  const page = document.getElementById("crmAuditPage");
  if (!page) return;

  const apiList = page.dataset.apiList;
  const gridBody = document.getElementById("crmAuditGridBody");
  const emptyEl = document.getElementById("crmAuditEmpty");
  const countEl = document.getElementById("crmAuditCount");

  function renderRows(rows) {
    if (!rows.length) {
      gridBody.innerHTML = "";
      emptyEl.classList.remove("d-none");
      return;
    }
    emptyEl.classList.add("d-none");
    gridBody.innerHTML = rows
      .map(function (row) {
        const entity = (row.EntityType || "—") + (row.EntityID ? " #" + row.EntityID : "");
        const details = row.ChangeSummary || row.Details || row.NewValues || row.OldValues || "";
        return (
          "<tr>" +
          "<td>" + CrmCommon.formatDate(row.CreatedDate || row.AuditDate) + "</td>" +
          "<td>" + CrmCommon.escapeHtml(row.UserName || row.user_name || "—") + "</td>" +
          "<td>" + CrmCommon.escapeHtml(row.ActionType || row.Action || "—") + "</td>" +
          "<td>" + CrmCommon.escapeHtml(entity) + "</td>" +
          '<td class="small">' + CrmCommon.escapeHtml(String(details).slice(0, 200)) + "</td>" +
          "</tr>"
        );
      })
      .join("");
  }

  async function loadAudit() {
    const params = new URLSearchParams();
    const entityType = document.getElementById("crmAuditEntityType").value.trim();
    const entityId = document.getElementById("crmAuditEntityId").value;
    if (entityType) params.set("entity_type", entityType);
    if (entityId) params.set("entity_id", entityId);
    const data = await CrmCommon.apiFetch(apiList + "?" + params.toString());
    renderRows(data.rows || []);
    if (countEl) countEl.textContent = (data.total || 0) + " entr(ies)";
  }

  document.getElementById("crmAuditLoadBtn").addEventListener("click", function () {
    loadAudit().catch(function (err) {
      CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
    });
  });

  loadAudit().catch(function () { /* ignore */ });
})();
