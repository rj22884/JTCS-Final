(function () {
  const els = {
    addBtn: document.getElementById("purposeAddBtn"),
    addNewBtn: document.getElementById("purposeAddNewBtn"),
    editBtn: document.getElementById("purposeEditBtn"),
    deleteBtn: document.getElementById("purposeDeleteBtn"),
    refreshBtn: document.getElementById("purposeRefreshBtn"),
    search: document.getElementById("purposeSearch"),
    count: document.getElementById("purposeCount"),
    gridBody: document.getElementById("purposeGridBody"),
    empty: document.getElementById("purposeEmpty"),
    modalEl: document.getElementById("purposeModal"),
    modalTitle: document.getElementById("purposeModalTitle"),
    form: document.getElementById("purposeForm"),
    purposeId: document.getElementById("purposeId"),
    purposeName: document.getElementById("purposeName"),
    description: document.getElementById("purposeDescription"),
    activeStatus: document.getElementById("purposeActiveStatus"),
  };

  if (!els.gridBody || !window.PURPOSE_MASTER_API) return;

  const modal = els.modalEl && window.bootstrap ? new bootstrap.Modal(els.modalEl) : null;
  let rows = [];
  let selectedId = null;
  let searchTimer = null;

  function apiUrl(template, id) {
    return String(template || "").replace("/0", "/" + String(id));
  }

  function csrfToken() {
    return els.form?.querySelector('[name="csrf_token"]')?.value || "";
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function parseJsonResponse(res) {
    const contentType = res.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      throw new Error("Server returned an unexpected response. Refresh and try again.");
    }
    const data = await res.json();
    if (!res.ok || data.ok === false) {
      throw new Error(data.error || ("Request failed (HTTP " + res.status + ")."));
    }
    return data;
  }

  function setSelected(purposeId) {
    selectedId = purposeId ? parseInt(purposeId, 10) : null;
    const hasSelection = !!selectedId;
    if (els.editBtn) els.editBtn.disabled = !hasSelection;
    if (els.deleteBtn) els.deleteBtn.disabled = !hasSelection;
    Array.from(els.gridBody.querySelectorAll("tr")).forEach(function (row) {
      row.classList.toggle("table-active", parseInt(row.dataset.purposeId, 10) === selectedId);
    });
  }

  function renderRows(data) {
    rows = data || [];
    els.gridBody.innerHTML = "";
    if (!rows.length) {
      if (els.empty) els.empty.classList.remove("d-none");
      if (els.count) els.count.textContent = "0 records";
      setSelected(null);
      return;
    }
    if (els.empty) els.empty.classList.add("d-none");
    if (els.count) {
      els.count.textContent = rows.length + " record" + (rows.length === 1 ? "" : "s");
    }

    rows.forEach(function (row) {
      const tr = document.createElement("tr");
      tr.dataset.purposeId = String(row.purpose_id);
      tr.innerHTML =
        "<td>" + escapeHtml(row.purpose_id) + "</td>" +
        "<td>" + escapeHtml(row.purpose_name) + "</td>" +
        "<td>" + escapeHtml(row.description) + "</td>" +
        "<td>" + (row.active_status
          ? '<span class="badge text-bg-success">Active</span>'
          : '<span class="badge text-bg-secondary">Inactive</span>') + "</td>" +
        '<td class="text-end">' +
          '<button type="button" class="btn btn-sm btn-outline-primary me-1 purpose-edit-btn" data-id="' + row.purpose_id + '"><i class="bi bi-pencil"></i></button>' +
          '<button type="button" class="btn btn-sm btn-outline-danger purpose-delete-btn" data-id="' + row.purpose_id + '"><i class="bi bi-trash"></i></button>' +
        "</td>";
      tr.addEventListener("click", function (ev) {
        if (ev.target.closest("button")) return;
        setSelected(row.purpose_id);
      });
      els.gridBody.appendChild(tr);
    });
    setSelected(selectedId);
  }

  async function loadRows(search) {
    const url = new URL(window.PURPOSE_MASTER_API.list, window.location.origin);
    if (search) url.searchParams.set("search", search);
    const res = await fetch(url.toString(), { headers: { Accept: "application/json" } });
    const data = await parseJsonResponse(res);
    renderRows(data.rows || []);
  }

  function resetForm() {
    els.form.reset();
    els.purposeId.value = "";
    if (els.activeStatus) els.activeStatus.checked = true;
  }

  function openCreate() {
    resetForm();
    if (els.modalTitle) els.modalTitle.textContent = "Add Purpose";
    if (modal) modal.show();
  }

  async function openEdit(purposeId) {
    const res = await fetch(apiUrl(window.PURPOSE_MASTER_API.record, purposeId), {
      headers: { Accept: "application/json" },
    });
    const data = await parseJsonResponse(res);
    const row = data.record;
    els.purposeId.value = row.purpose_id;
    els.purposeName.value = row.purpose_name || "";
    els.description.value = row.description || "";
    els.activeStatus.checked = !!row.active_status;
    if (els.modalTitle) els.modalTitle.textContent = "Edit Purpose";
    if (modal) modal.show();
  }

  async function deleteRecord(purposeId) {
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!window.confirm("Delete / deactivate this purpose?")) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: "Delete / deactivate this purpose?" });
      if (!creds) return;
    }
    const res = await fetch(apiUrl(window.PURPOSE_MASTER_API.delete, purposeId), {
      method: "POST",
      headers: Object.assign(
        { Accept: "application/json", "X-CSRFToken": csrfToken() },
        creds ? { "Content-Type": "application/json" } : {}
      ),
      ...(creds
        ? { body: JSON.stringify({ user_id: creds.user_id, password: creds.password }) }
        : {}),
    });
    const data = await parseJsonResponse(res);
    alert(data.message || "Deleted.");
    selectedId = null;
    await loadRows(els.search ? els.search.value.trim() : "");
  }

  els.form.addEventListener("submit", async function (ev) {
    ev.preventDefault();
    const id = els.purposeId.value ? parseInt(els.purposeId.value, 10) : null;
    const url = id
      ? apiUrl(window.PURPOSE_MASTER_API.update, id)
      : window.PURPOSE_MASTER_API.create;
    const body = new FormData(els.form);
    if (!els.activeStatus.checked) body.set("ActiveStatus", "0");
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { Accept: "application/json", "X-CSRFToken": csrfToken() },
        body: body,
      });
      const data = await parseJsonResponse(res);
      alert(data.message || "Saved.");
      if (modal) modal.hide();
      await loadRows(els.search ? els.search.value.trim() : "");
    } catch (err) {
      alert(err.message || "Save failed.");
    }
  });

  els.gridBody.addEventListener("click", function (ev) {
    const editBtn = ev.target.closest(".purpose-edit-btn");
    const deleteBtn = ev.target.closest(".purpose-delete-btn");
    if (editBtn) {
      openEdit(editBtn.dataset.id).catch(function (err) {
        alert(err.message || "Unable to load record.");
      });
    } else if (deleteBtn) {
      deleteRecord(deleteBtn.dataset.id).catch(function (err) {
        alert(err.message || "Unable to delete.");
      });
    }
  });

  if (els.addBtn) els.addBtn.addEventListener("click", openCreate);
  if (els.addNewBtn) els.addNewBtn.addEventListener("click", openCreate);
  if (els.editBtn) {
    els.editBtn.addEventListener("click", function () {
      if (!selectedId) return;
      openEdit(selectedId).catch(function (err) {
        alert(err.message || "Unable to load record.");
      });
    });
  }
  if (els.deleteBtn) {
    els.deleteBtn.addEventListener("click", function () {
      if (!selectedId) return;
      deleteRecord(selectedId).catch(function (err) {
        alert(err.message || "Unable to delete.");
      });
    });
  }
  if (els.refreshBtn) {
    els.refreshBtn.addEventListener("click", function () {
      loadRows(els.search ? els.search.value.trim() : "").catch(function (err) {
        alert(err.message || "Unable to refresh.");
      });
    });
  }
  if (els.search) {
    els.search.addEventListener("input", function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () {
        loadRows(els.search.value.trim()).catch(function () {});
      }, 250);
    });
  }

  renderRows(window.PURPOSE_MASTER_INITIAL_ROWS || []);
})();
