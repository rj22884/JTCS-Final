(function () {
  "use strict";

  const form = document.getElementById("pscanEntryForm");
  if (!form) return;

  const els = {
    newEntryBtn: document.getElementById("pscanNewEntryBtn"),
    refreshGridBtn: document.getElementById("pscanRefreshGridBtn"),
    workMasterBtn: document.getElementById("pscanWorkMasterBtn"),
    entryModalEl: document.getElementById("pscanEntryModal"),
    entryModalTitle: document.getElementById("pscanEntryModalTitle"),
    workMasterModalEl: document.getElementById("pscanWorkMasterModal"),
    gridBody: document.getElementById("pscanDataGridBody"),
    gridCount: document.getElementById("pscanGridCount"),
    gridEmpty: document.getElementById("pscanGridEmpty"),
    billNo: document.getElementById("BillNo"),
    workDate: document.getElementById("WorkDate"),
    printingScanId: document.getElementById("PrintingScanID"),
    saleAmount: document.getElementById("SaleAmount"),
    paymentLines: document.getElementById("pscanPaymentLines"),
    paymentSummary: document.getElementById("pscanPaymentSummary"),
    addPaymentBtn: document.getElementById("pscanAddPaymentBtn"),
    workTypeSelect: document.getElementById("WorkID"),
    workMasterBody: document.getElementById("pscanWorkMasterBody"),
    workMasterEmpty: document.getElementById("pscanWorkMasterEmpty"),
    workMasterError: document.getElementById("pscanWorkMasterError"),
    workMasterForm: document.getElementById("pscanWorkMasterForm"),
    workName: document.getElementById("pscanWorkName"),
    workLedgerKind: document.getElementById("pscanWorkLedgerKind"),
    workEditId: document.getElementById("pscanWorkEditId"),
    workFilterKind: document.getElementById("pscanWorkFilterKind"),
    workCancelEditBtn: document.getElementById("pscanWorkCancelEditBtn"),
  };

  const entryModal = els.entryModalEl ? new bootstrap.Modal(els.entryModalEl) : null;
  const workMasterModal = els.workMasterModalEl ? new bootstrap.Modal(els.workMasterModalEl) : null;
  let editingEntryId = null;

  function apiUrl(template, entryId) {
    return String(template || "").replace("/0", "/" + String(entryId));
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function isEditMode() {
    return !!editingEntryId;
  }

  function setEditMode(entryId) {
    editingEntryId = entryId ? parseInt(entryId, 10) : null;
    if (els.printingScanId) {
      els.printingScanId.value = editingEntryId ? String(editingEntryId) : "";
    }
    if (els.entryModalTitle) {
      els.entryModalTitle.textContent = editingEntryId
        ? "Edit Printing & Scanning Entry"
        : "Printing & Scanning Entry";
    }
  }

  function fetchNextBillNo(workDate) {
    const baseUrl = window.PSCAN_NEXT_BILL_URL;
    if (!baseUrl || !workDate || isEditMode()) return Promise.resolve();
    const url = baseUrl + "?work_date=" + encodeURIComponent(workDate);
    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (data.ok && els.billNo) {
          els.billNo.value = data.bill_no || "";
        }
      })
      .catch(function () {
        return null;
      });
  }

  function paymentModeLabel(item) {
    return (
      item.display_account_number ||
      item.account_number ||
      item.masked_account_number ||
      item.bank_name ||
      "Account"
    );
  }

  function paymentModeValue(item) {
    return String(item.bank_account_id || "");
  }

  function buildPaymentSelect(selectedValue) {
    const select = document.createElement("select");
    select.className = "form-select pscan-payment-bank";
    select.required = true;
    const accounts = window.PSCAN_BANK_ACCOUNTS || [];
    if (!accounts.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "No bank account in JtcsBankAccountMaster";
      select.appendChild(opt);
      select.disabled = true;
      return select;
    }
    accounts.forEach(function (item) {
      const opt = document.createElement("option");
      opt.value = paymentModeValue(item);
      opt.textContent = paymentModeLabel(item);
      select.appendChild(opt);
    });
    if (
      selectedValue &&
      !Array.from(select.options).some(function (opt) {
        return opt.value === String(selectedValue);
      })
    ) {
      const opt = document.createElement("option");
      opt.value = String(selectedValue);
      opt.textContent = "Current account";
      select.appendChild(opt);
    }
    autoSelectPaymentBank(select, selectedValue);
    return select;
  }

  function autoSelectPaymentBank(select, preferredValue) {
    if (
      preferredValue &&
      Array.from(select.options).some(function (opt) {
        return opt.value === String(preferredValue);
      })
    ) {
      select.value = String(preferredValue);
      return;
    }
    const cashOption = Array.from(select.options).find(function (opt) {
      return opt.value && opt.textContent.trim() === "Cash";
    });
    if (cashOption) {
      select.value = cashOption.value;
      return;
    }
    const firstOption = Array.from(select.options).find(function (opt) {
      return opt.value;
    });
    if (firstOption) select.value = firstOption.value;
  }

  function getPaymentTotal() {
    let total = 0;
    els.paymentLines?.querySelectorAll(".pscan-payment-amount").forEach(function (input) {
      const val = parseFloat(input.value || "0");
      if (!Number.isNaN(val)) total += val;
    });
    return total;
  }

  function updatePaymentSummary() {
    if (!els.paymentSummary) return;
    const sale = parseFloat(els.saleAmount?.value || "0");
    const total = getPaymentTotal();
    if (!sale && !total) {
      els.paymentSummary.textContent = "";
      els.paymentSummary.className = "small text-muted ms-auto";
      return;
    }
    const diff = Math.round((sale - total) * 100) / 100;
    if (total + 0.001 >= sale) {
      if (Math.abs(diff) < 0.001) {
        els.paymentSummary.textContent = "Received: " + total.toFixed(2) + " (matched)";
      } else {
        els.paymentSummary.textContent =
          "Received: " + total.toFixed(2) + " (>= Sale: " + sale.toFixed(2) + ")";
      }
      els.paymentSummary.className = "small text-success ms-auto";
    } else {
      els.paymentSummary.textContent =
        "Received: " + total.toFixed(2) + " / Sale: " + sale.toFixed(2) + " (minimum)";
      els.paymentSummary.className = "small text-danger ms-auto";
    }
  }

  function updatePaymentRemoveButtons() {
    const lines = els.paymentLines?.querySelectorAll(".pscan-payment-line") || [];
    const hideRemove = lines.length <= 1;
    lines.forEach(function (line) {
      const btn = line.querySelector(".pscan-payment-remove");
      if (btn) btn.disabled = hideRemove;
    });
  }

  function addPaymentLine(options) {
    options = options || {};
    if (!els.paymentLines) return null;

    const line = document.createElement("div");
    line.className = "pscan-payment-line";

    const bankWrap = document.createElement("div");
    const bankLabel = document.createElement("label");
    bankLabel.className = "form-label";
    bankLabel.textContent = "Payment Mode";
    const select = buildPaymentSelect(options.bankAccountId);
    bankWrap.appendChild(bankLabel);
    bankWrap.appendChild(select);

    const amountWrap = document.createElement("div");
    const amountLabel = document.createElement("label");
    amountLabel.className = "form-label";
    amountLabel.textContent = "Received Amt";
    const amount = document.createElement("input");
    amount.type = "number";
    amount.step = "0.01";
    amount.min = "0";
    amount.className = "form-control pscan-payment-amount";
    amount.required = true;
    amount.value = options.amount != null && options.amount !== "" ? options.amount : "0";
    amount.addEventListener("input", updatePaymentSummary);
    amountWrap.appendChild(amountLabel);
    amountWrap.appendChild(amount);

    const actionWrap = document.createElement("div");
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn btn-outline-danger btn-sm pscan-payment-remove";
    removeBtn.innerHTML = "<i class=\"bi bi-trash\"></i>";
    removeBtn.title = "Remove";
    removeBtn.addEventListener("click", function () {
      if ((els.paymentLines?.querySelectorAll(".pscan-payment-line") || []).length <= 1) return;
      line.remove();
      updatePaymentRemoveButtons();
      updatePaymentSummary();
    });
    actionWrap.appendChild(removeBtn);

    line.appendChild(bankWrap);
    line.appendChild(amountWrap);
    line.appendChild(actionWrap);
    els.paymentLines.appendChild(line);
    updatePaymentRemoveButtons();
    updatePaymentSummary();
    return line;
  }

  function resetPaymentLines(lines) {
    if (!els.paymentLines) return;
    els.paymentLines.innerHTML = "";
    const rows = lines && lines.length ? lines : [{}];
    rows.forEach(function (row) {
      addPaymentLine(row);
    });
    updatePaymentSummary();
  }

  function validatePaymentLines() {
    const lines = els.paymentLines?.querySelectorAll(".pscan-payment-line") || [];
    if (!lines.length) return "At least one payment mode is required.";
    for (let i = 0; i < lines.length; i++) {
      const bank = lines[i].querySelector(".pscan-payment-bank");
      const amount = lines[i].querySelector(".pscan-payment-amount");
      if (!bank?.value) return "Each payment mode must be selected.";
      const val = parseFloat(amount?.value || "0");
      if (Number.isNaN(val) || val <= 0) {
        return "Each received amount must be greater than zero.";
      }
    }
    const sale = parseFloat(els.saleAmount?.value || "0");
    const total = getPaymentTotal();
    if (total + 0.001 < sale) {
      return "Received amount must be greater than or equal to Sale Value.";
    }
    return null;
  }

  function syncPaymentLinesToForm() {
    if (!form || !els.paymentLines) return;
    form.querySelectorAll(".pscan-payment-sync").forEach(function (el) {
      el.remove();
    });
    const lines = els.paymentLines.querySelectorAll(".pscan-payment-line");
    lines.forEach(function (line) {
      const bank = line.querySelector(".pscan-payment-bank");
      const amount = line.querySelector(".pscan-payment-amount");
      if (!bank || !amount) return;

      const wrap = document.createElement("div");
      wrap.className = "pscan-payment-sync d-none";

      const bankHidden = document.createElement("input");
      bankHidden.type = "hidden";
      bankHidden.name = "PaymentBankAccountID[]";
      bankHidden.value = bank.value || "";

      const amountHidden = document.createElement("input");
      amountHidden.type = "hidden";
      amountHidden.name = "PaymentAmount[]";
      amountHidden.value = amount.value || "0";

      wrap.appendChild(bankHidden);
      wrap.appendChild(amountHidden);
      form.appendChild(wrap);
    });
  }

  function resetEntryForm() {
    if (!form) return;
    setEditMode(null);
    form.reset();
    if (els.workDate) els.workDate.value = window.PSCAN_DEFAULT_DATE || "";
    if (els.billNo) els.billNo.value = "";
    resetPaymentLines([{}]);
    return fetchNextBillNo(els.workDate?.value || "");
  }

  function openEntryModal() {
    resetEntryForm().then(function () {
      entryModal?.show();
    });
  }

  function populateEntryForm(record) {
    setEditMode(record.printing_scan_id);
    if (els.billNo) els.billNo.value = record.bill_no || "";
    if (els.workDate) els.workDate.value = (record.work_date || "").slice(0, 10);
    if (els.workTypeSelect) els.workTypeSelect.value = String(record.work_id || "");
    const customerName = document.getElementById("CustomerName");
    const mobileNumber = document.getElementById("MobileNumber");
    const remarks = document.getElementById("Remarks");
    if (customerName) customerName.value = record.customer_name || "";
    if (mobileNumber) mobileNumber.value = record.mobile_number || "";
    if (remarks) remarks.value = record.remarks || "";
    if (els.saleAmount) els.saleAmount.value = record.sale_amount || "";
    if (record.payments && record.payments.length) {
      resetPaymentLines(
        record.payments.map(function (payment) {
          return {
            bankAccountId: payment.bank_account_id,
            amount: payment.amount,
          };
        })
      );
    } else {
      resetPaymentLines([{ amount: record.sale_amount || "" }]);
    }
  }

  function loadEntryRecord(entryId) {
    const url = apiUrl(window.PSCAN_RECORD_URL, entryId);
    if (!url) return Promise.reject(new Error("Record URL not configured."));
    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, data: data };
        });
      })
      .then(function (result) {
        if (!result.ok || !result.data.ok) {
          throw new Error(result.data.error || "Unable to load record.");
        }
        populateEntryForm(result.data.record || {});
        entryModal?.show();
      });
  }

  async function deleteEntry(entryId) {
    if (!entryId) return;
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!(await JTCSDialog.confirm("Delete this printing & scanning bill and linked transactions?"))) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({
        message: "Delete this printing & scanning bill and linked transactions?",
      });
      if (!creds) return;
    }
    const url = apiUrl(window.PSCAN_DELETE_URL, entryId);
    const body = new FormData();
    body.append("csrf_token", window.PSCAN_CSRF || "");
    if (creds) window.JTCSDeleteConfirm.appendCreds(body, creds);
    fetch(url, {
      method: "POST",
      body: body,
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, data: data };
        });
      })
      .then(function (result) {
        if (!result.ok || !result.data.ok) {
          throw new Error(result.data.error || "Unable to delete record.");
        }
        loadGrid();
      })
      .catch(function (err) {
        alert(err.message || "Unable to delete record.");
      });
  }

  function formatMoney(value) {
    const num = parseFloat(value || "0");
    if (Number.isNaN(num)) return "—";
    return num.toFixed(2);
  }

  function formatDate(value) {
    if (typeof window.formatDisplaySmart === "function") {
      return window.formatDisplaySmart(value);
    }
    if (typeof window.formatDisplayDate === "function") {
      return window.formatDisplayDate(value);
    }
    if (!value) return "—";
    return String(value).slice(0, 10);
  }

  function renderGrid(rows) {
    if (!els.gridBody) return;
    els.gridBody.innerHTML = "";
    if (!rows.length) {
      els.gridEmpty?.classList.remove("d-none");
      if (els.gridCount) els.gridCount.textContent = "0 records";
      return;
    }
    els.gridEmpty?.classList.add("d-none");
    if (els.gridCount) els.gridCount.textContent = rows.length + " record(s)";

    rows.forEach(function (row) {
      const tr = document.createElement("tr");
      tr.dataset.entryId = String(row.printing_scan_id || "");
      tr.innerHTML =
        "<td>" + escapeHtml(row.bill_no || "") + "</td>" +
        "<td>" + escapeHtml(formatDate(row.work_date)) + "</td>" +
        "<td>" + escapeHtml(row.work_name || "") + "</td>" +
        "<td class=\"text-end\">" + escapeHtml(formatMoney(row.sale_amount)) + "</td>" +
        "<td>" + escapeHtml(row.customer_name || "—") + "</td>" +
        "<td>" + escapeHtml(row.mobile_number || "—") + "</td>" +
        "<td>" + escapeHtml(row.remarks || "—") + "</td>" +
        "<td>" + escapeHtml(formatDate(row.created_date)) + "</td>" +
        "<td class=\"text-end\">" +
        "<button type=\"button\" class=\"btn btn-outline-primary btn-sm me-1 pscan-grid-edit-btn\" title=\"Edit\">" +
        "<i class=\"bi bi-pencil\"></i></button>" +
        "<button type=\"button\" class=\"btn btn-outline-danger btn-sm pscan-grid-delete-btn\" title=\"Delete\">" +
        "<i class=\"bi bi-trash\"></i></button>" +
        "</td>";
      tr.querySelector(".pscan-grid-edit-btn")?.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        loadEntryRecord(row.printing_scan_id).catch(function (err) {
          alert(err.message || "Unable to load record.");
        });
      });
      tr.querySelector(".pscan-grid-delete-btn")?.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        deleteEntry(row.printing_scan_id);
      });
      els.gridBody.appendChild(tr);
    });
  }

  function loadGrid() {
    const url = window.PSCAN_GRID_URL;
    if (!url) return;
    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (data.ok) renderGrid(data.rows || []);
      })
      .catch(function () {
        if (els.gridEmpty) {
          els.gridEmpty.textContent = "Unable to load records.";
          els.gridEmpty.classList.remove("d-none");
        }
      });
  }

  function getLedgerKind() {
    return window.PSCAN_LEDGER_KIND || "Income";
  }

  function refreshWorkTypeOptions(rows) {
    if (!els.workTypeSelect) return;
    const ledgerKind = getLedgerKind();
    const current = els.workTypeSelect.value;
    els.workTypeSelect.innerHTML = "<option value=\"\">Select work type</option>";
    (rows || [])
      .filter(function (row) {
        return row.ledger_kind === ledgerKind;
      })
      .forEach(function (row) {
        const opt = document.createElement("option");
        opt.value = String(row.work_id);
        opt.textContent = row.work_name;
        els.workTypeSelect.appendChild(opt);
      });
    if (current) els.workTypeSelect.value = current;
  }

  function loadEntryWorkTypes() {
    const baseUrl = window.PSCAN_WORK_TYPES_URL;
    if (!baseUrl) return Promise.resolve();
    const url = baseUrl + "?ledger_kind=" + encodeURIComponent(getLedgerKind());
    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "Unable to load work types.");
        refreshWorkTypeOptions(data.rows || []);
        return data.rows || [];
      })
      .catch(function () {
        return [];
      });
  }

  function showWorkMasterError(message) {
    if (!els.workMasterError) return;
    if (!message) {
      els.workMasterError.classList.add("d-none");
      els.workMasterError.textContent = "";
      return;
    }
    els.workMasterError.textContent = message;
    els.workMasterError.classList.remove("d-none");
  }

  function clearWorkMasterForm() {
    if (els.workEditId) els.workEditId.value = "";
    if (els.workName) els.workName.value = "";
    if (els.workLedgerKind) els.workLedgerKind.value = getLedgerKind();
  }

  function renderWorkMasterRows(rows) {
    if (!els.workMasterBody) return;
    els.workMasterBody.innerHTML = "";
    if (!rows.length) {
      els.workMasterEmpty?.classList.remove("d-none");
      return;
    }
    els.workMasterEmpty?.classList.add("d-none");
    rows.forEach(function (row) {
      const tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" + (row.work_name || "") + "</td>" +
        "<td>" + (row.ledger_kind || "") + "</td>" +
        "<td class=\"text-end\">" +
        "<button type=\"button\" class=\"btn btn-outline-primary btn-sm me-1 pscan-work-edit\" data-id=\"" +
        row.work_id +
        "\" data-name=\"" +
        (row.work_name || "").replace(/"/g, "&quot;") +
        "\" data-kind=\"" +
        (row.ledger_kind || "") +
        "\">Edit</button>" +
        "<button type=\"button\" class=\"btn btn-outline-danger btn-sm pscan-work-delete\" data-id=\"" +
        row.work_id +
        "\">Delete</button>" +
        "</td>";
      els.workMasterBody.appendChild(tr);
    });
  }

  function loadWorkMaster() {
    const baseUrl = window.PSCAN_WORK_TYPES_URL;
    if (!baseUrl) return Promise.resolve();
    const kind = els.workFilterKind?.value || getLedgerKind();
    const url = baseUrl + "?ledger_kind=" + encodeURIComponent(kind);
    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "Unable to load work types.");
        renderWorkMasterRows(data.rows || []);
        if (kind === getLedgerKind()) {
          refreshWorkTypeOptions(data.rows || []);
        }
        return data.rows || [];
      })
      .catch(function (err) {
        showWorkMasterError(err.message || "Unable to load work types.");
        return [];
      });
  }

  function saveWorkMaster(event) {
    event.preventDefault();
    showWorkMasterError("");
    const payload = {
      work_name: els.workName?.value || "",
      ledger_kind: els.workLedgerKind?.value || "",
    };
    const editId = els.workEditId?.value || "";
    if (editId) payload.work_id = parseInt(editId, 10);

    fetch(window.PSCAN_WORK_TYPES_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": window.PSCAN_CSRF || "",
      },
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, data: data };
        });
      })
      .then(function (result) {
        if (!result.ok || !result.data.ok) {
          throw new Error(result.data.error || "Unable to save work type.");
        }
        clearWorkMasterForm();
        return loadWorkMaster().then(function () {
          return loadEntryWorkTypes();
        });
      })
      .catch(function (err) {
        showWorkMasterError(err.message || "Unable to save work type.");
      });
  }

  async function deleteWorkMaster(workId) {
    if (!workId) return;
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!(await JTCSDialog.confirm("Deactivate this work type?"))) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: "Deactivate this work type?" });
      if (!creds) return;
    }
    const template = window.PSCAN_WORK_TYPE_DELETE_URL || "";
    const url = template.replace("/0", "/" + workId);
    fetch(url, {
      method: "DELETE",
      headers: Object.assign(
        { Accept: "application/json", "X-CSRFToken": window.PSCAN_CSRF || "" },
        creds ? { "Content-Type": "application/json" } : {}
      ),
      ...(creds
        ? { body: JSON.stringify({ user_id: creds.user_id, password: creds.password }) }
        : {}),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, data: data };
        });
      })
      .then(function (result) {
        if (!result.ok || !result.data.ok) {
          throw new Error(result.data.error || "Unable to delete work type.");
        }
        return loadWorkMaster().then(function () {
          return loadEntryWorkTypes();
        });
      })
      .catch(function (err) {
        showWorkMasterError(err.message || "Unable to delete work type.");
      });
  }

  els.newEntryBtn?.addEventListener("click", openEntryModal);
  els.refreshGridBtn?.addEventListener("click", loadGrid);
  els.addPaymentBtn?.addEventListener("click", function () {
    addPaymentLine();
  });
  els.saleAmount?.addEventListener("input", updatePaymentSummary);
  els.workDate?.addEventListener("change", function () {
    fetchNextBillNo(els.workDate.value || "");
  });

  form?.addEventListener("submit", function (event) {
    const paymentError = validatePaymentLines();
    if (paymentError) {
      event.preventDefault();
      alert(paymentError);
      return;
    }
    syncPaymentLinesToForm();
  });

  els.workMasterBtn?.addEventListener("click", function () {
    showWorkMasterError("");
    clearWorkMasterForm();
    loadWorkMaster().then(function () {
      workMasterModal?.show();
    });
  });

  els.workMasterForm?.addEventListener("submit", saveWorkMaster);
  els.workCancelEditBtn?.addEventListener("click", function () {
    clearWorkMasterForm();
    showWorkMasterError("");
  });
  els.workFilterKind?.addEventListener("change", loadWorkMaster);

  els.workMasterBody?.addEventListener("click", function (event) {
    const editBtn = event.target.closest(".pscan-work-edit");
    if (editBtn) {
      if (els.workEditId) els.workEditId.value = editBtn.dataset.id || "";
      if (els.workName) els.workName.value = editBtn.dataset.name || "";
      if (els.workLedgerKind) els.workLedgerKind.value = editBtn.dataset.kind || getLedgerKind();
      showWorkMasterError("");
      return;
    }
    const deleteBtn = event.target.closest(".pscan-work-delete");
    if (deleteBtn) {
      deleteWorkMaster(deleteBtn.dataset.id);
    }
  });

  resetPaymentLines([{}]);
  loadEntryWorkTypes();
  loadGrid();
  if (window.PSCAN_AUTO_LOAD_ENTRY_ID) {
    var autoId = parseInt(window.PSCAN_AUTO_LOAD_ENTRY_ID, 10);
    if (!Number.isNaN(autoId) && autoId > 0) {
      loadEntryRecord(autoId).catch(function (err) {
        alert(err.message || "Unable to load record.");
      });
    }
  }
})();
