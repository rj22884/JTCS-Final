(function () {
  "use strict";

  const form = document.getElementById("oieEntryForm");
  if (!form) return;

  const els = {
    newEntryBtn: document.getElementById("oieNewEntryBtn"),
    refreshGridBtn: document.getElementById("oieRefreshGridBtn"),
    entryModalEl: document.getElementById("oieEntryModal"),
    entryModalTitle: document.getElementById("oieEntryModalTitle"),
    gridBody: document.getElementById("oieDataGridBody"),
    gridCount: document.getElementById("oieGridCount"),
    gridEmpty: document.getElementById("oieGridEmpty"),
    gridSearch: document.getElementById("oieGridSearch"),
    gridFilterKind: document.getElementById("oieGridFilterKind"),
    gridDateFrom: document.getElementById("oieGridDateFrom"),
    gridDateTo: document.getElementById("oieGridDateTo"),
    applyFilterBtn: document.getElementById("oieApplyFilterBtn"),
    clearFilterBtn: document.getElementById("oieClearFilterBtn"),
    pageSize: document.getElementById("oiePageSize"),
    pageInfo: document.getElementById("oiePageInfo"),
    pagerNav: document.getElementById("oiePagerNav"),
    statsRow: document.getElementById("oieStatsRow"),
    statIncomeAmount: document.getElementById("oieStatIncomeAmount"),
    statIncomeCount: document.getElementById("oieStatIncomeCount"),
    statIncomeCash: document.getElementById("oieStatIncomeCash"),
    statIncomeBank: document.getElementById("oieStatIncomeBank"),
    statExpenseAmount: document.getElementById("oieStatExpenseAmount"),
    statExpenseCount: document.getElementById("oieStatExpenseCount"),
    statExpenseCash: document.getElementById("oieStatExpenseCash"),
    statExpenseBank: document.getElementById("oieStatExpenseBank"),
    statMiscAmount: document.getElementById("oieStatMiscAmount"),
    statMiscCount: document.getElementById("oieStatMiscCount"),
    statMiscCash: document.getElementById("oieStatMiscCash"),
    statMiscBank: document.getElementById("oieStatMiscBank"),
    billNo: document.getElementById("BillNo"),
    workDate: document.getElementById("WorkDate"),
    entryId: document.getElementById("EntryID"),
    categoryLabel: document.getElementById("oieCategoryLabel"),
    categoryLines: document.getElementById("oieCategoryLines"),
    categorySummary: document.getElementById("oieCategorySummary"),
    addCategoryBtn: document.getElementById("oieAddCategoryBtn"),
    customerName: document.getElementById("CustomerName"),
    mobileNumber: document.getElementById("MobileNumber"),
    remarks: document.getElementById("Remarks"),
    customerResults: document.getElementById("oieCustomerResults"),
    customerSelected: document.getElementById("oieCustomerSelected"),
    addCustomerBtn: document.getElementById("oieAddCustomerBtn"),
    customerModalEl: document.getElementById("oieCustomerModal"),
    customerForm: document.getElementById("oieCustomerForm"),
    customerSaveBtn: document.getElementById("oieCustomerSaveBtn"),
    customerFormError: document.getElementById("oieCustomerFormError"),
    ledgerIncome: document.getElementById("LedgerKindIncome"),
    ledgerExpense: document.getElementById("LedgerKindExpense"),
    ledgerMisc: document.getElementById("LedgerKindMisc"),
    customerId: document.getElementById("oieCustomerId"),
    workDone: document.getElementById("oieWorkDone"),
    tallyBill: document.getElementById("oieTallyBillGenerated"),
    autoBillBtn: document.getElementById("oieAutoBillBtn"),
    miscWorkflowWrap: document.getElementById("oieMiscWorkflowWrap"),
    tallyBillWrap: document.getElementById("oieTallyBillWrap"),
    tallyBillNo: document.getElementById("oieTallyBillNo"),
    tallyBillDate: document.getElementById("oieTallyBillDate"),
    tallyBillAmount: document.getElementById("oieTallyBillAmount"),
    paymentSection: document.getElementById("oiePaymentSection"),
    paymentFieldset: document.getElementById("oiePaymentFieldset"),
    paymentLockedHint: document.getElementById("oiePaymentLockedHint"),
    paymentSectionNum: document.getElementById("oiePaymentSectionNum"),
    remarksSectionNum: document.getElementById("oieRemarksSectionNum"),
    paymentLines: document.getElementById("oiePaymentLines"),
    paymentSummary: document.getElementById("oiePaymentSummary"),
    addPaymentBtn: document.getElementById("oieAddPaymentBtn"),
  };

  const entryModal = els.entryModalEl ? new bootstrap.Modal(els.entryModalEl) : null;
  const customerModal = els.customerModalEl ? new bootstrap.Modal(els.customerModalEl) : null;
  let editingEntryId = null;
  let billNoTouched = false;
  let customerSearchSeq = 0;
  let customerSearchTimer = null;
  let searchTimer = null;
  const PAGE_SIZES = [10, 50, 100, 200, 500, 1000];
  const PAGE_SIZE_KEY = "oie-page-size";
  let allGridRows = [];
  let sortState = { key: "work_date", dir: "desc" };
  let pageState = { page: 1, pageSize: 50 };

  function readStoredPageSize() {
    try {
      const raw = Number(localStorage.getItem(PAGE_SIZE_KEY) || "");
      if (PAGE_SIZES.indexOf(raw) !== -1) return raw;
    } catch (err) {
      /* ignore */
    }
    return 50;
  }

  function persistPageSize(size) {
    try {
      localStorage.setItem(PAGE_SIZE_KEY, String(size));
    } catch (err) {
      /* ignore */
    }
  }

  function currentPageSize() {
    const raw = Number(els.pageSize?.value || pageState.pageSize);
    return PAGE_SIZES.indexOf(raw) !== -1 ? raw : 50;
  }

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

  function currentLedgerKind() {
    if (els.ledgerExpense && els.ledgerExpense.checked) return "Expense";
    if (els.ledgerMisc && els.ledgerMisc.checked) return "Misc.";
    return "Income";
  }

  function isMiscKind() {
    return currentLedgerKind() === "Misc.";
  }

  function isWorkDoneChecked() {
    return !!(els.workDone && els.workDone.checked);
  }

  function isTallyChecked() {
    return !!(els.tallyBill && els.tallyBill.checked);
  }

  function isPaymentActive() {
    return !isMiscKind() || isTallyChecked();
  }

  function syncMiscWorkflow() {
    const misc = isMiscKind();
    els.miscWorkflowWrap?.classList.toggle("d-none", !misc);
    if (!misc) {
      if (els.workDone) els.workDone.checked = false;
      if (els.tallyBill) {
        els.tallyBill.checked = false;
        els.tallyBill.disabled = true;
      }
    } else if (els.tallyBill) {
      const workDone = isWorkDoneChecked();
      els.tallyBill.disabled = !workDone;
      if (!workDone) els.tallyBill.checked = false;
    }
    const tally = isTallyChecked();
    els.tallyBillWrap?.classList.toggle("d-none", !tally);
    els.autoBillBtn?.classList.toggle("d-none", !tally);
    if (tally && els.tallyBillDate && !els.tallyBillDate.value) {
      els.tallyBillDate.value = window.OIE_DEFAULT_DATE || new Date().toISOString().slice(0, 10);
    }
    if (tally && els.tallyBillAmount && !(els.tallyBillAmount.value || "").trim()) {
      const cat = getCategoryTotal();
      if (cat > 0) els.tallyBillAmount.value = cat.toFixed(2);
    }
    const paymentOn = isPaymentActive();
    if (els.paymentFieldset) els.paymentFieldset.disabled = !paymentOn;
    els.paymentSection?.classList.toggle("oie-payment-section-locked", !paymentOn);
    els.paymentLockedHint?.classList.toggle("d-none", paymentOn);
    if (els.paymentSectionNum) els.paymentSectionNum.textContent = misc ? "4" : "3";
    if (els.remarksSectionNum) els.remarksSectionNum.textContent = misc ? "5" : "4";
    if (paymentOn) ensurePaymentLines();
  }

  function isEditMode() {
    return !!editingEntryId;
  }

  function setEditMode(entryId) {
    editingEntryId = entryId ? parseInt(entryId, 10) : null;
    if (els.entryId) {
      els.entryId.value = editingEntryId ? String(editingEntryId) : "";
    }
    if (els.entryModalTitle) {
      els.entryModalTitle.textContent = editingEntryId ? "Edit Entry" : "New Entry";
    }
  }

  function workTypesForKind(kind) {
    if (kind === "Expense") return window.OIE_EXPENSE_WORK_TYPES || [];
    if (kind === "Misc.") return window.OIE_MISC_WORK_TYPES || [];
    return window.OIE_INCOME_WORK_TYPES || [];
  }

  function categoryLabelText(kind) {
    if (kind === "Expense") return "Expense Categories";
    if (kind === "Misc.") return "Misc. Categories";
    return "Income Categories";
  }

  function categorySelectLabelText(kind) {
    if (kind === "Expense") return "Expense Category *";
    if (kind === "Misc.") return "Work / Category *";
    return "Income Category *";
  }

  function syncLedgerLabels() {
    const kind = currentLedgerKind();
    if (els.categoryLabel) {
      els.categoryLabel.textContent = categoryLabelText(kind);
    }
    els.categoryLines?.querySelectorAll(".oie-category-line").forEach(function (line) {
      const catLabel = line.querySelector(".oie-category-select-label");
      const amtLabel = line.querySelector(".oie-category-amount-label");
      const subWrap = line.querySelector(".oie-subwork-wrap");
      if (catLabel) {
        catLabel.textContent = categorySelectLabelText(kind);
      }
      if (amtLabel) {
        amtLabel.textContent = "Amount *";
      }
      if (subWrap) {
        subWrap.classList.toggle("d-none", kind !== "Misc.");
      }
      line.classList.toggle("oie-category-line-misc", kind === "Misc.");
    });
    els.paymentLines?.querySelectorAll(".oie-payment-line").forEach(function (line) {
      const label = line.querySelector(".oie-payment-amount-label");
      if (label) {
        label.textContent = kind === "Expense" ? "Paid Amount" : "Received Amount";
      }
    });
    updateCategorySummary();
    updatePaymentSummary();
    syncMiscWorkflow();
  }

  function buildCategorySelect(selectedId) {
    const select = document.createElement("select");
    select.className = "form-select oie-category-work";
    select.required = true;
    const optEmpty = document.createElement("option");
    optEmpty.value = "";
    optEmpty.textContent = "-- Select --";
    select.appendChild(optEmpty);

    const types = workTypesForKind(currentLedgerKind());
    types.forEach(function (item) {
      const opt = document.createElement("option");
      opt.value = String(item.work_id);
      opt.textContent = item.work_name;
      select.appendChild(opt);
    });
    if (selectedId) {
      select.value = String(selectedId);
    }
    return select;
  }

  function refreshCategorySelectOptions() {
    const kind = currentLedgerKind();
    els.categoryLines?.querySelectorAll(".oie-category-line").forEach(function (line) {
      const select = line.querySelector(".oie-category-work");
      if (!select) return;
      const current = select.value;
      const rebuilt = buildCategorySelect(current);
      select.innerHTML = rebuilt.innerHTML;
      if (current && Array.from(select.options).some(function (opt) { return opt.value === current; })) {
        select.value = current;
      } else {
        select.value = "";
      }
      line.classList.toggle("oie-category-line-misc", kind === "Misc.");
      const subWrap = line.querySelector(".oie-subwork-wrap");
      if (subWrap) subWrap.classList.toggle("d-none", kind !== "Misc.");
      if (kind === "Misc.") {
        const opt = select.options[select.selectedIndex];
        const workName = opt && opt.value ? opt.textContent : "";
        loadSubWorksForLine(line, workName, null);
      }
    });
  }

  function getCategoryTotal() {
    let total = 0;
    els.categoryLines?.querySelectorAll(".oie-category-amount").forEach(function (input) {
      const val = parseFloat(input.value || "0");
      if (!Number.isNaN(val)) total += val;
    });
    return total;
  }

  function updateCategorySummary() {
    if (!els.categorySummary) return;
    const total = getCategoryTotal();
    if (!total) {
      els.categorySummary.textContent = "";
      els.categorySummary.className = "small text-muted ms-auto";
      return;
    }
    els.categorySummary.textContent = "Total: " + total.toFixed(2);
    els.categorySummary.className = "small text-success ms-auto";
  }

  function updateCategoryRemoveButtons() {
    const lines = els.categoryLines?.querySelectorAll(".oie-category-line") || [];
    const hideRemove = lines.length <= 1;
    lines.forEach(function (line) {
      const btn = line.querySelector(".oie-category-remove");
      if (btn) btn.disabled = hideRemove;
    });
  }

  function syncFirstPaymentFromCategories() {
    const lines = els.paymentLines?.querySelectorAll(".oie-payment-line") || [];
    if (lines.length !== 1) {
      updatePaymentSummary();
      return;
    }
    const amountInput = lines[0].querySelector(".oie-payment-amount");
    if (!amountInput) return;
    const categoryTotal = getCategoryTotal();
    // Keep payment in sync when there is a single payment line.
    amountInput.value = categoryTotal > 0 ? categoryTotal.toFixed(2) : "0";
    updatePaymentSummary();
  }

  function buildSubWorkSelect(selectedId) {
    const select = document.createElement("select");
    select.className = "form-select oie-category-subwork";
    const optEmpty = document.createElement("option");
    optEmpty.value = "";
    optEmpty.textContent = "-- Select Sub Work --";
    select.appendChild(optEmpty);
    if (selectedId) {
      select.dataset.pendingValue = String(selectedId);
    }
    return select;
  }

  function loadSubWorksForLine(line, workName, selectedId) {
    const select = line.querySelector(".oie-category-subwork");
    if (!select) return Promise.resolve();
    select.innerHTML = "";
    const optEmpty = document.createElement("option");
    optEmpty.value = "";
    optEmpty.textContent = workName ? "Loading..." : "-- Select Sub Work --";
    select.appendChild(optEmpty);
    select.disabled = !workName;
    if (!workName || !window.OIE_SUB_WORKS_URL) {
      optEmpty.textContent = "-- Select Sub Work --";
      return Promise.resolve();
    }
    const url =
      window.OIE_SUB_WORKS_URL +
      "?work_name=" +
      encodeURIComponent(workName);
    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        select.innerHTML = "";
        const empty = document.createElement("option");
        empty.value = "";
        empty.textContent = "-- Select Sub Work --";
        select.appendChild(empty);
        const rows = data.ok ? data.rows || [] : [];
        rows.forEach(function (row) {
          const opt = document.createElement("option");
          opt.value = String(row.work_type_id);
          opt.textContent = row.sub_work_type;
          select.appendChild(opt);
        });
        const want = selectedId || select.dataset.pendingValue || "";
        delete select.dataset.pendingValue;
        if (want && Array.from(select.options).some(function (o) { return o.value === String(want); })) {
          select.value = String(want);
        }
        select.disabled = false;
        select.required = rows.length > 0 && currentLedgerKind() === "Misc.";
      })
      .catch(function () {
        select.innerHTML = "";
        const empty = document.createElement("option");
        empty.value = "";
        empty.textContent = "-- Select Sub Work --";
        select.appendChild(empty);
        select.disabled = false;
      });
  }

  function addCategoryLine(options) {
    options = options || {};
    if (!els.categoryLines) return null;

    const kind = currentLedgerKind();
    const line = document.createElement("div");
    line.className = "oie-category-line" + (kind === "Misc." ? " oie-category-line-misc" : "");

    const catWrap = document.createElement("div");
    const catLabel = document.createElement("label");
    catLabel.className = "form-label oie-category-select-label";
    catLabel.textContent = categorySelectLabelText(kind);
    const select = buildCategorySelect(options.work_id || options.workId);
    catWrap.appendChild(catLabel);
    catWrap.appendChild(select);

    const subWrap = document.createElement("div");
    subWrap.className = "oie-subwork-wrap" + (kind === "Misc." ? "" : " d-none");
    const subLabel = document.createElement("label");
    subLabel.className = "form-label";
    subLabel.textContent = "Sub Work *";
    const subSelect = buildSubWorkSelect(options.work_type_id || options.workTypeId);
    subWrap.appendChild(subLabel);
    subWrap.appendChild(subSelect);

    select.addEventListener("change", function () {
      const opt = select.options[select.selectedIndex];
      const workName = opt && opt.value ? opt.textContent : "";
      if (currentLedgerKind() === "Misc.") {
        loadSubWorksForLine(line, workName, null);
      }
    });

    const amountWrap = document.createElement("div");
    const amountLabel = document.createElement("label");
    amountLabel.className = "form-label oie-category-amount-label";
    amountLabel.textContent = "Amount *";
    const amount = document.createElement("input");
    amount.type = "number";
    amount.step = "0.01";
    amount.min = "0";
    amount.className = "form-control oie-category-amount";
    amount.required = true;
    amount.value = options.amount != null && options.amount !== "" ? options.amount : "";
    amount.placeholder = "0.00";
    amount.addEventListener("input", function () {
      updateCategorySummary();
      syncFirstPaymentFromCategories();
    });
    amountWrap.appendChild(amountLabel);
    amountWrap.appendChild(amount);

    const actionWrap = document.createElement("div");
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn btn-outline-danger btn-sm oie-category-remove";
    removeBtn.innerHTML = '<i class="bi bi-trash"></i>';
    removeBtn.title = "Remove";
    removeBtn.addEventListener("click", function () {
      if ((els.categoryLines?.querySelectorAll(".oie-category-line") || []).length <= 1) return;
      line.remove();
      updateCategoryRemoveButtons();
      updateCategorySummary();
      syncFirstPaymentFromCategories();
    });
    actionWrap.appendChild(removeBtn);

    line.appendChild(catWrap);
    line.appendChild(subWrap);
    line.appendChild(amountWrap);
    line.appendChild(actionWrap);
    els.categoryLines.appendChild(line);

    if (kind === "Misc.") {
      const opt = select.options[select.selectedIndex];
      const workName = opt && opt.value ? opt.textContent : "";
      if (workName) {
        loadSubWorksForLine(line, workName, options.work_type_id || options.workTypeId);
      }
    }

    updateCategoryRemoveButtons();
    updateCategorySummary();
    return line;
  }

  function resetCategoryLines(lines) {
    if (!els.categoryLines) return;
    els.categoryLines.innerHTML = "";
    const rows = lines && lines.length ? lines : [{}];
    rows.forEach(function (row) {
      addCategoryLine(row);
    });
    updateCategorySummary();
  }

  function validateCategoryLines() {
    const lines = els.categoryLines?.querySelectorAll(".oie-category-line") || [];
    if (!lines.length) return "At least one category is required.";
    const seen = {};
    const kind = currentLedgerKind();
    for (let i = 0; i < lines.length; i++) {
      const select = lines[i].querySelector(".oie-category-work");
      const subSelect = lines[i].querySelector(".oie-category-subwork");
      const amount = lines[i].querySelector(".oie-category-amount");
      if (!select?.value) return "Each category must be selected.";
      if (seen[select.value]) return "Duplicate categories are not allowed.";
      seen[select.value] = true;
      if (kind === "Misc." && subSelect && !subSelect.disabled) {
        const hasOptions = Array.from(subSelect.options).some(function (o) { return o.value; });
        if (hasOptions && !subSelect.value) {
          return "Each Misc. category must have a Sub Work selected.";
        }
      }
      const val = parseFloat(amount?.value || "0");
      if (Number.isNaN(val) || val <= 0) {
        return "Each category amount must be greater than zero.";
      }
    }
    if (getCategoryTotal() <= 0) {
      return "Category total must be greater than zero.";
    }
    return null;
  }

  function syncCategoryLinesToForm() {
    if (!form || !els.categoryLines) return;
    form.querySelectorAll(".oie-category-sync").forEach(function (el) {
      el.remove();
    });
    const lines = els.categoryLines.querySelectorAll(".oie-category-line");
    lines.forEach(function (line) {
      const select = line.querySelector(".oie-category-work");
      const subSelect = line.querySelector(".oie-category-subwork");
      const amount = line.querySelector(".oie-category-amount");
      if (!select || !amount) return;

      const wrap = document.createElement("div");
      wrap.className = "oie-category-sync d-none";

      const workHidden = document.createElement("input");
      workHidden.type = "hidden";
      workHidden.name = "WorkID[]";
      workHidden.value = select.value || "";

      const subHidden = document.createElement("input");
      subHidden.type = "hidden";
      subHidden.name = "WorkTypeID[]";
      subHidden.value = subSelect && !subSelect.classList.contains("d-none")
        ? (subSelect.value || "")
        : "";

      const amountHidden = document.createElement("input");
      amountHidden.type = "hidden";
      amountHidden.name = "CategoryAmount[]";
      amountHidden.value = amount.value || "0";

      wrap.appendChild(workHidden);
      wrap.appendChild(subHidden);
      wrap.appendChild(amountHidden);
      form.appendChild(wrap);
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
    select.className = "form-select oie-payment-bank";
    select.required = true;
    const accounts = window.OIE_BANK_ACCOUNTS || [];
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
    els.paymentLines?.querySelectorAll(".oie-payment-amount").forEach(function (input) {
      const val = parseFloat(input.value || "0");
      if (!Number.isNaN(val)) total += val;
    });
    return total;
  }

  function updatePaymentSummary() {
    if (!els.paymentSummary) return;
    const total = getPaymentTotal();
    const categoryTotal = getCategoryTotal();
    const kind = currentLedgerKind();
    const paidLabel = kind === "Expense" ? "Paid" : "Received";
    if (!total && !categoryTotal) {
      els.paymentSummary.textContent = "";
      els.paymentSummary.className = "small text-muted ms-auto";
      return;
    }
    let text = paidLabel + ": " + total.toFixed(2);
    if (categoryTotal > 0) {
      text += " / Categories: " + categoryTotal.toFixed(2);
    }
    els.paymentSummary.textContent = text;
    const matched = categoryTotal > 0 && Math.abs(total - categoryTotal) < 0.005;
    els.paymentSummary.className =
      "small ms-auto " + (matched || !categoryTotal ? "text-success" : "text-danger");
  }

  function updatePaymentRemoveButtons() {
    const lines = els.paymentLines?.querySelectorAll(".oie-payment-line") || [];
    const hideRemove = lines.length <= 1;
    lines.forEach(function (line) {
      const btn = line.querySelector(".oie-payment-remove");
      if (btn) btn.disabled = hideRemove;
    });
  }

  function syncFirstPaymentAmount() {
    updatePaymentSummary();
  }

  function defaultPaymentDate() {
    return (
      els.workDate?.value ||
      window.OIE_DEFAULT_DATE ||
      new Date().toISOString().slice(0, 10)
    );
  }

  function syncPaymentDatesBeforeSave() {
    const fallback = defaultPaymentDate();
    if (!fallback) return;
    els.paymentLines?.querySelectorAll(".oie-payment-date").forEach(function (input) {
      if (!input.value) input.value = fallback;
    });
  }

  function addPaymentLine(options) {
    options = options || {};
    if (!els.paymentLines) return null;

    const kind = currentLedgerKind();
    const line = document.createElement("div");
    line.className = "oie-payment-line";

    const bankWrap = document.createElement("div");
    bankWrap.className = "oie-payment-bank-wrap";
    const bankLabel = document.createElement("label");
    bankLabel.className = "form-label";
    bankLabel.textContent = "Payment Mode *";
    const select = buildPaymentSelect(options.bank_account_id || options.bankAccountId);
    bankWrap.appendChild(bankLabel);
    bankWrap.appendChild(select);

    const dateWrap = document.createElement("div");
    dateWrap.className = "oie-payment-date-wrap";
    const dateLabel = document.createElement("label");
    dateLabel.className = "form-label";
    dateLabel.textContent = "Date *";
    const dateInput = document.createElement("input");
    dateInput.type = "date";
    dateInput.className = "form-control oie-payment-date";
    dateInput.required = true;
    dateInput.value = options.payment_date || defaultPaymentDate();
    dateInput.addEventListener("change", function () {
      dateInput.dataset.userEdited = "1";
    });
    dateWrap.appendChild(dateLabel);
    dateWrap.appendChild(dateInput);

    const amountWrap = document.createElement("div");
    amountWrap.className = "oie-payment-amount-wrap";
    const amountLabel = document.createElement("label");
    amountLabel.className = "form-label oie-payment-amount-label";
    amountLabel.textContent = kind === "Expense" ? "Paid Amount" : "Received Amount";
    const amount = document.createElement("input");
    amount.type = "number";
    amount.step = "0.01";
    amount.min = "0";
    amount.className = "form-control oie-payment-amount";
    amount.required = true;
    amount.value = options.amount != null && options.amount !== "" ? options.amount : "0";
    amount.addEventListener("input", updatePaymentSummary);
    amountWrap.appendChild(amountLabel);
    amountWrap.appendChild(amount);

    const actionWrap = document.createElement("div");
    actionWrap.className = "oie-payment-action-wrap";
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn btn-outline-danger btn-sm oie-payment-remove";
    removeBtn.innerHTML = '<i class="bi bi-trash"></i>';
    removeBtn.title = "Remove";
    removeBtn.addEventListener("click", function () {
      if ((els.paymentLines?.querySelectorAll(".oie-payment-line") || []).length <= 1) return;
      line.remove();
      updatePaymentRemoveButtons();
      updatePaymentSummary();
    });
    actionWrap.appendChild(removeBtn);

    line.appendChild(bankWrap);
    line.appendChild(dateWrap);
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
    syncFirstPaymentAmount();
  }

  function validatePaymentLines() {
    if (!isPaymentActive()) return null;
    const paymentTotal = getPaymentTotal();
    if (isMiscKind() && paymentTotal <= 0) return null;
    const lines = els.paymentLines?.querySelectorAll(".oie-payment-line") || [];
    if (!lines.length) return "At least one payment mode is required.";
    for (let i = 0; i < lines.length; i++) {
      const bank = lines[i].querySelector(".oie-payment-bank");
      const amount = lines[i].querySelector(".oie-payment-amount");
      const paymentDate = lines[i].querySelector(".oie-payment-date");
      if (!bank?.value) return "Each payment mode must be selected.";
      if (!paymentDate?.value) return "Each payment line must have a date.";
      const val = parseFloat(amount?.value || "0");
      if (Number.isNaN(val) || val <= 0) {
        return "Each payment amount must be greater than zero.";
      }
    }
    if (paymentTotal <= 0) {
      return "Total payment amount must be greater than zero.";
    }
    return null;
  }

  function syncPaymentLinesToForm() {
    if (!form || !els.paymentLines) return;
    form.querySelectorAll(".oie-payment-sync").forEach(function (el) {
      el.remove();
    });
    if (!isPaymentActive()) return;
    const lines = els.paymentLines.querySelectorAll(".oie-payment-line");
    lines.forEach(function (line) {
      const bank = line.querySelector(".oie-payment-bank");
      const amount = line.querySelector(".oie-payment-amount");
      const paymentDate = line.querySelector(".oie-payment-date");
      if (!bank || !amount) return;

      const wrap = document.createElement("div");
      wrap.className = "oie-payment-sync d-none";

      const bankHidden = document.createElement("input");
      bankHidden.type = "hidden";
      bankHidden.name = "PaymentBankAccountID[]";
      bankHidden.value = bank.value || "";

      const amountHidden = document.createElement("input");
      amountHidden.type = "hidden";
      amountHidden.name = "PaymentAmount[]";
      amountHidden.value = amount.value || "0";

      const dateHidden = document.createElement("input");
      dateHidden.type = "hidden";
      dateHidden.name = "PaymentDate[]";
      dateHidden.value = paymentDate?.value || defaultPaymentDate();

      wrap.appendChild(bankHidden);
      wrap.appendChild(amountHidden);
      wrap.appendChild(dateHidden);
      form.appendChild(wrap);
    });
  }

  function fetchNextBillNo() {
    const baseUrl = window.OIE_NEXT_BILL_URL;
    const workDate = els.workDate ? els.workDate.value : "";
    if (!baseUrl || !workDate || isEditMode()) return Promise.resolve();
    const url =
      baseUrl +
      "?work_date=" +
      encodeURIComponent(workDate) +
      "&ledger_kind=" +
      encodeURIComponent(currentLedgerKind());
    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (data.ok && els.billNo && !billNoTouched) {
          els.billNo.value = data.bill_no || "";
        }
      })
      .catch(function () {
        return null;
      });
  }

  function refreshBillNoIfNeeded() {
    if (isEditMode() || billNoTouched) return Promise.resolve();
    return fetchNextBillNo();
  }

  function csrfToken() {
    return (
      window.OIE_CSRF ||
      form.querySelector('input[name="csrf_token"]')?.value ||
      ""
    );
  }

  function hideCustomerResults() {
    if (!els.customerResults) return;
    els.customerResults.classList.add("d-none");
    els.customerResults.innerHTML = "";
  }

  function clearCustomerSelectionHint() {
    if (!els.customerSelected) return;
    els.customerSelected.textContent = "";
    els.customerSelected.classList.add("d-none");
  }

  function selectCustomer(customer) {
    if (!customer) return;
    if (els.customerId) {
      els.customerId.value = String(customer.customer_id || customer.CustomerID || "");
    }
    if (els.customerName) {
      els.customerName.value = customer.customer_name || customer.CustomerName || "";
    }
    if (els.mobileNumber) {
      els.mobileNumber.value = customer.mobile_number || customer.MobileNumber || "";
    }
    if (els.customerSelected) {
      const pan = customer.pan_number || customer.PANNumber || "";
      const bits = [customer.mobile_number || customer.MobileNumber || "", pan].filter(Boolean);
      els.customerSelected.textContent = bits.length
        ? "Selected: " + bits.join(" · ")
        : "Customer selected from master";
      els.customerSelected.classList.remove("d-none");
    }
    hideCustomerResults();
  }

  function searchCustomers(query) {
    const q = (query || "").trim();
    if (q.length < 2) {
      hideCustomerResults();
      return;
    }
    const seq = ++customerSearchSeq;
    const base = window.OIE_CUSTOMER_SEARCH_URL || "/others/income-expense/customers/search";
    const url = base + "?q=" + encodeURIComponent(q);
    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (seq !== customerSearchSeq || !els.customerResults) return;
        if (!data.ok) {
          els.customerResults.innerHTML =
            '<div class="list-group-item text-muted">Search failed</div>';
          els.customerResults.classList.remove("d-none");
          return;
        }
        const list = data.rows || [];
        if (!list.length) {
          els.customerResults.innerHTML =
            '<div class="list-group-item text-muted">No customers found</div>';
        } else {
          els.customerResults.innerHTML = list
            .map(function (row) {
              const sub = [row.mobile_number, row.pan_number].filter(Boolean).join(" · ");
              const btn = document.createElement("button");
              btn.type = "button";
              btn.className = "list-group-item list-group-item-action oie-customer-pick";
              btn.dataset.id = String(row.customer_id || "");
              btn.dataset.name = row.customer_name || "";
              btn.dataset.mobile = row.mobile_number || "";
              btn.dataset.pan = row.pan_number || "";
              btn.innerHTML =
                "<strong>" +
                escapeHtml(row.customer_name) +
                "</strong>" +
                (sub ? '<div class="small text-muted">' + escapeHtml(sub) + "</div>" : "");
              return btn.outerHTML;
            })
            .join("");
        }
        els.customerResults.classList.remove("d-none");
      })
      .catch(function () {
        if (seq !== customerSearchSeq || !els.customerResults) return;
        els.customerResults.innerHTML =
          '<div class="list-group-item text-muted">Search failed</div>';
        els.customerResults.classList.remove("d-none");
      });
  }

  const OTHER_CUSTOMER_TYPE = "Other";
  const PLACEHOLDER_PAN = "PANNOTAVBL";
  const OTHER_OPTIONAL_FIELDS = [
    "pan_number",
    "aadhaar_number",
    "date_of_birth",
    "email_id",
    "mobile_number",
  ];

  function isOtherCustomerType() {
    const typeField = els.customerForm?.elements?.namedItem("customer_type");
    return String(typeField && typeField.value ? typeField.value : "").trim().toLowerCase() ===
      OTHER_CUSTOMER_TYPE.toLowerCase();
  }

  function syncCustomerOtherRequired() {
    if (!els.customerForm) return;
    const otherMode = isOtherCustomerType();
    OTHER_OPTIONAL_FIELDS.forEach(function (name) {
      const field = els.customerForm.elements.namedItem(name);
      if (!field || !field.id) return;
      const label = els.customerForm.querySelector('label[for="' + field.id + '"]');
      if (label) label.classList.toggle("oie-required", !otherMode);
      if (otherMode) field.removeAttribute("required");
      else field.setAttribute("required", "required");
    });
  }

  function openCustomerModal() {
    if (els.customerForm) els.customerForm.reset();
    if (els.customerFormError) {
      els.customerFormError.classList.add("d-none");
      els.customerFormError.textContent = "";
    }
    syncCustomerOtherRequired();
    customerModal?.show();
  }

  function saveCustomer() {
    if (!els.customerForm) return;
    const otherMode = isOtherCustomerType();
    const required = [
      ["customer_group", "Customer group"],
      ["customer_type", "Customer type"],
      ["customer_name", "Customer name"],
    ];
    if (!otherMode) {
      required.push(
        ["pan_number", "PAN"],
        ["aadhaar_number", "Aadhaar"],
        ["date_of_birth", "Date of birth"],
        ["email_id", "Email ID"],
        ["mobile_number", "Mobile number"]
      );
    }
    for (let i = 0; i < required.length; i++) {
      const field = els.customerForm.elements.namedItem(required[i][0]);
      const value = (field && field.value ? String(field.value) : "").trim();
      if (!value) {
        if (els.customerFormError) {
          els.customerFormError.textContent = required[i][1] + " is required.";
          els.customerFormError.classList.remove("d-none");
        } else {
          alert(required[i][1] + " is required.");
        }
        return;
      }
    }

    const formData = new FormData(els.customerForm);
    const payload = Object.fromEntries(formData.entries());
    if (otherMode && !(String(payload.pan_number || "").trim())) {
      payload.pan_number = PLACEHOLDER_PAN;
      const panField = els.customerForm.elements.namedItem("pan_number");
      if (panField && !String(panField.value || "").trim()) panField.value = PLACEHOLDER_PAN;
    }
    if (otherMode) {
      const pan = String(payload.pan_number || "").trim().toUpperCase();
      if (pan && pan.length !== 10) {
        if (els.customerFormError) {
          els.customerFormError.textContent = "Valid 10-character PAN is required.";
          els.customerFormError.classList.remove("d-none");
        }
        return;
      }
      const mobile = String(payload.mobile_number || "").replace(/\D/g, "");
      if (mobile && mobile.length !== 10) {
        if (els.customerFormError) {
          els.customerFormError.textContent = "Valid 10-digit mobile number is required.";
          els.customerFormError.classList.remove("d-none");
        }
        return;
      }
      const aadhaar = String(payload.aadhaar_number || "").replace(/\D/g, "");
      if (aadhaar && aadhaar.length !== 12) {
        if (els.customerFormError) {
          els.customerFormError.textContent = "Valid 12-digit Aadhaar is required.";
          els.customerFormError.classList.remove("d-none");
        }
        return;
      }
    }
    if (els.customerSaveBtn) els.customerSaveBtn.disabled = true;
    if (els.customerFormError) {
      els.customerFormError.classList.add("d-none");
      els.customerFormError.textContent = "";
    }
    const createUrl = window.OIE_CUSTOMER_CREATE_URL || "/others/income-expense/customers";
    fetch(createUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) {
            throw new Error(data.error || "Unable to add customer.");
          }
          return data;
        });
      })
      .then(function (data) {
        const c = data.customer || {};
        selectCustomer({
          customer_id: c.customer_id || c.CustomerID,
          customer_name: c.customer_name || c.CustomerName,
          mobile_number: c.mobile_number || c.MobileNumber,
          pan_number: c.pan_number || c.PANNumber,
        });
        customerModal?.hide();
        els.customerForm.reset();
      })
      .catch(function (err) {
        if (els.customerFormError) {
          els.customerFormError.textContent = err.message || "Unable to add customer.";
          els.customerFormError.classList.remove("d-none");
        } else {
          alert(err.message || "Unable to add customer.");
        }
      })
      .finally(function () {
        if (els.customerSaveBtn) els.customerSaveBtn.disabled = false;
      });
  }

  function resetForm() {
    setEditMode(null);
    billNoTouched = false;
    form.reset();
    clearCustomerSelectionHint();
    hideCustomerResults();
    if (els.workDate && !els.workDate.value) {
      els.workDate.value = new Date().toISOString().slice(0, 10);
    }
    if (els.ledgerIncome) els.ledgerIncome.checked = true;
    syncLedgerLabels();
    resetCategoryLines([{}]);
    resetPaymentLines([{}]);
    return fetchNextBillNo();
  }

  function openNewEntry() {
    resetForm().then(function () {
      ensureCategoryLines();
      ensurePaymentLines();
      if (entryModal) entryModal.show();
    });
  }

  function ensureCategoryLines() {
    const lines = els.categoryLines?.querySelectorAll(".oie-category-line") || [];
    if (!lines.length) {
      resetCategoryLines([{}]);
    }
  }

  function ensurePaymentLines() {
    const lines = els.paymentLines?.querySelectorAll(".oie-payment-line") || [];
    if (!lines.length) {
      resetPaymentLines([{}]);
    }
  }

  function formatDisplayDate(value) {
    if (window.formatDisplaySmart) return window.formatDisplaySmart(value);
    if (window.formatDisplayDate) return window.formatDisplayDate(value);
    if (window.JtcsFormatDisplayDate) return window.JtcsFormatDisplayDate(value);
    return value || "";
  }

  function ledgerBadge(kind) {
    const cls =
      kind === "Expense"
        ? "oie-ledger-badge-expense"
        : kind === "Misc."
          ? "oie-ledger-badge-misc"
          : "oie-ledger-badge-income";
    return '<span class="badge ' + cls + '">' + escapeHtml(kind || "Income") + "</span>";
  }

  function formatAmount(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return "0.00";
    return num.toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function parseAmount(value) {
    const num = Number(value);
    return Number.isFinite(num) ? num : 0;
  }

  function rowSearchText(row) {
    return [
      row.bill_no,
      row.ledger_kind,
      row.work_name,
      row.account_label,
      row.customer_name,
      row.mobile_number,
      row.remarks,
      row.amount,
    ]
      .join(" ")
      .toLowerCase();
  }

  function rowsForStats() {
    const search = (els.gridSearch?.value || "").trim().toLowerCase();
    const dateFrom = (els.gridDateFrom?.value || "").trim();
    const dateTo = (els.gridDateTo?.value || "").trim();
    return (allGridRows || []).filter(function (row) {
      const workDate = (row.work_date || "").slice(0, 10);
      if (dateFrom && workDate && workDate < dateFrom) return false;
      if (dateTo && workDate && workDate > dateTo) return false;
      if (search && rowSearchText(row).indexOf(search) === -1) return false;
      return true;
    });
  }

  function getFilteredRows() {
    const filterKind = els.gridFilterKind ? els.gridFilterKind.value : "";
    return rowsForStats().filter(function (row) {
      if (filterKind && row.ledger_kind !== filterKind) return false;
      return true;
    });
  }

  function sortRows(rows) {
    const key = sortState.key || "work_date";
    const dir = sortState.dir === "asc" ? 1 : -1;
    const numericKeys = { amount: true, entry_id: true };
    return rows.slice().sort(function (a, b) {
      let av = a[key];
      let bv = b[key];
      if (numericKeys[key]) {
        av = parseAmount(av);
        bv = parseAmount(bv);
        if (av === bv) return (a.entry_id - b.entry_id) * dir;
        return (av - bv) * dir;
      }
      av = String(av == null ? "" : av).toLowerCase();
      bv = String(bv == null ? "" : bv).toLowerCase();
      if (av === bv) return (a.entry_id - b.entry_id) * dir;
      return av < bv ? -1 * dir : 1 * dir;
    });
  }

  function syncSortHeaders() {
    document.querySelectorAll("#oieDataGrid th.oie-sortable").forEach(function (th) {
      const key = th.getAttribute("data-sort-key") || "";
      const active = key === sortState.key;
      th.classList.toggle("oie-sorted", active);
      const icon = th.querySelector(".oie-sort-icon");
      if (!icon) return;
      icon.className =
        "bi oie-sort-icon " +
        (active
          ? sortState.dir === "asc"
            ? "bi-sort-up"
            : "bi-sort-down"
          : "bi-arrow-down-up");
    });
  }

  function syncStatCardActive() {
    const current = els.gridFilterKind ? els.gridFilterKind.value : "";
    document.querySelectorAll(".oie-stat-card[data-kind-filter]").forEach(function (card) {
      const value = card.getAttribute("data-kind-filter") || "";
      card.classList.toggle("is-active", value === current);
    });
  }

  function isCashAccount(row) {
    return String(row.account_label || "").trim().toLowerCase() === "cash";
  }

  function updateStats() {
    const rows = rowsForStats();
    let incomeAmt = 0;
    let expenseAmt = 0;
    let miscAmt = 0;
    let incomeCash = 0;
    let incomeBank = 0;
    let expenseCash = 0;
    let expenseBank = 0;
    let miscCash = 0;
    let miscBank = 0;
    let incomeCount = 0;
    let expenseCount = 0;
    let miscCount = 0;
    rows.forEach(function (row) {
      const amount = parseAmount(row.amount);
      const cash = isCashAccount(row);
      if (row.ledger_kind === "Expense") {
        expenseAmt += amount;
        expenseCount += 1;
        if (cash) expenseCash += amount;
        else expenseBank += amount;
      } else if (row.ledger_kind === "Misc.") {
        miscAmt += amount;
        miscCount += 1;
        if (cash) miscCash += amount;
        else miscBank += amount;
      } else {
        incomeAmt += amount;
        incomeCount += 1;
        if (cash) incomeCash += amount;
        else incomeBank += amount;
      }
    });
    if (els.statIncomeAmount) els.statIncomeAmount.textContent = formatAmount(incomeAmt);
    if (els.statIncomeCount) els.statIncomeCount.textContent = String(incomeCount);
    if (els.statIncomeCash) els.statIncomeCash.textContent = formatAmount(incomeCash);
    if (els.statIncomeBank) els.statIncomeBank.textContent = formatAmount(incomeBank);
    if (els.statExpenseAmount) els.statExpenseAmount.textContent = formatAmount(expenseAmt);
    if (els.statExpenseCount) els.statExpenseCount.textContent = String(expenseCount);
    if (els.statExpenseCash) els.statExpenseCash.textContent = formatAmount(expenseCash);
    if (els.statExpenseBank) els.statExpenseBank.textContent = formatAmount(expenseBank);
    if (els.statMiscAmount) els.statMiscAmount.textContent = formatAmount(miscAmt);
    if (els.statMiscCount) els.statMiscCount.textContent = String(miscCount);
    if (els.statMiscCash) els.statMiscCash.textContent = formatAmount(miscCash);
    if (els.statMiscBank) els.statMiscBank.textContent = formatAmount(miscBank);
    syncStatCardActive();
  }

  function pageWindow(current, total) {
    if (total <= 7) {
      const pages = [];
      for (let i = 1; i <= total; i++) pages.push(i);
      return pages;
    }
    const pages = [1];
    const start = Math.max(2, current - 1);
    const end = Math.min(total - 1, current + 1);
    if (start > 2) pages.push("ellipsis");
    for (let i = start; i <= end; i++) pages.push(i);
    if (end < total - 1) pages.push("ellipsis");
    pages.push(total);
    return pages;
  }

  function pagerItem(label, page, options) {
    const opts = options || {};
    const disabled = !!opts.disabled;
    const active = !!opts.active;
    const ellipsis = !!opts.ellipsis;
    if (ellipsis) {
      return '<li class="page-item disabled"><span class="page-link">…</span></li>';
    }
    const cls = "page-item" + (disabled ? " disabled" : "") + (active ? " active" : "");
    if (disabled && !active) {
      return '<li class="' + cls + '"><span class="page-link">' + label + "</span></li>";
    }
    return (
      '<li class="' +
      cls +
      '"><button type="button" class="page-link oie-page-btn" data-page="' +
      page +
      '"' +
      (active ? ' aria-current="page"' : "") +
      ">" +
      label +
      "</button></li>"
    );
  }

  function renderPager(total, pageSize, page, totalPages) {
    pageState.page = page;
    pageState.pageSize = pageSize;
    if (els.gridCount) {
      els.gridCount.textContent = total + " record(s)";
    }
    if (els.pageInfo) {
      if (!total) {
        els.pageInfo.textContent = "Showing 0 of 0";
      } else {
        const from = (page - 1) * pageSize + 1;
        const to = Math.min(page * pageSize, total);
        els.pageInfo.textContent = "Showing " + from + "–" + to + " of " + total;
      }
    }
    if (!els.pagerNav) return;
    if (!total) {
      els.pagerNav.innerHTML = "";
      return;
    }
    const items = [
      pagerItem("Previous", page - 1, { disabled: page <= 1 }),
    ];
    pageWindow(page, totalPages).forEach(function (item) {
      if (item === "ellipsis") {
        items.push(pagerItem("", 0, { ellipsis: true }));
        return;
      }
      items.push(pagerItem(String(item), item, { active: item === page }));
    });
    items.push(pagerItem("Next", page + 1, { disabled: page >= totalPages }));
    els.pagerNav.innerHTML = items.join("");
  }

  function renderGrid(options) {
    if (!els.gridBody) return;
    const opts = options || {};
    const filtered = sortRows(getFilteredRows());
    updateStats();
    syncSortHeaders();

    const pageSize = currentPageSize();
    const total = filtered.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize) || 1);
    let page = opts.resetPage ? 1 : pageState.page;
    if (page > totalPages) page = totalPages;
    if (page < 1) page = 1;

    if (els.gridEmpty) {
      els.gridEmpty.classList.toggle("d-none", total > 0);
    }

    const start = total ? (page - 1) * pageSize : 0;
    const pageRows = filtered.slice(start, start + pageSize);
    renderPager(total, pageSize, page, totalPages);

    els.gridBody.innerHTML = pageRows
      .map(function (row) {
        const category = row.work_name || "";
        return (
          "<tr>" +
          "<td>" +
          escapeHtml(row.bill_no) +
          "</td>" +
          "<td>" +
          ledgerBadge(row.ledger_kind) +
          (row.ledger_kind === "Misc."
            ? (row.work_done
                ? '<span class="badge text-bg-success oie-wf-badge">Work Done</span>'
                : "") +
              (row.tally_bill_generated
                ? '<span class="badge text-bg-primary oie-wf-badge">Tally Bill</span>'
                : row.work_done
                  ? '<span class="badge text-bg-warning oie-wf-badge">Bill Pending</span>'
                  : "")
            : "") +
          "</td>" +
          "<td>" +
          escapeHtml(formatDisplayDate(row.work_date)) +
          "</td>" +
          '<td class="oie-category-cell" title="' +
          escapeHtml(category) +
          '">' +
          escapeHtml(category) +
          "</td>" +
          '<td class="oie-account-cell">' +
          escapeHtml(row.account_label || "—") +
          "</td>" +
          '<td class="text-end">' +
          escapeHtml(formatAmount(row.amount)) +
          "</td>" +
          "<td>" +
          escapeHtml(row.customer_name) +
          "</td>" +
          "<td>" +
          escapeHtml(row.mobile_number) +
          "</td>" +
          "<td>" +
          escapeHtml(row.remarks || "") +
          "</td>" +
          "<td>" +
          escapeHtml(formatDisplayDate(row.created_date)) +
          "</td>" +
          '<td class="text-end text-nowrap">' +
          '<button type="button" class="btn btn-outline-secondary btn-sm oie-grid-edit-btn" data-id="' +
          row.entry_id +
          '" title="Edit"><i class="bi bi-pencil"></i></button> ' +
          '<button type="button" class="btn btn-outline-danger btn-sm oie-grid-delete-btn" data-id="' +
          row.entry_id +
          '" title="Delete"><i class="bi bi-trash"></i></button>' +
          "</td>" +
          "</tr>"
        );
      })
      .join("");
  }

  function renderGridFromStart() {
    renderGrid({ resetPage: true });
  }

  function goToPage(page) {
    pageState.page = page;
    renderGrid();
  }

  function clearGridFilters() {
    if (els.gridSearch) els.gridSearch.value = "";
    if (els.gridFilterKind) els.gridFilterKind.value = "";
    if (els.gridDateFrom) els.gridDateFrom.value = "";
    if (els.gridDateTo) els.gridDateTo.value = "";
    sortState = { key: "work_date", dir: "desc" };
    renderGridFromStart();
  }

  function loadGrid() {
    const url = window.OIE_GRID_URL;
    if (!url) return Promise.resolve();
    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) { return parseJsonResponse(res); })
      .then(function (data) {
        allGridRows = data.rows || [];
        renderGridFromStart();
      })
      .catch(function (err) {
        console.error(err);
      });
  }

  function loadEntry(entryId) {
    const url = apiUrl(window.OIE_RECORD_URL, entryId);
    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (!data.ok || !data.record) {
          alert(data.error || "Could not load record.");
          return;
        }
        const record = data.record;
        setEditMode(record.entry_id);
        billNoTouched = true;
        if (els.billNo) els.billNo.value = record.bill_no || "";
        if (els.workDate) els.workDate.value = record.work_date || "";
        if (record.ledger_kind === "Expense" && els.ledgerExpense) {
          els.ledgerExpense.checked = true;
        } else if (record.ledger_kind === "Misc." && els.ledgerMisc) {
          els.ledgerMisc.checked = true;
        } else if (els.ledgerIncome) {
          els.ledgerIncome.checked = true;
        }
        const hasPayments = (record.payments || []).some(function (p) {
          return parseFloat(p.amount || "0") > 0;
        });
        if (els.workDone) {
          els.workDone.checked = !!record.work_done || (record.ledger_kind === "Misc." && hasPayments);
        }
        if (els.tallyBill) {
          els.tallyBill.checked =
            !!record.tally_bill_generated || (record.ledger_kind === "Misc." && hasPayments);
        }
        if (els.customerId) els.customerId.value = record.customer_id ? String(record.customer_id) : "";
        if (els.tallyBillNo) {
          els.tallyBillNo.value = record.tally_bill_no || (hasPayments ? record.bill_no || "" : "");
        }
        if (els.tallyBillDate) {
          els.tallyBillDate.value = (record.tally_bill_date || record.work_date || "").slice(0, 10);
        }
        if (els.tallyBillAmount) {
          els.tallyBillAmount.value = record.tally_bill_amount || (hasPayments ? record.amount || "" : "");
        }
        syncLedgerLabels();
        const categoryRows =
          record.categories && record.categories.length
            ? record.categories
            : [{ work_id: record.work_id, amount: record.amount }];
        resetCategoryLines(categoryRows);
        if (els.customerName) els.customerName.value = record.customer_name || "";
        if (els.mobileNumber) els.mobileNumber.value = record.mobile_number || "";
        if (els.remarks) els.remarks.value = record.remarks || "";
        clearCustomerSelectionHint();
        hideCustomerResults();
        if (els.customerId) els.customerId.value = record.customer_id ? String(record.customer_id) : "";
        if (els.customerSelected && record.customer_id) {
          els.customerSelected.textContent = "Customer selected from master";
          els.customerSelected.classList.remove("d-none");
        }
        resetPaymentLines(record.payments && record.payments.length ? record.payments : [{}]);
        syncMiscWorkflow();
        if (entryModal) entryModal.show();
      });
  }

  async function deleteEntry(entryId) {
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!(await JTCSDialog.confirm("Delete this income / expense record?"))) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: "Delete this income / expense record?" });
      if (!creds) return;
    }
    const url = apiUrl(window.OIE_DELETE_URL, entryId);
    const csrf = form.querySelector('input[name="csrf_token"]');
    const body = new FormData();
    if (csrf) body.append("csrf_token", csrf.value);
    if (creds) window.JTCSDeleteConfirm.appendCreds(body, creds);
    fetch(url, { method: "POST", body: body, headers: { Accept: "application/json" } })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (data.ok) {
          loadGrid();
        } else {
          alert(data.error || "Delete failed.");
        }
      })
      .catch(function () {
        alert("Delete failed.");
      });
  }

  function parseJsonResponse(res) {
    const contentType = res.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      return res.text().then(function (body) {
        if (res.status === 401 || res.status === 403 || /sign in|login/i.test(body || "")) {
          throw new Error("Session expired. Please sign in again and retry save.");
        }
        if (/csrf/i.test(body || "")) {
          throw new Error("Security token expired. Refresh the page (Ctrl+F5) and try again.");
        }
        throw new Error(
          "Server returned an unexpected response (HTTP " +
            res.status +
            "). Refresh the page and try again."
        );
      });
    }
    return res.json().then(function (data) {
      if (!res.ok || !data.ok) {
        throw new Error(data.error || "Request failed.");
      }
      return data;
    });
  }

  function validateMiscWorkflow() {
    if (!isMiscKind()) return null;
    if (isTallyChecked() && !isWorkDoneChecked()) {
      return "Work Done must be checked before Tally Bill Generated.";
    }
    if (!isTallyChecked()) return null;
    if (!(els.tallyBillNo?.value || "").trim()) {
      return "Tally bill number is required when Tally Bill Generated is checked.";
    }
    const billAmount = parseFloat(els.tallyBillAmount?.value || "0");
    if (!billAmount || billAmount <= 0) {
      return "Bill amount is required when Tally Bill Generated is checked.";
    }
    if (!(els.customerName?.value || "").trim()) {
      return "Customer name is required when Tally Bill Generated is checked.";
    }
    return null;
  }

  function openAutomatedBill() {
    const customerId = (els.customerId?.value || "").trim();
    if (!customerId) {
      alert("Please select a customer first.");
      return;
    }
    const params = new URLSearchParams();
    params.set("customer_id", customerId);
    const customerName = (els.customerName?.value || "").trim();
    if (customerName) params.set("customer_name", customerName);
    const url = "/accounting/invoice?" + params.toString();
    const width = Math.min(1600, Math.max(1280, Math.floor((screen.availWidth || 1400) * 0.92)));
    const height = Math.min(1000, Math.max(820, Math.floor((screen.availHeight || 900) * 0.92)));
    const left = Math.max(0, Math.floor(((screen.availWidth || width) - width) / 2));
    const top = Math.max(0, Math.floor(((screen.availHeight || height) - height) / 2));
    const features = [
      "width=" + width,
      "height=" + height,
      "left=" + left,
      "top=" + top,
      "menubar=yes",
      "toolbar=yes",
      "location=yes",
      "status=yes",
      "resizable=yes",
      "scrollbars=yes",
    ].join(",");
    const win = window.open(url, "jtcsAccountingInvoiceWindow", features);
    if (!win) {
      alert("Pop-up blocked. Please allow pop-ups for this site, then try again.");
      return;
    }
    try {
      win.focus();
    } catch (e) {
      /* ignore */
    }
  }

  window.OIE_applyBillingResult = function (data) {
    if (!data) return;
    if (els.tallyBillNo && data.bill_no) els.tallyBillNo.value = data.bill_no;
    if (els.tallyBillAmount && data.bill_amount != null) els.tallyBillAmount.value = data.bill_amount;
    if (els.tallyBillDate && data.bill_date) els.tallyBillDate.value = data.bill_date;
    if (els.tallyBill) els.tallyBill.checked = true;
    syncMiscWorkflow();
  };

  function saveEntry() {
    const categoryError = validateCategoryLines();
    if (categoryError) {
      alert(categoryError);
      return Promise.resolve();
    }
    const workflowError = validateMiscWorkflow();
    if (workflowError) {
      alert(workflowError);
      return Promise.resolve();
    }
    const paymentError = validatePaymentLines();
    if (paymentError) {
      alert(paymentError);
      return Promise.resolve();
    }
    syncPaymentDatesBeforeSave();
    syncCategoryLinesToForm();
    syncPaymentLinesToForm();
    const saveBtn = document.getElementById("oieSaveBtn");
    if (saveBtn) saveBtn.disabled = true;
    const saveUrl = window.OIE_SAVE_URL || "/others/income-expense/save";
    const body = new FormData(form);
    return fetch(saveUrl, {
      method: "POST",
      body: body,
      headers: {
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": csrfToken(),
      },
    })
      .then(function (res) { return parseJsonResponse(res); })
      .then(function (data) {
        entryModal?.hide();
        return loadGrid().then(function () {
          return data;
        });
      })
      .catch(function (err) {
        alert(err.message || "Unable to save entry.");
      })
      .finally(function () {
        if (saveBtn) saveBtn.disabled = false;
      });
  }

  function ensureBillNoThenSave() {
    if (isEditMode() || (els.billNo && els.billNo.value.trim())) {
      return saveEntry();
    }
    return refreshBillNoIfNeeded().then(function () {
      if (!els.billNo?.value?.trim()) {
        alert("Bill number could not be generated. Check work date.");
        return;
      }
      return saveEntry();
    });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    ensureBillNoThenSave();
  });

  if (els.newEntryBtn) {
    els.newEntryBtn.addEventListener("click", openNewEntry);
  }
  if (els.refreshGridBtn) {
    els.refreshGridBtn.addEventListener("click", loadGrid);
  }
  if (els.gridFilterKind) {
    els.gridFilterKind.addEventListener("change", renderGridFromStart);
  }
  if (els.gridDateFrom) {
    els.gridDateFrom.addEventListener("change", renderGridFromStart);
  }
  if (els.gridDateTo) {
    els.gridDateTo.addEventListener("change", renderGridFromStart);
  }
  if (els.applyFilterBtn) {
    els.applyFilterBtn.addEventListener("click", renderGridFromStart);
  }
  if (els.clearFilterBtn) {
    els.clearFilterBtn.addEventListener("click", clearGridFilters);
  }
  if (els.gridSearch) {
    els.gridSearch.addEventListener("input", function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(renderGridFromStart, 250);
    });
  }
  if (els.pageSize) {
    const storedSize = readStoredPageSize();
    els.pageSize.value = String(storedSize);
    pageState.pageSize = storedSize;
    els.pageSize.addEventListener("change", function () {
      const size = currentPageSize();
      pageState.pageSize = size;
      persistPageSize(size);
      renderGridFromStart();
    });
  }
  if (els.pagerNav) {
    els.pagerNav.addEventListener("click", function (event) {
      const btn = event.target.closest(".oie-page-btn");
      if (!btn || !els.pagerNav.contains(btn)) return;
      const page = Number(btn.getAttribute("data-page") || "");
      if (!Number.isFinite(page) || page < 1) return;
      goToPage(page);
    });
  }
  if (els.statsRow) {
    els.statsRow.addEventListener("click", function (event) {
      const card = event.target.closest(".oie-stat-card[data-kind-filter]");
      if (!card || !els.statsRow.contains(card)) return;
      if (els.gridFilterKind) {
        els.gridFilterKind.value = card.getAttribute("data-kind-filter") || "";
      }
      renderGridFromStart();
    });
  }
  document.querySelectorAll("#oieDataGrid th.oie-sortable").forEach(function (th) {
    th.addEventListener("click", function () {
      const key = th.getAttribute("data-sort-key") || "";
      if (!key) return;
      if (sortState.key === key) {
        sortState.dir = sortState.dir === "asc" ? "desc" : "asc";
      } else {
        sortState.key = key;
        sortState.dir = key === "work_date" || key === "created_date" || key === "amount" ? "desc" : "asc";
      }
      renderGridFromStart();
    });
  });
  if (els.workDate) {
    els.workDate.addEventListener("change", function () {
      fetchNextBillNo();
      const workDate = els.workDate.value;
      if (!workDate) return;
      els.paymentLines?.querySelectorAll(".oie-payment-date").forEach(function (input) {
        if (!input.dataset.userEdited) input.value = workDate;
      });
    });
  }
  if (els.billNo) {
    els.billNo.addEventListener("input", function () {
      billNoTouched = true;
    });
  }
  if (els.addPaymentBtn) {
    els.addPaymentBtn.addEventListener("click", function () {
      addPaymentLine({});
    });
  }
  if (els.addCategoryBtn) {
    els.addCategoryBtn.addEventListener("click", function () {
      addCategoryLine({});
    });
  }

  if (els.customerName) {
    els.customerName.addEventListener("input", function () {
      if (els.customerId) els.customerId.value = "";
      clearCustomerSelectionHint();
      clearTimeout(customerSearchTimer);
      customerSearchTimer = setTimeout(function () {
        searchCustomers(els.customerName.value);
      }, 280);
    });
    els.customerName.addEventListener("focus", function () {
      if ((els.customerName.value || "").trim().length >= 2) {
        searchCustomers(els.customerName.value);
      }
    });
  }

  if (els.customerResults) {
    els.customerResults.addEventListener("click", function (event) {
      const pick = event.target.closest(".oie-customer-pick");
      if (!pick) return;
      selectCustomer({
        customer_id: pick.getAttribute("data-id"),
        customer_name: pick.getAttribute("data-name"),
        mobile_number: pick.getAttribute("data-mobile"),
        pan_number: pick.getAttribute("data-pan"),
      });
    });
  }

  if (els.addCustomerBtn) {
    els.addCustomerBtn.addEventListener("click", openCustomerModal);
  }
  const custTypeField = document.getElementById("oieCustType");
  custTypeField?.addEventListener("change", syncCustomerOtherRequired);

  if (els.customerSaveBtn) {
    els.customerSaveBtn.addEventListener("click", saveCustomer);
  }

  document.addEventListener("click", function (event) {
    if (
      !event.target.closest("#CustomerName") &&
      !event.target.closest("#oieCustomerResults") &&
      !event.target.closest("#oieAddCustomerBtn")
    ) {
      hideCustomerResults();
    }
  });

  form.querySelectorAll('input[name="LedgerKind"]').forEach(function (radio) {
    radio.addEventListener("change", function () {
      syncLedgerLabels();
      refreshCategorySelectOptions();
      billNoTouched = false;
      fetchNextBillNo();
      if ((currentLedgerKind() === "Expense" || currentLedgerKind() === "Misc.") && els.billNo) {
        els.billNo.value = "";
      }
    });
  });

  els.workDone?.addEventListener("change", syncMiscWorkflow);
  els.tallyBill?.addEventListener("change", syncMiscWorkflow);
  els.autoBillBtn?.addEventListener("click", openAutomatedBill);

  if (els.gridBody) {
    els.gridBody.addEventListener("click", function (event) {
      const editBtn = event.target.closest(".oie-grid-edit-btn");
      if (editBtn) {
        loadEntry(editBtn.getAttribute("data-id"));
        return;
      }
      const deleteBtn = event.target.closest(".oie-grid-delete-btn");
      if (deleteBtn) {
        deleteEntry(deleteBtn.getAttribute("data-id"));
      }
    });
  }

  if (els.entryModalEl) {
    els.entryModalEl.addEventListener("shown.bs.modal", function () {
      ensureCategoryLines();
      ensurePaymentLines();
    });
  }

  resetCategoryLines([{}]);
  resetPaymentLines([{}]);
  loadGrid();
  if (window.OIE_AUTO_LOAD_ENTRY_ID) {
    var autoId = parseInt(window.OIE_AUTO_LOAD_ENTRY_ID, 10);
    if (!Number.isNaN(autoId) && autoId > 0) {
      loadEntry(autoId);
    }
  }
})();
