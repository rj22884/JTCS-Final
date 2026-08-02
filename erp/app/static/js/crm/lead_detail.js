(function () {
  "use strict";

  const page = document.getElementById("crmLeadDetailPage");
  if (!page) return;

  const api = {
    convert: page.dataset.apiConvert,
    assign: page.dataset.apiAssign,
  };

  const assignModalEl = document.getElementById("crmLeadDetailAssignModal");
  const assignModal = assignModalEl ? bootstrap.Modal.getOrCreateInstance(assignModalEl) : null;
  const assignForm = document.getElementById("crmLeadDetailAssignForm");
  const assignError = document.getElementById("crmLeadDetailAssignError");
  const convertBtn = document.getElementById("crmLeadDetailConvertBtn");
  const assignBtn = document.getElementById("crmLeadDetailAssignBtn");

  if (convertBtn) {
    convertBtn.addEventListener("click", async function () {
      if (!window.confirm("Convert this lead to customer?")) return;
      convertBtn.disabled = true;
      try {
        const data = await CrmCommon.apiFetch(api.convert, { method: "POST", body: {} });
        const customerId = (data && data.customer_id) || (data && data.result && data.result.customer_id) || null;
        if (customerId) {
          window.location.href = "/crm/customer-360/" + customerId;
          return;
        }
        window.location.reload();
      } catch (err) {
        CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
        convertBtn.disabled = false;
      }
    });
  }

  if (assignBtn && assignModal) {
    assignBtn.addEventListener("click", function () {
      const input = document.getElementById("crmLeadDetailAssignUserId");
      if (input) input.value = "";
      if (assignError) assignError.classList.add("d-none");
      assignModal.show();
    });
  }

  if (assignForm) {
    assignForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      if (assignError) assignError.classList.add("d-none");
      const userId = parseInt(document.getElementById("crmLeadDetailAssignUserId").value, 10);
      try {
        await CrmCommon.apiFetch(api.assign, {
          method: "POST",
          body: { assigned_user_id: userId },
        });
        if (assignModal) assignModal.hide();
        window.location.reload();
      } catch (err) {
        if (assignError) {
          assignError.textContent = (err.data && err.data.error) || err.message;
          assignError.classList.remove("d-none");
        } else {
          CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
        }
      }
    });
  }
})();
