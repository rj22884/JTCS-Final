(function () {
  const els = {
    addBtn: document.getElementById("workMasterAddBtn"),
    addCategoryBtn: document.getElementById("workMasterAddCategoryBtn"),
    editBtn: document.getElementById("workMasterEditBtn"),
    deleteBtn: document.getElementById("workMasterDeleteBtn"),
    refreshBtn: document.getElementById("workMasterRefreshBtn"),
    search: document.getElementById("workMasterSearch"),
    filterKind: document.getElementById("workMasterFilterKind"),
    filterStatus: document.getElementById("workMasterFilterStatus"),
    count: document.getElementById("workMasterCount"),
    gridBody: document.getElementById("workMasterGridBody"),
    empty: document.getElementById("workMasterEmpty"),
    status: document.getElementById("workMasterStatus"),
    modalEl: document.getElementById("workMasterModal"),
    modalTitle: document.getElementById("workMasterModalTitle"),
    form: document.getElementById("workMasterForm"),
    workId: document.getElementById("workMasterId"),
    workName: document.getElementById("workMasterName"),
    isIncome: document.getElementById("workMasterIsIncome"),
    isExpense: document.getElementById("workMasterIsExpense"),
    isMisc: document.getElementById("workMasterIsMisc"),
    typeEditWrap: document.getElementById("workMasterTypeEditWrap"),
    typeViewWrap: document.getElementById("workMasterTypeViewWrap"),
    typeViewBadge: document.getElementById("workMasterTypeViewBadge"),
    underGroup: document.getElementById("workMasterUnderGroup"),
    openingBalance: document.getElementById("workMasterOpeningBalance"),
    openingBalanceDate: document.getElementById("workMasterOpeningBalanceDate"),
    obDr: document.getElementById("workMasterObDr"),
    obCr: document.getElementById("workMasterObCr"),
    statusActive: document.getElementById("workMasterStatusActive"),
    statusInactive: document.getElementById("workMasterStatusInactive"),
    saveBtn: document.getElementById("workMasterSaveBtn"),
    editModeBtn: document.getElementById("workMasterEditModeBtn"),
  };

  if (!els.gridBody || !window.WORK_MASTER_API) return;

  const modal = els.modalEl && window.bootstrap ? new bootstrap.Modal(els.modalEl) : null;
  let rows = [];
  let selectedId = null;
  /** Locked id for the open edit session — never rely only on the hidden input. */
  let editingWorkId = null;
  let searchTimer = null;
  let formMode = "add";
  let saving = false;

  function apiUrl(template, workId) {
    return String(template || "").replace(/\/0(?=$|\/)/, "/" + String(workId));
  }

  function csrfToken() {
    return (
      window.WORK_MASTER_CSRF ||
      els.form?.querySelector('[name="csrf_token"]')?.value ||
      ""
    );
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

  function yesNoCell(isTrue) {
    return isTrue
      ? "<span class=\"work-master-yes\">Yes</span>"
      : "<span class=\"work-master-no\">No</span>";
  }

  function selectedKind() {
    const checked = document.querySelector('input[name="workMasterKind"]:checked');
    const value = (checked && checked.value) || "";
    if (value === "Expense" || value === "Misc." || value === "Income") return value;
    if (els.isMisc?.checked) return "Misc.";
    if (els.isExpense?.checked) return "Expense";
    return "Income";
  }

  function setKind(kind) {
    let value = kind || "Income";
    if (value === "Misc" || String(value).toLowerCase() === "misc.") value = "Misc.";
    if (els.isIncome) els.isIncome.checked = value === "Income";
    if (els.isExpense) els.isExpense.checked = value === "Expense";
    if (els.isMisc) els.isMisc.checked = value === "Misc.";
    if (els.typeViewBadge) els.typeViewBadge.textContent = value;
  }

  function setActiveStatus(isActive) {
    const active = isActive !== false;
    if (els.statusActive) els.statusActive.checked = active;
    if (els.statusInactive) els.statusInactive.checked = !active;
  }

  function selectedActiveStatus() {
    if (els.statusInactive?.checked) return "0";
    return "1";
  }

  function setFormMode(mode) {
    formMode = mode;
    const isReadonly = mode === "view";
    const isSave = mode === "add" || mode === "edit";

    els.form?.classList.toggle("work-master-readonly", isReadonly);
    if (els.workName) els.workName.readOnly = isReadonly;
    if (els.underGroup) els.underGroup.disabled = isReadonly;
    if (els.openingBalance) els.openingBalance.readOnly = isReadonly;
    if (els.openingBalanceDate) els.openingBalanceDate.readOnly = isReadonly;
    if (els.obDr) els.obDr.disabled = isReadonly;
    if (els.obCr) els.obCr.disabled = isReadonly;
    if (els.statusActive) els.statusActive.disabled = isReadonly;
    if (els.statusInactive) els.statusInactive.disabled = isReadonly;
    els.typeEditWrap?.classList.toggle("d-none", isReadonly);
    els.typeViewWrap?.classList.toggle("d-none", !isReadonly);

    if (els.saveBtn) {
      els.saveBtn.classList.toggle("d-none", !isSave);
      els.saveBtn.disabled = !isSave || saving;
    }
    if (els.editModeBtn) {
      els.editModeBtn.classList.toggle("d-none", mode !== "view");
    }
  }

  function setSelected(workId) {
    selectedId = workId ? parseInt(workId, 10) : null;
    const hasSelection = !!selectedId;
    if (els.editBtn) els.editBtn.disabled = !hasSelection;
    if (els.deleteBtn) els.deleteBtn.disabled = !hasSelection;
    Array.from(els.gridBody.querySelectorAll("tr")).forEach(function (row) {
      row.classList.toggle("table-active", parseInt(row.dataset.workId, 10) === selectedId);
    });
  }

  function renderRows(data) {
    rows = data || [];
    els.gridBody.innerHTML = "";
    if (!rows.length) {
      els.empty?.classList.remove("d-none");
      if (els.count) els.count.textContent = "0 records";
      setSelected(null);
      return;
    }
    els.empty?.classList.add("d-none");
    if (els.count) {
      els.count.textContent = rows.length + " record" + (rows.length === 1 ? "" : "s");
    }
    rows.forEach(function (row) {
      const tr = document.createElement("tr");
      tr.dataset.workId = String(row.work_id);
      if (!row.active_status) tr.classList.add("table-secondary");
      tr.innerHTML =
        "<td>" + escapeHtml(row.work_id) + "</td>" +
        "<td>" + escapeHtml(row.work_name) + "</td>" +
        "<td>" + yesNoCell(!!row.is_income) + "</td>" +
        "<td>" + yesNoCell(!!row.is_expense) + "</td>" +
        "<td>" + yesNoCell(!!row.is_misc) + "</td>" +
        "<td>" + escapeHtml(row.ledger_kind) + "</td>" +
        "<td>" + escapeHtml(row.under_group || "—") + "</td>" +
        "<td>" + (row.active_status
          ? "<span class=\"badge text-bg-success\">Active</span>"
          : "<span class=\"badge text-bg-secondary\">Inactive</span>") + "</td>" +
        "<td class=\"text-end work-master-grid-actions\">" +
        "<button type=\"button\" class=\"btn btn-outline-primary btn-sm me-1 work-master-row-edit\" data-id=\"" +
        row.work_id +
        "\"><i class=\"bi bi-pencil\"></i> Edit</button>" +
        "<button type=\"button\" class=\"btn btn-outline-danger btn-sm work-master-row-delete\" data-id=\"" +
        row.work_id +
        "\"><i class=\"bi bi-trash\"></i> Delete</button>" +
        "</td>";
      tr.addEventListener("click", function (event) {
        if (event.target.closest(".work-master-row-edit, .work-master-row-delete")) return;
        setSelected(row.work_id);
      });
      tr.addEventListener("dblclick", function () {
        setSelected(row.work_id);
        openEditModal(row.work_id);
      });
      els.gridBody.appendChild(tr);
    });
    if (selectedId && rows.some(function (row) { return row.work_id === selectedId; })) {
      setSelected(selectedId);
    } else {
      setSelected(null);
    }
  }

  async function loadRows() {
    const params = new URLSearchParams();
    const q = (els.search?.value || "").trim();
    const kind = (els.filterKind?.value || "").trim();
    const status = (els.filterStatus?.value || "").trim();
    if (q) params.set("search", q);
    if (kind) params.set("ledger_kind", kind);
    if (status) params.set("status", status);
    const res = await fetch(window.WORK_MASTER_API.list + "?" + params.toString(), {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load work types.");
    renderRows(data.rows || []);
  }

  function defaultDrCrFromUnderType(underType) {
    return String(underType || "").trim().toLowerCase() === "liabilities" ? "Cr" : "Dr";
  }

  function setOpeningDrCr(value) {
    const v = value === "Cr" ? "Cr" : "Dr";
    if (els.obDr) els.obDr.checked = v === "Dr";
    if (els.obCr) els.obCr.checked = v === "Cr";
  }

  function applyDefaultDrCrFromUnderGroup() {
    const opt = els.underGroup?.selectedOptions && els.underGroup.selectedOptions[0];
    const under = (opt && opt.dataset.underType) || "";
    setOpeningDrCr(defaultDrCrFromUnderType(under));
  }

  function selectedOpeningDrCr() {
    if (els.obCr?.checked) return "Cr";
    return "Dr";
  }

  function clearForm() {
    editingWorkId = null;
    if (els.workId) els.workId.value = "";
    if (els.workName) els.workName.value = "";
    if (els.underGroup) els.underGroup.value = "";
    if (els.openingBalance) els.openingBalance.value = "";
    if (els.openingBalanceDate) els.openingBalanceDate.value = "";
    setOpeningDrCr("Dr");
    setActiveStatus(true);
    setKind("Income");
  }

  function fillForm(record) {
    if (!record) {
      clearForm();
      return;
    }
    const id = record.work_id != null ? parseInt(record.work_id, 10) : null;
    editingWorkId = id && !Number.isNaN(id) ? id : null;
    if (els.workId) els.workId.value = editingWorkId != null ? String(editingWorkId) : "";
    if (els.workName) els.workName.value = record.work_name || "";
    setKind(
      record.ledger_kind ||
        (record.is_misc ? "Misc." : record.is_income ? "Income" : "Expense")
    );
    if (els.underGroup) {
      els.underGroup.value =
        record.chart_group_id != null ? String(record.chart_group_id) : "";
    }
    if (els.openingBalance) els.openingBalance.value = record.opening_balance || "";
    if (els.openingBalanceDate) {
      els.openingBalanceDate.value = record.opening_balance_date || "";
    }
    if (record.opening_balance_dr_cr) {
      setOpeningDrCr(record.opening_balance_dr_cr);
    } else {
      applyDefaultDrCrFromUnderGroup();
    }
    setActiveStatus(record.active_status !== false);
  }

  function openAddModal() {
    clearForm();
    setFormMode("add");
    if (els.modalTitle) els.modalTitle.textContent = "Add Work / Category";
    modal?.show();
    els.workName?.focus();
  }

  async function loadRecord(workId) {
    const res = await fetch(apiUrl(window.WORK_MASTER_API.record, workId), {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load work type.");
    return data.record || {};
  }

  async function openEditModal(workId) {
    const targetId = workId || selectedId;
    if (!targetId) {
      alert("Select a work type to edit.");
      return;
    }
    try {
      const record = await loadRecord(targetId);
      fillForm(record);
      setSelected(targetId);
      setFormMode("edit");
      if (els.modalTitle) els.modalTitle.textContent = "Edit Work / Category";
      modal?.show();
      els.workName?.focus();
    } catch (err) {
      alert(err.message || String(err));
    }
  }

  async function deleteWorkType(workId) {
    const targetId = workId || selectedId;
    if (!targetId) {
      alert("Select a work type to delete.");
      return;
    }
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!confirm("Mark selected work type as Inactive?")) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({
        message: "Mark selected work type as Inactive?",
      });
      if (!creds) return;
    }
    try {
      const body = new FormData();
      body.append("csrf_token", csrfToken());
      if (creds) window.JTCSDeleteConfirm.appendCreds(body, creds);
      const res = await fetch(apiUrl(window.WORK_MASTER_API.delete, targetId), {
        method: "POST",
        body: body,
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Delete failed.");
      showStatus(data.message || "Work type marked inactive.", "success");
      if (selectedId === targetId) selectedId = null;
      await loadRows();
    } catch (err) {
      alert(err.message || String(err));
    }
  }

  async function saveRecord() {
    if (formMode === "view" || saving) return;
    if (!els.workName?.value.trim()) {
      alert("Work name is required.");
      els.workName.focus();
      return;
    }
    const underGroupId = (els.underGroup?.value || "").trim();
    if (!underGroupId) {
      alert("Under Group is required.");
      els.underGroup?.focus();
      return;
    }

    // Prefer locked edit id so Expense→Misc. never posts as create (duplicate).
    const fieldId = parseInt((els.workId?.value || "").trim(), 10);
    const workId =
      editingWorkId ||
      (fieldId && !Number.isNaN(fieldId) ? fieldId : null) ||
      (formMode === "edit" && selectedId ? selectedId : null);

    const kind = selectedKind();
    const body = new FormData();
    body.append("csrf_token", csrfToken());
    body.append("work_name", els.workName.value.trim());
    body.append("ledger_kind", kind);
    body.append("LedgerKind", kind);
    body.append("is_income", kind === "Income" ? "1" : "0");
    body.append("is_expense", kind === "Expense" ? "1" : "0");
    body.append("is_misc", kind === "Misc." ? "1" : "0");
    body.append("chart_group_id", underGroupId);
    body.append("ChartGroupID", underGroupId);
    body.append("opening_balance", (els.openingBalance?.value || "").trim());
    body.append("OpeningBalance", (els.openingBalance?.value || "").trim());
    body.append("opening_balance_date", (els.openingBalanceDate?.value || "").trim());
    body.append("OpeningBalanceDate", (els.openingBalanceDate?.value || "").trim());
    body.append("opening_balance_dr_cr", selectedOpeningDrCr());
    body.append("OpeningBalanceDrCr", selectedOpeningDrCr());
    body.append("active_status", selectedActiveStatus());
    body.append("ActiveStatus", selectedActiveStatus());

    const url = workId
      ? apiUrl(window.WORK_MASTER_API.update, workId)
      : window.WORK_MASTER_API.create;

    saving = true;
    if (els.saveBtn) els.saveBtn.disabled = true;

    try {
      const res = await fetch(url, {
        method: "POST",
        body: body,
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      let data = {};
      try {
        data = await res.json();
      } catch (parseErr) {
        throw new Error("Save failed (server returned " + res.status + ").");
      }
      if (!res.ok || !data.ok) throw new Error(data.error || "Save failed.");
      if (data.record?.work_id) {
        selectedId = data.record.work_id;
        editingWorkId = data.record.work_id;
      }
      showStatus(data.message || "Saved successfully.", "success");
      modal?.hide();
      await loadRows();
    } catch (err) {
      alert(err.message || String(err));
    } finally {
      saving = false;
      if (els.saveBtn) els.saveBtn.disabled = formMode === "view";
    }
  }

  els.form?.addEventListener("submit", function (e) {
    e.preventDefault();
    e.stopPropagation();
    saveRecord();
  });

  els.editModeBtn?.addEventListener("click", function () {
    setFormMode("edit");
    if (els.modalTitle) els.modalTitle.textContent = "Edit Work / Category";
    els.workName?.focus();
  });

  els.gridBody.addEventListener("click", function (event) {
    const editBtn = event.target.closest(".work-master-row-edit");
    if (editBtn) {
      event.stopPropagation();
      openEditModal(parseInt(editBtn.dataset.id, 10));
      return;
    }
    const deleteBtn = event.target.closest(".work-master-row-delete");
    if (deleteBtn) {
      event.stopPropagation();
      deleteWorkType(parseInt(deleteBtn.dataset.id, 10));
    }
  });

  els.underGroup?.addEventListener("change", applyDefaultDrCrFromUnderGroup);

  els.addBtn?.addEventListener("click", openAddModal);
  els.addCategoryBtn?.addEventListener("click", openAddModal);
  els.editBtn?.addEventListener("click", function () { openEditModal(); });
  els.deleteBtn?.addEventListener("click", function () { deleteWorkType(); });
  els.refreshBtn?.addEventListener("click", function () {
    loadRows().catch(function (err) { alert(err.message || String(err)); });
  });
  els.filterKind?.addEventListener("change", function () {
    loadRows().catch(function (err) { alert(err.message || String(err)); });
  });
  els.filterStatus?.addEventListener("change", function () {
    loadRows().catch(function (err) { alert(err.message || String(err)); });
  });
  els.search?.addEventListener("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () {
      loadRows().catch(function (err) { alert(err.message || String(err)); });
    }, 250);
  });

  els.modalEl?.addEventListener("hidden.bs.modal", function () {
    if (saving) return;
    setFormMode("add");
    clearForm();
  });

  document.addEventListener("jtcs:edit", function () { openEditModal(); });
  document.addEventListener("jtcs:delete", function () { deleteWorkType(); });

  setFormMode("add");

  if (window.WORK_MASTER_INITIAL_ROWS && window.WORK_MASTER_INITIAL_ROWS.length) {
    renderRows(window.WORK_MASTER_INITIAL_ROWS);
  } else {
    loadRows().catch(function (err) { alert(err.message || String(err)); });
  }
})();
