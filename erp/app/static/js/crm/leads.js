(function () {
  "use strict";

  const page = document.getElementById("crmLeadsPage");
  if (!page) return;

  const api = {
    list: page.dataset.apiList,
    create: page.dataset.apiCreate,
    convert: page.dataset.apiConvert,
    assign: page.dataset.apiAssign,
  };

  const gridBody = document.getElementById("crmLeadGridBody");
  const emptyEl = document.getElementById("crmLeadEmpty");
  const countEl = document.getElementById("crmLeadCount");
  const searchInput = document.getElementById("crmLeadSearch");
  const statusFilter = document.getElementById("crmLeadStatusFilter");
  const createForm = document.getElementById("crmLeadCreateForm");
  const formError = document.getElementById("crmLeadFormError");
  const assignForm = document.getElementById("crmLeadAssignForm");
  const assignError = document.getElementById("crmLeadAssignError");
  const assignModalEl = document.getElementById("crmLeadAssignModal");
  const createModalEl = document.getElementById("crmLeadCreateModal");
  let assignModal = assignModalEl ? bootstrap.Modal.getOrCreateInstance(assignModalEl) : null;
  let createModal = createModalEl ? bootstrap.Modal.getOrCreateInstance(createModalEl) : null;

  function renderRows(rows) {
    if (!rows.length) {
      gridBody.innerHTML = "";
      emptyEl.classList.remove("d-none");
      return;
    }
    emptyEl.classList.add("d-none");
    gridBody.innerHTML = rows
      .map(function (row) {
        const id = row.LeadID;
        const canConvert = row.Status !== "Converted" && row.Status !== "Closed" && row.Status !== "Lost";
        const detailHref = "/crm/leads/" + id;
        return (
          "<tr>" +
          '<td><a href="' +
          detailHref +
          '" class="text-decoration-none">' +
          CrmCommon.escapeHtml(id) +
          "</a></td>" +
          '<td><a href="' +
          detailHref +
          '" class="text-decoration-none fw-semibold">' +
          CrmCommon.escapeHtml(row.FullName || "—") +
          "</a></td>" +
          "<td>" + CrmCommon.escapeHtml(row.Mobile || "—") + "</td>" +
          "<td>" + CrmCommon.escapeHtml(row.Email || "—") + "</td>" +
          "<td>" + CrmCommon.escapeHtml(row.Source || "—") + "</td>" +
          "<td>" + CrmCommon.escapeHtml(row.Status || "—") + "</td>" +
          "<td>" + CrmCommon.escapeHtml(row.Priority || "—") + "</td>" +
          "<td>" + CrmCommon.formatDateOnly(row.CreatedDate) + "</td>" +
          '<td class="text-end">' +
          (canConvert
            ? '<button type="button" class="btn btn-sm btn-outline-success me-1 crm-lead-convert" data-id="' + id + '">Convert</button>'
            : "") +
          '<button type="button" class="btn btn-sm btn-outline-secondary crm-lead-assign" data-id="' + id + '">Assign</button>' +
          "</td></tr>"
        );
      })
      .join("");
  }

  async function loadLeads() {
    const params = new URLSearchParams();
    if (statusFilter && statusFilter.value) params.set("status", statusFilter.value);
    if (searchInput && searchInput.value.trim()) params.set("search", searchInput.value.trim());
    const data = await CrmCommon.apiFetch(api.list + "?" + params.toString());
    renderRows(data.rows || []);
    if (countEl) countEl.textContent = (data.total || 0) + " lead(s)";
  }

  if (document.getElementById("crmLeadRefreshBtn")) {
    document.getElementById("crmLeadRefreshBtn").addEventListener("click", loadLeads);
  }
  if (searchInput) searchInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") loadLeads();
  });
  if (statusFilter) statusFilter.addEventListener("change", loadLeads);

  if (createForm) {
    createForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      formError.classList.add("d-none");
      const payload = {
        full_name: document.getElementById("crmLeadFullName").value.trim(),
        mobile: document.getElementById("crmLeadMobile").value.trim() || null,
        email: document.getElementById("crmLeadEmail").value.trim() || null,
        business_name: document.getElementById("crmLeadBusiness").value.trim() || null,
        source: document.getElementById("crmLeadSource").value,
        request_type: document.getElementById("crmLeadRequestType").value,
        priority: document.getElementById("crmLeadPriority").value,
        message: document.getElementById("crmLeadMessage").value.trim() || null,
      };
      try {
        await CrmCommon.apiFetch(api.create, { method: "POST", body: payload });
        createForm.reset();
        if (createModal) createModal.hide();
        loadLeads();
      } catch (err) {
        formError.textContent = (err.data && err.data.error) || err.message;
        formError.classList.remove("d-none");
      }
    });
  }

  gridBody.addEventListener("click", async function (e) {
    const convertBtn = e.target.closest(".crm-lead-convert");
    const assignBtn = e.target.closest(".crm-lead-assign");
    if (convertBtn) {
      const id = convertBtn.dataset.id;
      if (!(await JTCSDialog.confirm("Convert this lead to customer?"))) return;
      try {
        await CrmCommon.apiFetch(CrmCommon.urlTemplate(api.convert, id), { method: "POST", body: {} });
        loadLeads();
      } catch (err) {
        CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
      }
    }
    if (assignBtn) {
      document.getElementById("crmLeadAssignId").value = assignBtn.dataset.id;
      document.getElementById("crmLeadAssignUserId").value = "";
      assignError.classList.add("d-none");
      if (assignModal) assignModal.show();
    }
  });

  if (assignForm) {
    assignForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      assignError.classList.add("d-none");
      const id = document.getElementById("crmLeadAssignId").value;
      const userId = parseInt(document.getElementById("crmLeadAssignUserId").value, 10);
      try {
        await CrmCommon.apiFetch(CrmCommon.urlTemplate(api.assign, id), {
          method: "POST",
          body: { assigned_user_id: userId },
        });
        if (assignModal) assignModal.hide();
        loadLeads();
      } catch (err) {
        assignError.textContent = (err.data && err.data.error) || err.message;
        assignError.classList.remove("d-none");
      }
    });
  }

  loadLeads();
})();
