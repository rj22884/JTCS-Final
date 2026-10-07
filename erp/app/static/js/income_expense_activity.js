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
    generateBillWrap: document.getElementById("oieGenerateBillWrap"),
    generateBillLabel: document.getElementById("oieGenerateBillLabel"),
    generateBillYes: document.getElementById("oieGenerateBillYes"),
    generateBillNo: document.getElementById("oieGenerateBillNo"),
    paymentReceivedYes: document.getElementById("oiePaymentReceivedYes"),
    paymentReceivedNo: document.getElementById("oiePaymentReceivedNo"),
    invoiceStatus: document.getElementById("oieInvoiceStatus"),
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
    if (window.OIE_FORCE_LEDGER_KIND) {
      return String(window.OIE_FORCE_LEDGER_KIND);
    }
    if (els.ledgerExpense && els.ledgerExpense.checked) return "Expense";
    if (els.ledgerMisc && els.ledgerMisc.checked) return "Misc.";
    return "Income";
  }

  function applyForcedLedgerKindUi() {
    const forced = window.OIE_FORCE_LEDGER_KIND ? String(window.OIE_FORCE_LEDGER_KIND) : "";
    if (window.OIE_HIDE_MISC && !forced) {
      els.statsRow?.querySelectorAll(".oie-stat-misc").forEach(function (el) {
        el.classList.add("d-none");
      });
      if (els.gridFilterKind) {
        Array.from(els.gridFilterKind.options).forEach(function (opt) {
          if (opt.value === "Misc.") opt.hidden = true;
        });
        if (els.gridFilterKind.value === "Misc.") els.gridFilterKind.value = "";
      }
      if (els.ledgerMisc) {
        els.ledgerMisc.closest(".form-check")?.classList.add("d-none");
        if (els.ledgerMisc.checked && els.ledgerIncome) els.ledgerIncome.checked = true;
      }
      const legend = form.querySelector(".oie-entry-type-fieldset legend");
      if (legend) legend.textContent = "Income / Expense";
    }
    if (!forced) return;
    if (forced === "Misc." && els.ledgerMisc) {
      els.ledgerMisc.checked = true;
    } else if (forced === "Expense" && els.ledgerExpense) {
      els.ledgerExpense.checked = true;
    } else if (els.ledgerIncome) {
      els.ledgerIncome.checked = true;
    }
    const typeFieldset = form.querySelector(".oie-entry-type-fieldset");
    if (typeFieldset) typeFieldset.classList.add("d-none");
    if (els.statsRow && forced === "Misc.") {
      els.statsRow.querySelectorAll(".oie-stat-income, .oie-stat-expense").forEach(function (el) {
        el.classList.add("d-none");
      });
    }
    if (els.gridFilterKind) {
      els.gridFilterKind.value = forced;
      Array.from(els.gridFilterKind.options).forEach(function (opt) {
        if (opt.value && opt.value !== forced) opt.hidden = true;
      });
      els.gridFilterKind.closest(".col-md-2")?.classList.add("d-none");
    }
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

  function miscPaymentBox() {
    return document.getElementById("oieMiscPaymentReceived");
  }

  function isPaymentReceivedYes() {
    if (miscInvoicePage) return !!(miscPaymentBox() && miscPaymentBox().checked);
    return !!(els.paymentReceivedYes && els.paymentReceivedYes.checked);
  }

  function setPaymentReceivedChoice(yes) {
    const box = miscPaymentBox();
    if (miscInvoicePage && box) box.checked = !!yes;
    if (els.paymentReceivedYes) els.paymentReceivedYes.checked = !!yes;
    if (els.paymentReceivedNo) els.paymentReceivedNo.checked = !yes;
  }

  function isPaymentActive() {
    if (miscInvoicePage) return isPaymentReceivedYes();
    if (!isMiscKind()) return true;
    return isTallyChecked() && isPaymentReceivedYes();
  }

  let lastSaleRecord = null;

  function sourcePaymentReceived() {
    return isPaymentReceivedYes();
  }

  function pushPaymentReceived(paid) {
    const billNo = (els.billNo?.value || els.tallyBillNo?.value || "").trim();
    if (!billNo || !window.OIE_PAYMENT_RECEIVED_URL) return Promise.resolve();
    return fetch(window.OIE_PAYMENT_RECEIVED_URL, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": window.OIE_CSRF || "",
      },
      body: JSON.stringify({ bill_no: billNo, payment_received: !!paid }),
    }).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok || !data.ok) throw new Error(data.error || "Unable to update Payment Received.");
        return data;
      });
    });
  }

  let approveInFlight = false;
  let autoApproveFor = 0;

  function saleStatusText(record) {
    if (!record) return "";
    const approved = record.bill_approved ? "Approved" : "Approve pending";
    const paid = sourcePaymentReceived() ? "Yes" : "No";
    const no = record.invoice_no ? record.invoice_no + " — " : "";
    let text = "Sale invoice " + no + approved + " · Payment Received: " + paid;
    const amount = Number(record.invoice_value);
    if (Number.isFinite(amount)) {
      text +=
        " · Total Invoice Amount: ₹" +
        amount.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    return text;
  }

  function paintInvoiceStatus(record) {
    const box = els.invoiceStatus;
    if (!box) return;
    box.classList.remove("oie-pay-no", "oie-pay-yes");
    if (!record) {
      box.textContent = "";
      box.classList.add("d-none");
      return;
    }
    box.textContent = saleStatusText(record);
    box.classList.remove("d-none");
    if (sourcePaymentReceived()) box.classList.add("oie-pay-yes");
    else box.classList.add("oie-pay-no");
  }

  function saleIsApproved() {
    return !!(lastSaleRecord && lastSaleRecord.bill_approved);
  }

  let entryFieldsLocked = false;

  function approvedEditMessage() {
    const paid = isPaymentReceivedYes() || !!(lastSaleRecord && lastSaleRecord.payment_received);
    if (paid) {
      return "Payment aa chuki hai aur admin ne approve kar diya hai. Isko edit ya delete karne ke liye pehle admin se unapprove karwao.";
    }
    return "Admin ne approve kar diya hai. Isko edit ya delete karne ke liye pehle admin se unapprove karwao.";
  }

  async function ensureEntryChangeAllowed() {
    await refreshInvoiceStatus();
    if (!saleIsApproved()) return true;
    const message = approvedEditMessage();
    if (window.JTCSDialog?.alert) await window.JTCSDialog.alert(message, "warning");
    else alert(message);
    return false;
  }

  function syncEntryActionButtons() {
    const existing = isEditMode();
    const editBtn = document.getElementById("oieEditBtn");
    const deleteBtn = document.getElementById("oieDeleteBtn");
    if (editBtn) editBtn.classList.toggle("d-none", !existing);
    if (deleteBtn) deleteBtn.classList.toggle("d-none", !existing);
  }

  function setEntryFieldsLocked(locked) {
    entryFieldsLocked = !!locked;
    if (!form) return;
    form.querySelectorAll("input, select, textarea, button").forEach(function (el) {
      if (el.id === "oieEditBtn" || el.id === "oieDeleteBtn" || el.id === "oieBillNoCopy") return;
      if (el.getAttribute("data-bs-dismiss") === "modal") return;
      if (el.type === "hidden") return;
      el.disabled = !!locked;
    });
    if (els.tallyBillNo) els.tallyBillNo.disabled = true;
    const billCopyBtn = document.getElementById("oieBillNoCopy");
    if (billCopyBtn) billCopyBtn.disabled = false;
    if (els.paymentFieldset) els.paymentFieldset.disabled = !!locked;
    if (miscInvoicePage) {
      ["oieBillingSame", "oieBillingOther", "oieBillingSearch"].forEach(function (id) {
        const el = document.getElementById(id);
        if (el) el.disabled = false;
      });
      document.querySelectorAll("#oieInvoiceActions button").forEach(function (btn) {
        btn.disabled = false;
      });
    }
    const saveBtn = document.getElementById("oieSaveBtn");
    if (saveBtn) saveBtn.disabled = !!locked;
    if (!locked) syncMiscWorkflow();
    syncEntryActionButtons();
  }

  function hasCreditPayment() {
    const lines = els.paymentLines?.querySelectorAll(".oie-payment-line") || [];
    for (let i = 0; i < lines.length; i++) {
      const select = lines[i].querySelector("select");
      const text =
        (select && select.selectedOptions && select.selectedOptions[0] && select.selectedOptions[0].textContent) ||
        "";
      if (/credit/i.test(text)) return true;
    }
    return false;
  }

  function syncGenerateBillPrompt(_lookupDone) {
    const approved = saleIsApproved();
    [els.paymentReceivedYes, els.paymentReceivedNo].forEach(
      function (input) {
        if (input) input.disabled = approved || entryFieldsLocked;
      }
    );
    if (!isPaymentReceivedYes()) autoApproveFor = 0;
    const fieldsPaymentOn = isPaymentActive();
    const creditOpen = approved && hasCreditPayment() && !entryFieldsLocked;
    const fieldsOn = !entryFieldsLocked && (creditOpen || (!approved && fieldsPaymentOn));
    if (creditOpen) els.paymentSection?.classList.remove("d-none");
    if (els.paymentFieldset) els.paymentFieldset.disabled = !fieldsOn;
    els.paymentSection?.classList.toggle("oie-payment-section-locked", !fieldsOn && !creditOpen);
  }

  async function refreshInvoiceStatus() {
    const box = els.invoiceStatus;
    if (!box) return;
    const billNo = (els.tallyBillNo?.value || els.billNo?.value || "").trim();
    if (!isTallyChecked() || !billNo || !window.OIE_INVOICE_STATUS_URL) {
      lastSaleRecord = null;
      paintInvoiceStatus(null);
      syncGenerateBillPrompt(true);
      return;
    }
    try {
      const url = new URL(window.OIE_INVOICE_STATUS_URL, window.location.origin);
      url.searchParams.set("bill_no", billNo);
      const res = await fetch(url.toString(), { credentials: "same-origin" });
      const data = await res.json();
      if (!data.ok || !data.found || !data.record) {
        lastSaleRecord = null;
        paintInvoiceStatus(null);
        syncGenerateBillPrompt(true);
        return;
      }
      lastSaleRecord = data.record;
      paintInvoiceStatus(data.record);
      syncGenerateBillPrompt(true);
    } catch (_err) {
      paintInvoiceStatus(null);
      syncGenerateBillPrompt(true);
    }
  }

  function resetGenerateBillChoice() {
    if (els.generateBillYes) els.generateBillYes.checked = false;
    if (els.generateBillNo) els.generateBillNo.checked = true;
    syncCustomerBillSummary();
  }

  function keepGenerateBillYes() {
    if (els.generateBillYes) els.generateBillYes.checked = true;
    if (els.generateBillNo) els.generateBillNo.checked = false;
    syncCustomerBillSummary();
  }

  function formatInrAmount(value) {
    const amount = Number(value);
    const safe = Number.isFinite(amount) ? amount : 0;
    return "₹" + safe.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  let billSummarySeq = 0;

  function syncCustomerBillSummary() {
    const box = document.getElementById("oieCustomerBillSummary");
    if (!box) return;
    const show = isMiscKind() && !!(els.generateBillYes && els.generateBillYes.checked);
    box.classList.toggle("d-none", !show);
    if (!show) {
      box.innerHTML = "";
      return;
    }
    const customerId = (els.customerId?.value || "").trim();
    if (!customerId || !window.OIE_CUSTOMER_BILL_SUMMARY_URL) {
      box.innerHTML = '<div class="small text-muted">Select a customer to see previous bills.</div>';
      return;
    }
    const seq = ++billSummarySeq;
    box.innerHTML = '<div class="small text-muted">Loading previous bills…</div>';
    const url = new URL(window.OIE_CUSTOMER_BILL_SUMMARY_URL, window.location.origin);
    url.searchParams.set("customer_id", customerId);
    fetch(url.toString(), { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (seq !== billSummarySeq) return;
        if (!data.ok) throw new Error(data.error || "Unable to load previous bills.");
        const overdue = Number(data.overdue_amount) || 0;
        box.innerHTML =
          '<div><span class="text-muted">Cumulative Invoice Total</span><br><strong>' +
          formatInrAmount(data.invoice_total) +
          "</strong></div>" +
          '<div class="mt-1"><span class="text-muted">Payment Received Total</span><br><strong>' +
          formatInrAmount(data.payment_received_total) +
          "</strong></div>" +
          '<div class="mt-1"><span class="text-muted">Overdue Amount</span><br><strong class="' +
          (overdue > 0 ? "is-overdue" : "") +
          '">' +
          formatInrAmount(overdue) +
          "</strong></div>";
      })
      .catch(function () {
        if (seq !== billSummarySeq) return;
        box.innerHTML = '<div class="small text-danger">Unable to load previous bills.</div>';
      });
  }

  function copyBillNumber(button) {
    const value = (els.tallyBillNo?.value || "").trim();
    if (!value) return;
    const done = function () {
      const icon = button && button.querySelector("i");
      if (!icon) return;
      icon.className = "bi bi-check2";
      window.setTimeout(function () {
        icon.className = "bi bi-copy";
      }, 1200);
    };
    const fallback = function () {
      const area = document.createElement("textarea");
      area.value = value;
      document.body.appendChild(area);
      area.select();
      try { document.execCommand("copy"); } catch (_err) { /* ignore */ }
      area.remove();
      done();
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(value).then(done).catch(fallback);
      return;
    }
    fallback();
  }

  async function lookupGeneratedInvoice(billNo) {
    if (!billNo || !window.OIE_INVOICE_STATUS_URL) return null;
    const url = new URL(window.OIE_INVOICE_STATUS_URL, window.location.origin);
    url.searchParams.set("bill_no", billNo);
    const res = await fetch(url.toString(), { credentials: "same-origin" });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!data.ok || !data.found || !data.record) return null;
    return data.record;
  }

  async function declineGeneratedBill() {
    const billNo = (els.tallyBillNo?.value || els.billNo?.value || "").trim();
    const record = await lookupGeneratedInvoice(billNo);
    if (!record) return;
    keepGenerateBillYes();
    const sure = window.JTCSDialog?.confirm
      ? await window.JTCSDialog.confirm(
          "All payment received bills and invoices related to this bill will be deleted. Are you sure?",
          { title: "Delete related bills", okLabel: "Yes", cancelLabel: "No", type: "warning" }
        )
      : window.confirm(
          "All payment received bills and invoices related to this bill will be deleted. Are you sure?"
        );
    if (!sure) return;
    let creds = null;
    if (window.JTCSDeleteConfirm?.ask) {
      creds = await window.JTCSDeleteConfirm.ask({
        message: "Enter your User ID and password to delete the invoices related to this bill.",
        title: "Confirm",
        confirmLabel: "Confirm",
        confirmIcon: "bi-shield-lock",
        variant: "warning",
      });
    }
    if (!creds || !creds.user_id || !creds.password) return;
    const permanent = window.JTCSDialog?.confirm
      ? await window.JTCSDialog.confirm(
          "This will permanently delete all invoices related to this bill.",
          { title: "Permanently delete", okLabel: "Yes", cancelLabel: "No", type: "danger" }
        )
      : window.confirm("This will permanently delete all invoices related to this bill.");
    if (!permanent) return;
    const res = await fetch(window.OIE_INVOICE_DELETE_URL, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": window.OIE_CSRF || csrfToken(),
      },
      body: JSON.stringify({
        bill_no: billNo,
        user_id: creds.user_id,
        password: creds.password,
      }),
    });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok || !data.ok) {
      const message = data.error || "Unable to delete the related invoices.";
      if (window.JTCSDialog?.alert) window.JTCSDialog.alert(message, "error");
      else alert(message);
      return;
    }
    resetGenerateBillChoice();
    lastSaleRecord = null;
    paintInvoiceStatus(null);
    syncGenerateBillPrompt(true);
    if (window.JTCSDialog?.alert) {
      window.JTCSDialog.alert(data.message || "Related invoices deleted.", "success");
    }
  }

  function categoryLineData(line) {
    if (!line) {
      return {
        item: "",
        item_id: "",
        gst_rate_percent: "18",
        hsn_sac: "",
        unit: "NOS",
        rate: "",
      };
    }
    const sub = line.querySelector(".oie-category-subwork");
    const amount = line.querySelector(".oie-category-amount");
    const opt = sub && sub.selectedIndex >= 0 ? sub.options[sub.selectedIndex] : null;
    return {
      item: opt && opt.value ? (opt.textContent || "").trim() : "",
      item_id: opt ? opt.getAttribute("data-item-id") || "" : "",
      gst_rate_percent: opt ? opt.getAttribute("data-gst-rate") || "18" : "18",
      hsn_sac: opt ? opt.getAttribute("data-hsn") || "" : "",
      unit: opt ? opt.getAttribute("data-unit") || "NOS" : "NOS",
      rate: amount && amount.value !== "" ? amount.value : "",
    };
  }

  function firstCategoryLineData() {
    return categoryLineData(els.categoryLines?.querySelector(".oie-category-line"));
  }

  function collectCategoryLinesForBill() {
    const lines = [];
    els.categoryLines?.querySelectorAll(".oie-category-line").forEach(function (line) {
      const data = categoryLineData(line);
      if (data.item) lines.push(data);
    });
    return lines;
  }

  function taxYearFromDate(iso) {
    const parts = String(iso || "").trim().split("-");
    const year = parseInt(parts[0], 10);
    const month = parseInt(parts[1], 10);
    if (!year || !month) return "";
    const start = month >= 4 ? year : year - 1;
    return start + "-" + String(start + 1).slice(-2);
  }

  function collectGenerateBillSeed() {
    const billNo = (els.billNo?.value || "").trim();
    const seed = {
      date: (els.workDate?.value || "").trim(),
      tax_year: taxYearFromDate(els.workDate?.value),
      invoice_no: billNo,
      bill_no: billNo,
      tally_bill_no: (els.tallyBillNo?.value || billNo).trim(),
      customer_id: (els.customerId?.value || "").trim(),
      customer_name: (els.customerName?.value || "").trim(),
      mobile: (els.mobileNumber?.value || "").trim(),
      item: "",
      sub_work: "",
      item_id: "",
      gst_rate_percent: "",
      hsn_sac: "",
      unit: "NOS",
      rate: "",
      lines: [],
      state_code: (window.OIE_COMPANY_STATE_CODE || "05").trim(),
      source: "Miscellaneous",
      payment_received: isPaymentReceivedYes(),
      entry_id: (els.entryId && els.entryId.value) || "",
    };
    if (lastSaleRecord && lastSaleRecord.invoice_id) {
      seed.open_edit = true;
      seed.invoice_id = lastSaleRecord.invoice_id;
    }
    return seed;
  }

  function openGenerateBillPopup(presetSeed) {
    if (!presetSeed && (!isMiscKind() || !isTallyChecked())) return;
    const seed = presetSeed || collectGenerateBillSeed();
    if (!seed.invoice_no) {
      alert("Bill Number is required before generating bill.");
      resetGenerateBillChoice();
      return;
    }
    if (!seed.customer_name) {
      alert("Please enter Customer Name before generating bill.");
      resetGenerateBillChoice();
      return;
    }
    try {
      sessionStorage.setItem("oieMiscGenerateBill", JSON.stringify(seed));
    } catch (_err) {
      /* ignore quota errors */
    }
    const url = window.OIE_GENERATE_BILL_URL || "/activities/miscellaneous/generate-bill";
    if (!url) {
      alert("Generate bill is available only for Miscellaneous.");
      resetGenerateBillChoice();
      return;
    }
    const host = window.top || window;
    if (typeof host.jtcsOpenPageWindow === "function") {
      let existing = null;
      try {
        const path = new URL(url, window.location.origin);
        const key = path.pathname.replace(/\/+$/, "") + path.search;
        existing = host.document.querySelector(
          '.jtcs-page-win[data-key="' + key.replace(/"/g, "") + '"]'
        );
      } catch (_err) {
        existing = null;
      }
      host.jtcsOpenPageWindow(url, "Generate Bill");
      if (existing) {
        const frame = existing.querySelector("iframe");
        if (frame) frame.src = url;
      }
      return;
    }
    const width = Math.round(14.4 * 96);
    const height = Math.round(9.1 * 96);
    const left = Math.max(0, Math.floor(((screen.availWidth || width) - width) / 2));
    const top = Math.max(0, Math.floor(((screen.availHeight || height) - height) / 2));
    const features = [
      "width=" + width,
      "height=" + height,
      "left=" + left,
      "top=" + top,
      "menubar=no",
      "toolbar=no",
      "location=no",
      "status=no",
      "resizable=yes",
      "scrollbars=yes",
    ].join(",");
    const win = window.open(url, "oieMiscGenerateBillWindow", features);
    if (!win) {
      alert("Pop-up blocked. Please allow pop-ups for this site, then try again.");
      resetGenerateBillChoice();
      return;
    }
    try {
      win.focus();
    } catch (_e) {
      /* ignore */
    }
  }

  const miscInvoicePage = !!document.getElementById("oieInvoiceCheck");

  function syncMiscWorkflow() {
    const misc = isMiscKind();
    els.miscWorkflowWrap?.classList.toggle("d-none", !misc);
    if (miscInvoicePage && misc) {
      if (els.tallyBillWrap) els.tallyBillWrap.classList.add("d-none");
      els.paymentSection?.classList.add("d-none");
      if (els.paymentFieldset) els.paymentFieldset.disabled = true;
      els.paymentSection?.classList.remove("oie-payment-section-locked");
      if (els.paymentLockedHint) els.paymentLockedHint.classList.add("d-none");
      if (els.remarksSectionNum) els.remarksSectionNum.textContent = "4";
      syncMiscBillingPanel();
      return;
    }
    if (!misc) {
      if (els.workDone) els.workDone.checked = false;
      if (els.tallyBill) {
        els.tallyBill.checked = false;
        els.tallyBill.disabled = true;
      }
      resetGenerateBillChoice();
    } else if (els.tallyBill) {
      const workDone = isWorkDoneChecked();
      els.tallyBill.disabled = !workDone;
      if (!workDone) {
        els.tallyBill.checked = false;
        resetGenerateBillChoice();
      }
    }
    const showBill = isMiscKind() && (isWorkDoneChecked() || isTallyChecked());
    els.tallyBillWrap?.classList.toggle("d-none", !showBill);
    if (!showBill) {
      resetGenerateBillChoice();
      setPaymentReceivedChoice(false);
    }
    if (showBill && els.tallyBillNo && !(els.tallyBillNo.value || "").trim() && els.billNo) {
      els.tallyBillNo.value = (els.billNo.value || "").trim();
    }
    if (els.tallyBillNo) els.tallyBillNo.disabled = true;
    refreshInvoiceStatus();
    const paymentOn = isPaymentActive();
    els.paymentSection?.classList.toggle("d-none", isMiscKind() && !paymentOn);
    if (els.paymentFieldset) els.paymentFieldset.disabled = !paymentOn;
    els.paymentSection?.classList.toggle("oie-payment-section-locked", !paymentOn);
    els.paymentLockedHint?.classList.toggle("d-none", paymentOn);
    if (els.paymentSectionNum) els.paymentSectionNum.textContent = misc ? "4" : "3";
    if (els.remarksSectionNum) els.remarksSectionNum.textContent = misc ? "5" : "4";
    if (paymentOn) {
      ensurePaymentLines();
      const lines = els.paymentLines?.querySelectorAll(".oie-payment-line") || [];
      if (lines.length === 1 && getPaymentTotal() <= 0) {
        syncFirstPaymentFromCategories();
      }
    }
    syncGenerateBillPrompt();
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
    if (kind === "Expense") return "Category Master (Expense)";
    if (kind === "Misc.") return "Category Master (Misc.)";
    return "Category Master (Income)";
  }

  function categorySelectLabelText(kind) {
    if (kind === "Expense") return "Category *";
    if (kind === "Misc.") return "Category *";
    return "Category *";
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
    optEmpty.textContent = "-- Select Category --";
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
    if (!amountInput || lines[0].dataset.paymentCleared === "1") {
      updatePaymentSummary();
      return;
    }
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
          if (row.item_id) opt.setAttribute("data-item-id", String(row.item_id));
          if (row.gst_rate_percent != null) {
            opt.setAttribute("data-gst-rate", String(row.gst_rate_percent));
          }
          if (row.hsn_sac) opt.setAttribute("data-hsn", String(row.hsn_sac));
          if (row.unit) opt.setAttribute("data-unit", String(row.unit));
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
      const lineKey =
        kind === "Misc."
          ? select.value + ":" + (subSelect?.value || "")
          : select.value;
      if (seen[lineKey]) return "Duplicate categories are not allowed.";
      seen[lineKey] = true;
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

  function isQrBillReceivedAccount(item) {
    const flag = item && item.qr_bill_received;
    return flag === true || flag === 1 || flag === "1";
  }

  function paymentReceivedAccounts() {
    return (window.OIE_BANK_ACCOUNTS || []).filter(isQrBillReceivedAccount);
  }

  function buildPaymentSelect(selectedValue) {
    const select = document.createElement("select");
    select.className = "form-select oie-payment-bank";
    select.required = true;
    const accounts = paymentReceivedAccounts();
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = "-- Select --";
    select.appendChild(blank);
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
      const current = (window.OIE_BANK_ACCOUNTS || []).find(function (item) {
        return paymentModeValue(item) === String(selectedValue);
      });
      const opt = document.createElement("option");
      opt.value = String(selectedValue);
      opt.textContent = current ? paymentModeLabel(current) : "Current account";
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
    if (!preferredValue) {
      select.value = "";
      return;
    }
    const cashOption = Array.from(select.options).find(function (opt) {
      return opt.value && opt.textContent.trim() === "Cash";
    });
    if (cashOption) {
      select.value = cashOption.value;
      return;
    }
    select.value = "";
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

  function clearPaymentLine(line) {
    const select = line.querySelector("select");
    const amount = line.querySelector(".oie-payment-amount");
    const date = line.querySelector(".oie-payment-date");
    line.dataset.paymentCleared = "1";
    if (select) {
      select.value = "";
      select.required = false;
    }
    if (amount) {
      amount.value = "";
      amount.required = false;
    }
    if (date) {
      date.value = defaultPaymentDate();
      date.required = false;
      delete date.dataset.userEdited;
    }
    if (lastSaleRecord) paintInvoiceStatus(lastSaleRecord);
  }

  function updatePaymentRemoveButtons() {
    const lines = els.paymentLines?.querySelectorAll(".oie-payment-line") || [];
    lines.forEach(function (line) {
      const btn = line.querySelector(".oie-payment-remove");
      if (btn) btn.disabled = false;
    });
  }

  function syncFirstPaymentAmount() {
    updatePaymentSummary();
  }

  function remainingPaymentAmount() {
    const rem = Math.round((getCategoryTotal() - getPaymentTotal()) * 100) / 100;
    return rem > 0 ? rem : 0;
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
    select.name = "PaymentBankAccountID[]";
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
    dateInput.name = "PaymentDate[]";
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
    amount.name = "PaymentAmount[]";
    amount.value = options.amount != null && options.amount !== "" ? options.amount : "0";
    amount.addEventListener("input", function () {
      if (String(amount.value || "").trim() !== "") line.dataset.paymentCleared = "";
      updatePaymentSummary();
      if (lastSaleRecord) paintInvoiceStatus(lastSaleRecord);
    });
    select.addEventListener("change", function () {
      if (select.value) line.dataset.paymentCleared = "";
    });
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
      const lines = els.paymentLines?.querySelectorAll(".oie-payment-line") || [];
      if (lines.length <= 1) {
        clearPaymentLine(line);
        updatePaymentSummary();
        return;
      }
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
    const lines = els.paymentLines?.querySelectorAll(".oie-payment-line") || [];
    const paymentTotal = getPaymentTotal();
    const extraLines = lines.length > 1;
    const mustValidate = !isMiscKind() || paymentTotal > 0 || extraLines;
    if (!mustValidate) return null;
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
    if (els.paymentFieldset) els.paymentFieldset.disabled = false;
    const lines = els.paymentLines.querySelectorAll(".oie-payment-line");
    lines.forEach(function (line, index) {
      const bank = line.querySelector(".oie-payment-bank");
      const amount = line.querySelector(".oie-payment-amount");
      const paymentDate = line.querySelector(".oie-payment-date");
      if (!bank || !amount) return;

      bank.disabled = false;
      amount.disabled = false;
      if (paymentDate) paymentDate.disabled = false;
      bank.removeAttribute("name");
      amount.removeAttribute("name");
      if (paymentDate) paymentDate.removeAttribute("name");

      const wrap = document.createElement("div");
      wrap.className = "oie-payment-sync d-none";
      wrap.setAttribute("aria-hidden", "true");

      const bankHidden = document.createElement("input");
      bankHidden.type = "hidden";
      bankHidden.name = "PaymentBankAccountID[]";
      bankHidden.value = bank.value || "";
      bankHidden.className = "oie-payment-sync";

      const amountHidden = document.createElement("input");
      amountHidden.type = "hidden";
      amountHidden.name = "PaymentAmount[]";
      amountHidden.value = amount.value || "0";
      amountHidden.className = "oie-payment-sync";

      const dateHidden = document.createElement("input");
      dateHidden.type = "hidden";
      dateHidden.name = "PaymentDate[]";
      dateHidden.value = paymentDate?.value || defaultPaymentDate();
      dateHidden.className = "oie-payment-sync";

      const indexHidden = document.createElement("input");
      indexHidden.type = "hidden";
      indexHidden.name = "PaymentLineIndex[]";
      indexHidden.value = String(index);
      indexHidden.className = "oie-payment-sync";

      wrap.appendChild(bankHidden);
      wrap.appendChild(amountHidden);
      wrap.appendChild(dateHidden);
      wrap.appendChild(indexHidden);
      form.appendChild(wrap);
    });
    if (isPaymentReceivedYes() || getPaymentTotal() > 0) {
      const flag = document.createElement("input");
      flag.type = "hidden";
      flag.name = "PaymentReceived";
      flag.value = "1";
      flag.className = "oie-payment-sync";
      form.appendChild(flag);
    }
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
    syncCustomerBillSummary();
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
    if (miscInvoicePage) {
      paintMiscInvoice(null);
      clearMiscBilling();
      hideMiscInvoiceEditor();
    }
    resetCategoryLines([{}]);
    resetPaymentLines([{}]);
    return fetchNextBillNo();
  }

  function openNewEntry() {
    resetForm().then(function () {
      ensureCategoryLines();
      ensurePaymentLines();
      setEntryFieldsLocked(false);
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

  function miscInvoiceCell(row) {
    const invoice = row.sale_invoice;
    if (!invoice || !invoice.invoice_id || !window.JtcsInvoiceActions) {
      return "<td>—</td>";
    }
    return '<td data-misc-entry-id="' + escapeHtml(row.entry_id) + '">' + window.JtcsInvoiceActions.summaryHtml(invoice) + "</td>";
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
          (window.OIE_FORCE_LEDGER_KIND === "Misc."
            ? '<td class="d-none"></td>'
            : "<td>" +
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
              "</td>") +
          "<td>" +
          escapeHtml(formatDisplayDate(row.work_date)) +
          "</td>" +
          '<td class="oie-category-cell" title="' +
          escapeHtml(category) +
          '">' +
          escapeHtml(category) +
          (window.OIE_FORCE_LEDGER_KIND === "Misc."
            ? (row.work_done
                ? ' <span class="badge text-bg-success oie-wf-badge">Work Done</span>'
                : "") +
              (row.sale_invoice && row.sale_invoice.invoice_id
                ? ' <span class="badge text-bg-primary oie-wf-badge">Invoice</span>'
                : "")
            : "") +
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
          (window.OIE_FORCE_LEDGER_KIND === "Misc." ? miscInvoiceCell(row) : "") +
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
    if (els.gridFilterKind) {
      els.gridFilterKind.value = window.OIE_FORCE_LEDGER_KIND
        ? String(window.OIE_FORCE_LEDGER_KIND)
        : "";
    }
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
        let rows = data.rows || [];
        if (window.OIE_HIDE_MISC && !window.OIE_FORCE_LEDGER_KIND) {
          rows = rows.filter(function (row) {
            return row.ledger_kind !== "Misc.";
          });
        }
        allGridRows = rows;
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
          els.workDone.checked = miscInvoicePage
            ? !!record.work_done
            : !!record.work_done || (record.ledger_kind === "Misc." && hasPayments);
        }
        if (els.tallyBill) {
          els.tallyBill.checked = miscInvoicePage
            ? !!record.tally_bill_generated
            : !!record.tally_bill_generated || (record.ledger_kind === "Misc." && hasPayments);
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
        if (miscInvoicePage) paintMiscInvoice(record.linked_invoice || null);
        if (els.customerId) els.customerId.value = record.customer_id ? String(record.customer_id) : "";
        if (els.customerSelected && record.customer_id) {
          els.customerSelected.textContent = "Customer selected from master";
          els.customerSelected.classList.remove("d-none");
        }
        setPaymentReceivedChoice(
          miscInvoicePage
            ? !!(record.linked_invoice && record.linked_invoice.invoice_id) &&
                (hasPayments || !!record.payment_received)
            : hasPayments || !!record.payment_received
        );
        resetPaymentLines(record.payments && record.payments.length ? record.payments : [{}]);
        syncMiscWorkflow();
        setEntryFieldsLocked(true);
        if (entryModal) entryModal.show();
      });
  }

  async function gridDeleteAllowed(row) {
    const billNo = ((row && (row.tally_bill_no || row.bill_no)) || "").trim();
    const maybeBilled = !!(row && (row.tally_bill_generated || row.sale_invoice));
    if (!maybeBilled || !billNo || !window.OIE_INVOICE_STATUS_URL) return true;
    try {
      const url = new URL(window.OIE_INVOICE_STATUS_URL, window.location.origin);
      url.searchParams.set("bill_no", billNo);
      const res = await fetch(url.toString(), { credentials: "same-origin" });
      const data = await res.json();
      if (!data.ok || !data.found || !data.record || !data.record.bill_approved) return true;
      const paid = !!(row && row.payment_received) || !!(data.record && data.record.payment_received);
      const message = paid
        ? "Payment aa chuki hai aur admin ne approve kar diya hai. Isko edit ya delete karne ke liye pehle admin se unapprove karwao."
        : "Admin ne approve kar diya hai. Isko edit ya delete karne ke liye pehle admin se unapprove karwao.";
      if (window.JTCSDialog?.alert) await window.JTCSDialog.alert(message, "warning");
      else alert(message);
      return false;
    } catch (_err) {
      return true;
    }
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
          entryModal?.hide();
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
    if (!(els.customerName?.value || "").trim()) {
      return "Customer name is required when Tally Bill Generated is checked.";
    }
    return null;
  }

  function saveEntry() {
    if (entryFieldsLocked) return Promise.resolve();
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
    const tallyNoDisabled = !!(els.tallyBillNo && els.tallyBillNo.disabled);
    if (tallyNoDisabled) els.tallyBillNo.disabled = false;
    const body = new FormData(form);
    if (tallyNoDisabled) els.tallyBillNo.disabled = true;
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
        if (data && data.entry_id && els.entryId) {
          els.entryId.value = String(data.entry_id);
          editingEntryId = parseInt(data.entry_id, 10) || editingEntryId;
        }
        if (miscInvoicePage && miscCreatingInvoice) {
          return loadGrid().then(function () { return data; });
        }
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
    if (entryFieldsLocked) return;
    ensureBillNoThenSave();
  });

  document.getElementById("oieEditBtn")?.addEventListener("click", function () {
    ensureEntryChangeAllowed().then(function (allowed) {
      if (!allowed) return;
      setEntryFieldsLocked(false);
    });
  });

  document.getElementById("oieDeleteBtn")?.addEventListener("click", function () {
    if (!editingEntryId) return;
    ensureEntryChangeAllowed().then(function (allowed) {
      if (!allowed) return;
      deleteEntry(editingEntryId);
    });
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
      const rem = remainingPaymentAmount();
      addPaymentLine({ amount: rem > 0 ? rem.toFixed(2) : "" });
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

  const MANUAL_INVOICE_MESSAGE =
    "Invoice cannot be selected manually. Please click 'Create Invoice' to generate the invoice first.";
  let miscLinkedInvoice = null;
  let miscCreatingInvoice = false;
  let miscInvoiceEditorOpen = false;
  let miscAllowModalHide = false;
  let miscPayToken = 0;

  function miscMoney(value) {
    const amount = Number(value || 0);
    return "₹" + amount.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function miscFormatDate(iso) {
    const text = String(iso || "").slice(0, 10);
    const parts = text.split("-");
    if (parts.length !== 3) return text || "—";
    return parts[2] + "/" + parts[1] + "/" + parts[0];
  }

  function clearMiscBilling() {
    const same = document.getElementById("oieBillingSame");
    const other = document.getElementById("oieBillingOther");
    const id = document.getElementById("oieBillingCustomerId");
    const search = document.getElementById("oieBillingSearch");
    const results = document.getElementById("oieBillingResults");
    if (same) same.checked = false;
    if (other) other.checked = false;
    if (id) id.value = "";
    if (search) search.value = "";
    results?.classList.add("d-none");
  }

  function miscBillingChoice() {
    if (document.getElementById("oieBillingSame")?.checked) return "SAME_CUSTOMER";
    if (document.getElementById("oieBillingOther")?.checked) return "OTHER_CUSTOMER";
    return "";
  }

  function syncMiscBillingPanel() {
    const wrap = document.getElementById("oieBillingWrap");
    const pick = document.getElementById("oieBillingPick");
    if (!wrap) return;
    const show = miscCreatingInvoice || !!(document.getElementById("oieInvoiceCheck")?.checked);
    wrap.classList.toggle("d-none", !show);
    pick?.classList.toggle("d-none", !(show && miscBillingChoice() === "OTHER_CUSTOMER"));
  }

  function paintMiscPayment(adjustment) {
    const body = document.getElementById("oiePaymentAdjustBody");
    if (!body) return;
    if (!adjustment) {
      body.innerHTML = '<div class="oie-pay-status">Payment Not Received</div>';
      return;
    }
    const entries = adjustment.entries || [];
    let html = "";
    if (!entries.length) {
      html += '<div class="oie-pay-status">Payment Not Received</div>';
    } else if (entries.length === 1) {
      const entry = entries[0];
      html += '<div><span class="oie-pay-label">Money In/Out Amount Adjusted</span> <strong>' + miscMoney(entry.money_inout_transaction_amount) + "</strong></div>";
      html += '<div><span class="oie-pay-label">Amount Adjusted to This Invoice</span> <strong>' + miscMoney(entry.allocated_amount) + "</strong></div>";
      html += '<div><span class="oie-pay-label">Remaining Amount from This Money In/Out Entry</span> <strong>' + miscMoney(entry.remaining_money_inout_amount) + "</strong></div>";
    } else {
      html += "<details class=\"oie-pay-details\"><summary>" + entries.length + " Money In/Out entries</summary>";
      entries.forEach(function (entry) {
        html += '<div class="oie-pay-entry">';
        html += "<div><strong>" + escapeHtml(miscFormatDate(entry.work_date)) + "</strong></div>";
        html += "<div>Money In/Out Amount Adjusted <strong>" + miscMoney(entry.money_inout_transaction_amount) + "</strong></div>";
        html += "<div>Amount Adjusted to This Invoice <strong>" + miscMoney(entry.allocated_amount) + "</strong></div>";
        html += "<div>Remaining Amount from This Money In/Out Entry <strong>" + miscMoney(entry.remaining_money_inout_amount) + "</strong></div>";
        html += "</div>";
      });
      html += "</details>";
    }
    html += "<div>Customer Total Sale Amount <strong>" + miscMoney(adjustment.customer_total_sale) + "</strong></div>";
    html += "<div>Customer Total Received Amount <strong>" + miscMoney(adjustment.customer_total_received) + "</strong></div>";
    html += "<div>Customer Outstanding Amount <strong>" + miscMoney(adjustment.customer_outstanding) + "</strong></div>";
    body.innerHTML = html;
  }

  function loadMiscPayment(invoiceId) {
    const body = document.getElementById("oiePaymentAdjustBody");
    const id = parseInt(invoiceId, 10);
    if (!id) {
      paintMiscPayment(null);
      return;
    }
    const token = ++miscPayToken;
    if (body) body.innerHTML = "";
    fetch("/accounting/api/invoices/" + id + "/payment-adjustment", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (token !== miscPayToken) return;
        paintMiscPayment(data && data.ok ? data.adjustment : null);
      })
      .catch(function () {
        if (token !== miscPayToken) return;
        paintMiscPayment(null);
      });
  }

  function paintMiscInvoice(invoice) {
    miscLinkedInvoice = invoice && invoice.invoice_id ? invoice : null;
    const box = document.getElementById("oieInvoiceSummary");
    const check = document.getElementById("oieInvoiceCheck");
    const createBtn = document.getElementById("oieCreateInvoiceBtn");
    document.querySelectorAll("#oieInvoiceActions .oie-inv-act").forEach(function (btn) {
      btn.classList.toggle("d-none", !miscLinkedInvoice);
    });
    if (createBtn) createBtn.classList.toggle("d-none", !!miscLinkedInvoice);
    if (check) check.checked = !!miscLinkedInvoice;
    if (!box) return;
    if (!miscLinkedInvoice) {
      box.classList.add("d-none");
      paintMiscPayment(null);
      syncMiscBillingPanel();
      syncMiscWorkflow();
      return;
    }
    box.classList.remove("d-none");
    const no = document.getElementById("oieInvoiceNo");
    const dt = document.getElementById("oieInvoiceDate");
    const amt = document.getElementById("oieInvoiceAmount");
    if (no) no.textContent = miscLinkedInvoice.invoice_no || "—";
    if (dt) dt.textContent = miscFormatDate(miscLinkedInvoice.invoice_date);
    if (amt) amt.textContent = miscMoney(miscLinkedInvoice.invoice_value);
    const followupCustomer = parseInt(els.customerId?.value || "0", 10) || 0;
    const invoiceCustomer = parseInt(miscLinkedInvoice.customer_id || "0", 10) || 0;
    if (invoiceCustomer && followupCustomer && invoiceCustomer !== followupCustomer) {
      const other = document.getElementById("oieBillingOther");
      if (other) other.checked = true;
      const id = document.getElementById("oieBillingCustomerId");
      const search = document.getElementById("oieBillingSearch");
      if (id) id.value = String(invoiceCustomer);
      if (search) search.value = miscLinkedInvoice.customer_name || "";
    } else if (followupCustomer) {
      const same = document.getElementById("oieBillingSame");
      if (same) same.checked = true;
    }
    syncMiscBillingPanel();
    loadMiscPayment(miscLinkedInvoice.invoice_id);
    syncMiscWorkflow();
  }

  function miscInvoiceFrame() {
    return document.getElementById("oieInvoiceEditorFrame");
  }

  function miscInvoiceShell() {
    return document.querySelector("#oieEntryModal .oie-entry-modal");
  }

  function hideMiscInvoiceEditor() {
    miscInvoiceShell()?.classList.remove("is-invoice-edit");
    const frame = miscInvoiceFrame();
    if (frame) frame.src = "about:blank";
    miscInvoiceEditorOpen = false;
  }

  function showMiscInvoiceEditor() {
    const invoiceId = miscLinkedInvoice ? parseInt(miscLinkedInvoice.invoice_id, 10) : 0;
    if (!invoiceId) {
      alert("Unable to edit invoice: Invoice ID is missing or invalid.");
      return;
    }
    const frame = miscInvoiceFrame();
    const shell = miscInvoiceShell();
    if (!frame || !shell) return;
    const params = new URLSearchParams();
    params.set("edit", String(invoiceId));
    params.set("fu_embed", "1");
    params.set("misc_entry_id", (els.entryId?.value || "").trim());
    appendMiscInclusiveParams(params);
    const customerId = (els.customerId?.value || "").trim();
    if (customerId) params.set("contact_customer_id", customerId);
    appendMiscReceiptOrigin(params);
    const choice = miscBillingChoice();
    if (choice === "SAME_CUSTOMER" || choice === "OTHER_CUSTOMER") {
      const billCustomerId = selectedMiscBillingId();
      if (!billCustomerId) {
        alert(choice === "OTHER_CUSTOMER"
          ? "Please select the Billing Customer."
          : "Please select a customer first.");
        return;
      }
      params.set("misc_bill_customer_id", billCustomerId);
    }
    frame.src = "/accounting/invoice/sale?" + params.toString();
    shell.classList.add("is-invoice-edit");
    miscInvoiceEditorOpen = true;
  }

  function miscInvoiceDirty() {
    const frame = miscInvoiceFrame();
    try {
      return !!(frame && frame.contentWindow && frame.contentWindow.jtcsInvoiceIsDirty && frame.contentWindow.jtcsInvoiceIsDirty());
    } catch (_err) {
      return false;
    }
  }

  function confirmMiscUnsaved() {
    const message = "You have unsaved changes in this invoice. Are you sure you want to close without saving?";
    if (window.JTCSDialog && JTCSDialog.confirm) {
      return JTCSDialog.confirm(message, { title: "Unsaved invoice", okLabel: "Discard Changes", cancelLabel: "Cancel", type: "warning" });
    }
    return Promise.resolve(window.confirm(message));
  }

  function settleMiscInvoiceEditor() {
    if (!miscInvoiceEditorOpen) return Promise.resolve(true);
    if (!miscInvoiceDirty()) {
      hideMiscInvoiceEditor();
      return Promise.resolve(true);
    }
    return confirmMiscUnsaved().then(function (discard) {
      if (!discard) return false;
      hideMiscInvoiceEditor();
      return true;
    });
  }

  function miscInclusiveSeeds() {
    if (!miscInvoicePage) return [];
    const seeds = [];
    els.categoryLines?.querySelectorAll(".oie-category-line").forEach(function (line) {
      const data = categoryLineData(line);
      const amount = parseFloat(data.rate);
      if (!(amount > 0)) return;
      seeds.push({
        item_id: data.item_id || "",
        gst_rate_percent: data.item_id ? data.gst_rate_percent || "0" : "0",
        amount: amount,
        particulars: data.item || "",
        hsn_sac: data.hsn_sac || "",
        unit: data.unit || "NOS",
      });
    });
    return seeds;
  }

  function appendMiscInclusiveParams(params) {
    const seeds = miscInclusiveSeeds();
    if (!seeds.length) return;
    params.set("misc_inclusive", "1");
    params.set("misc_lines", JSON.stringify(seeds));
  }

  function selectedMiscBillingId() {
    if (miscBillingChoice() === "OTHER_CUSTOMER") {
      return (document.getElementById("oieBillingCustomerId")?.value || "").trim();
    }
    if (miscBillingChoice() === "SAME_CUSTOMER") return (els.customerId?.value || "").trim();
    return "";
  }

  function appendMiscReceiptOrigin(params) {
    if (!window.JtcsInvoiceReceiptReturn || !params) return;
    const origin = String(window.OIE_FORCE_LEDGER_KIND || "") === "Misc." ? "MISC" : "";
    window.JtcsInvoiceReceiptReturn.appendModuleReturn(
      params,
      origin,
      window.location.pathname + window.location.search
    );
  }

  function openMiscInvoiceWindow() {
    const choice = miscBillingChoice();
    if (!choice) {
      alert("Please select Same Customer or Other Customer.");
      return false;
    }
    const customerId = selectedMiscBillingId();
    if (choice === "OTHER_CUSTOMER" && !customerId) {
      alert("Please select the Billing Customer.");
      document.getElementById("oieBillingSearch")?.focus();
      return false;
    }
    if (!customerId) {
      alert("Please select a customer first.");
      return false;
    }
    const params = new URLSearchParams();
    params.set("open_form", "1");
    params.set("customer_id", customerId);
    const contactId = (els.customerId?.value || "").trim();
    if (contactId) params.set("contact_customer_id", contactId);
    const entryId = (els.entryId?.value || "").trim();
    if (entryId) params.set("misc_entry_id", entryId);
    appendMiscInclusiveParams(params);
    appendMiscReceiptOrigin(params);
    if (choice !== "OTHER_CUSTOMER") {
      const name = (els.customerName?.value || "").trim();
      if (name) params.set("customer_name", name);
    }
    const host = window.top || window;
    if (typeof host.jtcsOpenPageWindow !== "function") {
      alert("Invoice window could not be opened in this page. Refresh and try again.");
      return false;
    }
    host.jtcsOpenPageWindow("/accounting/invoice/sale?" + params.toString(), "Sale / Service Invoice");
    return true;
  }

  function ensureMiscSaved() {
    const existing = (els.entryId?.value || "").trim();
    if (existing) return Promise.resolve(existing);
    return saveEntry().then(function () {
      return (els.entryId?.value || "").trim();
    });
  }

  function beginMiscCreateInvoice() {
    const customerId = (els.customerId?.value || "").trim();
    if (!customerId) {
      alert("Please select a customer before opening the Invoice module.");
      return;
    }
    miscCreatingInvoice = true;
    const check = document.getElementById("oieInvoiceCheck");
    if (check && !miscLinkedInvoice) check.checked = false;
    syncMiscBillingPanel();
    if (!miscBillingChoice()) {
      alert("Please select Same Customer or Other Customer.");
      return;
    }
    if (miscBillingChoice() === "OTHER_CUSTOMER" && !(document.getElementById("oieBillingCustomerId")?.value || "").trim()) {
      alert("Please select the Billing Customer.");
      document.getElementById("oieBillingSearch")?.focus();
      return;
    }
    ensureMiscSaved().then(function (entryId) {
      if (!entryId) return;
      openMiscInvoiceWindow();
    }).catch(function (err) {
      alert(err.message || "Unable to open the Invoice module.");
    });
  }

  function reassignMiscBilling(billingCustomerId) {
    const entryId = (els.entryId?.value || "").trim();
    const billingId = String(billingCustomerId || "").trim();
    if (!entryId || !billingId || !miscLinkedInvoice || !miscLinkedInvoice.invoice_id) return;
    if (String(miscLinkedInvoice.customer_id || "") === billingId) return;
    const url = apiUrl(window.OIE_BILLING_CUSTOMER_URL, entryId);
    fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": csrfToken() || window.OIE_CSRF || "",
      },
      body: JSON.stringify({ billing_customer_id: Number(billingId) }),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok && data.ok, data: data };
        });
      })
      .then(function (payload) {
        if (!payload.ok || !payload.data.invoice) {
          throw new Error((payload.data && payload.data.error) || "Unable to change the billing customer.");
        }
        const invoice = payload.data.invoice;
        paintMiscInvoice(Object.assign({}, miscLinkedInvoice, {
          customer_id: invoice.customer_id,
          customer_name: invoice.customer_name,
          contact_mobile: invoice.contact_mobile,
          invoice_no: invoice.invoice_no || miscLinkedInvoice.invoice_no,
          invoice_date: invoice.invoice_date || miscLinkedInvoice.invoice_date,
          invoice_value: invoice.invoice_value != null ? invoice.invoice_value : miscLinkedInvoice.invoice_value,
        }));
        loadGrid();
      })
      .catch(function (err) {
        const message = err.message || "Unable to change the billing customer.";
        if (window.JTCSDialog?.alert) window.JTCSDialog.alert(message, "error");
        else alert(message);
        paintMiscInvoice(miscLinkedInvoice);
      });
  }

  if (miscInvoicePage) {
    document.getElementById("oieInvoiceCheck")?.addEventListener("change", function (event) {
      const checkbox = event.target;
      if (checkbox.checked && !miscLinkedInvoice) {
        checkbox.checked = false;
        miscCreatingInvoice = false;
        syncMiscBillingPanel();
        if (window.JTCSDialog && JTCSDialog.alert) JTCSDialog.alert(MANUAL_INVOICE_MESSAGE, "warning");
        else alert(MANUAL_INVOICE_MESSAGE);
        return;
      }
      if (!checkbox.checked) miscCreatingInvoice = false;
      syncMiscBillingPanel();
    });
    document.getElementById("oieBillingSame")?.addEventListener("change", function () {
      syncMiscBillingPanel();
      if (!this.checked || !miscLinkedInvoice) return;
      const sameId = (els.customerId?.value || "").trim();
      if (!sameId) {
        alert("Please select a customer first.");
        this.checked = false;
        syncMiscBillingPanel();
        return;
      }
      reassignMiscBilling(sameId);
    });
    document.getElementById("oieBillingOther")?.addEventListener("change", syncMiscBillingPanel);
    document.getElementById("oieCreateInvoiceBtn")?.addEventListener("click", beginMiscCreateInvoice);
    document.getElementById("oieInvoiceEditorBack")?.addEventListener("click", function () {
      settleMiscInvoiceEditor();
    });
    els.entryModalEl?.addEventListener("hide.bs.modal", function (event) {
      if (miscAllowModalHide || !miscInvoiceEditorOpen) return;
      event.preventDefault();
      settleMiscInvoiceEditor().then(function (done) {
        if (!done) return;
        miscAllowModalHide = true;
        entryModal?.hide();
        miscAllowModalHide = false;
      });
    });
    document.getElementById("oieInvoiceActions")?.addEventListener("click", function (event) {
      const btn = event.target.closest(".oie-inv-act");
      if (!btn || !window.JtcsInvoiceActions || !miscLinkedInvoice) return;
      if (btn.getAttribute("data-inv-act") === "edit") {
        showMiscInvoiceEditor();
        return;
      }
      window.JtcsInvoiceActions.run(btn.getAttribute("data-inv-act"), miscLinkedInvoice, {
        miscEntryId: (els.entryId?.value || "").trim(),
        onDeleted: function () {
          miscCreatingInvoice = false;
          paintMiscInvoice(null);
          clearMiscBilling();
          loadGrid();
        },
      });
    });
    let billingTimer = null;
    document.getElementById("oieBillingSearch")?.addEventListener("input", function () {
      const input = document.getElementById("oieBillingSearch");
      const results = document.getElementById("oieBillingResults");
      const q = (input?.value || "").trim();
      if (document.getElementById("oieBillingCustomerId")) {
        document.getElementById("oieBillingCustomerId").value = "";
      }
      clearTimeout(billingTimer);
      if (!results || q.length < 2) {
        results?.classList.add("d-none");
        return;
      }
      billingTimer = setTimeout(function () {
        const url = (window.OIE_CUSTOMER_SEARCH_URL || "") + "?q=" + encodeURIComponent(q);
        fetch(url, { headers: { Accept: "application/json" } })
          .then(function (res) { return res.json(); })
          .then(function (data) {
            const list = (data && data.rows) || [];
            results.innerHTML = list.map(function (row) {
              const sub = [row.mobile_number, row.pan_number].filter(Boolean).join(" · ");
              return '<button type="button" class="list-group-item list-group-item-action oie-billing-pick" data-id="' +
                escapeHtml(row.customer_id) + '" data-name="' + escapeHtml(row.customer_name) + '"><strong>' +
                escapeHtml(row.customer_name) + "</strong>" +
                (sub ? '<div class="small text-muted">' + escapeHtml(sub) + "</div>" : "") + "</button>";
            }).join("") || '<div class="list-group-item text-muted">No customers found</div>';
            results.classList.remove("d-none");
          })
          .catch(function () { results.classList.add("d-none"); });
      }, 280);
    });
    document.getElementById("oieBillingResults")?.addEventListener("click", function (event) {
      const pick = event.target.closest(".oie-billing-pick");
      if (!pick) return;
      const id = document.getElementById("oieBillingCustomerId");
      const search = document.getElementById("oieBillingSearch");
      if (id) id.value = pick.getAttribute("data-id") || "";
      if (search) search.value = pick.getAttribute("data-name") || "";
      document.getElementById("oieBillingResults")?.classList.add("d-none");
      if (miscLinkedInvoice) reassignMiscBilling(pick.getAttribute("data-id") || "");
    });
    window.addEventListener("message", function (event) {
      if (event.origin !== window.location.origin) return;
      const data = event.data || {};
      if (data.type === "jtcs-invoice-receipt-closed") {
        if (String(window.OIE_FORCE_LEDGER_KIND || "") !== "Misc.") return;
        if (String(data.receipt_origin || "").trim().toUpperCase() !== "MISC") return;
        hideMiscInvoiceEditor();
        return;
      }
      const currentId = (els.entryId?.value || "").trim();
      if (!data.misc_entry_id) return;
      if (data.misc_entry_id && currentId && String(data.misc_entry_id) !== currentId) return;
      if (data.type === "jtcs-invoice-saved" && data.record) {
        paintMiscInvoice({
          invoice_id: data.record.invoice_id,
          invoice_no: data.record.invoice_no,
          invoice_date: data.record.invoice_date,
          invoice_value: data.record.invoice_value,
          customer_id: data.record.customer_id,
          customer_name: data.record.customer_name,
          contact_mobile: data.record.contact_mobile,
        });
        miscCreatingInvoice = false;
        loadGrid();
        if (miscInvoiceEditorOpen) setTimeout(hideMiscInvoiceEditor, 0);
      }
      if (data.type === "jtcs-invoice-deleted") {
        paintMiscInvoice(null);
        clearMiscBilling();
        loadGrid();
      }
    });
  }

  els.workDone?.addEventListener("change", syncMiscWorkflow);
  els.tallyBill?.addEventListener("change", syncMiscWorkflow);
  els.tallyBillNo?.addEventListener("change", refreshInvoiceStatus);
  els.tallyBillNo?.addEventListener("blur", refreshInvoiceStatus);
  window.jtcsRefreshInvoiceStatus = refreshInvoiceStatus;
  window.addEventListener("focus", refreshInvoiceStatus);

  els.paymentLines?.addEventListener("change", function (ev) {
    if (!ev.target.closest("select")) return;
    if (saleIsApproved()) syncGenerateBillPrompt();
  });

  els.paymentLines?.addEventListener("input", function () {
    if (!lastSaleRecord) return;
    paintInvoiceStatus(lastSaleRecord);
  });

  async function declineExistingPayment() {
    const hasPayment = getPaymentTotal() > 0;
    if (!hasPayment) {
      setPaymentReceivedChoice(false);
      syncMiscWorkflow();
      return;
    }
    setPaymentReceivedChoice(true);
    const sure = window.JTCSDialog?.confirm
      ? await window.JTCSDialog.confirm(
          "Payment already received for this bill will be deleted. Are you sure?",
          { title: "Delete payment", okLabel: "Yes", cancelLabel: "No", type: "warning" }
        )
      : window.confirm("Payment already received for this bill will be deleted. Are you sure?");
    if (!sure) return;
    let creds = null;
    if (window.JTCSDeleteConfirm?.ask) {
      creds = await window.JTCSDeleteConfirm.ask({
        message: "Enter your User ID and password to delete this payment.",
        title: "Confirm",
        confirmLabel: "Confirm",
        confirmIcon: "bi-shield-lock",
        variant: "warning",
      });
    }
    if (!creds || !creds.user_id || !creds.password) return;
    const permanent = window.JTCSDialog?.confirm
      ? await window.JTCSDialog.confirm(
          "This will permanently delete the payment on this bill.",
          { title: "Permanently delete", okLabel: "Yes", cancelLabel: "No", type: "danger" }
        )
      : window.confirm("This will permanently delete the payment on this bill.");
    if (!permanent) return;
    resetPaymentLines([{}]);
    const line = els.paymentLines?.querySelector(".oie-payment-line");
    if (line) clearPaymentLine(line);
    setPaymentReceivedChoice(false);
    syncMiscWorkflow();
    if (lastSaleRecord) paintInvoiceStatus(lastSaleRecord);
    await pushPaymentReceived(false);
  }

  els.paymentReceivedYes?.addEventListener("click", function () {
    setTimeout(function () {
      if (!isPaymentReceivedYes()) return;
      if (els.tallyBill && isWorkDoneChecked()) els.tallyBill.checked = true;
      syncMiscWorkflow();
      if (lastSaleRecord) paintInvoiceStatus(lastSaleRecord);
      pushPaymentReceived(true).catch(function (err) {
        if (window.JTCSDialog?.alert) window.JTCSDialog.alert(err.message || String(err), "error");
      });
    }, 0);
  });

  els.paymentReceivedNo?.addEventListener("click", function () {
    setTimeout(function () {
      if (els.paymentReceivedNo && !els.paymentReceivedNo.checked) return;
      declineExistingPayment().catch(function (err) {
        setPaymentReceivedChoice(true);
        const message = err.message || String(err);
        if (window.JTCSDialog?.alert) window.JTCSDialog.alert(message, "error");
        else alert(message);
      });
    }, 0);
  });

  document.getElementById("oieBillNoCopy")?.addEventListener("click", function () {
    copyBillNumber(this);
  });

  if (els.gridBody) {
    els.gridBody.addEventListener("click", function (event) {
      const invoiceBtn = event.target.closest(".jtcs-inv-act");
      if (invoiceBtn && window.JtcsInvoiceActions) {
        event.preventDefault();
        const holder = invoiceBtn.closest("[data-invoice-json]");
        let invoice = null;
        if (holder) {
          try { invoice = JSON.parse(holder.getAttribute("data-invoice-json") || "{}"); }
          catch (_err) { invoice = null; }
        }
        if (!invoice || !invoice.invoice_id) {
          const id = parseInt(invoiceBtn.getAttribute("data-invoice-id") || "", 10);
          if (id) invoice = { invoice_id: id };
        }
        if (!invoice) return;
        const miscEntryId = invoiceBtn.closest("[data-misc-entry-id]")
          ? invoiceBtn.closest("[data-misc-entry-id]").getAttribute("data-misc-entry-id")
          : "";
        const action = invoiceBtn.getAttribute("data-inv-act");
        if (action === "edit") {
          const row = allGridRows.find(function (item) {
            return String(item.entry_id) === String(miscEntryId);
          }) || {};
          openGenerateBillPopup({
            entry_id: miscEntryId,
            invoice_id: invoice.invoice_id,
            open_edit: true,
            date: row.work_date || "",
            invoice_no: invoice.invoice_no || row.tally_bill_no || row.bill_no || "",
            bill_no: row.bill_no || "",
            tally_bill_no: row.tally_bill_no || row.bill_no || invoice.invoice_no || "",
            customer_id: invoice.customer_id || row.customer_id || "",
            customer_name: invoice.customer_name || row.customer_name || "",
            mobile: invoice.contact_mobile || row.mobile_number || "",
            source: "Miscellaneous",
          });
          return;
        }
        window.JtcsInvoiceActions.run(action, invoice, {
          miscEntryId: miscEntryId,
          onDeleted: function () { loadGrid(); },
        });
        return;
      }
      const editBtn = event.target.closest(".oie-grid-edit-btn");
      if (editBtn) {
        loadEntry(editBtn.getAttribute("data-id"));
        return;
      }
      const deleteBtn = event.target.closest(".oie-grid-delete-btn");
      if (deleteBtn) {
        event.preventDefault();
        const entryId = deleteBtn.getAttribute("data-id");
        const row = allGridRows.find(function (item) {
          return String(item.entry_id) === String(entryId);
        });
        gridDeleteAllowed(row).then(function (allowed) {
          if (!allowed) return;
          deleteEntry(entryId);
        });
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
  applyForcedLedgerKindUi();
  syncLedgerLabels();
  window.addEventListener("message", function (event) {
    if (event.origin !== window.location.origin) return;
    const data = event.data || {};
    if (data.type === "jtcs-misc-invoice-saved") loadGrid();
  });
  loadGrid();
  if (window.OIE_AUTO_LOAD_ENTRY_ID) {
    var autoId = parseInt(window.OIE_AUTO_LOAD_ENTRY_ID, 10);
    if (!Number.isNaN(autoId) && autoId > 0) {
      loadEntry(autoId);
    }
  }
})();
