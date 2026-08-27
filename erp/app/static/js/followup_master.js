(function () {
  "use strict";

  const els = {
    addBtn: document.getElementById("fuMasterAddBtn"),
    editBtn: document.getElementById("fuMasterEditBtn"),
    deleteBtn: document.getElementById("fuMasterDeleteBtn"),
    refreshBtn: document.getElementById("fuMasterRefreshBtn"),
    search: document.getElementById("fuMasterSearch"),
    count: document.getElementById("fuMasterCount"),
    gridBody: document.getElementById("fuMasterGridBody"),
    empty: document.getElementById("fuMasterEmpty"),
    status: document.getElementById("fuMasterStatus"),
    modalEl: document.getElementById("fuMasterModal"),
    modalTitle: document.getElementById("fuMasterModalTitle"),
    form: document.getElementById("fuMasterForm"),
    stageId: document.getElementById("fuMasterStageId"),
    stageName: document.getElementById("fuMasterStageName"),
    stageCode: document.getElementById("fuMasterStageCode"),
    stageCodeWrap: document.getElementById("fuMasterStageCodeWrap"),
    displayOrder: document.getElementById("fuMasterDisplayOrder"),
    activeStatusWrap: document.getElementById("fuMasterStatusWrap"),
    activeStatus: document.getElementById("fuMasterActiveStatus"),
    saveBtn: document.getElementById("fuMasterSaveBtn"),
  };

  if (!els.gridBody || !window.FU_MASTER_API) return;

  const modal = els.modalEl ? new bootstrap.Modal(els.modalEl) : null;
  let rows = window.FU_MASTER_INITIAL_ROWS || [];
  let selectedId = null;
  let formMode = "add";

  function apiUrl(template, stageId) {
    return String(template || "").replace(/\/0(?=$|\/)/, "/" + String(stageId));
  }

  function csrfToken() {
    return window.FU_MASTER_CSRF || "";
  }

  function showStatus(message, type) {
    if (!els.status) return;
    if (!message) {
      els.status.classList.add("d-none");
      els.status.textContent = "";
      return;
    }
    els.status.textContent = message;
    els.status.className = "alert py-2 small mb-3 alert-" + (type || "success");
    els.status.classList.remove("d-none");
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function isActive(row) {
    return row.active_status !== false && row.active_status !== 0 && row.active_status !== "0";
  }

  function setSelected(stageId) {
    selectedId = stageId || null;
    const row = rows.find(function (r) { return r.stage_id === selectedId; });
    const has = !!selectedId;
    if (els.editBtn) els.editBtn.disabled = !has;
    if (els.deleteBtn) els.deleteBtn.disabled = !has || (row && !isActive(row));
    els.gridBody.querySelectorAll("tr").forEach(function (tr) {
      tr.classList.toggle("table-active", tr.dataset.id === String(selectedId));
    });
  }

  function renderGrid(data) {
    rows = data || [];
    if (!rows.length) {
      els.gridBody.innerHTML = "";
      els.empty?.classList.remove("d-none");
      if (els.count) els.count.textContent = "0 records";
      setSelected(null);
      return;
    }
    els.empty?.classList.add("d-none");
    if (els.count) {
      els.count.textContent = rows.length + " record" + (rows.length === 1 ? "" : "s");
    }
    els.gridBody.innerHTML = rows.map(function (row) {
      const active = isActive(row);
      const deleteBtn = active
        ? '<button type="button" class="btn btn-outline-danger btn-sm fu-master-row-delete" data-id="' + row.stage_id + '" title="Delete"><i class="bi bi-trash"></i></button>'
        : '<button type="button" class="btn btn-outline-secondary btn-sm" disabled title="Already inactive"><i class="bi bi-trash"></i></button>';
      return (
        "<tr data-id=\"" + row.stage_id + "\">" +
        "<td>" + row.stage_id + "</td>" +
        "<td><code>" + escapeHtml(row.stage_code) + "</code></td>" +
        "<td>" + escapeHtml(row.stage_name) + "</td>" +
        "<td>" + row.display_order + "</td>" +
        "<td>" + (active ? '<span class="badge bg-success">Active</span>' : '<span class="badge bg-secondary">Inactive</span>') + "</td>" +
        '<td class="text-end fu-master-actions">' +
        '<button type="button" class="btn btn-outline-primary btn-sm fu-master-row-edit" data-id="' + row.stage_id + '" title="Edit"><i class="bi bi-pencil"></i></button> ' +
        deleteBtn +
        "</td>" +
        "</tr>"
      );
    }).join("");
    setSelected(selectedId);
  }

  function loadGrid() {
    const params = new URLSearchParams();
    const search = (els.search?.value || "").trim();
    if (search) params.set("search", search);
    const url = window.FU_MASTER_API.list + (params.toString() ? "?" + params.toString() : "");
    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "Unable to load records.");
        renderGrid(data.rows);
      })
      .catch(function (err) {
        showStatus(err.message || "Unable to load records.", "danger");
      });
  }

  function openModal(mode, record) {
    formMode = mode;
    if (els.modalTitle) {
      els.modalTitle.textContent = mode === "add" ? "Add Workflow Stage" : "Edit Workflow Stage";
    }
    if (els.stageId) els.stageId.value = record ? String(record.stage_id) : "";
    if (els.stageName) els.stageName.value = record ? record.stage_name : "";
    if (els.stageCode) els.stageCode.value = record ? record.stage_code : "";
    if (els.displayOrder) els.displayOrder.value = record ? record.display_order : 1;
    if (els.stageCodeWrap) {
      els.stageCodeWrap.classList.toggle("d-none", mode === "edit");
    }
    if (els.activeStatusWrap) {
      els.activeStatusWrap.classList.toggle("d-none", mode !== "edit");
    }
    if (els.activeStatus) {
      els.activeStatus.value = record && !isActive(record) ? "0" : "1";
    }
    modal?.show();
  }

  function saveStage() {
    const name = (els.stageName?.value || "").trim();
    if (!name) {
      showStatus("Stage name is required.", "warning");
      return;
    }
    const payload = {
      stage_name: name,
      display_order: parseInt(els.displayOrder?.value || "1", 10) || 1,
    };
    let url = window.FU_MASTER_API.create;
    if (formMode === "edit" && els.stageId?.value) {
      url = apiUrl(window.FU_MASTER_API.update, els.stageId.value);
      payload.active_status = els.activeStatus?.value === "1";
    } else {
      payload.stage_code = (els.stageCode?.value || "").trim();
    }
    els.saveBtn.disabled = true;
    fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify(payload),
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "Save failed.");
        showStatus(data.message || "Saved successfully.", "success");
        modal?.hide();
        loadGrid();
      })
      .catch(function (err) {
        showStatus(err.message || "Unable to save.", "danger");
      })
      .finally(function () {
        els.saveBtn.disabled = false;
      });
  }

  async function deleteStage(stageId) {
    const id = stageId || selectedId;
    if (!id) return;
    const row = rows.find(function (r) { return r.stage_id === id; });
    const label = row ? row.stage_name : "this workflow stage";
    const message =
      'Delete "' + label + '"?\n\nThis is a soft delete — the stage will be marked Inactive and hidden from followup entry checkboxes.';
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!(await JTCSDialog.confirm(message))) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: message });
      if (!creds) return;
    }
    fetch(apiUrl(window.FU_MASTER_API.delete, id), {
      method: "POST",
      headers: Object.assign(
        { Accept: "application/json", "X-CSRFToken": csrfToken() },
        creds ? { "Content-Type": "application/json" } : {}
      ),
      ...(creds
        ? { body: JSON.stringify({ user_id: creds.user_id, password: creds.password }) }
        : {}),
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "Delete failed.");
        showStatus(data.message || "Stage marked inactive.", "success");
        setSelected(null);
        loadGrid();
      })
      .catch(function (err) {
        if (window.JTCSDialog?.alert) JTCSDialog.alert(err.message || "Unable to delete.", "error");
        showStatus(err.message || "Unable to delete.", "danger");
      });
  }

  els.addBtn?.addEventListener("click", function () { openModal("add"); });
  els.editBtn?.addEventListener("click", function () {
    const row = rows.find(function (r) { return r.stage_id === selectedId; });
    if (row) openModal("edit", row);
  });
  els.deleteBtn?.addEventListener("click", function () { deleteStage(selectedId); });
  els.refreshBtn?.addEventListener("click", loadGrid);
  els.saveBtn?.addEventListener("click", saveStage);
  els.search?.addEventListener("input", function () {
    clearTimeout(window._fuMasterSearchTimer);
    window._fuMasterSearchTimer = setTimeout(loadGrid, 300);
  });

  els.gridBody.addEventListener("click", function (event) {
    const editBtn = event.target.closest(".fu-master-row-edit");
    if (editBtn) {
      const id = parseInt(editBtn.dataset.id, 10);
      const row = rows.find(function (r) { return r.stage_id === id; });
      setSelected(id);
      if (row) openModal("edit", row);
      return;
    }
    const delBtn = event.target.closest(".fu-master-row-delete");
    if (delBtn) {
      const id = parseInt(delBtn.dataset.id, 10);
      setSelected(id);
      deleteStage(id);
      return;
    }
    const tr = event.target.closest("tr[data-id]");
    if (tr && !event.target.closest(".fu-master-actions")) {
      setSelected(parseInt(tr.dataset.id, 10));
    }
  });

  renderGrid(rows);
})();
