(function () {
  "use strict";

  const page = document.getElementById("crmFollowupsPage");
  if (!page) return;

  const api = {
    list: page.dataset.apiList,
    create: page.dataset.apiCreate,
    complete: page.dataset.apiComplete,
  };

  const gridBody = document.getElementById("crmFollowupGridBody");
  const emptyEl = document.getElementById("crmFollowupEmpty");
  const countEl = document.getElementById("crmFollowupCount");
  const statusFilter = document.getElementById("crmFollowupStatusFilter");
  const createForm = document.getElementById("crmFollowupCreateForm");
  const formError = document.getElementById("crmFollowupFormError");
  const createModalEl = document.getElementById("crmFollowupCreateModal");
  const createModal = createModalEl ? bootstrap.Modal.getOrCreateInstance(createModalEl) : null;

  function renderRows(rows) {
    if (!rows.length) {
      gridBody.innerHTML = "";
      emptyEl.classList.remove("d-none");
      return;
    }
    emptyEl.classList.add("d-none");
    gridBody.innerHTML = rows
      .map(function (row) {
        const id = row.FollowUpID;
        const who = row.CustomerName || (row.CustomerID ? "C#" + row.CustomerID : "") || row.LeadName || (row.LeadID ? "L#" + row.LeadID : "") || "—";
        const canComplete = row.Status === "Pending";
        return (
          "<tr>" +
          "<td>" + CrmCommon.escapeHtml(row.FollowUpType || "—") + "</td>" +
          "<td>" + CrmCommon.escapeHtml(row.Subject || "—") + "</td>" +
          "<td>" + CrmCommon.escapeHtml(who) + "</td>" +
          "<td>" + CrmCommon.formatDate(row.DueAt) + "</td>" +
          "<td>" + CrmCommon.escapeHtml(row.Priority || "—") + "</td>" +
          "<td>" + CrmCommon.escapeHtml(row.Status || "—") + "</td>" +
          '<td class="text-end">' +
          (canComplete ? '<button type="button" class="btn btn-sm btn-outline-success crm-fu-complete" data-id="' + id + '">Complete</button>' : "—") +
          "</td></tr>"
        );
      })
      .join("");
  }

  async function loadFollowups() {
    const params = new URLSearchParams();
    if (statusFilter && statusFilter.value) params.set("status", statusFilter.value);
    const data = await CrmCommon.apiFetch(api.list + "?" + params.toString());
    renderRows(data.rows || []);
    if (countEl) countEl.textContent = (data.total || 0) + " follow-up(s)";
  }

  if (document.getElementById("crmFollowupRefreshBtn")) {
    document.getElementById("crmFollowupRefreshBtn").addEventListener("click", loadFollowups);
  }
  if (statusFilter) statusFilter.addEventListener("change", loadFollowups);

  if (createForm) {
    createForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      formError.classList.add("d-none");
      const dueVal = document.getElementById("crmFollowupDue").value;
      const payload = {
        followup_type: document.getElementById("crmFollowupType").value,
        subject: document.getElementById("crmFollowupSubject").value.trim() || null,
        due_at: dueVal ? dueVal.replace("T", " ") + ":00" : null,
        priority: document.getElementById("crmFollowupPriority").value,
        notes: document.getElementById("crmFollowupNotes").value.trim() || null,
      };
      const cid = document.getElementById("crmFollowupCustomerId").value;
      const lid = document.getElementById("crmFollowupLeadId").value;
      if (cid) payload.customer_id = parseInt(cid, 10);
      if (lid) payload.lead_id = parseInt(lid, 10);
      try {
        await CrmCommon.apiFetch(api.create, { method: "POST", body: payload });
        createForm.reset();
        if (createModal) createModal.hide();
        loadFollowups();
      } catch (err) {
        formError.textContent = (err.data && err.data.error) || err.message;
        formError.classList.remove("d-none");
      }
    });
  }

  gridBody.addEventListener("click", async function (e) {
    const btn = e.target.closest(".crm-fu-complete");
    if (!btn) return;
    try {
      await CrmCommon.apiFetch(CrmCommon.urlTemplate(api.complete, btn.dataset.id), { method: "POST", body: {} });
      loadFollowups();
    } catch (err) {
      CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
    }
  });

  loadFollowups();
})();
