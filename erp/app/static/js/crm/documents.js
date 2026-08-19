(function () {
  "use strict";

  const page = document.getElementById("crmDocumentsPage");
  if (!page) return;

  const api = {
    list: page.dataset.apiList,
    upload: page.dataset.apiUpload,
    versions: page.dataset.apiVersions,
    delete: page.dataset.apiDelete,
  };

  const gridBody = document.getElementById("crmDocGridBody");
  const emptyEl = document.getElementById("crmDocEmpty");
  const uploadForm = document.getElementById("crmDocUploadForm");
  const uploadError = document.getElementById("crmDocUploadError");
  const versionsModalEl = document.getElementById("crmDocVersionsModal");
  const versionsModal = versionsModalEl ? bootstrap.Modal.getOrCreateInstance(versionsModalEl) : null;
  const versionList = document.getElementById("crmDocVersionList");

  function syncCustomerIds(fromId, toId) {
    const from = document.getElementById(fromId);
    const to = document.getElementById(toId);
    if (from && to && from.value) to.value = from.value;
  }

  function renderRows(rows) {
    if (!rows.length) {
      gridBody.innerHTML = "";
      emptyEl.classList.remove("d-none");
      return;
    }
    emptyEl.classList.add("d-none");
    gridBody.innerHTML = rows
      .map(function (row) {
        const id = row.DocumentID;
        return (
          "<tr>" +
          "<td>" + CrmCommon.escapeHtml(row.Title || row.FileName || "—") + "</td>" +
          "<td>" + CrmCommon.escapeHtml(row.FolderType || "—") + "</td>" +
          "<td>" + CrmCommon.escapeHtml(row.VersionNo || row.CurrentVersion || "1") + "</td>" +
          "<td>" + CrmCommon.formatDateOnly(row.UploadedDate || row.CreatedDate) + "</td>" +
          '<td class="text-end">' +
          '<button type="button" class="btn btn-sm btn-outline-primary me-1 crm-doc-versions" data-id="' + id + '">Versions</button>' +
          '<button type="button" class="btn btn-sm btn-outline-danger crm-doc-delete" data-id="' + id + '"><i class="bi bi-trash"></i></button>' +
          "</td></tr>"
        );
      })
      .join("");
  }

  async function loadDocuments() {
    const cid = document.getElementById("crmDocListCustomerId").value;
    if (!cid) {
      CrmCommon.showAlert("Enter a customer ID.", "info");
      return;
    }
    const params = new URLSearchParams({ customer_id: cid });
    const folder = document.getElementById("crmDocListFolder").value;
    if (folder) params.set("folder", folder);
    const data = await CrmCommon.apiFetch(api.list + "?" + params.toString());
    renderRows(data.rows || []);
  }

  document.getElementById("crmDocListBtn").addEventListener("click", function () {
    loadDocuments().catch(function (err) {
      CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
    });
  });

  if (uploadForm) {
    uploadForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      uploadError.classList.add("d-none");
      const formData = new FormData(uploadForm);
      try {
        await CrmCommon.apiFetch(api.upload, { method: "POST", body: formData });
        uploadForm.reset();
        syncCustomerIds("crmDocCustomerId", "crmDocListCustomerId");
        document.getElementById("crmDocListCustomerId").value = formData.get("customer_id");
        loadDocuments();
      } catch (err) {
        uploadError.textContent = (err.data && err.data.error) || err.message;
        uploadError.classList.remove("d-none");
      }
    });
  }

  gridBody.addEventListener("click", async function (e) {
    const verBtn = e.target.closest(".crm-doc-versions");
    const delBtn = e.target.closest(".crm-doc-delete");
    if (verBtn) {
      try {
        const data = await CrmCommon.apiFetch(CrmCommon.urlTemplate(api.versions, verBtn.dataset.id));
        const rows = data.rows || [];
        versionList.innerHTML = rows.length
          ? rows.map(function (v) {
              return (
                '<li class="list-group-item d-flex justify-content-between">' +
                "<span>v" + CrmCommon.escapeHtml(v.VersionNo || v.version) + " — " + CrmCommon.escapeHtml(v.FileName || "") + "</span>" +
                '<span class="text-muted small">' + CrmCommon.formatDate(v.UploadedDate || v.CreatedDate) + "</span></li>"
              );
            }).join("")
          : '<li class="list-group-item text-muted">No versions.</li>';
        if (versionsModal) versionsModal.show();
      } catch (err) {
        CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
      }
    }
    if (delBtn) {
      if (!(await JTCSDialog.confirm("Delete this document?"))) return;
      try {
        await CrmCommon.apiFetch(CrmCommon.urlTemplate(api.delete, delBtn.dataset.id), { method: "DELETE" });
        loadDocuments();
      } catch (err) {
        CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
      }
    }
  });
})();
