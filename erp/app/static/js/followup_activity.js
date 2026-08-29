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
  const paymentLineHasDate = isItrModule || isDscModule || isGstModule || isTdsModule;

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
    formType: document.getElementById("fuFormType"),
    quarter: document.getElementById("fuQuarter"),
    customerSearch: document.getElementById("fuCustomerSearch"),
    customerId: document.getElementById("fuCustomerId"),
    customerResults: document.getElementById("fuCustomerResults"),
    customerSelected: document.getElementById("fuCustomerSelected"),
    addCustomerBtn: document.getElementById("fuAddCustomerBtn"),
    workflowChecks: document.getElementById("fuWorkflowChecks"),
    itrFiledWrap: document.getElementById("fuItrFiledWrap"),
    itrFiledDate: document.getElementById("fuItrFiledDate"),
    tallyBillWrap: document.getElementById("fuTallyBillWrap"),
    billNo: document.getElementById("fuBillNo"),
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
  let itrSyncPollTimer = null;
  let pendingItrSyncEntryId = null;
  let rows = [];
  let rawGridRows = [];
  // ITR default: entry date/time ascending (oldest first).
  let gridSortKey = isItrModule ? "created_date" : null;
  let gridSortDir = "asc";
  const bankAccounts = window.FU_BANK_ACCOUNTS || [];
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

  function canDownloadThankYou(row) {
    // ITR: thank-you letter only after Payment Received is ticked.
    if (isItrModule) return rowHasPaymentReceived(row);
    return rowHasTallyBill(row);
  }

  function isItrPaymentReceivedLocked(row) {
    return isItrModule && rowHasPaymentReceived(row);
  }

  async function openEntryForEdit(entryId) {
    return loadEntry(entryId);
  }

  function canDownloadPaymentReminder(row) {
    // ITR only: after Tally Bill Generated, while payment is still pending.
    if (!isItrModule) return false;
    if (!rowHasTallyBill(row)) return false;
    if (rowHasPaymentReceived(row)) return false;
    return !!(window.FU_API && window.FU_API.payment_reminder);
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
    const tallyChecked = isStageChecked("tally_bill_generated");
    const paymentChecked = isStageChecked("payment_received");
    if (!tallyChecked && !paymentChecked) return;
    payload.bill_no = (els.billNo?.value || "").trim();
    payload.bill_date = els.billDate?.value || "";
    payload.bill_amount = els.billAmount?.value || "";
    if (isStageChecked("itr_filed") && els.itrFiledDate) {
      payload.itr_filed_date = els.itrFiledDate.value || "";
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
      if ((els.paymentLines?.querySelectorAll(".fu-payment-line") || []).length <= 1) return;
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
      return parseInt(cb.value, 10);
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

  function validateDscEntry() {
    if (!isDscModule) return null;
    const locked = els.applicationNumber?.dataset.locked === "1";
    const applicationNo = (els.applicationNumber?.value || "").trim();
    if (isDscApplicationStageChecked() && !isStageChecked("documents_received") && !applicationNo && !locked) {
      return "Application number is required when Application No. is checked.";
    }
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
      const billAmount = parseFloat(els.billAmount?.value || "0");
      if (!billAmount || billAmount <= 0) {
        return "Bill amount is required when Tally Bill Generated is checked.";
      }
    }
    if (isStageChecked("payment_received")) {
      if (!(els.billNo?.value || "").trim()) {
        return "Tally bill number is required before marking Payment Received.";
      }
      const billAmount = parseFloat(els.billAmount?.value || "0");
      if (!billAmount || billAmount <= 0) {
        return "Bill amount is required for Payment Received.";
      }
    }
    return null;
  }

  function syncWorkflowPanels() {
    const itrChecked = isStageChecked("itr_filed");
    const tallyChecked = isStageChecked("tally_bill_generated");
    const paymentChecked = isStageChecked("payment_received");
    els.itrFiledWrap?.classList.toggle("d-none", !itrChecked);
    els.tallyBillWrap?.classList.toggle("d-none", !tallyChecked);
    els.autoBillBtn?.classList.toggle("d-none", !tallyChecked);
    els.paymentWrap?.classList.toggle("d-none", !paymentChecked);
    if (paymentChecked && !els.paymentLines?.querySelector(".fu-payment-line")) {
      resetPaymentLines([]);
    }
    if (itrChecked && els.itrFiledDate && !els.itrFiledDate.value) {
      els.itrFiledDate.value = window.FU_DEFAULT_DATE || new Date().toISOString().slice(0, 10);
    }
    if (tallyChecked && els.billDate && !els.billDate.value) {
      els.billDate.value = window.FU_DEFAULT_DATE || new Date().toISOString().slice(0, 10);
    }
    syncUnverifiedPanel();
    syncDscApplicationField();
  }

  function syncUnverifiedPanel() {
    const unverified = els.workflowChecks?.querySelector('.fu-stage-check[data-stage-code="unverified"]');
    const show = !!(unverified && unverified.checked);
    els.unverifiedWrap?.classList.toggle("d-none", !show);
  }

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
  }

  function hideCustomerResults() {
    if (!els.customerResults) return;
    els.customerResults.classList.add("d-none");
    els.customerResults.innerHTML = "";
  }

  function selectCustomer(customer) {
    if (!customer) return;
    if (els.customerId) els.customerId.value = String(customer.customer_id || customer.CustomerID || "");
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
    if (els.formType) els.formType.value = "";
    if (els.quarter) els.quarter.value = "";
    if (els.applicationNumber) {
      els.applicationNumber.value = "";
      delete els.applicationNumber.dataset.locked;
    }
    if (els.location) els.location.value = "";
    if (els.introducedBy) els.introducedBy.value = "";
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
      { key: "bill_no", type: "text" },
      { key: "bill_date", type: "date" },
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

  function renderGrid(data) {
    if (data) rawGridRows = data;
    rows = applyItrGridSort(rawGridRows);
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
      const periodCol = (isItrModule || isTdsModule || isGstModule)
        ? "<td>" + escapeHtml(row.tax_period || "—") + "</td>"
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
      const thankYouCell = canDownloadThankYou(row)
        ? '<a class="btn btn-outline-success btn-sm fu-thank-btn" href="' +
          escapeHtml(apiUrl(window.FU_API.thank_you_letter, row.entry_id) + "?format=png") +
          '" title="Download Thank You Letter (PNG)"><i class="bi bi-download"></i> PNG</a>'
        : '<span class="text-muted" title="' +
          (isItrModule ? "Available after Payment Received" : "Available after Tally Bill Generated") +
          '">—</span>';
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
          : '<td class="text-center text-muted" title="Available after Tally Bill Generated">—</td>')
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
      const deleteDisabledAttrs = ' title="Delete"';
      const editTitle = "Edit";
      const appNoValue = isDscModule
        ? (row.application_number || row.bill_no || "")
        : (row.bill_no || "");
      const mobileCell = isDscModule
        ? copyableCell(row.mobile_number)
        : "<td>" + escapeHtml(row.mobile_number || "—") + "</td>";
      const emailCell = isDscModule ? copyableCell(row.email_id) : "";
      const panCell = isDscModule
        ? copyableCell(row.pan_number)
        : "<td>" + escapeHtml(row.pan_number || "—") + "</td>";
      const appOrBillCell = isDscModule
        ? copyableCell(appNoValue)
        : "<td>" + escapeHtml(appNoValue || "—") + "</td>";
      return (
        '<tr' + (paymentLocked ? ' class="fu-payment-received-row"' : "") + ">" +
        "<td>" + escapeHtml(formatDate(row.work_date)) + "</td>" +
        periodCol +
        tdsPeriodCols +
        gstFieldCols +
        "<td><strong>" + escapeHtml(row.customer_name) + "</strong></td>" +
        mobileCell +
        emailCell +
        panCell +
        appOrBillCell +
        "<td>" + escapeHtml(formatDate(row.bill_date)) + "</td>" +
        workOrCheckCell +
        returnCol +
        filingCols +
        '<td><span class="fu-status-badge ' + statusBadgeClass(status) + '">' + escapeHtml(status) + "</span></td>" +
        (isItrModule
          ? "<td>" + escapeHtml(formatPaymentReceiveDateCell(row)) + "</td>"
          : "") +
        remarksCellHtml(row) +
        paymentReminderCell +
        rowSyncCell +
        "<td>" + thankYouCell + "</td>" +
        '<td class="text-end fu-grid-actions">' +
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
        "</td>" +
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
    resetEntryForm();
    entryModal?.show();
  }

  function fillEntryForm(record) {
    resetEntryForm();
    if (!record) return;
    if (els.entryId) els.entryId.value = String(record.entry_id || "");
    if (els.workDate) els.workDate.value = (record.work_date || "").slice(0, 10);
    if (els.taxPeriod) els.taxPeriod.value = record.tax_period || "";
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
    (record.stage_ids || []).forEach(function (stageId) {
      const cb = els.workflowChecks?.querySelector('.fu-stage-check[value="' + stageId + '"]');
      if (cb) cb.checked = true;
    });
    syncWorkflowPanels();
    if (els.entryModalTitle) {
      els.entryModalTitle.textContent = workTypeLabel + " — Edit Entry";
    }
    entryModal?.show();
  }

  function openBillingPage() {
    const customerId = (els.customerId?.value || "").trim();
    if (!customerId) {
      alert("Please select a customer first.");
      return;
    }
    // Open Accounting Invoice in a separate large browser window with normal
    // chrome (back / maximize / restore) — not the old followup/billing popup.
    const params = new URLSearchParams();
    params.set("customer_id", customerId);
    const customerName = (els.customerSearch?.value || "").trim();
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

  function saveEntry() {
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
    if (isDscModule) {
      if (els.applicationNumber) {
        payload.application_number = (els.applicationNumber.value || "").trim();
      }
      payload.location = (els.location?.value || "").trim();
      payload.introduced_by = (els.introducedBy?.value || "").trim();
      payload.email_id = (els.customerEmail?.value || "").trim();
    }
    appendBillingPayload(payload);
    if (isStageChecked("payment_received")) {
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
    const dscError = validateDscEntry();
    if (dscError) {
      alert(dscError);
      return;
    }
    if (els.saveBtn) els.saveBtn.disabled = true;
    fetch(window.FU_API.save, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify(payload),
    })
      .then(function (res) { return parseJsonResponse(res); })
      .then(function () {
        entryModal?.hide();
        return loadGrid();
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
    }
    clearTimeout(customerSearchTimer);
    customerSearchTimer = setTimeout(function () {
      searchCustomers(els.customerSearch.value);
    }, 300);
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

  els.workflowChecks?.addEventListener("change", function (event) {
    if (event.target.classList.contains("fu-stage-check")) syncWorkflowPanels();
  });

  els.autoBillBtn?.addEventListener("click", openBillingPage);
  els.addPaymentBtn?.addEventListener("click", function () { addPaymentLine({}); });
  els.billAmount?.addEventListener("input", updatePaymentSummary);

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
  });

  applyItrDefaultStatusFilter();
  syncStatCardActive();

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
