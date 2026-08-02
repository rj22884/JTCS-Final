(function () {
  "use strict";

  const page = document.getElementById("crmWorkflowPage");
  if (!page) return;

  const api = {
    start: page.dataset.apiStart,
    advance: page.dataset.apiAdvance,
    list: page.dataset.apiList,
  };

  const instanceBody = document.getElementById("crmWfInstanceBody");
  const startModalEl = document.getElementById("crmWfStartModal");
  const startModal = startModalEl ? bootstrap.Modal.getOrCreateInstance(startModalEl) : null;
  const startForm = document.getElementById("crmWfStartForm");
  const startError = document.getElementById("crmWfStartError");

  function renderInstances(rows) {
    if (!rows.length) {
      instanceBody.innerHTML = '<tr><td colspan="6" class="text-muted">No active instances.</td></tr>';
      return;
    }
    instanceBody.innerHTML = rows
      .map(function (inst) {
        const id = inst.InstanceID;
        const who = [
          inst.CustomerID ? "C#" + inst.CustomerID : "",
          inst.LeadID ? "L#" + inst.LeadID : "",
        ].filter(Boolean).join(" ") || "—";
        const canAdvance = inst.Status !== "Completed";
        return (
          "<tr data-instance-id=\"" + id + "\">" +
          "<td>" + id + "</td>" +
          "<td>" + CrmCommon.escapeHtml(inst.WorkflowName || inst.WorkflowCode || "—") + "</td>" +
          "<td>" + CrmCommon.escapeHtml(inst.CurrentStepName || inst.CurrentStepCode || "—") + "</td>" +
          "<td>" + CrmCommon.escapeHtml(inst.Status || "—") + "</td>" +
          "<td>" + CrmCommon.escapeHtml(who) + "</td>" +
          '<td class="text-end">' +
          (canAdvance ? '<button type="button" class="btn btn-sm btn-outline-primary crm-wf-advance-btn" data-id="' + id + '">Advance</button>' : "") +
          "</td></tr>"
        );
      })
      .join("");
  }

  async function loadInstances() {
    const data = await CrmCommon.apiFetch(api.list);
    renderInstances(data.rows || []);
  }

  document.getElementById("crmWfRefreshBtn").addEventListener("click", function () {
    loadInstances().catch(function (err) {
      CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
    });
  });

  page.querySelectorAll(".crm-wf-start-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.getElementById("crmWfStartCode").value = btn.dataset.code;
      startError.classList.add("d-none");
      if (startModal) startModal.show();
    });
  });

  if (startForm) {
    startForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      startError.classList.add("d-none");
      const payload = { definition_code: document.getElementById("crmWfStartCode").value };
      const cid = document.getElementById("crmWfStartCustomerId").value;
      const lid = document.getElementById("crmWfStartLeadId").value;
      if (cid) payload.customer_id = parseInt(cid, 10);
      if (lid) payload.lead_id = parseInt(lid, 10);
      try {
        await CrmCommon.apiFetch(api.start, { method: "POST", body: payload });
        startForm.reset();
        if (startModal) startModal.hide();
        loadInstances();
      } catch (err) {
        startError.textContent = (err.data && err.data.error) || err.message;
        startError.classList.remove("d-none");
      }
    });
  }

  instanceBody.addEventListener("click", async function (e) {
    const btn = e.target.closest(".crm-wf-advance-btn");
    if (!btn) return;
    try {
      await CrmCommon.apiFetch(CrmCommon.urlTemplate(api.advance, btn.dataset.id), {
        method: "POST",
        body: { notes: null },
      });
      loadInstances();
    } catch (err) {
      CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
    }
  });
})();
