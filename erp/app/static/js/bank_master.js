(function () {
  const els = {
    addBtn: document.getElementById("bankMasterAddBtn"),
    addNewBtn: document.getElementById("bankMasterAddNewBtn"),
    editBtn: document.getElementById("bankMasterEditBtn"),
    deleteBtn: document.getElementById("bankMasterDeleteBtn"),
    refreshBtn: document.getElementById("bankMasterRefreshBtn"),
    search: document.getElementById("bankMasterSearch"),
    count: document.getElementById("bankMasterCount"),
    gridBody: document.getElementById("bankMasterGridBody"),
    empty: document.getElementById("bankMasterEmpty"),
    modalEl: document.getElementById("bankMasterModal"),
    modalTitle: document.getElementById("bankMasterModalTitle"),
    form: document.getElementById("bankMasterForm"),
    accountId: document.getElementById("bankMasterAccountId"),
    bankName: document.getElementById("bankMasterBankName"),
    accountType: document.getElementById("bankMasterAccountType"),
    underGroup: document.getElementById("bankMasterUnderGroup"),
    upiWrap: document.getElementById("bankMasterUpiWrap"),
    upiId: document.getElementById("bankMasterUpiId"),
    accountNumber: document.getElementById("bankMasterAccountNumber"),
    maskedAccountNumber: document.getElementById("bankMasterMaskedAccountNumber"),
    ifsc: document.getElementById("bankMasterIfsc"),
    branch: document.getElementById("bankMasterBranch"),
    holder: document.getElementById("bankMasterHolder"),
    openingBalance: document.getElementById("bankMasterOpeningBalance"),
    openingBalanceDate: document.getElementById("bankMasterOpeningBalanceDate"),
    obDr: document.getElementById("bankMasterObDr"),
    obCr: document.getElementById("bankMasterObCr"),
    displayOrder: document.getElementById("bankMasterDisplayOrder"),
    displayOrderHint: document.getElementById("bankMasterDisplayOrderHint"),
    description: document.getElementById("bankMasterDescription"),
    activeStatus: document.getElementById("bankMasterActiveStatus"),
    qrBillReceived: document.getElementById("bankMasterQrBillReceived"),
  };

  function accountTypeNeedsUpi(accountType) {
    const key = String(accountType || "").trim().toLowerCase();
    if (!key) return false;
    if (key === "sb" || key.indexOf("sb ") === 0 || key.indexOf("sb-") === 0) return true;
    return key.indexOf("ca-current") === 0;
  }

  function toggleUpiField() {
    const need = accountTypeNeedsUpi(els.accountType?.value);
    if (els.upiWrap) els.upiWrap.classList.toggle("d-none", !need);
    if (els.upiId) {
      els.upiId.required = false;
      if (!need) els.upiId.value = "";
    }
  }

  function isCashAccount(bankName, accountNumber) {
    return String(bankName || "").trim().toLowerCase() === "cash"
      || String(accountNumber || "").trim().toLowerCase() === "cash";
  }

  function defaultUnderGroupId(isCash) {
    if (isCash) {
      return window.BANK_MASTER_DEFAULT_CASH_GROUP_ID
        || window.BANK_MASTER_DEFAULT_BANK_GROUP_ID
        || "";
    }
    return window.BANK_MASTER_DEFAULT_BANK_GROUP_ID || "";
  }

  function applyDefaultUnderGroup(forceCash) {
    if (!els.underGroup) return;
    const cash = forceCash === true
      || isCashAccount(els.bankName?.value, els.accountNumber?.value);
    const target = String(defaultUnderGroupId(cash) || "");
    if (!target) return;
    // Only auto-set when empty or still on the opposite default.
    const current = String(els.underGroup.value || "");
    const bankDefault = String(window.BANK_MASTER_DEFAULT_BANK_GROUP_ID || "");
    const cashDefault = String(window.BANK_MASTER_DEFAULT_CASH_GROUP_ID || "");
    const isBlank = !current;
    const isOtherDefault = cash
      ? current === bankDefault
      : current === cashDefault;
    if (isBlank || isOtherDefault) {
      els.underGroup.value = target;
    }
  }

  function applyCashDisplayOrderLock(forceCash) {
    const cash = forceCash === true
      || isCashAccount(els.bankName?.value, els.accountNumber?.value);
    if (els.displayOrder) {
      if (cash) {
        els.displayOrder.value = "1";
        els.displayOrder.readOnly = true;
        els.displayOrder.min = "1";
      } else {
        els.displayOrder.readOnly = false;
        els.displayOrder.min = "2";
        if (!els.displayOrder.value || parseInt(els.displayOrder.value, 10) < 2) {
          els.displayOrder.value = "100";
        }
      }
    }
    if (els.displayOrderHint) {
      els.displayOrderHint.textContent = cash
        ? "Cash is always order 1 and cannot be changed."
        : "Enter 2, 3, 4… — this order is used in Payment Received account list (Cash stays on top).";
    }
    applyDefaultUnderGroup(cash);
  }

  if (!els.gridBody || !window.BANK_MASTER_API) return;

  const modal = els.modalEl && window.bootstrap ? new bootstrap.Modal(els.modalEl) : null;
  let rows = [];
  let selectedId = null;
  let searchTimer = null;

  function apiUrl(template, accountId) {
    return String(template || "").replace("/0", "/" + String(accountId));
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
      const body = await res.text();
      const csrfHint = /csrf/i.test(body || "")
        ? " Refresh the page (Ctrl+F5) and try again."
        : "";
      throw new Error("Server returned an unexpected response." + csrfHint);
    }
    const data = await res.json();
    if (!res.ok || data.ok === false) {
      throw new Error(data.error || ("Request failed (HTTP " + res.status + ")."));
    }
    return data;
  }

  function setSelected(accountId) {
    selectedId = accountId ? parseInt(accountId, 10) : null;
    const hasSelection = !!selectedId;
    if (els.editBtn) els.editBtn.disabled = !hasSelection;
    if (els.deleteBtn) els.deleteBtn.disabled = !hasSelection;
    Array.from(els.gridBody.querySelectorAll("tr")).forEach(function (row) {
      row.classList.toggle("table-active", parseInt(row.dataset.accountId, 10) === selectedId);
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
      tr.dataset.accountId = String(row.account_id);
      tr.innerHTML =
        "<td>" + escapeHtml(row.account_id) + "</td>" +
        "<td>" + escapeHtml(row.bank_name) + "</td>" +
        "<td>" + escapeHtml(row.account_number || row.masked_account_number) + "</td>" +
        "<td>" + escapeHtml(row.account_type) + "</td>" +
        "<td>" + escapeHtml(row.under_group || "—") + "</td>" +
        "<td>" + escapeHtml(row.upi_id || "—") + "</td>" +
        "<td>" + escapeHtml(row.ifsc_code) + "</td>" +
        "<td>" + escapeHtml(row.branch_name) + "</td>" +
        "<td>" + escapeHtml(row.account_holder_name) + "</td>" +
        '<td class="text-end">' + escapeHtml(row.opening_balance) + "</td>" +
        '<td class="text-end">' + escapeHtml(row.display_order != null ? row.display_order : "") + "</td>" +
        "<td>" + (row.qr_bill_received
          ? '<span class="badge text-bg-primary">Yes</span>'
          : '<span class="badge text-bg-light border">No</span>') + "</td>" +
        "<td>" + (row.active_status
          ? '<span class="badge text-bg-success">Active</span>'
          : '<span class="badge text-bg-secondary">Inactive</span>') + "</td>" +
        '<td class="text-end text-nowrap">' +
        '<button type="button" class="btn btn-outline-secondary btn-sm bank-master-edit-btn" data-id="' +
        row.account_id +
        '" title="Edit"><i class="bi bi-pencil"></i></button> ' +
        '<button type="button" class="btn btn-outline-danger btn-sm bank-master-delete-btn" data-id="' +
        row.account_id +
        '" title="Delete"><i class="bi bi-trash"></i></button>' +
        "</td>";
      tr.addEventListener("click", function (event) {
        if (event.target.closest("button")) return;
        setSelected(row.account_id);
      });
      tr.addEventListener("dblclick", function (event) {
        if (event.target.closest("button")) return;
        setSelected(row.account_id);
        openEditModal(row.account_id);
      });
      els.gridBody.appendChild(tr);
    });
    if (selectedId && rows.some(function (row) { return row.account_id === selectedId; })) {
      setSelected(selectedId);
    } else {
      setSelected(null);
    }
  }

  async function loadRows() {
    try {
      const params = new URLSearchParams();
      const q = (els.search?.value || "").trim();
      if (q) params.set("search", q);
      const res = await fetch(window.BANK_MASTER_API.list + "?" + params.toString(), {
        headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await parseJsonResponse(res);
      renderRows(data.rows || []);
    } catch (err) {
      alert(err.message || String(err));
      renderRows([]);
    }
  }

  function ensureAccountTypeOption(code, label) {
    if (!els.accountType || !code) return;
    const exists = Array.from(els.accountType.options).some(function (opt) {
      return opt.value === code;
    });
    if (exists) return;
    const opt = document.createElement("option");
    opt.value = code;
    opt.textContent = label || code;
    els.accountType.appendChild(opt);
  }

  function defaultAccountTypeCode() {
    const types = window.BANK_MASTER_ACCOUNT_TYPES || [];
    if (types.length) return types[0].code || "CA-Current Asset";
    if (els.accountType?.options?.length) return els.accountType.options[0].value || "CA-Current Asset";
    return "CA-Current Asset";
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

  function clearForm() {
    els.form?.reset();
    if (els.accountId) els.accountId.value = "";
    if (els.activeStatus) els.activeStatus.checked = true;
    if (els.qrBillReceived) els.qrBillReceived.checked = false;
    if (els.accountType) els.accountType.value = defaultAccountTypeCode();
    if (els.displayOrder) els.displayOrder.value = "100";
    if (els.upiId) els.upiId.value = "";
    if (els.underGroup) els.underGroup.value = String(defaultUnderGroupId(false) || "");
    applyDefaultDrCrFromUnderGroup();
    applyCashDisplayOrderLock(false);
    toggleUpiField();
  }

  function fillForm(record) {
    clearForm();
    if (!record) return;
    if (els.accountId) els.accountId.value = String(record.account_id || "");
    if (els.bankName) els.bankName.value = record.bank_name || "";
    if (els.accountType) {
      const code = record.account_type || "CA-Current Asset";
      ensureAccountTypeOption(code, code);
      els.accountType.value = code;
    }
    if (els.underGroup) {
      const gid = record.chart_group_id != null
        ? String(record.chart_group_id)
        : String(defaultUnderGroupId(!!record.is_cash) || "");
      els.underGroup.value = gid;
    }
    if (els.upiId) els.upiId.value = record.upi_id || "";
    if (els.accountNumber) els.accountNumber.value = record.account_number || "";
    if (els.maskedAccountNumber) els.maskedAccountNumber.value = record.masked_account_number || "";
    if (els.ifsc) els.ifsc.value = record.ifsc_code || "";
    if (els.branch) els.branch.value = record.branch_name || "";
    if (els.holder) els.holder.value = record.account_holder_name || "";
    if (els.openingBalance) els.openingBalance.value = record.opening_balance || "";
    if (els.openingBalanceDate) els.openingBalanceDate.value = record.opening_balance_date || "";
    if (record.opening_balance_dr_cr) {
      setOpeningDrCr(record.opening_balance_dr_cr);
    } else {
      applyDefaultDrCrFromUnderGroup();
    }
    if (els.displayOrder) {
      els.displayOrder.value = String(
        record.display_order != null
          ? record.display_order
          : (record.is_cash ? 1 : 100)
      );
    }
    if (els.description) els.description.value = record.description || "";
    if (els.activeStatus) els.activeStatus.checked = !!record.active_status;
    if (els.qrBillReceived) els.qrBillReceived.checked = !!record.qr_bill_received;
    applyCashDisplayOrderLock(!!record.is_cash);
    // Keep saved under-group (do not overwrite with default after fill).
    if (els.underGroup && record.chart_group_id != null) {
      els.underGroup.value = String(record.chart_group_id);
    }
    toggleUpiField();
    if (els.upiId && record.upi_id) els.upiId.value = record.upi_id;
  }

  function openAddModal() {
    clearForm();
    if (els.modalTitle) els.modalTitle.textContent = "Add Bank Account";
    applyCashDisplayOrderLock(false);
    toggleUpiField();
    modal?.show();
    els.bankName?.focus();
  }

  async function openEditModal(accountId) {
    const id = accountId || selectedId;
    if (!id) {
      alert("Select a bank account to edit.");
      return;
    }
    setSelected(id);
    try {
      const res = await fetch(apiUrl(window.BANK_MASTER_API.record, id), {
        headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await parseJsonResponse(res);
      fillForm(data.record || {});
      if (els.modalTitle) els.modalTitle.textContent = "Edit Bank Account";
      modal?.show();
      els.bankName?.focus();
    } catch (err) {
      alert(err.message || String(err));
    }
  }

  async function deleteAccount(accountId) {
    const id = accountId || selectedId;
    if (!id) {
      alert("Select a bank account to delete.");
      return;
    }
    if (!(await JTCSDialog.confirm("This will permanently delete from your database.\n\nClick OK for Yes, or Cancel for No."))) {
      return;
    }
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      alert("User ID and password are required to delete.");
      return;
    }
    creds = await window.JTCSDeleteConfirm.ask({
      title: "Confirm Delete",
      message: "Enter your User ID and password to permanently delete this bank account from the database.",
      confirmLabel: "Yes",
      cancelLabel: "No",
    });
    if (!creds) return;
    setSelected(id);
    try {
      const body = new FormData();
      body.append("csrf_token", csrfToken());
      if (creds) window.JTCSDeleteConfirm.appendCreds(body, creds);
      const res = await fetch(apiUrl(window.BANK_MASTER_API.delete, id), {
        method: "POST",
        body: body,
        headers: {
          Accept: "application/json",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": csrfToken(),
        },
      });
      const data = await parseJsonResponse(res);
      alert(data.message || "Deleted.");
      selectedId = null;
      await loadRows();
    } catch (err) {
      alert(err.message || String(err));
    }
  }

  els.form?.addEventListener("submit", async function (e) {
    e.preventDefault();
    if (!els.bankName?.value.trim()) {
      alert("Bank Name is required.");
      els.bankName.focus();
      return;
    }
    if (!els.accountNumber?.value.trim()) {
      alert("Account Number is required.");
      els.accountNumber.focus();
      return;
    }
    if (!els.underGroup?.value) {
      alert("Chart of Account Group is required.");
      els.underGroup?.focus();
      return;
    }
    const accountId = (els.accountId?.value || "").trim();
    const body = new FormData(els.form);
    if (!els.activeStatus?.checked) {
      body.delete("ActiveStatus");
    }
    if (els.qrBillReceived?.checked) {
      body.set("QrBillReceived", "1");
    } else {
      body.set("QrBillReceived", "0");
    }
    // Always send UPI explicitly (hidden/cleared when not CA-Current / SB).
    if (accountTypeNeedsUpi(els.accountType?.value)) {
      body.set("UpiId", (els.upiId?.value || "").trim());
    } else {
      body.set("UpiId", "");
    }
    const url = accountId
      ? apiUrl(window.BANK_MASTER_API.update, accountId)
      : window.BANK_MASTER_API.create;
    const saveBtn = document.getElementById("bankMasterSaveBtn");
    if (saveBtn) saveBtn.disabled = true;
    try {
      const res = await fetch(url, {
        method: "POST",
        body: body,
        headers: {
          Accept: "application/json",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": csrfToken(),
        },
      });
      const data = await parseJsonResponse(res);
      modal?.hide();
      if (data.record?.account_id) selectedId = data.record.account_id;
      await loadRows();
    } catch (err) {
      alert(err.message || String(err));
    } finally {
      if (saveBtn) saveBtn.disabled = false;
    }
  });

  els.gridBody.addEventListener("click", function (event) {
    const editBtn = event.target.closest(".bank-master-edit-btn");
    if (editBtn) {
      event.preventDefault();
      event.stopPropagation();
      openEditModal(editBtn.getAttribute("data-id"));
      return;
    }
    const deleteBtn = event.target.closest(".bank-master-delete-btn");
    if (deleteBtn) {
      event.preventDefault();
      event.stopPropagation();
      deleteAccount(deleteBtn.getAttribute("data-id"));
    }
  });

  els.bankName?.addEventListener("input", function () {
    applyCashDisplayOrderLock();
  });
  els.accountNumber?.addEventListener("input", function () {
    applyCashDisplayOrderLock();
  });
  els.accountType?.addEventListener("change", toggleUpiField);
  els.underGroup?.addEventListener("change", applyDefaultDrCrFromUnderGroup);

  els.addBtn?.addEventListener("click", openAddModal);
  els.addNewBtn?.addEventListener("click", openAddModal);
  els.editBtn?.addEventListener("click", function () {
    openEditModal();
  });
  els.deleteBtn?.addEventListener("click", function () {
    deleteAccount();
  });
  els.refreshBtn?.addEventListener("click", loadRows);
  els.search?.addEventListener("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadRows, 250);
  });

  document.addEventListener("jtcs:edit", function () {
    openEditModal();
  });
  document.addEventListener("jtcs:delete", function () {
    deleteAccount();
  });

  if (window.BANK_MASTER_INITIAL_ROWS && window.BANK_MASTER_INITIAL_ROWS.length) {
    renderRows(window.BANK_MASTER_INITIAL_ROWS);
  } else {
    loadRows();
  }
})();
