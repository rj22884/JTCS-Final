(function () {
  "use strict";

  const page = document.getElementById("crmTasksPage");
  if (!page) return;

  const api = {
    list: page.dataset.apiList,
    create: page.dataset.apiCreate,
    complete: page.dataset.apiComplete,
    update: page.dataset.apiUpdate,
  };

  const gridBody = document.getElementById("crmTaskGridBody");
  const emptyEl = document.getElementById("crmTaskEmpty");
  const countEl = document.getElementById("crmTaskCount");
  const statusFilter = document.getElementById("crmTaskStatusFilter");
  const createForm = document.getElementById("crmTaskCreateForm");
  const formError = document.getElementById("crmTaskFormError");
  const createModalEl = document.getElementById("crmTaskCreateModal");
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
        const id = row.TaskID;
        const canComplete = row.Status !== "Completed";
        const n = Math.min(100, Math.max(0, parseInt(row.Progress, 10) || 0));
        return (
          "<tr>" +
          "<td>" + CrmCommon.escapeHtml(row.Title || "—") + "</td>" +
          "<td>" + CrmCommon.escapeHtml(row.Priority || "—") + "</td>" +
          "<td>" + CrmCommon.formatDate(row.Deadline) + "</td>" +
          "<td><div class=\"progress crm-task-progress\"><div class=\"progress-bar\" style=\"width:" + n + "%\"></div></div> <span class=\"small\">" + n + "%</span></td>" +
          "<td>" + CrmCommon.escapeHtml(row.Status || "—") + "</td>" +
          '<td class="text-end">' +
          (canComplete ? '<button type="button" class="btn btn-sm btn-outline-success crm-task-complete" data-id="' + id + '">Complete</button>' : "—") +
          "</td></tr>"
        );
      })
      .join("");
  }

  async function loadTasks() {
    const params = new URLSearchParams();
    if (statusFilter && statusFilter.value) params.set("status", statusFilter.value);
    const data = await CrmCommon.apiFetch(api.list + "?" + params.toString());
    renderRows(data.rows || []);
    if (countEl) countEl.textContent = (data.total || 0) + " task(s)";
  }

  if (document.getElementById("crmTaskRefreshBtn")) {
    document.getElementById("crmTaskRefreshBtn").addEventListener("click", loadTasks);
  }
  if (statusFilter) statusFilter.addEventListener("change", loadTasks);

  if (createForm) {
    createForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      formError.classList.add("d-none");
      const deadlineVal = document.getElementById("crmTaskDeadline").value;
      const payload = {
        title: document.getElementById("crmTaskTitle").value.trim(),
        description: document.getElementById("crmTaskDescription").value.trim() || null,
        priority: document.getElementById("crmTaskPriority").value,
        progress: parseInt(document.getElementById("crmTaskProgress").value, 10) || 0,
        deadline: deadlineVal ? deadlineVal.replace("T", " ") + ":00" : null,
      };
      const cid = document.getElementById("crmTaskCustomerId").value;
      const lid = document.getElementById("crmTaskLeadId").value;
      if (cid) payload.customer_id = parseInt(cid, 10);
      if (lid) payload.lead_id = parseInt(lid, 10);
      try {
        await CrmCommon.apiFetch(api.create, { method: "POST", body: payload });
        createForm.reset();
        if (createModal) createModal.hide();
        loadTasks();
      } catch (err) {
        formError.textContent = (err.data && err.data.error) || err.message;
        formError.classList.remove("d-none");
      }
    });
  }

  gridBody.addEventListener("click", async function (e) {
    const btn = e.target.closest(".crm-task-complete");
    if (!btn) return;
    try {
      await CrmCommon.apiFetch(CrmCommon.urlTemplate(api.complete, btn.dataset.id), { method: "POST", body: {} });
      loadTasks();
    } catch (err) {
      CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
    }
  });

  loadTasks();
})();
