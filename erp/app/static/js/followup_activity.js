(function () {
  "use strict";

  const page = document.getElementById("fuActivityPage");
  if (!page || !window.FU_API) return;

  const hasReturnType = page.dataset.hasReturnType === "1";
  const hasTdsPeriodSplit = page.dataset.hasTdsPeriodSplit === "1";
  const hasGstFields = page.dataset.hasGstFields === "1";
  const workTypeLabel = window.FU_MODULE || "ITR";
  const isDscModule = workTypeLabel === "DSC";
  const isItrModule = workTypeLabel === "ITR";
  const isTdsModule = workTypeLabel === "TDS" || hasTdsPeriodSplit;
  const isGstModule = workTypeLabel === "GST" || hasGstFields;
  const isTaxFollowup = isItrModule || isTdsModule || isGstModule;
  const invoiceTickEnabled = isTaxFollowup || isDscModule;
  const paymentLineHasDate = isItrModule || isDscModule || isGstModule || isTdsModule;
  let linkedInvoice = null;
  let creatingInvoice = false;
  const MANUAL_INVOICE_MESSAGE =
    "Invoice cannot be selected manually. Please click 'Create Invoice' to generate the invoice first.";
  const RETURN_FILED_MESSAGE =
    "Please uncheck Invoice first before unchecking Return Filed.";
  let savedPaymentReceived = false;

  const els = {
    newEntryBtn: document.getElementById("fuNewEntryBtn"),
    refreshBtn: document.getElementById("fuRefreshBtn"),
    syncBtn: document.getElementById("fuSyncBtn"),
    exportExcelBtn: document.getElementById("fuExportExcelBtn"),
    kdkLoginModalEl: document.getElementById("fuKdkLoginModal"),
    kdkProgressModalEl: document.getElementById("fuKdkProgressModal"),
    kdkUserId: document.getElementById("fuKdkUserId"),
    kdkPassword: document.getElementById("fuKdkPassword"),
    kdkRememberMe: document.getElementById("fuKdkRememberMe"),
    kdkLoginSyncBtn: document.getElementById("fuKdkLoginSyncBtn"),
    kdkProgressTitle: document.getElementById("fuKdkProgressModalTitle"),
    kdkProgressClient: document.getElementById("fuKdkProgressClient"),
    kdkProgressPan: document.getElementById("fuKdkProgressPan"),
    kdkProgressPeriod: document.getElementById("fuKdkProgressPeriod"),
    kdkProgressBar: document.getElementById("fuKdkProgressBar"),
    kdkProgressCount: document.getElementById("fuKdkProgressCount"),
    kdkProgressError: document.getElementById("fuKdkProgressError"),
    kdkProgressCloseBtn: document.getElementById("fuKdkProgressCloseBtn"),
    kdkLoginStatus: document.getElementById("fuKdkLoginStatus"),
    kdkPreviewImg: document.getElementById("fuKdkPreviewImg"),
    kdkPreviewPlaceholder: document.getElementById("fuKdkPreviewPlaceholder"),
    kdkPreviewCaption: document.getElementById("fuKdkPreviewCaption"),
    searchInput: document.getElementById("fuSearchInput"),
    periodFilter: document.getElementById("fuPeriodFilter"),
    returnTypeFilter: document.getElementById("fuReturnTypeFilter"),
    statusFilter: document.getElementById("fuStatusFilter"),
    dateFromFilter: document.getElementById("fuDateFromFilter"),
    dateToFilter: document.getElementById("fuDateToFilter"),
    searchBtn: document.getElementById("fuSearchBtn"),
    clearFilterBtn: document.getElementById("fuClearFilterBtn"),
    statsRow: document.getElementById("fuStatsRow"),
    gridBody: document.getElementById("fuDataGridBody"),
    gridEmpty: document.getElementById("fuGridEmpty"),
    gridCount: document.getElementById("fuGridCount"),
    gridMeta: document.getElementById("fuGridMeta"),
    statTotal: document.getElementById("fuStatTotal"),
    statPending: document.getElementById("fuStatPending"),
    statPaymentPending: document.getElementById("fuStatPaymentPending"),
    entryModalEl: document.getElementById("fuEntryModal"),
    entryModalTitle: document.getElementById("fuEntryModalTitle"),
    entryForm: document.getElementById("fuEntryForm"),
    entryId: document.getElementById("fuEntryId"),
    workDate: document.getElementById("fuWorkDate"),
    taxPeriod: document.getElementById("fuTaxPeriod"),
    gstMonth: document.getElementById("fuGstMonth"),
    formType: document.getElementById("fuFormType"),
    quarter: document.getElementById("fuQuarter"),
    customerSearch: document.getElementById("fuCustomerSearch"),
    customerId: document.getElementById("fuCustomerId"),
    billingWrap: document.getElementById("fuBillingCustomerWrap"),
    billingSame: document.getElementById("fuBillingSame"),
    billingOther: document.getElementById("fuBillingOther"),
    billingPick: document.getElementById("fuBillingCustomerPick"),
    billingCustomerId: document.getElementById("fuBillingCustomerId"),
    billingCustomerSearch: document.getElementById("fuBillingCustomerSearch"),
    billingCustomerResults: document.getElementById("fuBillingCustomerResults"),
    customerResults: document.getElementById("fuCustomerResults"),
    customerSelected: document.getElementById("fuCustomerSelected"),
    addCustomerBtn: document.getElementById("fuAddCustomerBtn"),
    workflowChecks: document.getElementById("fuWorkflowChecks"),
    itrFiledWrap: document.getElementById("fuItrFiledWrap"),
    itrFiledDate: document.getElementById("fuItrFiledDate"),
    tallyBillWrap: document.getElementById("fuTallyBillWrap"),
    billNo: document.getElementById("fuBillNo"),
    generateBillYes: document.getElementById("fuGenerateBillYes"),
    generateBillNo: document.getElementById("fuGenerateBillNo"),
    approveInvoiceYes: document.getElementById("fuApproveInvoiceYes"),
    approveInvoiceNo: document.getElementById("fuApproveInvoiceNo"),
    invoiceStatus: document.getElementById("fuInvoiceStatus"),
    billDate: document.getElementById("fuBillDate"),
    billAmount: document.getElementById("fuBillAmount"),
    autoBillBtn: document.getElementById("fuAutoBillBtn"),
    paymentWrap: document.getElementById("fuPaymentWrap"),
    paymentLines: document.getElementById("fuPaymentLines"),
    addPaymentBtn: document.getElementById("fuAddPaymentBtn"),
    paymentSummary: document.getElementById("fuPaymentSummary"),
    unverifiedWrap: document.getElementById("fuUnverifiedWrap"),
    reasonUnverified: document.getElementById("fuReasonUnverified"),
    remarks: document.getElementById("fuRemarks"),
    applicationNumber: document.getElementById("fuApplicationNumber"),
    location: document.getElementById("fuLocation"),
    introducedBy: document.getElementById("fuIntroducedBy"),
    dscType: document.getElementById("fuDscType"),
    dscClass: document.getElementById("fuDscClass"),
    dscYear: document.getElementById("fuDscYear"),
    customerEmail: document.getElementById("fuCustomerEmail"),
    saveBtn: document.getElementById("fuSaveBtn"),
    returnType: document.getElementById("fuReturnType"),
    filingFrequency: document.getElementById("fuFilingFrequency"),
    gstReturnType: document.getElementById("fuGstReturnType"),
    customerModalEl: document.getElementById("fuCustomerModal"),
    customerForm: document.getElementById("fuCustomerForm"),
    customerSaveBtn: document.getElementById("fuCustomerSaveBtn"),
    customerFormError: document.getElementById("fuCustomerFormError"),
  };

  const entryModal = els.entryModalEl ? new bootstrap.Modal(els.entryModalEl) : null;
  const allowCustomerAdd = window.FU_ALLOW_CUSTOMER_ADD === true;
  const customerModal = allowCustomerAdd && els.customerModalEl
    ? new bootstrap.Modal(els.customerModalEl)
    : null;
  let fuPincodeBinder = null;
  const kdkLoginModal = isItrModule && els.kdkLoginModalEl
    ? new bootstrap.Modal(els.kdkLoginModalEl)
    : null;
  const kdkProgressModal = isItrModule && els.kdkProgressModalEl
    ? new bootstrap.Modal(els.kdkProgressModalEl)
    : null;
  let searchTimer = null;
  let customerSearchTimer = null;
  let customerSearchSeq = 0;
  let billingSearchTimer = null;
  let billingSearchSeq = 0;
  let itrSyncPollTimer = null;
  let pendingItrSyncEntryId = null;
  let rows = [];
  let rawGridRows = [];
  // ITR default: entry date/time ascending (oldest first).
  let gridSortKey = isItrModule ? "created_date" : null;
  let gridSortDir = "asc";
  const bankAccounts = (window.FU_BANK_ACCOUNTS || []).filter(function (item) {
    const flag = item && item.qr_bill_received;
    return flag === true || flag === 1 || flag === "1";
  });
  const KDK_USER_KEY = "jtcs_itr_kdk_userid";
  const KDK_PASS_KEY = "jtcs_itr_kdk_password";
  const KDK_SAVE_KEY = "jtcs_itr_kdk_save";

  function rowHasTallyBill(row) {
    if (!row) return false;
    if (row.has_tally_bill === true || row.has_tally_bill === 1) return true;
    if ((row.bill_no || "").trim()) return true;
    if ((row.workflow_status || "") === "Tally Bill Generated") return true;
    return (row.completed_stages || []).some(function (s) {
      return (s.StageCode || s.stage_code || "").toLowerCase() === "tally_bill_generated";
    });
  }

  function formatPaymentReceiveDateCell(row) {
    // Only show dates when Payment Received is ticked; otherwise "-".
    if (!rowHasPaymentReceived(row)) return "—";
    let dates = Array.isArray(row.payment_receive_dates) ? row.payment_receive_dates.slice() : [];
    if (!dates.length && row.payment_receive_date) {
      dates = String(row.payment_receive_date)
        .split(",")
        .map(function (part) { return part.trim(); })
        .filter(Boolean);
    }
    if (!dates.length) return "—";
    const formatted = dates
      .map(function (value) { return formatDate(value); })
      .filter(function (value) { return value && value !== "—"; });
    return formatted.length ? formatted.join(", ") : "—";
  }

  function rowHasPaymentReceived(row) {
    if (!row) return false;
    if (row.payment_received === true || row.payment_received === 1) return true;
    if ((row.workflow_status || "") === "Payment Received") return true;
    return (row.completed_stages || []).some(function (s) {
      return (s.StageCode || s.stage_code || "").toLowerCase() === "payment_received";
    });
  }

  async function sendThankYouWhatsApp(button) {
    if (!button || button.disabled) return;
    const entryId = button.getAttribute("data-id");
    const name = (button.getAttribute("data-name") || "customer").trim();
    const template = window.FU_API && window.FU_API.thank_you_whatsapp;
    if (!entryId || !template) return;
    const ask = "Thank You letter image " + name + " ke WhatsApp par bhej dein?";
    const ok = window.confirm(ask);
    if (!ok) return;
    button.disabled = true;
    try {
      const res = await fetch(apiUrl(template, entryId), {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "X-CSRFToken": window.FU_CSRF || csrfToken(),
        },
      });
      const data = await res.json().catch(function () { return {}; });
      if (!res.ok || !data.ok) {
        throw new Error(data.error || "Unable to send the Thank You letter.");
      }
      const message = data.message || "Thank You letter image WhatsApp par chali gayi.";
      if (window.JTCSDialog?.alert) await window.JTCSDialog.alert(message, "success");
      else alert(message);
    } catch (err) {
      const message = err.message || "Unable to send the Thank You letter.";
      if (window.JTCSDialog?.alert) await window.JTCSDialog.alert(message, "error");
      else alert(message);
    } finally {
      button.disabled = false;
    }
  }

  function canDownloadThankYou(row) {
    return rowHasPaymentReceived(row);
  }

  function thankYouCellHtml(row) {
    const ready = canDownloadThankYou(row);
    const pngTitle = ready
      ? "Download Thank You Letter (PNG)"
      : "Available after Payment Received";
    const waTitle = ready
      ? "Send Thank You letter image on WhatsApp"
      : "Available after Payment Received";
    if (isDscModule || ready) {
      const pngHref = ready
        ? escapeHtml(apiUrl(window.FU_API.thank_you_letter, row.entry_id) + "?format=png")
        : "#";
      return (
        '<span class="fu-thank-actions">' +
        '<a class="btn btn-outline-success btn-sm fu-thank-btn' +
        (ready ? "" : " disabled") +
        '" href="' + pngHref + '" title="' + pngTitle + '"' +
        (ready ? "" : ' aria-disabled="true" tabindex="-1"') +
        '><i class="bi bi-download"></i> PNG</a>' +
        '<button type="button" class="btn btn-success btn-sm fu-thank-wa" data-id="' +
        row.entry_id +
        '" data-name="' + escapeHtml(row.customer_name || "") +
        '" title="' + waTitle + '"' +
        (ready ? "" : " disabled") +
        '><i class="bi bi-whatsapp"></i></button>' +
        "</span>"
      );
    }
    return (
      '<span class="text-muted" title="' +
      (isItrModule ? "Available after Payment Received" : "Available after Invoice") +
      '">—</span>'
    );
  }

  function isItrPaymentReceivedLocked(row) {
    return isItrModule && rowHasPaymentReceived(row);
  }

  async function openEntryForEdit(entryId) {
    return loadEntry(entryId);
  }

  function rowHasInvoiceStage(row) {
    if (!row) return false;
    const status = row.workflow_status || "";
    if (status === "Invoice" || status === "Tally Bill Generated") return true;
    return (row.completed_stages || []).some(function (stage) {
      const code = (stage.StageCode || stage.stage_code || "").toLowerCase();
      return code === "invoice" || code === "tally_bill_generated";
    });
  }

  function canDownloadPaymentReminder(row) {
    // ITR only: after Invoice, while payment is still pending.
    if (!isItrModule) return false;
    if (!rowHasInvoiceStage(row)) return false;
    if (rowHasPaymentReceived(row)) return false;
    return !!(window.FU_API && window.FU_API.payment_reminder);
  }

  function currentCustomerVideoBase() {
    const input = document.getElementById("fuDscVideoLink");
    const field = input ? input.closest(".fu-dsc-assist-field") : null;
    const saved = field && field.dataset.savedValue != null ? String(field.dataset.savedValue).trim() : "";
    const typed = input ? String(input.value || "").trim() : "";
    return typed || saved;
  }

  function buildDscRowVideoLink(applicationId, mobile) {
    const base = currentCustomerVideoBase();
    const app = String(applicationId == null ? "" : applicationId).trim();
    const mob = String(mobile == null ? "" : mobile).trim();
    if (!base || !app || !mob) return "";
    try {
      const url = new URL(base);
      url.searchParams.set("applicationId", app);
      url.searchParams.set("mobile", mob);
      return url.toString();
    } catch (err) {
      const sep = base.indexOf("?") >= 0 ? "&" : "?";
      return base + sep + "applicationId=" + encodeURIComponent(app) + "&mobile=" + encodeURIComponent(mob);
    }
  }

  function copyableCell(value) {
    const text = (value == null ? "" : String(value)).trim();
    if (!text) {
      return "<td>—</td>";
    }
    return (
      '<td class="fu-copy-cell">' +
      '<span class="fu-copy-text">' + escapeHtml(text) + "</span>" +
      '<button type="button" class="fu-copy-btn" title="Copy" aria-label="Copy">' +
      '<i class="bi bi-copy"></i></button>' +
      "</td>"
    );
  }

  function copyTextToClipboard(text, button) {
    const value = (text || "").trim();
    if (!value) return;
    const done = function () {
      if (!button) return;
      const icon = button.querySelector("i");
      if (!icon) return;
      icon.className = "bi bi-check2";
      button.classList.add("is-copied");
      window.setTimeout(function () {
        icon.className = "bi bi-copy";
        button.classList.remove("is-copied");
      }, 1200);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(value).then(done).catch(function () {
        fallbackCopy(value, done);
      });
      return;
    }
    fallbackCopy(value, done);
  }

  function dscAssistUrl() {
    return window.FU_API.assist || "/dsc/followup/assist";
  }

  function setDscAssistMode(field, savedValue) {
    const input = field.querySelector("input");
    const saveBtn = field.querySelector(".fu-dsc-assist-save");
    const editBtn = field.querySelector(".fu-dsc-assist-edit");
    const copyBtn = field.querySelector(".fu-dsc-assist-copy");
    const hasSaved = !!(savedValue || "").trim();
    field.dataset.savedValue = savedValue || "";
    if (input) {
      input.value = savedValue || "";
      input.readOnly = hasSaved;
      input.classList.toggle("fu-dsc-assist-readonly", hasSaved);
    }
    saveBtn?.classList.toggle("d-none", hasSaved);
    editBtn?.classList.toggle("d-none", !hasSaved);
    copyBtn?.classList.toggle("d-none", !hasSaved);
  }

  function startDscAssistEdit(field) {
    const input = field.querySelector("input");
    const saveBtn = field.querySelector(".fu-dsc-assist-save");
    const editBtn = field.querySelector(".fu-dsc-assist-edit");
    const copyBtn = field.querySelector(".fu-dsc-assist-copy");
    if (input) {
      input.readOnly = false;
      input.classList.remove("fu-dsc-assist-readonly");
      input.focus();
      input.select();
    }
    saveBtn?.classList.remove("d-none");
    editBtn?.classList.add("d-none");
    copyBtn?.classList.add("d-none");
  }

  async function saveDscAssistField(field) {
    const key = field.dataset.assistKey;
    const input = field.querySelector("input");
    const saveBtn = field.querySelector(".fu-dsc-assist-save");
    const value = (input?.value || "").trim();
    if (!key) return;
    if (saveBtn) saveBtn.disabled = true;
    try {
      const res = await fetch(dscAssistUrl(), {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
        },
        body: JSON.stringify({ key: key, value: value, csrf_token: csrfToken() }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.error || "Unable to save.");
      }
      const saved = (data.values && data.values[key]) || value;
      setDscAssistMode(field, saved);
    } catch (err) {
      alert(err.message || String(err));
    } finally {
      if (saveBtn) saveBtn.disabled = false;
    }
  }

  function initDscAssist() {
    const box = document.getElementById("fuDscAssist");
    if (!box || !isDscModule) return;
    box.querySelectorAll(".fu-dsc-assist-field").forEach(function (field) {
      field.querySelector(".fu-dsc-assist-save")?.addEventListener("click", function () {
        saveDscAssistField(field);
      });
      field.querySelector(".fu-dsc-assist-edit")?.addEventListener("click", function () {
        startDscAssistEdit(field);
      });
      field.querySelector(".fu-dsc-assist-copy")?.addEventListener("click", function () {
        const value = field.dataset.savedValue || field.querySelector("input")?.value || "";
        copyTextToClipboard(value, this);
      });
      field.querySelector("input")?.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          if (!this.readOnly) saveDscAssistField(field);
        }
      });
    });
    fetch(dscAssistUrl(), { headers: { Accept: "application/json" } })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data || !data.ok) return;
        const values = data.values || {};
        box.querySelectorAll(".fu-dsc-assist-field").forEach(function (field) {
          setDscAssistMode(field, values[field.dataset.assistKey] || "");
        });
      })
      .catch(function () { /* keep empty editable fields */ });
  }

  function fallbackCopy(text, done) {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.left = "-9999px";
    document.body.appendChild(area);
    area.select();
    try {
      document.execCommand("copy");
      if (typeof done === "function") done();
    } catch (err) {
      alert("Unable to copy.");
    }
    document.body.removeChild(area);
  }

  function isUdhaarText(value) {
    const raw = String(value || "").trim();
    if (!raw) return false;
    if (raw.indexOf("उधार") >= 0) return true;
    const lower = raw.toLowerCase();
    return (
      lower.indexOf("udhaar") >= 0 ||
      lower.indexOf("udhar") >= 0 ||
      lower === "credit" ||
      lower === "on credit" ||
      lower === "credit sale" ||
      lower === "receivable"
    );
  }

  function isUdhaarBank(bank) {
    if (!bank) return false;
    return (
      isUdhaarText(bank.bank_name) ||
      isUdhaarText(bank.label) ||
      isUdhaarText(bank.masked_account_number) ||
      isUdhaarText(bank.account_number) ||
      isUdhaarText(bank.display_account_number)
    );
  }

  function bankById(bankId) {
    const id = String(bankId || "");
    return (bankAccounts || []).find(function (bank) {
      return String(bank.bank_account_id || bank.BankAccountID || bank.id || "") === id;
    }) || null;
  }

  function paymentModeLabel(bank) {
    const name = (bank.bank_name || bank.label || "").trim();
    const masked = (bank.masked_account_number || "").trim();
    const display = (bank.display_account_number || bank.account_number || "").trim();
    if (isUdhaarBank(bank)) return "Udhaar";
    if (paymentLineHasDate) {
      if (name && name.toLowerCase() === "cash") return "Cash";
      if (masked) return masked;
      if (display.length > 20) return display.slice(0, 18) + "…";
      return display || name || "Bank";
    }
    return (display || name || "Bank") + (masked ? " (" + masked + ")" : "");
  }

  function defaultPaymentDate() {
    return (
      els.workDate?.value ||
      els.billDate?.value ||
      window.FU_DEFAULT_DATE ||
      new Date().toISOString().slice(0, 10)
    );
  }

  function defaultPaymentAmount() {
    const bill = els.billAmount?.value;
    if (bill && parseFloat(bill) > 0) return String(bill);
    return "0";
  }

  function syncPaymentDatesBeforeSave() {
    if (!paymentLineHasDate) return;
    const fallback = defaultPaymentDate();
    if (!fallback) return;
    els.paymentLines?.querySelectorAll(".fu-payment-date").forEach(function (input) {
      if (!input.value) input.value = fallback;
    });
  }

  function appendBillingPayload(payload) {
    if ((isStageChecked("return_filed") || isStageChecked("itr_filed")) && els.itrFiledDate) {
      payload.itr_filed_date = els.itrFiledDate.value || "";
    }
    if (isTaxFollowup) return;
    const tallyChecked = isStageChecked("tally_bill_generated");
    const paymentChecked = isStageChecked("payment_received");
    if (!tallyChecked && !paymentChecked) return;
    payload.bill_no = (els.billNo?.value || "").trim();
    payload.bill_date = els.billDate?.value || "";
    if (els.billAmount && String(els.billAmount.value || "").trim() !== "") {
      payload.bill_amount = els.billAmount.value;
    }
  }

  function buildPaymentSelect(selectedId) {
    const select = document.createElement("select");
    select.className = "form-select form-select-sm fu-payment-bank";
    select.required = true;
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = "-- Select bank / QR --";
    select.appendChild(empty);
    bankAccounts.forEach(function (bank) {
      const opt = document.createElement("option");
      opt.value = String(bank.bank_account_id || bank.BankAccountID || bank.id || "");
      opt.textContent = paymentModeLabel(bank);
      if (String(selectedId) === opt.value) opt.selected = true;
      select.appendChild(opt);
    });
    select.addEventListener("change", updatePaymentSummary);
    return select;
  }

  function getPaymentTotal() {
    let total = 0;
    els.paymentLines?.querySelectorAll(".fu-payment-amount").forEach(function (input) {
      const val = parseFloat(input.value || "0");
      if (!Number.isNaN(val)) total += val;
    });
    return total;
  }

  function getPaymentTotalsSplit() {
    let received = 0;
    let udhaar = 0;
    els.paymentLines?.querySelectorAll(".fu-payment-line").forEach(function (line) {
      const bank = line.querySelector(".fu-payment-bank");
      const amountInput = line.querySelector(".fu-payment-amount");
      const val = parseFloat(amountInput?.value || "0");
      if (Number.isNaN(val)) return;
      if (isUdhaarBank(bankById(bank?.value))) udhaar += val;
      else received += val;
    });
    return { received: received, udhaar: udhaar, total: received + udhaar };
  }

  function updatePaymentSummary() {
    if (!els.paymentSummary) return;
    const billAmount = parseFloat(els.billAmount?.value || "0") || 0;
    if (!isItrModule) {
      const total = getPaymentTotal();
      els.paymentSummary.textContent =
        "Received: ₹" + total.toFixed(2) + (billAmount ? " / Bill: ₹" + billAmount.toFixed(2) : "");
      return;
    }
    const split = getPaymentTotalsSplit();
    let text = "Received: ₹" + split.received.toFixed(2);
    if (split.udhaar > 0) text += " | Udhaar: ₹" + split.udhaar.toFixed(2);
    if (billAmount) text += " / Bill: ₹" + billAmount.toFixed(2);
    els.paymentSummary.textContent = text;
  }

  function addPaymentLine(options) {
    options = options || {};
    if (!els.paymentLines) return null;
    const line = document.createElement("div");
    line.className = "fu-payment-line" + (paymentLineHasDate ? " fu-payment-line--itr" : "");

    const bankWrap = document.createElement("div");
    bankWrap.className = "fu-payment-bank-wrap";
    const bankLabel = document.createElement("label");
    bankLabel.className = "form-label";
    bankLabel.textContent = "Payment Mode *";
    bankWrap.appendChild(bankLabel);
    bankWrap.appendChild(buildPaymentSelect(options.bank_account_id));

    let dateWrap = null;
    let dateInput = null;
    if (paymentLineHasDate) {
      dateWrap = document.createElement("div");
      dateWrap.className = "fu-payment-date-wrap";
      const dateLabel = document.createElement("label");
      dateLabel.className = "form-label";
      dateLabel.textContent = "Date *";
      dateInput = document.createElement("input");
      dateInput.type = "date";
      dateInput.className = "form-control form-control-sm fu-payment-date";
      dateInput.required = true;
      dateInput.value = options.payment_date || defaultPaymentDate();
      dateWrap.appendChild(dateLabel);
      dateWrap.appendChild(dateInput);
    }

    const amountWrap = document.createElement("div");
    amountWrap.className = "fu-payment-amount-wrap";
    const amountLabel = document.createElement("label");
    amountLabel.className = "form-label";
    amountLabel.textContent = "Received Amount *";
    const amount = document.createElement("input");
    amount.type = "number";
    amount.step = "0.01";
    amount.min = "0";
    amount.className = "form-control form-control-sm fu-payment-amount";
    amount.value = options.amount != null && options.amount !== "" && parseFloat(options.amount) > 0
      ? options.amount
      : defaultPaymentAmount();
    amount.addEventListener("input", updatePaymentSummary);
    amountWrap.appendChild(amountLabel);
    amountWrap.appendChild(amount);

    const actionWrap = document.createElement("div");
    actionWrap.className = "fu-payment-action-wrap";
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn btn-outline-danger btn-sm fu-payment-remove";
    removeBtn.innerHTML = '<i class="bi bi-trash"></i>';
    removeBtn.addEventListener("click", function () {
      const lines = els.paymentLines?.querySelectorAll(".fu-payment-line") || [];
      if (lines.length <= 1) {
        const select = line.querySelector("select");
        const amount = line.querySelector(".fu-payment-amount");
        const date = line.querySelector(".fu-payment-date");
        if (select) select.value = "";
        if (amount) amount.value = "";
        if (date) date.value = defaultPaymentDate();
        updatePaymentSummary();
        return;
      }
      line.remove();
      updatePaymentSummary();
    });
    actionWrap.appendChild(removeBtn);

    line.appendChild(bankWrap);
    if (dateWrap) line.appendChild(dateWrap);
    line.appendChild(amountWrap);
    line.appendChild(actionWrap);
    els.paymentLines.appendChild(line);
    updatePaymentSummary();
    return line;
  }

  function resetPaymentLines(lines) {
    if (!els.paymentLines) return;
    els.paymentLines.innerHTML = "";
    const rowsData = lines && lines.length ? lines : [{}];
    rowsData.forEach(function (row) { addPaymentLine(row); });
    if (els.billAmount?.value && rowsData.length === 1) {
      const firstAmount = els.paymentLines.querySelector(".fu-payment-amount");
      if (firstAmount && (!firstAmount.value || parseFloat(firstAmount.value) === 0)) {
        firstAmount.value = els.billAmount.value;
      }
    }
    updatePaymentSummary();
  }

  function collectPaymentLines() {
    const lines = [];
    els.paymentLines?.querySelectorAll(".fu-payment-line").forEach(function (line) {
      const bank = line.querySelector(".fu-payment-bank");
      const amount = line.querySelector(".fu-payment-amount");
      const paymentDate = line.querySelector(".fu-payment-date");
      if (!bank?.value) return;
      const row = {
        bank_account_id: parseInt(bank.value, 10),
        amount: String(amount?.value || "0"),
      };
      if (paymentLineHasDate) {
        row.payment_date = paymentDate?.value || defaultPaymentDate();
      } else if (paymentDate?.value) {
        row.payment_date = paymentDate.value;
      }
      lines.push(row);
    });
    return lines;
  }

  function validatePaymentLines() {
    if (!isStageChecked("payment_received")) return null;
    const lines = els.paymentLines?.querySelectorAll(".fu-payment-line") || [];
    if (!lines.length) return "Add at least one payment mode.";
    for (let i = 0; i < lines.length; i++) {
      const bank = lines[i].querySelector(".fu-payment-bank");
      const amount = lines[i].querySelector(".fu-payment-amount");
      const paymentDate = lines[i].querySelector(".fu-payment-date");
      if (!bank?.value) return "Each payment mode must be selected.";
      if (paymentLineHasDate && !paymentDate?.value) return "Each payment line must have a date.";
      const val = parseFloat(amount?.value || "0");
      if (Number.isNaN(val) || val <= 0) return "Each payment amount must be greater than zero.";
    }
    const billAmount = parseFloat(els.billAmount?.value || "0");
    const total = getPaymentTotal();
    if (billAmount > 0 && total - billAmount > 0.001) {
      // Overpayment is recorded as customer advance — allowed.
      return null;
    }
    return null;
  }

  function apiUrl(template, id) {
    return String(template || "").replace(/\/0(?=$|\/)/, "/" + String(id));
  }

  function csrfToken() {
    return els.entryForm?.querySelector('[name="csrf_token"]')?.value || window.FU_CSRF || "";
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function normalizeRejectComment(value) {
    let text = String(value == null ? "" : value).trim();
    if (!text || text === "null" || text === "undefined" || text === "None") {
      return "";
    }
    text = text.replace(/^Reject\s*comment\s*\(\s*IF\s*ANY\s*\)\s*:\s*/i, "").trim();
    return text;
  }

  function rejectCommentFromRow(row) {
    if (!row) return "";
    return normalizeRejectComment(
      row.reason_for_unverified != null
        ? row.reason_for_unverified
        : row.ReasonForUnverified
    );
  }

  function remarksRejectTipHtml(rejectComment) {
    const hasComment = !!rejectComment;
    const body = rejectComment || "No reject comment";
    const copyBtn = hasComment
      ? '<button type="button" class="fu-remarks-reject-copy" title="Copy reject comment" aria-label="Copy reject comment">' +
        '<i class="bi bi-copy"></i></button>'
      : "";
    return (
      '<div class="fu-remarks-reject-label-row">' +
      '<div class="fu-remarks-reject-label">Reject comment(IF ANY):</div>' +
      copyBtn +
      "</div>" +
      '<div class="fu-remarks-reject-body fu-copy-text">' +
      escapeHtml(body) +
      "</div>"
    );
  }

  let remarksRejectTipEl = null;
  let remarksRejectHideTimer = null;

  function clearRemarksRejectHideTimer() {
    if (remarksRejectHideTimer) {
      window.clearTimeout(remarksRejectHideTimer);
      remarksRejectHideTimer = null;
    }
  }

  function hideRemarksRejectTip() {
    clearRemarksRejectHideTimer();
    if (remarksRejectTipEl) {
      remarksRejectTipEl.remove();
      remarksRejectTipEl = null;
    }
  }

  function scheduleHideRemarksRejectTip() {
    clearRemarksRejectHideTimer();
    remarksRejectHideTimer = window.setTimeout(function () {
      hideRemarksRejectTip();
    }, 160);
  }

  function positionRemarksRejectTip(anchor) {
    if (!remarksRejectTipEl || !anchor) return;
    const margin = 8;
    const rect = anchor.getBoundingClientRect();
    const tipRect = remarksRejectTipEl.getBoundingClientRect();
    let left = rect.left;
    let top = rect.bottom + margin;
    if (left + tipRect.width > window.innerWidth - margin) {
      left = Math.max(margin, window.innerWidth - tipRect.width - margin);
    }
    if (left < margin) left = margin;
    if (top + tipRect.height > window.innerHeight - margin) {
      top = Math.max(margin, rect.top - tipRect.height - margin);
    }
    remarksRejectTipEl.style.left = left + "px";
    remarksRejectTipEl.style.top = top + "px";
  }

  function showRemarksRejectTip(anchor) {
    if (!anchor) return;
    clearRemarksRejectHideTimer();
    const rejectComment = normalizeRejectComment(anchor.getAttribute("data-reject-comment"));
    if (remarksRejectTipEl && remarksRejectTipEl._anchor === anchor) {
      positionRemarksRejectTip(anchor);
      return;
    }
    hideRemarksRejectTip();
    remarksRejectTipEl = document.createElement("div");
    remarksRejectTipEl.className = "fu-remarks-reject-popover";
    remarksRejectTipEl.setAttribute("role", "tooltip");
    remarksRejectTipEl.innerHTML = remarksRejectTipHtml(rejectComment);
    remarksRejectTipEl._anchor = anchor;
    remarksRejectTipEl._rejectComment = rejectComment;
    remarksRejectTipEl.addEventListener("mouseenter", function () {
      clearRemarksRejectHideTimer();
    });
    remarksRejectTipEl.addEventListener("mouseleave", function () {
      scheduleHideRemarksRejectTip();
    });
    remarksRejectTipEl.addEventListener("click", function (event) {
      const copyBtn = event.target.closest(".fu-remarks-reject-copy");
      if (!copyBtn) return;
      event.preventDefault();
      event.stopPropagation();
      const text = (remarksRejectTipEl._rejectComment || "").trim();
      if (!text) return;
      copyTextToClipboard(text, copyBtn);
    });
    document.body.appendChild(remarksRejectTipEl);
    positionRemarksRejectTip(anchor);
  }

  function remarksCellHtml(row) {
    const remarksText = row.remarks || "—";
    if (!isDscModule) {
      return "<td>" + escapeHtml(remarksText) + "</td>";
    }
    const rejectComment = rejectCommentFromRow(row);
    return (
      '<td class="fu-remarks-cell">' +
      '<span class="fu-remarks-tip" tabindex="0" data-reject-comment="' +
      escapeHtml(rejectComment) +
      '" title="">' +
      escapeHtml(remarksText) +
      '<i class="bi bi-info-circle fu-remarks-tip-icon" aria-hidden="true"></i>' +
      "</span></td>"
    );
  }

  function csvCell(value) {
    const text = String(value == null ? "" : value).replace(/"/g, '""');
    return '"' + text + '"';
  }

  function exportItrGridExcel() {
    if (!isItrModule) return;
    const dataRows = rows && rows.length ? rows : applyItrGridSort(rawGridRows || []);
    if (!dataRows.length) {
      alert("No records to export.");
      return;
    }
    const headers = [
      "Date",
      "Period",
      "Customer",
      "Mobile",
      "PAN",
      "Bill No.",
      "Bill Date",
      "Work Type",
      "Return Type",
      "Return Filing Status",
      "Filing Date",
      "Workflow Status",
      "Payment Receive Date",
      "Remarks",
    ];
    function exportDate(value) {
      if (!value) return "";
      const formatted = formatDate(value);
      return formatted === "—" ? "" : formatted;
    }
    const lines = [headers.map(csvCell).join(",")];
    dataRows.forEach(function (row) {
      const payDates = formatPaymentReceiveDateCell(row);
      lines.push(
        [
          exportDate(row.work_date),
          row.tax_period || "",
          row.customer_name || "",
          row.mobile_number || "",
          row.pan_number || "",
          row.bill_no || "",
          exportDate(row.bill_date),
          workTypeLabel,
          row.return_type || "",
          row.return_filing_status || "",
          exportDate(row.filing_date),
          row.workflow_status || "",
          payDates === "—" ? "" : payDates,
          row.remarks || "",
        ]
          .map(csvCell)
          .join(",")
      );
    });
    const stamp = new Date().toISOString().slice(0, 10);
    const blob = new Blob(["\ufeff" + lines.join("\r\n")], {
      type: "text/csv;charset=utf-8;",
    });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "ITR_Followup_" + stamp + ".csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
  }

  function formatDate(value) {
    if (window.formatDisplaySmart) return window.formatDisplaySmart(value, "—");
    if (!value) return "—";
    const raw = String(value).slice(0, 10);
    const parts = raw.split("-");
    if (parts.length === 3) return parts[2] + "/" + parts[1] + "/" + parts[0];
    return raw;
  }

  function statusBadgeClass(status) {
    const s = (status || "").toLowerCase();
    if (s === "pending") return "fu-status-pending";
    if (s === "unverified") return "fu-status-unverified";
    return "fu-status-done";
  }

  function selectedStageIds() {
    return Array.from(els.workflowChecks?.querySelectorAll(".fu-stage-check:checked") || []).map(function (cb) {
      return (cb.dataset.stageCode || cb.value || "").trim();
    }).filter(function (code) {
      if (!code) return false;
      if (code === "invoice" && !(linkedInvoice && linkedInvoice.invoice_id)) return false;
      return true;
    });
  }

  function isStageChecked(stageCode) {
    const cb = els.workflowChecks?.querySelector('.fu-stage-check[data-stage-code="' + stageCode + '"]');
    return !!(cb && cb.checked);
  }

  function isDscApplicationStageChecked() {
    return Array.from(els.workflowChecks?.querySelectorAll(".fu-stage-check:checked") || []).some(function (cb) {
      const code = (cb.dataset.stageCode || "").toLowerCase();
      return code === "application_received" || code === "application_no" || code.startsWith("application");
    });
  }

  function syncDscApplicationField() {
    if (!isDscModule || !els.applicationNumber) return;
    const locked = els.applicationNumber.dataset.locked === "1";
    const required = isDscApplicationStageChecked() && !isStageChecked("documents_received") && !locked;
    const label = document.querySelector('label[for="fuApplicationNumber"]');
    els.applicationNumber.required = required;
    if (label) label.classList.toggle("fu-required", required);
    els.applicationNumber.readOnly = locked;
    els.applicationNumber.classList.toggle("bg-light", locked);
    if (locked) {
      els.applicationNumber.title = "Application number is saved permanently and cannot be changed.";
    } else {
      els.applicationNumber.removeAttribute("title");
    }
  }

  function validateTallyPayment() {
    if (isTaxFollowup) {
      if (!isStageChecked("payment_received")) return null;
      const payTotal = getPaymentTotal();
      if (!payTotal || payTotal <= 0) {
        return "Add at least one payment amount for Payment Received.";
      }
      return null;
    }
    if (isStageChecked("tally_bill_generated")) {
      if (!(els.billNo?.value || "").trim()) {
        return "Tally bill number is required when Tally Bill Generated is checked.";
      }
    }
    if (isStageChecked("payment_received")) {
      if (!(els.billNo?.value || "").trim()) {
        return "Tally bill number is required before marking Payment Received.";
      }
      const payTotal = getPaymentTotal();
      if (!payTotal || payTotal <= 0) {
        return "Add at least one payment amount for Payment Received.";
      }
    }
    return null;
  }

  function validateDscEntry() {
    if (!isDscModule) return null;
    const locked = els.applicationNumber?.dataset.locked === "1";
    const applicationNo = (els.applicationNumber?.value || "").trim();
    if (isDscApplicationStageChecked() && !isStageChecked("documents_received") && !applicationNo && !locked) {
      return "Application number is required when Application No. is checked.";
    }
    if (!(els.dscType?.value || "").trim()) return "DSC type is required.";
    if (!(els.dscClass?.value || "").trim()) return "DSC class is required.";
    if (!(els.dscYear?.value || "").trim()) return "Year is required.";
    if (!(els.location?.value || "").trim()) {
      return "Location is required.";
    }
    if (!(els.introducedBy?.value || "").trim()) {
      return "Introduced by is required.";
    }
    if (isStageChecked("tally_bill_generated")) {
      if (!(els.billNo?.value || "").trim()) {
        return "Tally bill number is required when Tally Bill Generated is checked.";
      }
    }
    if (isStageChecked("payment_received")) {
      if (!(els.billNo?.value || "").trim()) {
        return "Tally bill number is required before marking Payment Received.";
      }
      const payTotal = getPaymentTotal();
      if (!payTotal || payTotal <= 0) {
        return "Add at least one payment amount for Payment Received.";
      }
    }
    return null;
  }

  let lastSaleRecord = null;
  let approveInFlight = false;
  let autoApproveFor = 0;

  function sourcePaymentReceived() {
    return isStageChecked("payment_received") || getPaymentTotal() > 0;
  }

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
    box.classList.remove("fu-pay-no", "fu-pay-yes");
    if (!record) {
      box.textContent = "";
      box.classList.add("d-none");
      return;
    }
    box.textContent = saleStatusText(record);
    box.classList.remove("d-none");
    if (sourcePaymentReceived()) box.classList.add("fu-pay-yes");
    else box.classList.add("fu-pay-no");
  }

  function saleIsApproved() {
    return !!(lastSaleRecord && lastSaleRecord.bill_approved);
  }

  let entryFieldsLocked = false;

  function approvedEditMessage() {
    const paid = isStageChecked("payment_received") || !!(lastSaleRecord && lastSaleRecord.payment_received);
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
    const existing = !!(els.entryId && (els.entryId.value || "").trim());
    const editBtn = document.getElementById("fuEditBtn");
    const deleteBtn = document.getElementById("fuDeleteBtn");
    if (editBtn) editBtn.classList.toggle("d-none", !existing);
    if (deleteBtn) deleteBtn.classList.toggle("d-none", !existing);
  }

  function setEntryFieldsLocked(locked) {
    entryFieldsLocked = !!locked;
    const entryForm = document.getElementById("fuEntryForm");
    entryForm?.querySelectorAll("input, select, textarea, button").forEach(function (el) {
      if (el.type === "hidden") return;
      if (el.id === "fuBillNoCopy") return;
      el.disabled = !!locked;
    });
    if (els.billNo) els.billNo.disabled = true;
    const billCopyBtn = document.getElementById("fuBillNoCopy");
    if (billCopyBtn) billCopyBtn.disabled = false;
    if (els.saveBtn) els.saveBtn.disabled = !!locked;
    if (!locked) syncWorkflowPanels();
    syncEntryActionButtons();
  }

  function hasCreditPayment() {
    const lines = els.paymentLines?.querySelectorAll(".fu-payment-line") || [];
    for (let i = 0; i < lines.length; i++) {
      const select = lines[i].querySelector("select");
      const text =
        (select && select.selectedOptions && select.selectedOptions[0] && select.selectedOptions[0].textContent) ||
        "";
      if (/credit/i.test(text)) return true;
    }
    return false;
  }

  function syncGenerateBillChoiceLabels() {
    const hasInvoice = !!(lastSaleRecord && lastSaleRecord.invoice_id);
    const yesLabel = document.querySelector('label[for="fuGenerateBillYes"]');
    const noLabel = document.querySelector('label[for="fuGenerateBillNo"]');
    if (yesLabel) yesLabel.textContent = hasInvoice ? "Edit" : "YES";
    if (noLabel) noLabel.textContent = hasInvoice ? "Delete" : "NO";
  }

  function syncGenerateBillPrompt(lookupDone) {
    syncGenerateBillChoiceLabels();
    const approved = saleIsApproved();
    if (els.generateBillYes) els.generateBillYes.disabled = approved || entryFieldsLocked;
    if (els.generateBillNo) els.generateBillNo.disabled = approved || entryFieldsLocked;
    const paymentOn = isStageChecked("payment_received");
    const invoiceId = lastSaleRecord && lastSaleRecord.invoice_id;
    const lockApprove = paymentOn || entryFieldsLocked;
    if (els.approveInvoiceYes) els.approveInvoiceYes.disabled = lockApprove;
    if (els.approveInvoiceNo) els.approveInvoiceNo.disabled = lockApprove;
    if (approved) {
      if (els.approveInvoiceYes) els.approveInvoiceYes.checked = true;
      if (els.approveInvoiceNo) els.approveInvoiceNo.checked = false;
    } else if (!paymentOn) {
      if (els.approveInvoiceYes) els.approveInvoiceYes.checked = false;
      if (els.approveInvoiceNo) els.approveInvoiceNo.checked = true;
    } else if (autoApproveFor === 0) {
      if (els.approveInvoiceYes) els.approveInvoiceYes.checked = true;
      if (els.approveInvoiceNo) els.approveInvoiceNo.checked = false;
    }
    if (!paymentOn) autoApproveFor = 0;
    const creditOpen = approved && hasCreditPayment() && !entryFieldsLocked;
    const lockPayments = entryFieldsLocked || (approved && !creditOpen);
    els.paymentWrap?.querySelectorAll("input, select, button, textarea").forEach(function (input) {
      if (lockPayments) {
        if (!input.dataset.approvalLocked) {
          input.dataset.approvalWasDisabled = input.disabled ? "1" : "0";
        }
        input.dataset.approvalLocked = "1";
        input.disabled = true;
      } else if (input.dataset.approvalLocked) {
        input.disabled = creditOpen ? false : input.dataset.approvalWasDisabled === "1";
        if (!creditOpen) {
          delete input.dataset.approvalLocked;
          delete input.dataset.approvalWasDisabled;
        }
      } else if (creditOpen) {
        input.disabled = false;
      }
    });
  }

  async function refreshInvoiceStatus() {
    const box = els.invoiceStatus;
    if (!box) return;
    const billNo = (els.billNo?.value || "").trim();
    if (!isStageChecked("tally_bill_generated") || !billNo || !window.FU_INVOICE_STATUS_URL) {
      lastSaleRecord = null;
      paintInvoiceStatus(null);
      syncGenerateBillPrompt(true);
      return;
    }
    try {
      const url = new URL(window.FU_INVOICE_STATUS_URL, window.location.origin);
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

  async function lookupGeneratedInvoice(billNo) {
    if (!billNo || !window.FU_INVOICE_STATUS_URL) return null;
    const url = new URL(window.FU_INVOICE_STATUS_URL, window.location.origin);
    url.searchParams.set("bill_no", billNo);
    const res = await fetch(url.toString(), { credentials: "same-origin" });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!data.ok || !data.found || !data.record) return null;
    return data.record;
  }

  async function declineGeneratedBill() {
    const billNo = (els.billNo?.value || "").trim();
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
    const res = await fetch(window.FU_INVOICE_DELETE_URL, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": window.FU_CSRF || csrfToken(),
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
    lastSaleRecord = null;
    resetGenerateBillChoice();
    paintInvoiceStatus(null);
    syncGenerateBillPrompt(true);
    if (window.JTCSDialog?.alert) {
      window.JTCSDialog.alert(data.message || "Related invoices deleted.", "success");
    }
  }

  function followupItemLabel() {
    const bits = [workTypeLabel];
    const formType = els.formType && els.formType.selectedIndex >= 0
      ? (els.formType.options[els.formType.selectedIndex].textContent || "").trim()
      : "";
    const quarter = els.quarter && els.quarter.selectedIndex >= 0
      ? (els.quarter.options[els.quarter.selectedIndex].textContent || "").trim()
      : "";
    if (formType && formType !== "— Select —" && !formType.startsWith("Select")) bits.push(formType);
    if (quarter && quarter !== "— Select —" && !quarter.startsWith("Select")) bits.push(quarter);
    return bits.filter(Boolean).join(" / ").slice(0, 200);
  }

  function openGenerateBillPopup() {
    if (!isStageChecked("tally_bill_generated")) return;
    const billNo = (els.billNo?.value || "").trim();
    const customerName = (els.customerSearch?.value || "").trim();
    if (!billNo) {
      alert("Bill Number is required before generating bill.");
      resetGenerateBillChoice();
      return;
    }
    if (!customerName) {
      alert("Please enter Customer Name before generating bill.");
      resetGenerateBillChoice();
      els.customerSearch?.focus();
      return;
    }
    const seed = {
      date: (els.workDate?.value || "").trim(),
      tax_year: (els.taxPeriod?.value || "").trim(),
      invoice_no: billNo,
      bill_no: billNo,
      tally_bill_no: billNo,
      customer_id: (els.customerId?.value || "").trim(),
      customer_name: customerName,
      item: followupItemLabel(),
      sub_work: followupItemLabel(),
      gst_rate_percent: "18",
      unit: "NOS",
      rate: "",
      state_code: "05",
    };
    seed.source = workTypeLabel;
    if (lastSaleRecord && lastSaleRecord.invoice_id) {
      seed.open_edit = true;
      seed.invoice_id = lastSaleRecord.invoice_id;
    }
    try {
      sessionStorage.setItem("oieMiscGenerateBill", JSON.stringify(seed));
    } catch (_err) {
      /* ignore quota errors */
    }
    const url = window.FU_GENERATE_BILL_URL || "/activities/miscellaneous/generate-bill";
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
      if (existing && seed.open_edit) {
        const frame = existing.querySelector("iframe");
        if (frame) frame.src = url;
      }
      return;
    }
    alert("Generate Bill could not be opened in this page. Refresh and try again.");
    resetGenerateBillChoice();
  }

  function formatInrAmount(value) {
    const amount = Number(value);
    const safe = Number.isFinite(amount) ? amount : 0;
    return "₹" + safe.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  let billSummarySeq = 0;

  function syncCustomerBillSummary() {
    const box = document.getElementById("fuCustomerBillSummary");
    if (!box) return;
    const show = !!(els.generateBillYes && els.generateBillYes.checked);
    box.classList.toggle("d-none", !show);
    if (!show) {
      box.innerHTML = "";
      return;
    }
    const customerId = (els.customerId?.value || "").trim();
    if (!customerId || !window.FU_CUSTOMER_BILL_SUMMARY_URL) {
      box.innerHTML = '<div class="small text-muted">Select a customer to see previous bills.</div>';
      return;
    }
    const seq = ++billSummarySeq;
    box.innerHTML = '<div class="small text-muted">Loading previous bills…</div>';
    const url = new URL(window.FU_CUSTOMER_BILL_SUMMARY_URL, window.location.origin);
    url.searchParams.set("customer_id", customerId);
    fetch(url.toString(), { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (seq !== billSummarySeq) return;
        if (!data.ok) throw new Error(data.error || "Unable to load previous bills.");
        const overdue = Number(data.overdue_amount) || 0;
        box.innerHTML =
          '<div><span class="text-muted">Cumulative Bill Amount</span><br><strong>' +
          formatInrAmount(data.invoice_total) +
          "</strong></div>" +
          '<div class="mt-1"><span class="text-muted">Cumulative Payment Received Amount</span><br><strong>' +
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

  function markTallyBillGenerated() {
    const tallyCb = els.workflowChecks?.querySelector(
      '.fu-stage-check[data-stage-code="tally_bill_generated"]'
    );
    if (tallyCb) tallyCb.checked = true;
  }

  function fetchNextTallyBillNo() {
    const api = window.FU_API && window.FU_API.next_bill_no;
    if (!api || !els.billNo || (els.billNo.value || "").trim()) return;
    const workDate = (els.workDate?.value || "").trim();
    const url = api + (api.indexOf("?") >= 0 ? "&" : "?") + "work_date=" + encodeURIComponent(workDate);
    fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (data.ok && els.billNo && !(els.billNo.value || "").trim()) {
          els.billNo.value = data.bill_no || "";
        }
      })
      .catch(function () { /* server fills the number on save */ });
  }

  function syncWorkflowPanels() {
    const returnChecked = isStageChecked("return_filed") || isStageChecked("itr_filed");
    const tallyChecked = isStageChecked("tally_bill_generated");
    const paymentChecked = isStageChecked("payment_received");
    els.itrFiledWrap?.classList.toggle("d-none", !returnChecked);
    if (!isTaxFollowup) {
      els.tallyBillWrap?.classList.remove("d-none");
      refreshInvoiceStatus();
    }
    els.paymentWrap?.classList.toggle("d-none", !paymentChecked);
    if (paymentChecked && !els.paymentLines?.querySelector(".fu-payment-line")) {
      resetPaymentLines([]);
    }
    if (returnChecked && els.itrFiledDate && !els.itrFiledDate.value) {
      els.itrFiledDate.value = window.FU_DEFAULT_DATE || new Date().toISOString().slice(0, 10);
    }
    if (!isTaxFollowup && tallyChecked && els.billDate && !els.billDate.value) {
      els.billDate.value = window.FU_DEFAULT_DATE || new Date().toISOString().slice(0, 10);
    }
    if (!isTaxFollowup && els.billNo && !(els.billNo.value || "").trim()) {
      fetchNextTallyBillNo();
    }
    if (!isTaxFollowup) syncCustomerBillSummary();
    syncUnverifiedPanel();
    syncBillingCustomerPanel();
    syncDscApplicationField();
    if (!isTaxFollowup) syncGenerateBillPrompt();
  }

  function syncUnverifiedPanel() {
    const unverified = els.workflowChecks?.querySelector('.fu-stage-check[data-stage-code="unverified"]');
    const show = !!(unverified && unverified.checked);
    els.unverifiedWrap?.classList.toggle("d-none", !show);
  }

  let lastFollowupCustomerId = "";

  function clearCustomerSelection() {
    if (els.customerId) els.customerId.value = "";
    if (els.customerSearch) els.customerSearch.value = "";
    if (els.customerSelected) {
      els.customerSelected.textContent = "";
      els.customerSelected.classList.add("d-none");
    }
    if (els.customerEmail) els.customerEmail.value = "";
    if (hasGstFields && els.filingFrequency) els.filingFrequency.value = "";
    hideCustomerResults();
    syncCustomerBillSummary();
    onFollowupCustomerChanged("");
  }

  function hideCustomerResults() {
    if (!els.customerResults) return;
    els.customerResults.classList.add("d-none");
    els.customerResults.innerHTML = "";
  }

  function selectCustomer(customer) {
    if (!customer) return;
    const newId = String(customer.customer_id || customer.CustomerID || "").trim();
    if (els.customerId) els.customerId.value = newId;
    if (els.customerSearch) {
      els.customerSearch.value = customer.customer_name || customer.CustomerName || "";
    }
    if (els.customerSelected) {
      const mobile = customer.mobile_number || customer.MobileNumber || "";
      const pan = customer.pan_number || customer.PANNumber || "";
      const parts = [mobile, pan];
      if (isDscModule) {
        const email = customer.email_id || customer.EmailID || "";
        if (email) parts.push(email);
      }
      els.customerSelected.textContent = parts.filter(Boolean).join(" · ");
      els.customerSelected.classList.remove("d-none");
    }
    if (isDscModule && els.customerEmail) {
      els.customerEmail.value = customer.email_id || customer.EmailID || "";
    }
    if (hasGstFields && els.filingFrequency) {
      els.filingFrequency.value =
        customer.filing_frequency || customer.FilingFrequency || "";
    }
    hideCustomerResults();
    syncCustomerBillSummary();
    onFollowupCustomerChanged(newId);
  }

  function onFollowupCustomerChanged(newId) {
    const next = String(newId || "").trim();
    const prev = lastFollowupCustomerId;
    if (!next) {
      lastFollowupCustomerId = "";
      clearBillingChoice();
      syncBillingCustomerPanel();
      return;
    }
    if (prev && prev !== next) {
      clearBillingChoice();
    }
    lastFollowupCustomerId = next;
    syncBillingCustomerPanel();
  }

  function normalizeReturnTypeValue(value) {
    if (!value || value === "Original") return "Original";
    if (value === "Revised") return "Revised1";
    const match = String(value).match(/^Revised(\d+)$/i);
    if (match) return "Revised" + match[1];
    return "Original";
  }

  function resetEntryForm() {
    if (els.entryForm) els.entryForm.reset();
    if (els.entryId) els.entryId.value = "";
    if (els.workDate) {
      els.workDate.value = new Date().toISOString().slice(0, 10);
    }
    if (els.taxPeriod && window.FU_DEFAULT_TAX_PERIOD) {
      els.taxPeriod.value = window.FU_DEFAULT_TAX_PERIOD;
    }
    if (els.gstMonth && window.FU_DEFAULT_GST_MONTH) {
      els.gstMonth.value = window.FU_DEFAULT_GST_MONTH;
    }
    if (els.formType) els.formType.value = "";
    if (els.quarter) els.quarter.value = "";
    if (els.applicationNumber) {
      els.applicationNumber.value = "";
      delete els.applicationNumber.dataset.locked;
    }
    if (els.location) els.location.value = "";
    if (els.introducedBy) els.introducedBy.value = "";
    if (els.dscType) els.dscType.value = "";
    if (els.dscClass) els.dscClass.value = "";
    if (els.dscYear) els.dscYear.value = "";
    clearCustomerSelection();
    els.workflowChecks?.querySelectorAll(".fu-stage-check").forEach(function (cb) {
      cb.checked = false;
    });
    if (els.reasonUnverified) els.reasonUnverified.value = "";
    if (els.remarks) els.remarks.value = "";
    if (els.itrFiledDate) els.itrFiledDate.value = window.FU_DEFAULT_DATE || new Date().toISOString().slice(0, 10);
    if (els.billNo) els.billNo.value = "";
    if (els.billDate) els.billDate.value = window.FU_DEFAULT_DATE || new Date().toISOString().slice(0, 10);
    if (els.billAmount) els.billAmount.value = "";
    resetPaymentLines([]);
    if (els.returnType) els.returnType.value = "Original";
    if (els.gstReturnType) els.gstReturnType.value = "";
    if (els.filingFrequency) els.filingFrequency.value = "";
    syncWorkflowPanels();
    savedPaymentReceived = false;
    creatingInvoice = false;
    paintInvoiceSummary(null);
    resetBillingCustomer();
    if (els.entryModalTitle) {
      els.entryModalTitle.textContent = workTypeLabel + " — Entry";
    }
  }

  function syncStatCardActive() {
    const current = (els.statusFilter?.value || "").trim();
    document.querySelectorAll(".fu-stat-card[data-status-filter]").forEach(function (card) {
      const value = (card.getAttribute("data-status-filter") || "").trim();
      card.classList.toggle("is-active", value === current);
    });
  }

  function updateStats(stats) {
    if (!stats) return;
    if (els.statTotal) els.statTotal.textContent = String(stats.total || 0);
    if (els.statPending) els.statPending.textContent = String(stats.pending || 0);
    if (els.statPaymentPending) els.statPaymentPending.textContent = String(stats.payment_pending || 0);
    if (els.gridMeta) {
      if (isItrModule) {
        els.gridMeta.textContent =
          "Total: " + (stats.total || 0) +
          " | Received: " + (stats.payment_received || 0);
      } else {
        els.gridMeta.textContent =
          "Total: " + (stats.total || 0) + " | Pending: " + (stats.pending || 0) +
          " | Received: " + (stats.payment_received || 0);
      }
    }
    const byStatus = stats.by_status || {};
    document.querySelectorAll(".fu-stat-stage").forEach(function (el) {
      const name = el.dataset.stageName || "";
      el.textContent = String(byStatus[name] || 0);
    });
    syncStatCardActive();
  }

  function applyItrDefaultStatusFilter() {
    if (!isItrModule || !els.statusFilter) return;
    // Default grid = yellow Pending card (Documents Received current stage).
    els.statusFilter.value = "documents_received";
  }

  function clearFilters() {
    if (els.searchInput) els.searchInput.value = "";
    if (els.statusFilter) {
      els.statusFilter.value = isItrModule ? "documents_received" : "";
    }
    if (els.returnTypeFilter) els.returnTypeFilter.value = "";
    if (els.dateFromFilter) els.dateFromFilter.value = "";
    if (els.dateToFilter) els.dateToFilter.value = "";
    if (els.periodFilter) els.periodFilter.value = "";
    if (isItrModule) {
      gridSortKey = "created_date";
      gridSortDir = "asc";
      updateItrSortHeaders();
    }
    syncStatCardActive();
    loadGrid();
  }

  function itrSortableColumns() {
    const cols = [
      { key: "work_date", type: "date" },
      { key: "tax_period", type: "text" },
      { key: "customer_name", type: "text" },
      { key: "mobile_number", type: "text" },
      { key: "pan_number", type: "text" },
      { key: "_work_type", type: "text" },
    ];
    if (hasReturnType) cols.push({ key: "return_type", type: "text" });
    if (isItrModule) {
      cols.push(
        { key: "return_filing_status", type: "text" },
        { key: "filing_date", type: "date" }
      );
    }
    cols.push({ key: "workflow_status", type: "text" });
    if (isItrModule) {
      cols.push({ key: "payment_receive_date", type: "text" });
    }
    cols.push({ key: "remarks", type: "text" });
    return cols;
  }

  function itrSortValue(row, col) {
    if (col.key === "_work_type") return workTypeLabel;
    const raw = row[col.key];
    if (raw == null || raw === "") return col.type === "text" ? "" : null;
    if (col.type === "date") return String(raw).slice(0, 10) || null;
    return String(raw).toLowerCase();
  }

  function compareItrRows(a, b, col, dir) {
    const av = itrSortValue(a, col);
    const bv = itrSortValue(b, col);
    const mul = dir === "asc" ? 1 : -1;
    if (col.type === "date") {
      if (!av && !bv) return 0;
      if (!av) return 1;
      if (!bv) return -1;
      if (av < bv) return -1 * mul;
      if (av > bv) return 1 * mul;
      return 0;
    }
    return String(av || "").localeCompare(String(bv || ""), undefined, {
      numeric: true,
      sensitivity: "base",
    }) * mul;
  }

  function compareItrEntryDateTime(a, b, dir) {
    // Oldest entry date/time at top when dir === "asc".
    const mul = dir === "asc" ? 1 : -1;
    const av = String(a.created_date || a.CreatedDate || a.work_date || a.WorkDate || "");
    const bv = String(b.created_date || b.CreatedDate || b.work_date || b.WorkDate || "");
    if (av && bv && av !== bv) {
      if (av < bv) return -1 * mul;
      if (av > bv) return 1 * mul;
    } else if (av && !bv) {
      return -1 * mul;
    } else if (!av && bv) {
      return 1 * mul;
    }
    const aid = parseInt(a.entry_id || a.EntryID || 0, 10) || 0;
    const bid = parseInt(b.entry_id || b.EntryID || 0, 10) || 0;
    if (aid < bid) return -1 * mul;
    if (aid > bid) return 1 * mul;
    return 0;
  }

  function applyItrGridSort(dataRows) {
    if (!isItrModule) return dataRows;
    if (!gridSortKey || gridSortKey === "created_date") {
      const dir = gridSortKey ? gridSortDir : "asc";
      return dataRows.slice().sort(function (a, b) {
        return compareItrEntryDateTime(a, b, dir);
      });
    }
    const col = itrSortableColumns().find(function (item) { return item.key === gridSortKey; });
    if (!col) {
      return dataRows.slice().sort(function (a, b) {
        return compareItrEntryDateTime(a, b, "asc");
      });
    }
    return dataRows.slice().sort(function (a, b) {
      const primary = compareItrRows(a, b, col, gridSortDir);
      if (primary !== 0) return primary;
      return compareItrEntryDateTime(a, b, "asc");
    });
  }

  function updateItrSortHeaders() {
    if (!isItrModule) return;
    const table = document.getElementById("fuDataGrid");
    if (!table) return;
    table.querySelectorAll("thead th.fu-sortable").forEach(function (th) {
      const key = th.dataset.sortKey;
      const icon = th.querySelector(".fu-sort-icon");
      const active = key === gridSortKey;
      th.classList.toggle("fu-sorted", active);
      th.classList.toggle("fu-sorted-asc", active && gridSortDir === "asc");
      th.classList.toggle("fu-sorted-desc", active && gridSortDir === "desc");
      th.setAttribute(
        "aria-sort",
        active ? (gridSortDir === "asc" ? "ascending" : "descending") : "none"
      );
      if (icon) icon.textContent = active ? (gridSortDir === "asc" ? " \u25B2" : " \u25BC") : "";
    });
  }

  function initItrGridSortHeaders() {
    if (!isItrModule) return;
    const table = document.getElementById("fuDataGrid");
    if (!table) return;
    const headers = table.querySelectorAll("thead tr th");
    const cols = itrSortableColumns();
    headers.forEach(function (th, index) {
      if (index >= cols.length) return;
      const col = cols[index];
      th.classList.add("fu-sortable");
      th.dataset.sortKey = col.key;
      th.setAttribute("role", "button");
      th.setAttribute("tabindex", "0");
      if (!th.querySelector(".fu-sort-icon")) {
        const icon = document.createElement("span");
        icon.className = "fu-sort-icon";
        icon.setAttribute("aria-hidden", "true");
        th.appendChild(icon);
      }
    });
    updateItrSortHeaders();
  }

  function onItrSortHeaderClick(sortKey) {
    if (!isItrModule || !sortKey) return;
    if (gridSortKey === sortKey) {
      gridSortDir = gridSortDir === "asc" ? "desc" : "asc";
    } else {
      gridSortKey = sortKey;
      gridSortDir = "asc";
    }
    updateItrSortHeaders();
    renderGrid();
  }

  function compareDscWorkDateDesc(a, b) {
    const av = String(a.work_date || a.WorkDate || "").slice(0, 10);
    const bv = String(b.work_date || b.WorkDate || "").slice(0, 10);
    if (av && bv && av !== bv) {
      if (av < bv) return 1;
      if (av > bv) return -1;
    } else if (av && !bv) {
      return -1;
    } else if (!av && bv) {
      return 1;
    }
    const aid = parseInt(a.entry_id || a.EntryID || 0, 10) || 0;
    const bid = parseInt(b.entry_id || b.EntryID || 0, 10) || 0;
    return bid - aid;
  }

  function applyDscGridSort(dataRows) {
    if (!isDscModule) return dataRows;
    return dataRows.slice().sort(function (a, b) {
      const aLocked = rowHasPaymentReceived(a) ? 1 : 0;
      const bLocked = rowHasPaymentReceived(b) ? 1 : 0;
      if (aLocked !== bLocked) return aLocked - bLocked;
      return compareDscWorkDateDesc(a, b);
    });
  }

  function applyGridSort(dataRows) {
    if (isDscModule) return applyDscGridSort(dataRows);
    return applyItrGridSort(dataRows);
  }

  function invoiceGridCell(row) {
    const invoice = row.linked_invoice;
    if (!invoice || !invoice.invoice_id || !window.JtcsInvoiceActions) {
      return "<td>—</td>";
    }
    return (
      '<td data-followup-entry-id="' + escapeHtml(row.entry_id) + '">' +
      window.JtcsInvoiceActions.summaryHtml(invoice) +
      "</td>"
    );
  }

  function renderGrid(data) {
    if (data) rawGridRows = data;
    rows = applyGridSort(rawGridRows);
    if (!els.gridBody) return;
    if (!rows.length) {
      els.gridBody.innerHTML = "";
      els.gridEmpty?.classList.remove("d-none");
      if (els.gridCount) els.gridCount.textContent = "0 records";
      return;
    }
    els.gridEmpty?.classList.add("d-none");
    if (els.gridCount) els.gridCount.textContent = rows.length + " record" + (rows.length === 1 ? "" : "s");

    els.gridBody.innerHTML = rows.map(function (row) {
      const status = row.workflow_status || "Pending";
      const returnCol = hasReturnType
        ? "<td>" + escapeHtml(row.return_type || "—") + "</td>"
        : "";
      const filingCols = isItrModule
        ? ("<td>" + escapeHtml(row.return_filing_status || "—") + "</td>" +
           "<td>" + escapeHtml(formatDate(row.filing_date) || "—") + "</td>")
        : "";
      const periodCol = (isItrModule || isTdsModule)
        ? "<td>" + escapeHtml(row.tax_period || "—") + "</td>"
        : "";
      const gstCaseCols = isGstModule
        ? ("<td>" + escapeHtml(row.gst_month || "—") + "</td>" +
           "<td>" + escapeHtml(row.tax_period || "—") + "</td>")
        : "";
      const tdsPeriodCols = isTdsModule
        ? ("<td>" + escapeHtml(row.form_type || "—") + "</td>" +
           "<td>" + escapeHtml(row.quarter || "—") + "</td>")
        : "";
      const gstFieldCols = hasGstFields
        ? ("<td>" + escapeHtml(row.filing_frequency || "—") + "</td>" +
           "<td>" + escapeHtml(row.return_type || "—") + "</td>")
        : "";
      const paymentLocked = isItrPaymentReceivedLocked(row);
      const thankYouCell = thankYouCellHtml(row);
      const paymentReminderCell = isItrModule
        ? (canDownloadPaymentReminder(row)
          ? '<td class="text-center">' +
            '<a class="btn btn-outline-warning btn-sm fu-pay-remind-btn' +
            (paymentLocked ? " disabled" : "") +
            '" href="' +
            escapeHtml(apiUrl(window.FU_API.payment_reminder, row.entry_id)) +
            '" title="Download Payment Reminder (PNG)" download' +
            (paymentLocked ? ' aria-disabled="true" tabindex="-1"' : "") +
            ">" +
            '<i class="bi bi-bell-fill"></i></a></td>'
          : '<td class="text-center text-muted" title="Available after Invoice">—</td>')
        : "";
      const rowSyncCell = isItrModule
        ? '<td class="fu-row-sync-cell">' +
          '<button type="button" class="btn btn-success btn-sm fu-kdk-row-sync" data-id="' +
          row.entry_id +
          '" data-customer="' + escapeHtml(row.customer_name || "") +
          '" data-pan="' + escapeHtml(row.pan_number || "") +
          '" data-period="' + escapeHtml(row.tax_period || "") +
          '" title="' +
          (paymentLocked ? "Locked after Payment Received" : "Sync this client from KDK") +
          '"' +
          (paymentLocked ? " disabled" : "") +
          ">" +
          '<i class="bi bi-arrow-repeat"></i> Sync</button></td>'
        : "";
      const appNo = (row.application_number || row.bill_no || "").toString().trim();
      const workOrCheckCell = isDscModule
        ? '<td class="fu-check-status-cell">' +
          '<button type="button" class="btn btn-outline-secondary btn-sm fu-status-sync" data-id="' +
          row.entry_id +
          '" data-app-no="' +
          escapeHtml(appNo) +
          '" title="Sync ID Sign status into Remarks"' +
          (appNo ? "" : " disabled") +
          '><i class="bi bi-arrow-repeat"></i></button>' +
          "</td>"
        : "<td>" + escapeHtml(workTypeLabel) + "</td>";
      const videoLocked = isDscModule && rowHasPaymentReceived(row);
      const videoLinkCell = isDscModule
        ? '<td class="fu-copy-cell fu-video-link-cell">' +
          '<button type="button" class="fu-copy-btn fu-video-link-copy' +
          (videoLocked ? " fu-video-link-locked" : "") +
          '" title="' +
          (videoLocked ? "Video Link locked after Payment Received" : "Copy Video Link") +
          '" aria-label="' +
          (videoLocked ? "Video Link locked" : "Copy Video Link") +
          '" data-app-no="' +
          escapeHtml(appNo) +
          '" data-mobile="' +
          escapeHtml(row.mobile_number || "") +
          '"' +
          (videoLocked ? " disabled" : "") +
          '><i class="' +
          (videoLocked ? "bi bi-x-lg" : "bi bi-copy") +
          '"></i></button></td>'
        : "";
      const deleteDisabledAttrs = rowHasPaymentReceived(row)
        ? ' disabled title="Remove Payment Received in Edit, then Delete will enable"'
        : ' title="Delete"';
      const editTitle = "Edit";
      const appNoValue = isDscModule
        ? (row.application_number || row.bill_no || "")
        : (row.bill_no || "");
      const dscMix = [row.dsc_type, row.dsc_class, row.dsc_year]
        .map(function (part) { return String(part || "").trim(); })
        .filter(Boolean)
        .join(" / ");
      const actionsCell =
        '<td class="text-nowrap fu-grid-actions">' +
        '<button type="button" class="btn btn-outline-primary btn-sm fu-edit-btn" data-id="' +
        row.entry_id +
        '" title="' +
        editTitle +
        '"><i class="bi bi-pencil"></i></button> ' +
        '<button type="button" class="btn btn-outline-danger btn-sm fu-delete-btn" data-id="' +
        row.entry_id +
        '"' +
        deleteDisabledAttrs +
        '><i class="bi bi-trash"></i></button>' +
        "</td>";
      const mobileCell = isDscModule
        ? copyableCell(row.mobile_number)
        : "<td>" + escapeHtml(row.mobile_number || "—") + "</td>";
      const emailCell = isDscModule ? copyableCell(row.email_id) : "";
      const panCell = isDscModule
        ? copyableCell(row.pan_number)
        : "<td>" + escapeHtml(row.pan_number || "—") + "</td>";
      const aadhaarCell = isDscModule ? copyableCell(row.aadhaar_number) : "";
      const appOrBillCell = isDscModule ? copyableCell(appNoValue) : "";
      return (
        '<tr' + (paymentLocked ? ' class="fu-payment-received-row"' : "") + ">" +
        (isDscModule ? actionsCell : "") +
        "<td>" + escapeHtml(formatDate(row.work_date)) + "</td>" +
        (isDscModule ? "<td>" + escapeHtml(dscMix || "—") + "</td>" : "") +
        periodCol +
        tdsPeriodCols +
        gstFieldCols +
        (isDscModule
          ? copyableCell(row.customer_name)
          : "<td><strong>" + escapeHtml(row.customer_name) + "</strong></td>") +
        gstCaseCols +
        (isDscModule ? copyableCell(row.employee_code) : "") +
        (isDscModule
          ? copyableCell(row.date_of_birth ? formatDate(row.date_of_birth) : "")
          : "") +
        mobileCell +
        emailCell +
        panCell +
        aadhaarCell +
        appOrBillCell +
        (isDscModule ? "<td>" + escapeHtml(formatDate(row.bill_date)) + "</td>" : "") +
        workOrCheckCell +
        videoLinkCell +
        returnCol +
        filingCols +
        invoiceGridCell(row) +
        '<td><span class="fu-status-badge ' + statusBadgeClass(status) + '">' + escapeHtml(status) + "</span>" +
        (row.sale_invoice
          ? '<div class="small mt-1">' +
            escapeHtml(row.sale_invoice.bill_status) +
            " · Payment " +
            escapeHtml(row.sale_invoice.payment_received) +
            "</div>"
          : "") +
        "</td>" +
        (isItrModule
          ? "<td>" + escapeHtml(formatPaymentReceiveDateCell(row)) + "</td>"
          : "") +
        remarksCellHtml(row) +
        paymentReminderCell +
        rowSyncCell +
        "<td>" + thankYouCell + "</td>" +
        (isDscModule ? "" : actionsCell) +
        "</tr>"
      );
    }).join("");
  }

  function loadGrid() {
    const params = new URLSearchParams();
    const search = (els.searchInput?.value || "").trim();
    const status = (els.statusFilter?.value || "").trim();
    const period = (els.periodFilter?.value || "").trim();
    const returnType = (els.returnTypeFilter?.value || "").trim();
    const dateFrom = (els.dateFromFilter?.value || "").trim();
    const dateTo = (els.dateToFilter?.value || "").trim();
    if (search) params.set("search", search);
    if (status) params.set("status", status);
    if (period) params.set("tax_period", period);
    if (returnType) params.set("return_type", returnType);
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    const url = window.FU_API.grid + (params.toString() ? "?" + params.toString() : "");
    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) {
        const contentType = res.headers.get("content-type") || "";
        if (!res.ok || !contentType.includes("application/json")) {
          throw new Error(
            res.ok
              ? "Invalid server response. Restart Flask and run: python scripts/apply_followup_billing.py"
              : "Unable to load followup records (HTTP " + res.status + "). Restart Flask server."
          );
        }
        return res.json();
      })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "Unable to load grid.");
        renderGrid(data.rows);
        updateStats(data.stats);
      })
      .catch(function (err) {
        console.error(err);
        alert(err.message || "Unable to load followup records.");
      });
  }

  function openNewEntry() {
    hideInvoiceEditor();
    resetEntryForm();
    setEntryFieldsLocked(false);
    entryModal?.show();
  }

  function fillEntryForm(record) {
    hideInvoiceEditor();
    resetEntryForm();
    if (!record) return;
    if (els.entryId) els.entryId.value = String(record.entry_id || "");
    if (els.workDate) els.workDate.value = (record.work_date || "").slice(0, 10);
    if (els.taxPeriod) els.taxPeriod.value = record.tax_period || "";
    if (els.gstMonth) els.gstMonth.value = record.gst_month || "";
    if (isTdsModule) {
      if (els.formType) {
        const formType = record.form_type || "";
        const hasOption = Array.from(els.formType.options).some(function (opt) {
          return opt.value === formType;
        });
        els.formType.value = hasOption ? formType : "";
      }
      if (els.quarter) els.quarter.value = record.quarter || "";
    }
    if (isDscModule && els.applicationNumber) {
      const appNo = record.application_number || "";
      els.applicationNumber.value = appNo;
      if (record.application_locked || appNo) {
        els.applicationNumber.dataset.locked = "1";
      } else {
        delete els.applicationNumber.dataset.locked;
      }
      if (els.billNo) els.billNo.value = record.bill_no || "";
    } else if (els.applicationNumber) {
      els.applicationNumber.value = record.bill_no || record.application_number || "";
    }
    if (els.location) els.location.value = record.location || "";
    if (els.introducedBy) els.introducedBy.value = record.introduced_by || "";
    if (els.dscType) els.dscType.value = record.dsc_type || "";
    if (els.dscClass) els.dscClass.value = record.dsc_class || "";
    if (els.dscYear) els.dscYear.value = record.dsc_year || "";
    if (els.itrFiledDate) els.itrFiledDate.value = (record.itr_filed_date || "").slice(0, 10);
    if (!isDscModule && els.billNo) els.billNo.value = record.bill_no || "";
    if (els.billDate) els.billDate.value = (record.bill_date || "").slice(0, 10);
    if (els.billAmount && record.bill_amount != null) els.billAmount.value = record.bill_amount;
    resetPaymentLines(record.payments || []);
    if (els.remarks) els.remarks.value = record.remarks || "";
    if (els.reasonUnverified) els.reasonUnverified.value = record.reason_for_unverified || "";
    if (record.customer_id) {
      selectCustomer({
        customer_id: record.customer_id,
        customer_name: record.customer_name,
        mobile_number: record.mobile_number,
        pan_number: record.pan_number,
        email_id: record.email_id,
        filing_frequency: record.filing_frequency,
      });
    }
    if (hasReturnType && els.returnType) {
      const normalized = normalizeReturnTypeValue(record.return_type);
      if (!els.returnType.querySelector('option[value="' + normalized + '"]')) {
        const option = document.createElement("option");
        option.value = normalized;
        option.textContent = normalized;
        els.returnType.appendChild(option);
      }
      els.returnType.value = normalized;
    }
    if (hasGstFields && els.gstReturnType) {
      els.gstReturnType.value = record.return_type || "";
    }
    function stageTickKey(value) {
      const aliases = {
        gstr1_filed: "return_filed",
        gstr3b_filed: "return_filed",
        itr_filed: "return_filed",
        application_no: "application_received",
      };
      const key = String(value || "").trim().toLowerCase().replace(/\s+/g, "_");
      if (isTaxFollowup && (key === "tally_bill_generated" || key === "tally_bill")) {
        return "invoice";
      }
      if (isTdsModule && key === "kyc") return "return_filed";
      return aliases[key] || key;
    }
    function tickStage(value) {
      const key = stageTickKey(value);
      if (!key) return;
      let cb = els.workflowChecks?.querySelector('.fu-stage-check[data-stage-code="' + key + '"]');
      if (!cb) cb = els.workflowChecks?.querySelector('.fu-stage-check[value="' + key + '"]');
      if (cb) cb.checked = true;
    }
    (record.stage_ids || []).forEach(tickStage);
    (record.completed_stages || []).forEach(function (stage) {
      tickStage(stage.StageCode || stage.stage_code || stage.StageName || stage.stage_name || "");
    });
    syncWorkflowPanels();
    savedPaymentReceived = isStageChecked("payment_received");
    paintInvoiceSummary(record.linked_invoice || null);
    const invoiceCb = invoiceStageCheckbox();
    lastFollowupCustomerId = record.customer_id ? String(record.customer_id) : "";
    if (linkedInvoice) {
      applyBillingChoice(record);
    } else {
      if (invoiceCb) invoiceCb.checked = false;
      const savedType = String(record.billing_type || "").trim().toUpperCase();
      if (savedType === "SAME_CUSTOMER" && els.billingSame) {
        els.billingSame.checked = true;
        if (els.billingOther) els.billingOther.checked = false;
        if (els.billingCustomerId) els.billingCustomerId.value = "";
        if (els.billingCustomerSearch) els.billingCustomerSearch.value = "";
      } else if (savedType === "OTHER_CUSTOMER" && els.billingOther) {
        els.billingOther.checked = true;
        if (els.billingSame) els.billingSame.checked = false;
        if (els.billingCustomerId) {
          els.billingCustomerId.value = record.billing_customer_id
            ? String(record.billing_customer_id)
            : "";
        }
        if (els.billingCustomerSearch) {
          els.billingCustomerSearch.value = record.billing_customer_name || "";
        }
      } else {
        clearBillingChoice();
      }
      syncBillingCustomerPanel();
    }
    syncWorkflowPanels();
    setEntryFieldsLocked(true);
    if (els.entryModalTitle) {
      els.entryModalTitle.textContent = workTypeLabel + " — Edit Entry";
    }
    entryModal?.show();
  }

  function invoiceStageCheckbox() {
    return els.workflowChecks?.querySelector('.fu-stage-check[data-stage-code="invoice"]') || null;
  }

  function formatInvoiceAmount(value) {
    const amount = Number(value || 0);
    return "₹" + amount.toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  let paymentAdjustToken = 0;

  function paintInvoiceSummary(invoice) {
    linkedInvoice = invoice && invoice.invoice_id ? invoice : null;
    const box = document.getElementById("fuInvoiceSummary");
    const createBtn = document.getElementById("fuCreateInvoiceBtn");
    if (createBtn) createBtn.classList.toggle("d-none", !!linkedInvoice);
    document.querySelectorAll("#fuInvoiceActions .fu-inv-act").forEach(function (btn) {
      btn.classList.toggle("d-none", !linkedInvoice);
    });
    if (!box) return;
    if (!linkedInvoice) {
      paymentAdjustToken += 1;
      box.classList.add("d-none");
      paintPaymentAdjustment(null);
      return;
    }
    box.classList.remove("d-none");
    const no = document.getElementById("fuInvoiceNo");
    const dt = document.getElementById("fuInvoiceDate");
    const amt = document.getElementById("fuInvoiceAmount");
    if (no) no.textContent = linkedInvoice.invoice_no || "—";
    if (dt) dt.textContent = formatDate(linkedInvoice.invoice_date);
    if (amt) amt.textContent = formatInvoiceAmount(linkedInvoice.invoice_value);
    loadPaymentAdjustment(linkedInvoice.invoice_id);
  }

  function paymentAdjustLine(label, amount) {
    return (
      "<div><span class=\"fu-pay-label\">" +
      escapeHtml(label) +
      "</span> <strong>" +
      escapeHtml(formatInvoiceAmount(amount)) +
      "</strong></div>"
    );
  }

  function paintPaymentAdjustment(adjustment) {
    const body = document.getElementById("fuPaymentAdjustBody");
    if (!body) return;
    if (!linkedInvoice) {
      body.innerHTML = "";
      return;
    }
    if (!adjustment || !adjustment.has_allocation) {
      let html = "<div class=\"fu-pay-status\">Payment Not Received</div>";
      if (adjustment) {
        html += paymentAdjustLine("Customer Total Sale Amount", adjustment.customer_total_sale);
        html += paymentAdjustLine("Customer Total Received Amount", adjustment.customer_total_received);
        html += paymentAdjustLine("Customer Outstanding Amount", adjustment.customer_outstanding);
      }
      body.innerHTML = html;
      return;
    }
    const entries = Array.isArray(adjustment.entries) ? adjustment.entries : [];
    let html = "";
    html += paymentAdjustLine("Money In/Out Amount Adjusted", adjustment.money_inout_transaction_amount);
    html += paymentAdjustLine("Amount Adjusted to This Invoice", adjustment.allocated_amount);
    html += paymentAdjustLine("Remaining Amount from This Money In/Out Entry", adjustment.remaining_money_inout_amount);
    if (entries.length > 1) {
      html += "<details class=\"fu-pay-details\"><summary>Details</summary>";
      entries.forEach(function (entry) {
        html +=
          "<div class=\"fu-pay-entry\">" +
          "<div><strong>" + escapeHtml(formatDate(entry.work_date)) + "</strong></div>" +
          paymentAdjustLine("Money In/Out Amount Adjusted", entry.money_inout_transaction_amount) +
          paymentAdjustLine("Amount Adjusted to This Invoice", entry.allocated_amount) +
          paymentAdjustLine("Remaining Amount from This Money In/Out Entry", entry.remaining_money_inout_amount) +
          "</div>";
      });
      html += "</details>";
    }
    html += paymentAdjustLine("Customer Total Sale Amount", adjustment.customer_total_sale);
    html += paymentAdjustLine("Customer Total Received Amount", adjustment.customer_total_received);
    html += paymentAdjustLine("Customer Outstanding Amount", adjustment.customer_outstanding);
    body.innerHTML = html;
  }

  function loadPaymentAdjustment(invoiceId) {
    const id = parseInt(invoiceId, 10);
    const body = document.getElementById("fuPaymentAdjustBody");
    if (!id || id <= 0) {
      paintPaymentAdjustment(null);
      return;
    }
    const token = ++paymentAdjustToken;
    if (body) body.innerHTML = "";
    fetch("/accounting/api/invoices/" + id + "/payment-adjustment", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, data: data };
        });
      })
      .then(function (result) {
        if (token !== paymentAdjustToken) return;
        if (!result.ok || !result.data || !result.data.ok) {
          paintPaymentAdjustment(null);
          return;
        }
        paintPaymentAdjustment(result.data.adjustment || null);
      })
      .catch(function () {
        if (token !== paymentAdjustToken) return;
        paintPaymentAdjustment(null);
      });
  }

  function clearInvoiceTickIfUnsaved() {
    if (linkedInvoice) return;
    if (billingChoice()) {
      syncWorkflowPanels();
      return;
    }
    const cb = invoiceStageCheckbox();
    if (!cb || !cb.checked) return;
    cb.checked = false;
    syncWorkflowPanels();
    if ((els.entryId?.value || "").trim()) {
      saveEntry({ keepOpen: true });
    }
  }

  function billingChoice() {
    if (els.billingSame && els.billingSame.checked) return "SAME_CUSTOMER";
    if (els.billingOther && els.billingOther.checked) return "OTHER_CUSTOMER";
    return "";
  }

  function billingIsOther() {
    return billingChoice() === "OTHER_CUSTOMER";
  }

  function selectedBillingCustomerId() {
    if (billingChoice() === "OTHER_CUSTOMER") return (els.billingCustomerId?.value || "").trim();
    if (billingChoice() === "SAME_CUSTOMER") return (els.customerId?.value || "").trim();
    return "";
  }

  function clearBillingChoice() {
    if (els.billingSame) els.billingSame.checked = false;
    if (els.billingOther) els.billingOther.checked = false;
    if (els.billingCustomerId) els.billingCustomerId.value = "";
    if (els.billingCustomerSearch) els.billingCustomerSearch.value = "";
    els.billingCustomerResults?.classList.add("d-none");
  }

  function resetBillingCustomer() {
    clearBillingChoice();
    syncBillingCustomerPanel();
  }

  function syncBillingCustomerPanel() {
    const customerId = (els.customerId?.value || "").trim();
    const show = !!customerId;
    els.billingWrap?.classList.toggle("d-none", !show);
    const other = show && billingIsOther();
    els.billingPick?.classList.toggle("d-none", !other);
  }

  function applyBillingChoice(record) {
    const followupId = parseInt((record && record.customer_id) || els.customerId?.value || "0", 10) || 0;
    const invoiceCustomer = linkedInvoice && linkedInvoice.customer_id
      ? parseInt(linkedInvoice.customer_id, 10) || 0
      : 0;
    if (!(invoiceCustomer && followupId)) {
      clearBillingChoice();
      syncBillingCustomerPanel();
      return;
    }
    if (invoiceCustomer !== followupId && els.billingOther) {
      els.billingOther.checked = true;
      if (els.billingSame) els.billingSame.checked = false;
      if (els.billingCustomerId) els.billingCustomerId.value = String(invoiceCustomer);
      if (els.billingCustomerSearch) {
        els.billingCustomerSearch.value = (linkedInvoice && linkedInvoice.customer_name) || "";
      }
    } else if (els.billingSame) {
      els.billingSame.checked = true;
      if (els.billingOther) els.billingOther.checked = false;
      if (els.billingCustomerId) els.billingCustomerId.value = "";
      if (els.billingCustomerSearch) els.billingCustomerSearch.value = "";
    }
    syncBillingCustomerPanel();
  }

  function appendReceiptOrigin(params) {
    if (!window.JtcsInvoiceReceiptReturn || !params) return;
    window.JtcsInvoiceReceiptReturn.appendModuleReturn(
      params,
      workTypeLabel,
      window.location.pathname + window.location.search
    );
  }

  function openInvoiceWindow(mode) {
    const choice = billingChoice();
    if (!choice) {
      alert("Please select Same Customer or Other Customer.");
      return false;
    }
    const customerId = selectedBillingCustomerId();
    if (choice === "OTHER_CUSTOMER" && !customerId) {
      alert("Please select the Billing Customer.");
      els.billingCustomerSearch?.focus();
      return false;
    }
    if (!customerId) {
      alert("Please select a customer first.");
      return false;
    }
    const entryId = (els.entryId?.value || "").trim();
    const params = new URLSearchParams();
    params.set("customer_id", customerId);
    const followupCustomerId = (els.customerId?.value || "").trim();
    if (followupCustomerId) params.set("contact_customer_id", followupCustomerId);
    if (entryId) params.set("followup_entry_id", entryId);
    if (!billingIsOther()) {
      const customerName = (els.customerSearch?.value || "").trim();
      if (customerName) params.set("customer_name", customerName);
    }
    let title = "Sale / Service Invoice";
    if (mode === "edit") {
      const invoiceId = linkedInvoice ? parseInt(linkedInvoice.invoice_id, 10) : 0;
      if (!invoiceId || invoiceId <= 0) {
        alert("Unable to edit invoice: Invoice ID is missing or invalid.");
        return false;
      }
      params.set("edit", String(invoiceId));
      title = "Edit Sale / Service Invoice";
    } else {
      params.set("open_form", "1");
    }
    appendReceiptOrigin(params);
    const url = "/accounting/invoice/sale?" + params.toString();
    const host = window.top || window;
    if (typeof host.jtcsOpenPageWindow !== "function") {
      alert("Invoice window could not be opened in this page. Refresh and try again.");
      return false;
    }
    host.jtcsOpenPageWindow(url, title);
    return true;
  }

  let invoiceEditorOpen = false;
  let allowEntryModalHide = false;

  function invoiceEditorFrame() {
    return document.getElementById("fuInvoiceEditorFrame");
  }

  function invoiceEditorShell() {
    return document.querySelector("#fuEntryModal .fu-entry-modal");
  }

  function invoiceEditorDirty() {
    const frame = invoiceEditorFrame();
    const win = frame && frame.contentWindow;
    try {
      return !!(win && typeof win.jtcsInvoiceIsDirty === "function" && win.jtcsInvoiceIsDirty());
    } catch (_err) {
      return false;
    }
  }

  function confirmUnsavedInvoice() {
    return new Promise(function (resolve) {
      const overlay = document.createElement("div");
      overlay.className = "jtcs-dialog-overlay is-open";
      overlay.setAttribute("role", "dialog");
      overlay.innerHTML =
        '<div class="jtcs-dialog" role="document" data-type="warning">' +
        '<div class="jtcs-dialog-accent" aria-hidden="true"></div>' +
        '<div class="jtcs-dialog-header">' +
        '<span class="jtcs-dialog-icon" aria-hidden="true"><i class="bi bi-exclamation-triangle-fill"></i></span>' +
        '<h5 class="jtcs-dialog-title">Unsaved invoice</h5></div>' +
        '<div class="jtcs-dialog-body"><p class="jtcs-dialog-message">' +
        "You have unsaved changes in this invoice. Are you sure you want to close without saving?" +
        "</p></div>" +
        '<div class="jtcs-dialog-footer">' +
        '<button type="button" class="btn btn-sm btn-primary" data-act="save">Save Changes</button>' +
        '<button type="button" class="btn btn-sm btn-outline-danger" data-act="discard">Discard Changes</button>' +
        '<button type="button" class="btn btn-sm btn-outline-secondary" data-act="cancel">Cancel</button>' +
        "</div></div>";
      document.body.appendChild(overlay);
      function finish(value) {
        overlay.remove();
        resolve(value);
      }
      overlay.querySelector('[data-act="save"]').addEventListener("click", function () { finish("save"); });
      overlay.querySelector('[data-act="discard"]').addEventListener("click", function () { finish("discard"); });
      overlay.querySelector('[data-act="cancel"]').addEventListener("click", function () { finish("cancel"); });
    });
  }

  function hideInvoiceEditor() {
    const shell = invoiceEditorShell();
    const frame = invoiceEditorFrame();
    if (shell) shell.classList.remove("is-invoice-edit");
    if (frame) frame.src = "about:blank";
    invoiceEditorOpen = false;
  }

  function showInvoiceEditor() {
    const invoiceId = linkedInvoice ? parseInt(linkedInvoice.invoice_id, 10) : 0;
    if (!invoiceId || invoiceId <= 0) {
      alert("Unable to edit invoice: Invoice ID is missing or invalid.");
      return false;
    }
    const frame = invoiceEditorFrame();
    const shell = invoiceEditorShell();
    if (!frame || !shell) {
      alert("Invoice editor could not be opened in this window. Refresh and try again.");
      return false;
    }
    const params = new URLSearchParams();
    params.set("edit", String(invoiceId));
    params.set("fu_embed", "1");
    const entryId = (els.entryId?.value || "").trim();
    if (entryId) params.set("followup_entry_id", entryId);
    const followupCustomerId = (els.customerId?.value || "").trim();
    if (followupCustomerId) params.set("contact_customer_id", followupCustomerId);
    appendReceiptOrigin(params);
    frame.src = "/accounting/invoice/sale?" + params.toString();
    shell.classList.add("is-invoice-edit");
    invoiceEditorOpen = true;
    return true;
  }

  function settleInvoiceEditor() {
    if (!invoiceEditorOpen) return Promise.resolve(true);
    if (!invoiceEditorDirty()) {
      hideInvoiceEditor();
      return Promise.resolve(true);
    }
    return confirmUnsavedInvoice().then(function (choice) {
      if (choice === "cancel") return false;
      if (choice !== "save") {
        hideInvoiceEditor();
        return true;
      }
      const frame = invoiceEditorFrame();
      const win = frame && frame.contentWindow;
      if (!win || typeof win.jtcsInvoiceSaveFromHost !== "function") {
        alert("Unable to save the invoice.");
        return false;
      }
      return win.jtcsInvoiceSaveFromHost().then(function (ok) {
        if (!ok) return false;
        hideInvoiceEditor();
        return true;
      }).catch(function (err) {
        alert(err.message || "Unable to save the invoice.");
        return false;
      });
    });
  }

  window.FU_applyBillingResult = function (data) {
    if (!data) return;
    if (els.billNo && data.bill_no) els.billNo.value = data.bill_no;
    if (els.billAmount && data.bill_amount != null) els.billAmount.value = data.bill_amount;
    if (els.billDate && data.bill_date) els.billDate.value = data.bill_date;
    const tallyCb = els.workflowChecks?.querySelector('.fu-stage-check[data-stage-code="tally_bill_generated"]');
    if (tallyCb) tallyCb.checked = true;
    syncWorkflowPanels();
  };

  function loadEntry(entryId) {
    return fetch(apiUrl(window.FU_API.record, entryId), { headers: { Accept: "application/json" } })
      .then(function (res) {
        if (!res.ok) {
          return parseJsonResponse(res).then(function (data) {
            throw new Error(data.error || "Record not found.");
          });
        }
        return parseJsonResponse(res);
      })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "Record not found.");
        fillEntryForm(data.record);
      });
  }

  function parseJsonResponse(res) {
    const contentType = res.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      return res.text().then(function (body) {
        const snippet = (body || "").replace(/\s+/g, " ").slice(0, 120);
        const csrfHint = /csrf/i.test(body || "") ? " Refresh the page (Ctrl+F5) and try again." : "";
        throw new Error(
          "Server returned an unexpected response." + csrfHint + " " + snippet
        );
      });
    }
    return res.json().then(function (data) {
      if (!res.ok || data.ok === false) {
        throw new Error(data.error || ("Request failed (HTTP " + res.status + ")."));
      }
      return data;
    });
  }

  function saveEntry(options) {
    options = options || {};
    if (entryFieldsLocked) return;
    const customerId = parseInt(els.customerId?.value || "", 10);
    if (!customerId) {
      alert("Please select a customer.");
      return;
    }
    const workDate = (els.workDate?.value || "").trim();
    if (!workDate) {
      alert("Work date is required.");
      return;
    }
    const entryIdRaw = (els.entryId?.value || "").trim();
    const payload = {
      work_date: workDate,
      tax_period: els.taxPeriod?.value || "",
      customer_id: customerId,
      remarks: els.remarks?.value || "",
      reason_for_unverified: els.reasonUnverified?.value || "",
      stage_ids: selectedStageIds(),
    };
    if (isGstModule && els.gstMonth) {
      const month = (els.gstMonth.value || "").trim();
      if (!month) {
        alert("Month is required.");
        els.gstMonth.focus();
        return;
      }
      payload.gst_month = month;
    }
    if (isTdsModule) {
      const formType = (els.formType?.value || "").trim();
      const quarter = (els.quarter?.value || "").trim();
      if (!formType) {
        alert("Return type is required.");
        els.formType?.focus();
        return;
      }
      if (!quarter) {
        alert("Quarter is required.");
        els.quarter?.focus();
        return;
      }
      payload.form_type = formType;
      payload.quarter = quarter;
    }
    if (entryIdRaw) payload.entry_id = parseInt(entryIdRaw, 10);
    const billingSel = billingChoice();
    if (billingSel || (linkedInvoice && linkedInvoice.invoice_id)) {
      if (!billingSel) {
        alert("Please select Same Customer or Other Customer.");
        return;
      }
      payload.billing_type = billingSel;
      if (billingSel === "OTHER_CUSTOMER") {
        const billingId = parseInt(els.billingCustomerId?.value || "", 10);
        if (!billingId) {
          alert("Please select the Billing Customer.");
          els.billingCustomerSearch?.focus();
          return;
        }
        payload.billing_customer_id = billingId;
      }
    }
    if (isDscModule) {
      if (els.applicationNumber) {
        payload.application_number = (els.applicationNumber.value || "").trim();
      }
      payload.location = (els.location?.value || "").trim();
      payload.introduced_by = (els.introducedBy?.value || "").trim();
      payload.dsc_type = (els.dscType?.value || "").trim();
      payload.dsc_class = (els.dscClass?.value || "").trim();
      payload.dsc_year = (els.dscYear?.value || "").trim();
      payload.email_id = (els.customerEmail?.value || "").trim();
    }
    appendBillingPayload(payload);
    if (options.clearPaymentReceived) {
      payload.clear_payment_received = true;
    } else if (isStageChecked("payment_received")) {
      syncPaymentDatesBeforeSave();
      const payError = validatePaymentLines();
      if (payError) {
        alert(payError);
        return;
      }
      payload.payment_lines = collectPaymentLines();
      if (!payload.payment_lines.length) {
        alert("Add at least one payment mode.");
        return;
      }
    }
    if (hasReturnType && els.returnType) {
      payload.return_type = els.returnType.value || "Original";
    }
    if (hasGstFields && els.gstReturnType) {
      const gstReturnType = (els.gstReturnType.value || "").trim();
      if (!gstReturnType) {
        alert("Return type is required.");
        els.gstReturnType.focus();
        return;
      }
      payload.return_type = gstReturnType;
    }
    const dscError = validateDscEntry() || validateTallyPayment();
    if (dscError) {
      alert(dscError);
      return;
    }
    if (els.saveBtn) els.saveBtn.disabled = true;
    return fetch(window.FU_API.save, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify(payload),
    })
      .then(function (res) { return parseJsonResponse(res); })
      .then(function (data) {
        if (data && data.record && data.record.entry_id && els.entryId) {
          els.entryId.value = String(data.record.entry_id);
        }
        if (data && data.record) {
          paintInvoiceSummary(data.record.linked_invoice || null);
        }
        savedPaymentReceived = isStageChecked("payment_received");
        if (options.keepOpen) return data && data.record;
        entryModal?.hide();
        return loadGrid().then(function () { return data && data.record; });
      })
      .catch(function (err) {
        alert(err.message || "Unable to save entry.");
      })
      .finally(function () {
        if (els.saveBtn) els.saveBtn.disabled = false;
      });
  }

  async function deleteEntry(entryId) {
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!(await JTCSDialog.confirm("Delete this followup entry?"))) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: "Delete this followup entry?" });
      if (!creds) return;
    }
    fetch(apiUrl(window.FU_API.delete, entryId), {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify(creds ? window.JTCSDeleteConfirm.withCreds({}, creds) : {}),
    })
      .then(function (res) { return parseJsonResponse(res); })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "Delete failed.");
        entryModal?.hide();
        loadGrid();
      })
      .catch(function (err) {
        alert(err.message || "Unable to delete entry.");
      });
  }

  function searchCustomers(query) {
    const q = (query || "").trim();
    if (q.length < 2) {
      hideCustomerResults();
      return;
    }
    const seq = ++customerSearchSeq;
    const url = window.FU_API.customer_search + "?q=" + encodeURIComponent(q);
    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (seq !== customerSearchSeq) return;
        if (!data.ok || !els.customerResults) return;
        const list = data.rows || [];
        if (!list.length) {
          els.customerResults.innerHTML = '<div class="list-group-item text-muted">No customers found</div>';
        } else {
          els.customerResults.innerHTML = list.map(function (row) {
            const subParts = [row.mobile_number, row.pan_number];
            if (isDscModule && row.email_id) subParts.push(row.email_id);
            const sub = subParts.filter(Boolean).join(" · ");
            return (
              '<button type="button" class="list-group-item list-group-item-action fu-customer-pick" ' +
              'data-id="' + row.customer_id + '" data-name="' + escapeHtml(row.customer_name) + '" ' +
              'data-mobile="' + escapeHtml(row.mobile_number) + '" data-pan="' + escapeHtml(row.pan_number) + '" ' +
              'data-email="' + escapeHtml(row.email_id || "") + '" ' +
              'data-filing-frequency="' + escapeHtml(row.filing_frequency || "") + '">' +
              "<strong>" + escapeHtml(row.customer_name) + "</strong>" +
              (sub ? '<div class="small text-muted">' + escapeHtml(sub) + "</div>" : "") +
              "</button>"
            );
          }).join("");
        }
        els.customerResults.classList.remove("d-none");
      })
      .catch(function () {
        if (seq !== customerSearchSeq) return;
        if (!els.customerResults) return;
        els.customerResults.innerHTML = '<div class="list-group-item text-muted">Search failed</div>';
        els.customerResults.classList.remove("d-none");
      });
  }

  function saveCustomer() {
    if (!els.customerForm) return;
    const formData = new FormData(els.customerForm);
    const payload = Object.fromEntries(formData.entries());
    els.customerSaveBtn.disabled = true;
    if (els.customerFormError) {
      els.customerFormError.classList.add("d-none");
      els.customerFormError.textContent = "";
    }
    fetch(window.FU_API.customer_create, {
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
        if (!data.ok) throw new Error(data.error || "Unable to add customer.");
        const c = data.customer || {};
        selectCustomer({
          customer_id: c.CustomerID || c.customer_id,
          customer_name: c.CustomerName || c.customer_name,
          mobile_number: c.MobileNumber || c.mobile_number,
          pan_number: c.PANNumber || c.pan_number,
          email_id: c.EmailID || c.email_id,
        });
        customerModal?.hide();
        els.customerForm.reset();
        const countryEl = els.customerForm.querySelector("#fuCustCountry");
        if (countryEl) {
          if (window.JtcsPincodeAutofill) {
            window.JtcsPincodeAutofill.ensureSelectValue(countryEl, "India");
          } else {
            countryEl.value = "India";
          }
        }
        if (fuPincodeBinder && fuPincodeBinder.resetCache) fuPincodeBinder.resetCache();
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
        els.customerSaveBtn.disabled = false;
      });
  }

  els.newEntryBtn?.addEventListener("click", openNewEntry);
  els.refreshBtn?.addEventListener("click", loadGrid);
  els.exportExcelBtn?.addEventListener("click", exportItrGridExcel);
  els.searchBtn?.addEventListener("click", loadGrid);
  els.saveBtn?.addEventListener("click", saveEntry);
  document.getElementById("fuEditBtn")?.addEventListener("click", function () {
    ensureEntryChangeAllowed().then(function (allowed) {
      if (!allowed) return;
      setEntryFieldsLocked(false);
    });
  });
  document.getElementById("fuDeleteBtn")?.addEventListener("click", function () {
    const entryId = (els.entryId?.value || "").trim();
    if (!entryId) return;
    ensureEntryChangeAllowed().then(function (allowed) {
      if (!allowed) return;
      deleteEntry(entryId);
    });
  });

  function itrSyncJobUrl(jobId) {
    const template = (window.FU_API && window.FU_API.itr_sync_job) || "/api/itr/sync-status/__JOB__";
    return String(template).replace("__JOB__", encodeURIComponent(jobId));
  }

  function setItrLoginStatusBanner(loginStatus) {
    if (!els.kdkLoginStatus) return;
    const text = (loginStatus || "").trim();
    if (!text) {
      els.kdkLoginStatus.textContent = "";
      els.kdkLoginStatus.className = "alert py-2 px-3 mb-3 d-none";
      return;
    }
    const failed = text.toLowerCase().indexOf("failed") >= 0;
    els.kdkLoginStatus.textContent = text;
    els.kdkLoginStatus.className =
      "alert py-2 px-3 mb-3 " + (failed ? "alert-danger" : "alert-success");
  }

  function updateItrKdkPreview(job) {
    const src = job && job.preview_image ? String(job.preview_image) : "";
    if (els.kdkPreviewCaption) {
      els.kdkPreviewCaption.textContent = (job && job.message) || "Waiting…";
    }
    if (!els.kdkPreviewImg) return;
    if (src.indexOf("data:image") === 0) {
      els.kdkPreviewImg.src = src;
      els.kdkPreviewImg.classList.remove("d-none");
      if (els.kdkPreviewPlaceholder) els.kdkPreviewPlaceholder.classList.add("d-none");
    }
  }

  function resetItrKdkPreview() {
    if (els.kdkPreviewImg) {
      els.kdkPreviewImg.removeAttribute("src");
      els.kdkPreviewImg.classList.add("d-none");
    }
    if (els.kdkPreviewPlaceholder) els.kdkPreviewPlaceholder.classList.remove("d-none");
    if (els.kdkPreviewCaption) els.kdkPreviewCaption.textContent = "Waiting…";
  }

  function updateItrSyncProgress(job) {
    const total = Number(job.total || 0);
    const completed = Number(job.completed || 0);
    const pct = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
    if (els.kdkProgressTitle) {
      els.kdkProgressTitle.textContent = job.message || (job.status === "completed" ? "Sync completed" : "Sync Started...");
    }
    if (els.kdkProgressClient) els.kdkProgressClient.textContent = job.current_client || "—";
    if (els.kdkProgressPan) els.kdkProgressPan.textContent = job.current_pan || "—";
    if (els.kdkProgressPeriod) els.kdkProgressPeriod.textContent = job.current_period || "—";
    if (els.kdkProgressCount) {
      els.kdkProgressCount.textContent = completed + " / " + total + (total === 1 ? " Client" : " Clients");
    }
    if (els.kdkProgressBar) {
      els.kdkProgressBar.style.width = pct + "%";
      els.kdkProgressBar.textContent = pct + "%";
      els.kdkProgressBar.setAttribute("aria-valuenow", String(pct));
    }
    updateItrKdkPreview(job);
    if (job.login_status) {
      setItrLoginStatusBanner(job.login_status);
    } else if ((job.error || "").toLowerCase().indexOf("login failed") >= 0) {
      setItrLoginStatusBanner("Login Failed");
    } else if ((job.message || "").toLowerCase().indexOf("login successfully") >= 0) {
      setItrLoginStatusBanner("Login Successfully");
    }
    if (els.kdkProgressError) {
      if (job.error) {
        els.kdkProgressError.textContent = job.error;
        els.kdkProgressError.classList.remove("d-none");
      } else {
        els.kdkProgressError.textContent = "";
        els.kdkProgressError.classList.add("d-none");
      }
    }
    if (els.kdkProgressCloseBtn) {
      els.kdkProgressCloseBtn.classList.remove("d-none");
      els.kdkProgressCloseBtn.textContent =
        (job.status === "completed" || job.status === "failed") ? "Close" : "Stop / Close";
    }
  }

  function pollItrSyncJob(jobId) {
    fetch(itrSyncJobUrl(jobId), {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) { return res.json().then(function (data) { return { res: res, data: data }; }); })
      .then(function (result) {
        if (!result.res.ok || !result.data.ok) {
          throw new Error((result.data && result.data.error) || "Unable to read sync progress.");
        }
        const job = result.data.job || {};
        updateItrSyncProgress(job);
        if (job.status === "failed") {
          if (itrSyncPollTimer) clearInterval(itrSyncPollTimer);
          itrSyncPollTimer = null;
          if ((job.login_status || job.error || "").toLowerCase().indexOf("login failed") >= 0) {
            setItrLoginStatusBanner("Login Failed");
          }
          return;
        }
        if (job.status === "completed") {
          if (itrSyncPollTimer) clearInterval(itrSyncPollTimer);
          itrSyncPollTimer = null;
          if (!job.login_status) setItrLoginStatusBanner("Login Successfully");
          loadGrid();
          return;
        }
      })
      .catch(function (err) {
        if (els.kdkProgressError) {
          els.kdkProgressError.textContent = err.message || String(err);
          els.kdkProgressError.classList.remove("d-none");
        }
      });
  }

  function openItrSyncLogin(entryId) {
    if (!isItrModule) return;
    pendingItrSyncEntryId = entryId != null && entryId !== "" ? Number(entryId) : null;
    if (Number.isNaN(pendingItrSyncEntryId)) pendingItrSyncEntryId = null;
    try {
      const saveOn = localStorage.getItem(KDK_SAVE_KEY) !== "0";
      const savedUser = localStorage.getItem(KDK_USER_KEY) || "";
      const savedPass = localStorage.getItem(KDK_PASS_KEY) || "";
      if (els.kdkUserId) els.kdkUserId.value = savedUser;
      if (els.kdkPassword) els.kdkPassword.value = savedPass;
      if (els.kdkRememberMe) els.kdkRememberMe.checked = saveOn;
    } catch (e) { /* ignore */ }
    if (els.kdkLoginSyncBtn) {
      els.kdkLoginSyncBtn.innerHTML = pendingItrSyncEntryId
        ? '<i class="bi bi-arrow-repeat"></i> Login &amp; Sync Client'
        : '<i class="bi bi-arrow-repeat"></i> Login &amp; Sync All';
    }
    kdkLoginModal?.show();
    setTimeout(function () {
      if (els.kdkUserId && !els.kdkUserId.value) {
        els.kdkUserId.focus();
      } else {
        els.kdkPassword?.focus();
      }
    }, 200);
  }

  function startItrSync() {
    if (!isItrModule) return;
    const userId = (els.kdkUserId?.value || "").trim();
    const password = els.kdkPassword?.value || "";
    if (!userId || !password) {
      alert("KDK Mobile Number and Password are required.");
      return;
    }
    try {
      if (els.kdkRememberMe?.checked) {
        localStorage.setItem(KDK_SAVE_KEY, "1");
        localStorage.setItem(KDK_USER_KEY, userId);
        localStorage.setItem(KDK_PASS_KEY, password);
      } else {
        localStorage.setItem(KDK_SAVE_KEY, "0");
        localStorage.removeItem(KDK_USER_KEY);
        localStorage.removeItem(KDK_PASS_KEY);
      }
    } catch (e) { /* ignore */ }

    const startUrl = (window.FU_API && window.FU_API.itr_sync_start) || "/api/itr/sync-status";
    const payload = { user_id: userId, password: password };
    if (pendingItrSyncEntryId) payload.entry_id = pendingItrSyncEntryId;

    if (els.kdkLoginSyncBtn) els.kdkLoginSyncBtn.disabled = true;
    setItrLoginStatusBanner("");
    resetItrKdkPreview();
    fetch(startUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(payload),
    })
      .then(function (res) { return res.json().then(function (data) { return { res: res, data: data }; }); })
      .then(function (result) {
        if (!result.res.ok || !result.data.ok) {
          const err = (result.data && result.data.error) || "Unable to start sync.";
          if (String(err).toLowerCase().indexOf("login failed") >= 0) {
            setItrLoginStatusBanner("Login Failed");
            alert("Login Failed");
          }
          throw new Error(err);
        }
        kdkLoginModal?.hide();
        updateItrSyncProgress({
          status: "running",
          message: "Logging in to KDK...",
          login_status: "",
          total: result.data.total || (pendingItrSyncEntryId ? 1 : 0),
          completed: 0,
          current_client: "",
          current_pan: "",
          current_period: "",
        });
        if (els.kdkProgressCloseBtn) els.kdkProgressCloseBtn.classList.remove("d-none");
        kdkProgressModal?.show();
        const jobId = result.data.job_id;
        if (itrSyncPollTimer) clearInterval(itrSyncPollTimer);
        pollItrSyncJob(jobId);
        itrSyncPollTimer = setInterval(function () { pollItrSyncJob(jobId); }, 900);
      })
      .catch(function (err) {
        alert(err.message || String(err));
      })
      .finally(function () {
        if (els.kdkLoginSyncBtn) els.kdkLoginSyncBtn.disabled = false;
      });
  }

  els.syncBtn?.addEventListener("click", function () {
    openItrSyncLogin(null);
  });
  els.kdkLoginSyncBtn?.addEventListener("click", startItrSync);
  els.kdkProgressModalEl?.addEventListener("hidden.bs.modal", function () {
    if (itrSyncPollTimer) {
      clearInterval(itrSyncPollTimer);
      itrSyncPollTimer = null;
    }
  });
  // Keep modal values when closed if Save is checked (prefill next open).
  els.kdkLoginModalEl?.addEventListener("hidden.bs.modal", function () {
    if (els.kdkRememberMe && !els.kdkRememberMe.checked && els.kdkPassword) {
      els.kdkPassword.value = "";
    }
  });

  if (allowCustomerAdd) {
    if (window.JtcsPincodeAutofill && window.FU_PINCODE_LOOKUP) {
      fuPincodeBinder = window.JtcsPincodeAutofill.bind({
        pincode: "fuCustPincode",
        country: "fuCustCountry",
        state: "fuCustState",
        district: "fuCustDistrict",
        city: "fuCustCity",
        stateGstCode: "fuCustStateGstCode",
        apiUrl: window.FU_PINCODE_LOOKUP,
        lookupOnBind: false,
      });
    }
    els.addCustomerBtn?.addEventListener("click", function () {
      if (els.customerForm) {
        els.customerForm.reset();
        const country = document.getElementById("fuCustCountry");
        if (country) {
          if (window.JtcsPincodeAutofill) {
            window.JtcsPincodeAutofill.ensureSelectValue(country, "India");
          } else {
            country.value = "India";
          }
        }
        if (fuPincodeBinder && fuPincodeBinder.resetCache) fuPincodeBinder.resetCache();
      }
      if (els.customerFormError) {
        els.customerFormError.classList.add("d-none");
        els.customerFormError.textContent = "";
      }
      customerModal?.show();
    });
    els.customerSaveBtn?.addEventListener("click", saveCustomer);
  }

  els.searchInput?.addEventListener("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadGrid, 350);
  });
  els.statusFilter?.addEventListener("change", function () {
    syncStatCardActive();
    loadGrid();
  });
  els.periodFilter?.addEventListener("change", loadGrid);
  els.returnTypeFilter?.addEventListener("change", loadGrid);
  els.dateFromFilter?.addEventListener("change", loadGrid);
  els.dateToFilter?.addEventListener("change", loadGrid);
  els.clearFilterBtn?.addEventListener("click", clearFilters);
  els.statsRow?.addEventListener("click", function (event) {
    const card = event.target.closest(".fu-stat-card[data-status-filter]");
    if (!card || !els.statsRow.contains(card)) return;
    const value = card.getAttribute("data-status-filter") || "";
    if (els.statusFilter) els.statusFilter.value = value;
    syncStatCardActive();
    loadGrid();
  });

  els.customerSearch?.addEventListener("input", function () {
    if (els.customerId?.value) {
      els.customerId.value = "";
      if (els.customerSelected) {
        els.customerSelected.textContent = "";
        els.customerSelected.classList.add("d-none");
      }
      if (els.customerEmail) els.customerEmail.value = "";
      onFollowupCustomerChanged("");
    }
    clearTimeout(customerSearchTimer);
    customerSearchTimer = setTimeout(function () {
      searchCustomers(els.customerSearch.value);
    }, 300);
  });

  function hideBillingResults() {
    els.billingCustomerResults?.classList.add("d-none");
  }

  function searchBillingCustomers(query) {
    const q = (query || "").trim();
    if (q.length < 2) {
      hideBillingResults();
      return;
    }
    const seq = ++billingSearchSeq;
    const url = window.FU_API.customer_search + "?q=" + encodeURIComponent(q);
    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (seq !== billingSearchSeq || !els.billingCustomerResults) return;
        const list = (data && data.rows) || [];
        if (!list.length) {
          els.billingCustomerResults.innerHTML = '<div class="list-group-item text-muted">No customers found</div>';
        } else {
          els.billingCustomerResults.innerHTML = list.map(function (row) {
            const sub = [row.mobile_number, row.pan_number].filter(Boolean).join(" · ");
            return (
              '<button type="button" class="list-group-item list-group-item-action fu-billing-pick" ' +
              'data-id="' + row.customer_id + '" data-name="' + escapeHtml(row.customer_name) + '">' +
              "<strong>" + escapeHtml(row.customer_name) + "</strong>" +
              (sub ? '<div class="small text-muted">' + escapeHtml(sub) + "</div>" : "") +
              "</button>"
            );
          }).join("");
        }
        els.billingCustomerResults.classList.remove("d-none");
      })
      .catch(function () {
        if (seq !== billingSearchSeq || !els.billingCustomerResults) return;
        els.billingCustomerResults.innerHTML = '<div class="list-group-item text-muted">Search failed</div>';
        els.billingCustomerResults.classList.remove("d-none");
      });
  }

  els.billingSame?.addEventListener("change", function () {
    syncBillingCustomerPanel();
    if (!this.checked) return;
    if (linkedInvoice && linkedInvoice.invoice_id) {
      const followupId = parseInt(els.customerId?.value || "0", 10) || 0;
      const invoiceCustomer = parseInt(linkedInvoice.customer_id || "0", 10) || 0;
      if (followupId && invoiceCustomer && followupId !== invoiceCustomer && (els.entryId?.value || "").trim()) {
        saveEntry({ keepOpen: true });
      }
    }
  });
  els.billingOther?.addEventListener("change", function () {
    syncBillingCustomerPanel();
    if (this.checked) els.billingCustomerSearch?.focus();
  });
  els.billingCustomerSearch?.addEventListener("input", function () {
    if (els.billingCustomerId) els.billingCustomerId.value = "";
    clearTimeout(billingSearchTimer);
    billingSearchTimer = setTimeout(function () {
      searchBillingCustomers(els.billingCustomerSearch.value);
    }, 300);
  });
  els.billingCustomerResults?.addEventListener("click", function (event) {
    const btn = event.target.closest(".fu-billing-pick");
    if (!btn) return;
    if (els.billingCustomerId) els.billingCustomerId.value = btn.dataset.id || "";
    if (els.billingCustomerSearch) els.billingCustomerSearch.value = btn.dataset.name || "";
    hideBillingResults();
    if (!linkedInvoice) beginCreateInvoice();
    else if ((els.entryId?.value || "").trim()) saveEntry({ keepOpen: true });
  });

  els.customerResults?.addEventListener("click", function (event) {
    const btn = event.target.closest(".fu-customer-pick");
    if (!btn) return;
    selectCustomer({
      customer_id: parseInt(btn.dataset.id, 10),
      customer_name: btn.dataset.name,
      mobile_number: btn.dataset.mobile,
      pan_number: btn.dataset.pan,
      email_id: btn.dataset.email || "",
      filing_frequency: btn.dataset.filingFrequency || "",
    });
  });

  function chooseInvoiceAction() {
    return new Promise(function (resolve) {
      const overlay = document.createElement("div");
      overlay.className = "jtcs-dialog-overlay is-open";
      overlay.setAttribute("role", "dialog");
      overlay.innerHTML =
        '<div class="jtcs-dialog" role="document" data-type="warning">' +
        '<div class="jtcs-dialog-accent" aria-hidden="true"></div>' +
        '<div class="jtcs-dialog-header">' +
        '<span class="jtcs-dialog-icon" aria-hidden="true"><i class="bi bi-exclamation-triangle-fill"></i></span>' +
        '<h5 class="jtcs-dialog-title">Delete invoice</h5></div>' +
        '<div class="jtcs-dialog-body"><p class="jtcs-dialog-message">' +
        "This invoice has already been created. Do you want to delete the invoice?" +
        "</p></div>" +
        '<div class="jtcs-dialog-footer">' +
        '<button type="button" class="btn btn-sm btn-primary" data-act="edit">Edit Invoice</button>' +
        '<button type="button" class="btn btn-sm btn-outline-secondary" data-act="cancel">No / Cancel</button>' +
        '<button type="button" class="btn btn-sm btn-danger" data-act="delete">Yes / Delete</button>' +
        "</div></div>";
      document.body.appendChild(overlay);
      function finish(value) {
        overlay.remove();
        resolve(value);
      }
      overlay.querySelector('[data-act="edit"]').addEventListener("click", function () { finish("edit"); });
      overlay.querySelector('[data-act="cancel"]').addEventListener("click", function () { finish("cancel"); });
      overlay.querySelector('[data-act="delete"]').addEventListener("click", function () { finish("delete"); });
    });
  }

  function postInvoiceDelete(invoiceId, creds, entryId) {
    const id = parseInt(invoiceId, 10);
    if (!id || id <= 0) {
      return Promise.reject(
        new Error("Unable to delete invoice: Invoice ID is missing or invalid.")
      );
    }
    const body = { from_source: true };
    const followupId = parseInt(entryId, 10);
    if (followupId > 0) body.followup_entry_id = followupId;
    return fetch("/accounting/api/invoices/" + id + "/delete", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify(Object.assign(
        body,
        creds ? window.JTCSDeleteConfirm.withCreds({}, creds) : {}
      )),
    }).then(function (res) { return parseJsonResponse(res); });
  }

  function confirmDeleteLinkedInvoice() {
    const invoiceId = linkedInvoice ? parseInt(linkedInvoice.invoice_id, 10) : 0;
    const entryId = (els.entryId?.value || "").trim();
    if (!invoiceId || invoiceId <= 0) {
      window.alert("Unable to delete invoice: Invoice ID is missing or invalid.");
      return Promise.resolve("cancel");
    }
    return chooseInvoiceAction().then(function (choice) {
      if (choice === "edit") {
        showInvoiceEditor();
        return "edit";
      }
      if (choice !== "delete") return "cancel";
      if (!window.JTCSDeleteConfirm || !window.JTCSDeleteConfirm.ask) {
        return postInvoiceDelete(invoiceId, null, entryId).then(function () { return "delete"; });
      }
      return window.JTCSDeleteConfirm.ask({
        message: "Enter your User ID and password to delete this invoice.",
        title: "Delete invoice",
        confirmLabel: "Yes / Delete",
        cancelLabel: "No / Cancel",
      }).then(function (creds) {
        if (!creds) return "cancel";
        return postInvoiceDelete(invoiceId, creds, entryId).then(function () { return "delete"; });
      });
    });
  }

  function ensureFollowupSaved() {
    const existing = (els.entryId?.value || "").trim();
    if (existing) return Promise.resolve(existing);
    return Promise.resolve(saveEntry({ keepOpen: true })).then(function (record) {
      if (!record || !record.entry_id) return "";
      return String(record.entry_id);
    });
  }

  function clearPaymentReceivedFields() {
    if (els.paymentLines) els.paymentLines.innerHTML = "";
    if (els.paymentSummary) els.paymentSummary.textContent = "";
  }

  function confirmUntickPaymentReceived(checkbox) {
    const message =
      "Payment Received is already recorded. If you untick it, Payment Received Date and Payment Received Amount will be removed. Do you want to continue?";
    const ask = window.JTCSDialog && JTCSDialog.confirm
      ? JTCSDialog.confirm(message, {
          title: "Payment Received",
          okLabel: "Yes, Untick",
          cancelLabel: "Cancel",
          type: "warning",
        })
      : Promise.resolve(window.confirm(message));
    checkbox.checked = true;
    ask.then(function (yes) {
      if (!yes) {
        checkbox.checked = true;
        syncWorkflowPanels();
        return;
      }
      checkbox.checked = false;
      clearPaymentReceivedFields();
      syncWorkflowPanels();
      const saved = saveEntry({ keepOpen: true, clearPaymentReceived: true });
      Promise.resolve(saved).then(function (record) {
        if (!record) {
          checkbox.checked = true;
          savedPaymentReceived = true;
          syncWorkflowPanels();
          return;
        }
        savedPaymentReceived = false;
        clearPaymentReceivedFields();
        syncWorkflowPanels();
        if (typeof syncCustomerBillSummary === "function") syncCustomerBillSummary();
        loadGrid();
      });
    });
  }

  els.workflowChecks?.addEventListener("change", function (event) {
    if (!event.target.classList.contains("fu-stage-check")) return;
    const code = (event.target.dataset.stageCode || "").toLowerCase();
    if (code === "payment_received") {
      event.target.checked = false;
      return;
    }
    if ((code === "return_filed" || code === "itr_filed") && !event.target.checked && isStageChecked("invoice")) {
      event.target.checked = true;
      syncWorkflowPanels();
      if (window.JTCSDialog && JTCSDialog.alert) {
        JTCSDialog.alert(RETURN_FILED_MESSAGE, "warning");
      } else {
        alert(RETURN_FILED_MESSAGE);
      }
      return;
    }
    if (invoiceTickEnabled && code === "invoice") {
      const checkbox = event.target;
      if (checkbox.checked && !(linkedInvoice && linkedInvoice.invoice_id)) {
        checkbox.checked = false;
        syncWorkflowPanels();
        if (window.JTCSDialog && JTCSDialog.alert) {
          JTCSDialog.alert(MANUAL_INVOICE_MESSAGE, "warning");
        } else {
          alert(MANUAL_INVOICE_MESSAGE);
        }
        return;
      }
      if (!checkbox.checked) {
        creatingInvoice = false;
        if (!(linkedInvoice && linkedInvoice.invoice_id)) clearBillingChoice();
      }
      if (checkbox.checked && linkedInvoice && linkedInvoice.invoice_id) {
        applyBillingChoice({});
      }
      syncWorkflowPanels();
      return;
    }
    syncWorkflowPanels();
  });

  function beginCreateInvoice() {
    const customerId = (els.customerId?.value || "").trim();
    if (!customerId) {
      alert("Please select a customer before opening the Invoice module.");
      return;
    }
    const cb = invoiceStageCheckbox();
    creatingInvoice = true;
    if (cb && !(linkedInvoice && linkedInvoice.invoice_id)) cb.checked = false;
    syncBillingCustomerPanel();
    syncWorkflowPanels();
    const choice = billingChoice();
    if (!choice) {
      alert("Please select Same Customer or Other Customer.");
      return;
    }
    if (choice === "OTHER_CUSTOMER" && !(els.billingCustomerId?.value || "").trim()) {
      alert("Please select the Billing Customer.");
      els.billingCustomerSearch?.focus();
      return;
    }
    ensureFollowupSaved().then(function (entryId) {
      if (!entryId) return;
      if (!openInvoiceWindow("create") && cb && !linkedInvoice && !billingChoice()) {
        cb.checked = false;
        syncWorkflowPanels();
      }
    }).catch(function (err) {
      alert(err.message || "Unable to open the Invoice module.");
    });
  }

  document.getElementById("fuInvoiceEditorBack")?.addEventListener("click", function () {
    settleInvoiceEditor();
  });
  els.entryModalEl?.addEventListener("hide.bs.modal", function (event) {
    if (allowEntryModalHide || !invoiceEditorOpen) return;
    event.preventDefault();
    settleInvoiceEditor().then(function (done) {
      if (!done) return;
      allowEntryModalHide = true;
      entryModal?.hide();
      allowEntryModalHide = false;
    });
  });
  document.getElementById("fuCreateInvoiceBtn")?.addEventListener("click", beginCreateInvoice);
  document.getElementById("fuInvoiceActions")?.addEventListener("click", function (event) {
    const btn = event.target.closest(".fu-inv-act");
    if (!btn || !window.JtcsInvoiceActions) return;
    const invoiceId = linkedInvoice ? parseInt(linkedInvoice.invoice_id, 10) : 0;
    if (!invoiceId) return;
    if (btn.getAttribute("data-inv-act") === "edit") {
      showInvoiceEditor();
      return;
    }
    window.JtcsInvoiceActions.run(btn.getAttribute("data-inv-act"), linkedInvoice, {
      followupEntryId: (els.entryId?.value || "").trim(),
      onDeleted: function () {
        const cb = invoiceStageCheckbox();
        if (cb) cb.checked = false;
        creatingInvoice = false;
        paintInvoiceSummary(null);
        clearBillingChoice();
        syncWorkflowPanels();
        loadGrid();
      },
    });
  });
  if (els.gridBody && window.JtcsInvoiceActions) {
    window.JtcsInvoiceActions.bind(els.gridBody, {
      onDeleted: function (invoiceId) {
        if (linkedInvoice && String(linkedInvoice.invoice_id) === String(invoiceId)) {
          const cb = invoiceStageCheckbox();
          if (cb) cb.checked = false;
          creatingInvoice = false;
          paintInvoiceSummary(null);
          clearBillingChoice();
          syncWorkflowPanels();
        }
        loadGrid();
      },
    });
  }

  window.addEventListener("message", function (event) {
    if (event.origin !== window.location.origin) return;
    const data = event.data || {};
    if (data.type === "jtcs-invoice-receipt-closed") {
      const origin = String(data.receipt_origin || "").trim().toUpperCase();
      if (origin !== String(workTypeLabel || "").trim().toUpperCase()) return;
      if (!window.JtcsInvoiceReceiptReturn || !window.JtcsInvoiceReceiptReturn.normalizeOrigin(origin)) return;
      hideInvoiceEditor();
      return;
    }
    if (data.misc_entry_id && !data.followup_entry_id) return;
    const currentId = (els.entryId?.value || "").trim();
    if (data.followup_entry_id && currentId && String(data.followup_entry_id) !== currentId) return;
    if (data.type === "jtcs-invoice-saved" && data.record) {
      paintInvoiceSummary({
        invoice_id: data.record.invoice_id,
        invoice_no: data.record.invoice_no,
        invoice_date: data.record.invoice_date,
        invoice_value: data.record.invoice_value,
        customer_id: data.record.customer_id,
        customer_name: data.record.customer_name,
        contact_mobile: data.record.contact_mobile,
        pay_url: data.record.pay_url || "",
      });
      applyBillingChoice({
        customer_id: els.customerId?.value,
        billing_customer_name: els.billingCustomerSearch?.value,
      });
      const cb = invoiceStageCheckbox();
      if (cb) cb.checked = true;
      creatingInvoice = false;
      syncWorkflowPanels();
      loadGrid();
      if (invoiceEditorOpen) {
        setTimeout(function () {
          if (invoiceEditorOpen) hideInvoiceEditor();
        }, 0);
      }
    }
    if (data.type === "jtcs-invoice-cancelled" || data.type === "jtcs-invoice-deleted") {
      if (data.type === "jtcs-invoice-deleted") paintInvoiceSummary(null);
      clearInvoiceTickIfUnsaved();
      if (data.type === "jtcs-invoice-deleted") {
        const cb = invoiceStageCheckbox();
        if (cb) cb.checked = false;
        creatingInvoice = false;
        paintInvoiceSummary(null);
        syncWorkflowPanels();
        loadGrid();
      }
    }
  });

  els.billNo?.addEventListener("change", refreshInvoiceStatus);
  els.billNo?.addEventListener("blur", refreshInvoiceStatus);
  window.jtcsRefreshInvoiceStatus = refreshInvoiceStatus;
  window.addEventListener("focus", function () {
    refreshInvoiceStatus();
    if (linkedInvoice && linkedInvoice.invoice_id) loadPaymentAdjustment(linkedInvoice.invoice_id);
  });

  els.paymentLines?.addEventListener("change", function (ev) {
    if (!ev.target.closest("select")) return;
    if (saleIsApproved()) syncGenerateBillPrompt();
  });

  els.paymentLines?.addEventListener("input", function () {
    if (!lastSaleRecord || !els.invoiceStatus) return;
    paintInvoiceStatus(lastSaleRecord);
  });

  // Invoice is opened from the Invoice stage. Generate/approve prompts are not used.
  els.addPaymentBtn?.addEventListener("click", function () { addPaymentLine({}); });
  els.billAmount?.addEventListener("input", updatePaymentSummary);
  document.getElementById("fuBillNoCopy")?.addEventListener("click", function () {
    copyTextToClipboard((els.billNo?.value || "").trim(), this);
  });

  function syncStatusUrl(entryId) {
    if (window.FU_API && window.FU_API.sync_status) {
      return apiUrl(window.FU_API.sync_status, entryId);
    }
    // Fallback: /dsc/followup/records/{id}/sync-idsign-status
    return "/dsc/followup/records/" + String(entryId) + "/sync-idsign-status";
  }

  function syncIdSignStatus(entryId, button, appNo) {
    if (!isDscModule) {
      alert("ID Sign sync is only for DSC followup.");
      return;
    }
    const ref = (appNo || "").toString().trim();
    if (!ref) {
      alert("Application number is required to sync status.");
      return;
    }
    const url = syncStatusUrl(entryId);
    if (button) {
      button.disabled = true;
      button.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    }
    fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": window.FU_CSRF || csrfToken(),
      },
      body: JSON.stringify({
        csrf_token: window.FU_CSRF || csrfToken(),
        application_number: ref,
        reference_no: ref,
      }),
    })
      .then(function (res) {
        return res.json().then(function (payload) {
          return { ok: res.ok, payload: payload };
        }).catch(function () {
          return {
            ok: false,
            payload: {
              error:
                "Invalid response from sync API. Restart Flask server and try again.",
            },
          };
        });
      })
      .then(function (result) {
        if (!result.ok || !result.payload.ok) {
          throw new Error((result.payload && result.payload.error) || "Sync failed.");
        }
        const remarks = result.payload.remarks || result.payload.status || "";
        const rejectComment = normalizeRejectComment(
          result.payload.reason_for_unverified != null
            ? result.payload.reason_for_unverified
            : result.payload.reject_comment
        );
        rawGridRows = (rawGridRows || []).map(function (row) {
          if (Number(row.entry_id) === Number(entryId)) {
            return Object.assign({}, row, {
              remarks: remarks,
              Remarks: remarks,
              reason_for_unverified: rejectComment || null,
              ReasonForUnverified: rejectComment || null,
            });
          }
          return row;
        });
        renderGrid();
      })
      .catch(function (err) {
        alert(err.message || "Unable to sync ID Sign status.");
      })
      .finally(function () {
        if (button) {
          button.disabled = false;
          button.innerHTML = '<i class="bi bi-arrow-repeat"></i>';
        }
      });
  }

  if (isDscModule && els.gridBody) {
    els.gridBody.addEventListener("mouseover", function (event) {
      const tip = event.target.closest(".fu-remarks-tip");
      if (!tip || !els.gridBody.contains(tip)) return;
      showRemarksRejectTip(tip);
    });
    els.gridBody.addEventListener("mouseout", function (event) {
      const tip = event.target.closest(".fu-remarks-tip");
      if (!tip) return;
      const related = event.relatedTarget;
      if (related && (tip.contains(related) || (remarksRejectTipEl && remarksRejectTipEl.contains(related)))) {
        return;
      }
      scheduleHideRemarksRejectTip();
    });
    els.gridBody.addEventListener("focusin", function (event) {
      const tip = event.target.closest(".fu-remarks-tip");
      if (!tip || !els.gridBody.contains(tip)) return;
      showRemarksRejectTip(tip);
    });
    els.gridBody.addEventListener("focusout", function (event) {
      const tip = event.target.closest(".fu-remarks-tip");
      if (!tip) return;
      const related = event.relatedTarget;
      if (related && (tip.contains(related) || (remarksRejectTipEl && remarksRejectTipEl.contains(related)))) {
        return;
      }
      scheduleHideRemarksRejectTip();
    });
    document.addEventListener("scroll", hideRemarksRejectTip, true);
    window.addEventListener("resize", hideRemarksRejectTip);
  }

  els.gridBody?.addEventListener("click", function (event) {
    const thankWaBtn = event.target.closest(".fu-thank-wa");
    if (thankWaBtn) {
      event.preventDefault();
      sendThankYouWhatsApp(thankWaBtn);
      return;
    }
    const videoCopyBtn = event.target.closest(".fu-video-link-copy");
    if (videoCopyBtn) {
      event.preventDefault();
      if (videoCopyBtn.disabled) return;
      const appNo = (videoCopyBtn.getAttribute("data-app-no") || "").trim();
      const mobile = (videoCopyBtn.getAttribute("data-mobile") || "").trim();
      if (!currentCustomerVideoBase()) {
        alert("Set Video link for Customer first.");
        return;
      }
      if (!appNo || !mobile) {
        alert("Application No. and Mobile are required to copy the Video Link.");
        return;
      }
      const url = buildDscRowVideoLink(appNo, mobile);
      if (!url) return;
      copyTextToClipboard(url, videoCopyBtn);
      if (window.JTCSDialog && typeof JTCSDialog.alert === "function") {
        JTCSDialog.alert("Video Link Copied", "success");
      }
      return;
    }
    const copyBtn = event.target.closest(".fu-copy-btn");
    if (copyBtn) {
      if (!isDscModule) return;
      const cell = copyBtn.closest(".fu-copy-cell");
      const text = (cell && cell.querySelector(".fu-copy-text")
        ? cell.querySelector(".fu-copy-text").textContent
        : ""
      ).trim();
      if (!text) return;
      copyTextToClipboard(text, copyBtn);
      return;
    }
    const syncBtn = event.target.closest(".fu-status-sync");
    if (syncBtn) {
      const entryId = parseInt(syncBtn.dataset.id, 10);
      if (!entryId) {
        alert("Invalid record.");
        return;
      }
      const appNo = (syncBtn.dataset.appNo || "").trim();
      if (!appNo) {
        alert("Application number is required to sync status.");
        return;
      }
      syncIdSignStatus(entryId, syncBtn, appNo);
      return;
    }
    const kdkRowSync = event.target.closest(".fu-kdk-row-sync");
    if (kdkRowSync) {
      if (kdkRowSync.disabled) return;
      const entryId = parseInt(kdkRowSync.dataset.id, 10);
      if (!entryId) {
        alert("Invalid record.");
        return;
      }
      const syncRow = rows.find(function (r) {
        return Number(r.entry_id) === entryId;
      });
      if (isItrPaymentReceivedLocked(syncRow)) {
        alert("Sync is locked after Payment Received.");
        return;
      }
      openItrSyncLogin(entryId);
      return;
    }
    const editBtn = event.target.closest(".fu-edit-btn");
    if (editBtn) {
      openEntryForEdit(parseInt(editBtn.dataset.id, 10)).catch(function (err) {
        alert(err.message || "Unable to load entry.");
      });
      return;
    }
    const delBtn = event.target.closest(".fu-delete-btn");
    if (delBtn) {
      if (delBtn.disabled) return;
      const delId = parseInt(delBtn.dataset.id, 10);
      deleteEntry(delId);
    }
  });

  if (isItrModule) {
    initItrGridSortHeaders();
    const gridTable = document.getElementById("fuDataGrid");
    const gridHead = gridTable?.querySelector("thead");
    gridHead?.addEventListener("click", function (event) {
      const th = event.target.closest("th.fu-sortable");
      if (!th) return;
      onItrSortHeaderClick(th.dataset.sortKey);
    });
    gridHead?.addEventListener("keydown", function (event) {
      if (event.key !== "Enter" && event.key !== " ") return;
      const th = event.target.closest("th.fu-sortable");
      if (!th) return;
      event.preventDefault();
      onItrSortHeaderClick(th.dataset.sortKey);
    });
  }

  document.addEventListener("click", function (event) {
    if (!event.target.closest("#fuCustomerSearch") && !event.target.closest("#fuCustomerResults")) {
      hideCustomerResults();
    }
    if (!event.target.closest("#fuBillingCustomerSearch") && !event.target.closest("#fuBillingCustomerResults")) {
      hideBillingResults();
    }
  });

  applyItrDefaultStatusFilter();
  syncStatCardActive();
  initDscAssist();

  loadGrid().finally(function () {
    if (!window.FU_AUTO_LOAD_ENTRY_ID) return;
    var autoId = parseInt(window.FU_AUTO_LOAD_ENTRY_ID, 10);
    if (!Number.isNaN(autoId) && autoId > 0) {
      openEntryForEdit(autoId).catch(function (err) {
        alert(err.message || "Unable to load entry.");
      });
    }
  });
})();
