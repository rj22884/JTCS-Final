(function () {
  const form = document.getElementById("stampActivityForm");
  if (!form) return;

  const els = {
    mobileGate: document.getElementById("stampMobileGate"),
    mainWorkspace: document.getElementById("stampMainWorkspace"),
    mobileInput: document.getElementById("stampMobileInput"),
    mobileContinueBtn: document.getElementById("stampMobileContinueBtn"),
    mobileError: document.getElementById("stampMobileError"),
    mobileDisplay: document.getElementById("stampMobileDisplay"),
    mobileHidden: document.getElementById("MobileNumber"),
    partialOcrAlert: document.getElementById("stampPartialOcrAlert"),
    formLayout: document.getElementById("stampFormLayout"),
    formContent: document.getElementById("stampFormContent"),
    saveBtn: document.getElementById("stampSaveBtn"),
    editBtn: document.getElementById("stampEditBtn"),
    ocrStatusText: document.getElementById("stampOcrStatusText"),
    ocrIcon: document.getElementById("stampOcrIcon"),
    ocrConfidenceWrap: document.getElementById("stampOcrConfidenceWrap"),
    ocrConfidence: document.getElementById("stampOcrConfidence"),
    ocrReason: document.getElementById("stampOcrReason"),
    ocrProviderBadge: document.getElementById("stampOcrProviderBadge"),
    ocrEngineAlert: document.getElementById("stampOcrEngineAlert"),
    installOcrBtn: document.getElementById("stampInstallOcrBtn"),
    ocrImageId: document.getElementById("OcrImageID"),
    modeManual: document.getElementById("modeManual"),
    modeOcr: document.getElementById("modeOcr"),
    imageColumn: document.getElementById("stampImageColumn"),
    photoBox: document.getElementById("stampPhotoBox"),
    placeholder: document.getElementById("stampPhotoPlaceholder"),
    preview: document.getElementById("stampPhotoPreview"),
    pdfPreview: document.getElementById("stampPdfPreview"),
    pdfName: document.getElementById("stampPdfName"),
    overlay: document.getElementById("stampOcrOverlay"),
    fileInput: document.getElementById("stampFileInput"),
    browseBtn: document.getElementById("stampBrowseBtn"),
    pasteBtn: document.getElementById("stampPasteBtn"),
    retryBtn: document.getElementById("stampRetryBtn"),
    clearImageBtn: document.getElementById("stampClearImageBtn"),
    certNumber: document.getElementById("CertificateNumber"),
    certIssuedDate: document.getElementById("CertificateIssuedDate"),
    transactionDate: document.getElementById("TransactionDate"),
    saleAmount: document.getElementById("SaleAmount"),
    paymentLines: document.getElementById("stampPaymentLines"),
    paymentAddBtn: document.getElementById("stampAddPaymentBtn"),
    paymentSummary: document.getElementById("stampPaymentSummary"),
    zoomModalEl: document.getElementById("stampZoomModal"),
    zoomImage: document.getElementById("stampZoomImage"),
    zoomBody: document.getElementById("stampZoomBody"),
    duplicateModalEl: document.getElementById("stampDuplicateModal"),
    duplicateBody: document.getElementById("stampDuplicateBody"),
    duplicateViewBtn: document.getElementById("stampDuplicateViewBtn"),
    searchPanel: document.getElementById("stampSearchPanel"),
    searchGridBody: document.getElementById("stampSearchGridBody"),
    searchEmpty: document.getElementById("stampSearchEmpty"),
    searchSummary: document.getElementById("stampSearchSummary"),
    stampIdInput: document.getElementById("StampID"),
    editStampIdInput: document.getElementById("EditStampID"),
    entryModalEl: document.getElementById("stampEntryModal"),
    entryCloseBtn: document.getElementById("stampEntryCloseBtn"),
    entryModeHidden: document.getElementById("EntryMode"),
    filterDateFrom: document.getElementById("stampFilterDateFrom"),
    filterDateTo: document.getElementById("stampFilterDateTo"),
    filterCert: document.getElementById("stampFilterCert"),
    filterMobile: document.getElementById("stampFilterMobile"),
    filterCustomer: document.getElementById("stampFilterCustomer"),
    filterPeriod: document.getElementById("stampFilterPeriod"),
    filterApplyBtn: document.getElementById("stampFilterApplyBtn"),
    filterResetBtn: document.getElementById("stampFilterResetBtn"),
    periodGrid: document.getElementById("stampPeriodGrid"),
    periodLabel: document.getElementById("stampPeriodLabel"),
    dataGridBody: document.getElementById("stampDataGridBody"),
    dataGridCount: document.getElementById("stampDataGridCount"),
    dataGridEmpty: document.getElementById("stampDataGridEmpty"),
    dataGridTitle: document.querySelector(".stamp-data-grid-panel .stamp-section-head"),
    pageSize: document.getElementById("stampPageSize"),
    pageInfo: document.getElementById("stampPageInfo"),
    pagerNav: document.getElementById("stampPagerNav"),
    cardDetailModalEl: document.getElementById("stampCardDetailModal"),
    cardDetailTitle: document.getElementById("stampCardDetailTitle"),
    cardDetailSub: document.getElementById("stampCardDetailSub"),
    cardDetailCount: document.getElementById("stampCardDetailCount"),
    cardDetailTotal: document.getElementById("stampCardDetailTotal"),
    cardDetailHead: document.getElementById("stampCardDetailHead"),
    cardDetailBody: document.getElementById("stampCardDetailBody"),
    cardDetailEmpty: document.getElementById("stampCardDetailEmpty"),
    dutyGroupFrom: document.getElementById("stampDutyGroupFrom"),
    dutyGroupTo: document.getElementById("stampDutyGroupTo"),
    dutyGroupApplyBtn: document.getElementById("stampDutyGroupApplyBtn"),
    dutyGroupClearBtn: document.getElementById("stampDutyGroupClearBtn"),
    dutyGroupBody: document.getElementById("stampDutyGroupBody"),
    dutyGroupHint: document.getElementById("stampDutyGroupHint"),
    dutyGroupTotalNos: document.getElementById("stampDutyGroupTotalNos"),
    dutyGroupTotalAmt: document.getElementById("stampDutyGroupTotalAmt"),
  };

  let mainGridRows = [];
  let applyingPeriodPreset = false;
  let gridSortKey = "transaction_date";
  let gridSortDir = "desc";
  let activeCardFilter = null;
  let lastPeriodSummary = {};
  let cardDetailModal = null;
  const PAGE_SIZES = [25, 50, 100, 200, 500, 1000];
  const PAGE_SIZE_KEY = "stamp-page-size";
  let pageState = { page: 1, pageSize: 50 };
  const CARD_META = {
    total_sale_amount: { label: "Total Stamp Sale Amount", className: "is-sale" },
    payment_received_amount: { label: "Payment Received Amount", className: "is-payment" },
    received_cash: { label: "Received in Cash", className: "is-cash" },
    received_non_cash: { label: "Received Other Than Cash", className: "is-noncash" },
    shcil_stamp_deposit: { label: "Deposited in SHCILStamp", className: "is-shcil" },
  };
  const gridFilters = {
    certificate_number: "",
    certificate_date: "",
    stamp_duty_amount: "",
    sale_amount: "",
    transaction_date: "",
    customer_name: "",
    mobile_number: "",
    payment_mode: "",
    transaction_id: "",
  };

  let selectedFile = null;
  let previewDataUrl = null;
  let ocrRunning = false;
  let mobileConfirmed = false;
  let switchingMode = false;
  let zoomModal = null;
  let duplicateModal = null;
  let entryModal = null;
  let zoomScale = 1;
  let zoomRotate = 0;
  let selectedStampId = null;
  let editingStampId = null;
  let saveMode = false;
  let blockedDuplicateCert = null;
  let searchResults = [];
  let ocrImportedLock = false;
  let txnDateManualOverride = false;

  function defaultTransactionDateToday() {
    if (!els.transactionDate) return;
    const today = (window.STAMP_DEFAULT_DATE || "").trim();
    if (today) els.transactionDate.value = today;
    setTransactionDateManual(true);
  }

  function defaultTransactionDateFromCert(force) {
    if (!els.certIssuedDate || !els.transactionDate) return;
    const certDate = (els.certIssuedDate.value || "").trim();
    if (!certDate) return;
    if (force || !txnDateManualOverride) {
      els.transactionDate.value = certDate;
    }
  }

  function setTransactionDateManual(value) {
    txnDateManualOverride = !!value;
  }

  const OCR_LOCKED_SECTION_IDS = ["stampSectionCert", "stampSectionParty"];
  const OCR_EDITABLE_SECTION_IDS = ["stampSectionAmount", "stampSectionRemarks"];

  const MANUAL_ENABLED_FIELD_IDS = [
    "CertificateNumber",
    "CertificateIssuedDate",
    "TransactionDate",
    "StampDutyPaidBy",
    "StampDutyAmount",
    "SaleAmount",
    "Remarks",
  ];

  const MANUAL_REQUIRED_FIELDS = [
    { id: "CertificateNumber", label: "Certificate Number" },
    { id: "CertificateIssuedDate", label: "Certificate Date" },
    { id: "TransactionDate", label: "Transaction Date" },
    { id: "StampDutyPaidBy", label: "Stamp Duty Paid By" },
    { id: "StampDutyAmount", label: "Stamp Duty Amount" },
    { id: "SaleAmount", label: "Sale Amount" },
  ];

  if (els.zoomModalEl && window.bootstrap) zoomModal = new bootstrap.Modal(els.zoomModalEl);
  if (els.duplicateModalEl && window.bootstrap) duplicateModal = new bootstrap.Modal(els.duplicateModalEl);
  if (els.entryModalEl && window.bootstrap) entryModal = new bootstrap.Modal(els.entryModalEl);
  if (els.cardDetailModalEl && window.bootstrap) cardDetailModal = new bootstrap.Modal(els.cardDetailModalEl);

  const fieldMap = {
    CertificateNumber: "CertificateNumber",
    CertificateIssuedDate: "CertificateIssuedDate",
    AccountReference: "AccountReference",
    UniqueDocumentReference: "UniqueDocumentReference",
    PurchasedBy: "PurchasedBy",
    DescriptionOfDocument: "DescriptionOfDocument",
    PropertyDescription: "PropertyDescription",
    ConsiderationPrice: "ConsiderationPrice",
    FirstPartyName: "FirstPartyName",
    SecondPartyName: "SecondPartyName",
    StampDutyPaidBy: "StampDutyPaidBy",
    StampDutyAmount: "StampDutyAmount",
  };

  const OCR_REQUIRED_FIELDS = [
    "CertificateNumber",
    "CertificateIssuedDate",
    "PurchasedBy",
    "FirstPartyName",
    "SecondPartyName",
    "StampDutyPaidBy",
    "StampDutyAmount",
  ];

  const MANDATORY_FIELD_IDS = [
    "CertificateNumber",
    "CertificateIssuedDate",
    "TransactionDate",
    "FirstPartyName",
    "StampDutyAmount",
    "SaleAmount",
  ];

  const REQUIRED_FIELDS = [
    { id: "CertificateNumber", label: "Certificate Number" },
    { id: "CertificateIssuedDate", label: "Certificate Date" },
    { id: "FirstPartyName", label: "First Party" },
    { id: "TransactionDate", label: "Transaction Date" },
    { id: "StampDutyAmount", label: "Stamp Duty Amount" },
    { id: "SaleAmount", label: "Sale Amount" },
  ];

  function isManualEntry() {
    return !!(els.modeManual && els.modeManual.checked);
  }

  function syncEntryModeHidden() {
    if (els.entryModeHidden) {
      els.entryModeHidden.value = isManualEntry() ? "manual" : "ocr";
    }
  }

  function activeRequiredFields() {
    if (ocrImportedLock) {
      return REQUIRED_FIELDS;
    }
    if (isManualEntry()) {
      return MANUAL_REQUIRED_FIELDS;
    }
    return REQUIRED_FIELDS;
  }

  function setManualFieldLock(active) {
    if (ocrImportedLock) return;

    const formContent = document.getElementById("stampFormContent");
    if (!formContent) return;

    const enabledSet = new Set(MANUAL_ENABLED_FIELD_IDS);
    formContent.querySelectorAll("input.stamp-field, textarea.stamp-field").forEach(function (el) {
      const allow = !active || enabledSet.has(el.id);
      el.disabled = !allow;
      el.readOnly = false;
      el.classList.toggle("stamp-field-manual-disabled", active && !allow);
      if (active && !allow) {
        el.removeAttribute("required");
      } else if (active && ["CertificateNumber", "CertificateIssuedDate", "TransactionDate", "StampDutyAmount", "SaleAmount"].includes(el.id)) {
        el.setAttribute("required", "required");
      } else if (active && el.id === "StampDutyPaidBy") {
        el.setAttribute("required", "required");
      } else if (!active && el.classList.contains("stamp-field-mandatory")) {
        el.setAttribute("required", "required");
      }
    });

    ["stampSectionCert", "stampSectionParty", "stampSectionAmount", "stampSectionRemarks"].forEach(function (sectionId) {
      const section = document.getElementById(sectionId);
      if (!section) return;
      section.classList.toggle("stamp-section-manual-locked", active && sectionId === "stampSectionParty");
    });

    if (els.paymentAddBtn) els.paymentAddBtn.disabled = !active && !editingStampId;
    els.paymentLines?.querySelectorAll("input, select, button").forEach(function (el) {
      if (editingStampId) {
        el.disabled = el.classList.contains("stamp-payment-remove")
          ? (els.paymentLines?.querySelectorAll(".stamp-payment-line") || []).length <= 1
          : false;
        return;
      }
      if (el.classList.contains("stamp-payment-remove")) {
        el.disabled = !active;
        return;
      }
      el.disabled = !active;
    });
    if (active) {
      els.certNumber?.focus();
    }
    if (editingStampId && els.transactionDate) {
      els.transactionDate.disabled = false;
      els.transactionDate.readOnly = false;
      els.transactionDate.classList.remove("stamp-field-readonly", "stamp-field-manual-disabled");
    }
  }

  function ensureTransactionDateEditable() {
    if (!els.transactionDate) return;
    els.transactionDate.disabled = false;
    els.transactionDate.readOnly = false;
    els.transactionDate.classList.remove("stamp-field-readonly", "stamp-field-manual-disabled");
  }

  function getMandatoryFields() {
    if (isManualEntry() && !ocrImportedLock) {
      const base = MANUAL_REQUIRED_FIELDS.map(function (field) {
        return document.getElementById(field.id);
      }).filter(function (el) {
        return el && !el.disabled;
      });
      const paymentFields = [];
      els.paymentLines?.querySelectorAll(".stamp-payment-bank, .stamp-payment-amount").forEach(function (el) {
        if (!el.disabled) paymentFields.push(el);
      });
      return base.concat(paymentFields);
    }
    const base = MANDATORY_FIELD_IDS.map(function (id) {
      return document.getElementById(id);
    }).filter(function (el) {
      return el && el.offsetParent !== null && !el.disabled && !el.readOnly;
    });
    const paymentFields = [];
    els.paymentLines?.querySelectorAll(".stamp-payment-bank, .stamp-payment-amount").forEach(function (el) {
      if (el.offsetParent !== null && !el.disabled) paymentFields.push(el);
    });
    return base.concat(paymentFields);
  }

  function formatMoney(value) {
    const num = parseFloat(value || "0");
    if (Number.isNaN(num)) return "0.00";
    return num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function formatDutyValue(value) {
    const num = parseFloat(value || "0");
    if (Number.isNaN(num)) return "0";
    if (Math.abs(num - Math.round(num)) < 0.001) return String(Math.round(num));
    return num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function dutyGroupDateParams() {
    const params = new URLSearchParams();
    const from = (els.dutyGroupFrom?.value || "").trim();
    const to = (els.dutyGroupTo?.value || "").trim();
    if (from) params.set("date_from", from);
    if (to) params.set("date_to", to);
    return params;
  }

  function renderDutyGrouping(data) {
    const rows = (data && data.rows) || [];
    if (els.dutyGroupHint) {
      const from = (data && data.date_from) || "";
      const to = (data && data.date_to) || "";
      if (!from && !to) els.dutyGroupHint.textContent = "All dates";
      else if (from && to) els.dutyGroupHint.textContent = from + " – " + to;
      else els.dutyGroupHint.textContent = from ? ("From " + from) : ("Upto " + to);
    }
    if (els.dutyGroupBody) {
      if (!rows.length) {
        els.dutyGroupBody.innerHTML =
          '<tr><td colspan="3" class="text-muted text-center py-3">No duty records</td></tr>';
      } else {
        els.dutyGroupBody.innerHTML = rows.map(function (row) {
          return (
            "<tr>" +
            "<td>" + escapeHtml(formatDutyValue(row.value)) + "</td>" +
            '<td class="text-end">' + escapeHtml(String(row.nos || 0)) + "</td>" +
            '<td class="text-end">' + escapeHtml(formatMoney(row.amount)) + "</td>" +
            "</tr>"
          );
        }).join("");
      }
    }
    if (els.dutyGroupTotalNos) els.dutyGroupTotalNos.textContent = String((data && data.total_nos) || 0);
    if (els.dutyGroupTotalAmt) els.dutyGroupTotalAmt.textContent = formatMoney((data && data.total_amount) || 0);
  }

  async function loadDutyGrouping() {
    if (!window.STAMP_DUTY_GROUP_URL || !els.dutyGroupBody) return;
    try {
      const res = await fetch(window.STAMP_DUTY_GROUP_URL + "?" + dutyGroupDateParams().toString(), {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load duty grouping.");
      renderDutyGrouping(data);
    } catch (err) {
      if (els.dutyGroupHint) els.dutyGroupHint.textContent = err.message || "Load failed";
      renderDutyGrouping({ rows: [], total_nos: 0, total_amount: "0.00" });
    }
  }

  function toIsoDate(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return y + "-" + m + "-" + d;
  }

  function getPeriodRange(preset) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const end = new Date(today);
    let start = new Date(today);
    if (preset === "today") {
      start = new Date(today);
    } else if (preset === "week") {
      start = new Date(today);
      const day = start.getDay();
      const diff = day === 0 ? 6 : day - 1;
      start.setDate(start.getDate() - diff);
    } else if (preset === "month") {
      start = new Date(today.getFullYear(), today.getMonth(), 1);
    } else if (preset === "year") {
      start = new Date(today.getFullYear(), 0, 1);
    } else {
      return {
        from: els.filterDateFrom?.value || "",
        to: els.filterDateTo?.value || "",
      };
    }
    return { from: toIsoDate(start), to: toIsoDate(end) };
  }

  function applyPeriodPreset(preset) {
    if (!preset || preset === "custom") return;
    const range = getPeriodRange(preset);
    applyingPeriodPreset = true;
    if (els.filterDateFrom) els.filterDateFrom.value = range.from;
    if (els.filterDateTo) els.filterDateTo.value = range.to;
    applyingPeriodPreset = false;
  }

  function markPeriodAsCustom() {
    if (applyingPeriodPreset || !els.filterPeriod) return;
    if (els.filterPeriod.value !== "custom") {
      els.filterPeriod.value = "custom";
    }
  }

  function formatDisplayDate(iso) {
    if (typeof window.formatDisplayDate === "function") {
      return window.formatDisplayDate(iso);
    }
    if (!iso) return "—";
    const parts = String(iso).split("-");
    if (parts.length !== 3) return iso;
    return parts[2] + "/" + parts[1] + "/" + parts[0];
  }

  function readGridFiltersFromDom() {
    document.querySelectorAll("#stampDataGrid .stamp-col-filter").forEach(function (input) {
      const key = input.dataset.filterKey;
      if (!key || !(key in gridFilters)) return;
      gridFilters[key] = (input.value || "").trim();
    });
  }

  function clearColumnFilters() {
    Object.keys(gridFilters).forEach(function (key) {
      gridFilters[key] = "";
    });
    document.querySelectorAll("#stampDataGrid .stamp-col-filter").forEach(function (input) {
      input.value = "";
    });
  }

  function hasActiveColumnFilters() {
    return Object.keys(gridFilters).some(function (key) {
      return !!(gridFilters[key] || "").trim();
    });
  }

  function rowFilterValue(row, key) {
    if (key === "certificate_date" || key === "transaction_date") {
      const iso = row[key] || "";
      return (formatDisplayDate(iso) + " " + iso).toLowerCase();
    }
    if (key === "transaction_id") {
      return row.transaction_id != null ? String(row.transaction_id) : "";
    }
    return String(row[key] == null ? "" : row[key]).toLowerCase();
  }

  function rowMatchesColumnFilters(row) {
    if (!hasActiveColumnFilters()) return true;
    return Object.keys(gridFilters).every(function (key) {
      const needle = (gridFilters[key] || "").trim().toLowerCase();
      if (!needle) return true;
      return rowFilterValue(row, key).indexOf(needle) !== -1;
    });
  }

  function sortValue(row, key) {
    if (key === "stamp_duty_amount" || key === "sale_amount") {
      const num = parseFloat(row[key] || "0");
      return Number.isNaN(num) ? 0 : num;
    }
    if (key === "transaction_id") {
      const num = parseInt(row.transaction_id, 10);
      return Number.isNaN(num) ? 0 : num;
    }
    if (key === "certificate_date" || key === "transaction_date") {
      return String(row[key] || "");
    }
    return String(row[key] == null ? "" : row[key]).toLowerCase();
  }

  function compareSortValues(a, b, dir) {
    const emptyA = a === "" || a == null;
    const emptyB = b === "" || b == null;
    if (emptyA && emptyB) return 0;
    if (emptyA) return 1;
    if (emptyB) return -1;
    if (typeof a === "number" && typeof b === "number") {
      return dir === "asc" ? a - b : b - a;
    }
    const sa = String(a);
    const sb = String(b);
    if (sa < sb) return dir === "asc" ? -1 : 1;
    if (sa > sb) return dir === "asc" ? 1 : -1;
    return 0;
  }

  function prepareGridRows(rows) {
    let prepared = (rows || []).filter(rowMatchesColumnFilters).filter(rowMatchesCardFilter);
    if (gridSortKey) {
      prepared = prepared.slice().sort(function (a, b) {
        return compareSortValues(sortValue(a, gridSortKey), sortValue(b, gridSortKey), gridSortDir);
      });
    }
    return prepared;
  }

  function rowMatchesCardFilter(row) {
    if (!activeCardFilter) return true;
    if (activeCardFilter === "received_cash") return !!row.has_cash;
    if (activeCardFilter === "received_non_cash") return !!row.has_non_cash;
    if (activeCardFilter === "shcil_stamp_deposit") return false;
    return true;
  }

  function updateGridSortHeaders() {
    document.querySelectorAll("#stampDataGrid thead th.stamp-sortable").forEach(function (th) {
      const key = th.dataset.sortKey;
      const icon = th.querySelector(".stamp-sort-icon");
      const active = key === gridSortKey;
      th.classList.toggle("stamp-sorted", active);
      th.setAttribute(
        "aria-sort",
        active ? (gridSortDir === "asc" ? "ascending" : "descending") : "none"
      );
      if (icon) {
        icon.textContent = active ? (gridSortDir === "asc" ? " ▲" : " ▼") : "";
      }
    });
  }

  function onGridSortHeader(sortKey) {
    if (!sortKey) return;
    if (gridSortKey === sortKey) {
      gridSortDir = gridSortDir === "asc" ? "desc" : "asc";
    } else {
      gridSortKey = sortKey;
      gridSortDir = "asc";
    }
    renderMainDataGrid(mainGridRows);
  }

  function effectiveCertificateFilter() {
    const top = (els.filterCert?.value || "").trim();
    const col = (gridFilters.certificate_number || "").trim();
    // Prefer the more specific / longer of the two active certificate inputs.
    if (top && col) return top.length >= col.length ? top : col;
    return top || col;
  }

  function effectiveCustomerFilter() {
    const top = (els.filterCustomer?.value || "").trim();
    const col = (gridFilters.customer_name || "").trim();
    if (top && col) return top.length >= col.length ? top : col;
    return top || col;
  }

  function buildGridQueryParams() {
    const params = new URLSearchParams();
    const cert = effectiveCertificateFilter();
    const customer = effectiveCustomerFilter();
    const mobile = (els.filterMobile?.value || "").trim();
    // Certificate / customer / mobile search is server-side (full JTCS). Period is ignored
    // so an integrated stamp is not hidden because its cert date is in another year.
    if (!cert && !customer && !mobile) {
      if (els.filterDateFrom?.value) params.set("date_from", els.filterDateFrom.value);
      if (els.filterDateTo?.value) params.set("date_to", els.filterDateTo.value);
    }
    if (cert) params.set("certificate", cert);
    if (els.filterMobile?.value.trim()) params.set("mobile", els.filterMobile.value.trim());
    if (customer) params.set("customer", customer);
    return params;
  }

  let certFilterReloadTimer = null;
  function scheduleCertificateServerReload() {
    if (certFilterReloadTimer) clearTimeout(certFilterReloadTimer);
    certFilterReloadTimer = setTimeout(function () {
      certFilterReloadTimer = null;
      loadMainGrid();
    }, 350);
  }

  function renderPeriodSummary(summary) {
    if (!els.periodGrid) return;
    summary = summary || {};
    lastPeriodSummary = summary;
    const cards = [
      { key: "total_sale_amount", label: "Total Stamp Sale Amount", className: "is-sale" },
      { key: "payment_received_amount", label: "Payment Received Amount", className: "is-payment" },
      { key: "received_cash", label: "Received in Cash", className: "is-cash" },
      { key: "received_non_cash", label: "Received Other Than Cash", className: "is-noncash" },
      { key: "shcil_stamp_deposit", label: "Deposited in SHCILStamp", className: "is-shcil" },
    ];
    els.periodGrid.innerHTML = "";
    cards.forEach(function (cardDef) {
      const card = document.createElement("button");
      card.type = "button";
      card.className =
        "stamp-period-card " +
        cardDef.className +
        (activeCardFilter === cardDef.key ? " is-active" : "");
      card.dataset.cardKey = cardDef.key;
      card.setAttribute("aria-pressed", activeCardFilter === cardDef.key ? "true" : "false");
      card.title = "Click to view " + cardDef.label + " details";
      card.innerHTML =
        "<div class=\"period-card-label\">" + escapeHtml(cardDef.label) + "</div>" +
        "<div class=\"period-card-value\">₹ " + escapeHtml(formatMoney(summary[cardDef.key] || "0")) + "</div>";
      card.addEventListener("click", function () {
        onPeriodCardClick(cardDef.key);
      });
      els.periodGrid.appendChild(card);
    });
    if (els.periodLabel) {
      const from = summary.period_from || els.filterDateFrom?.value || "";
      const to = summary.period_to || els.filterDateTo?.value || "";
      const count = summary.stamp_count != null ? summary.stamp_count : 0;
      if (from && to) {
        els.periodLabel.textContent =
          formatDisplayDate(from) + " to " + formatDisplayDate(to) + " · " + count + " stamp(s)";
      } else if (to) {
        els.periodLabel.textContent =
          "Up to " + formatDisplayDate(to) + " · " + count + " stamp(s)";
      } else {
        els.periodLabel.textContent = count + " stamp(s)";
      }
    }
    updateGridTitleForCard();
  }

  function updateGridTitleForCard() {
    if (!els.dataGridTitle) return;
    if (activeCardFilter && CARD_META[activeCardFilter]) {
      els.dataGridTitle.textContent =
        "Stamp Activity Records · " + CARD_META[activeCardFilter].label;
      return;
    }
    els.dataGridTitle.textContent = "Stamp Activity Records";
  }

  function clearCardFilter(options) {
    options = options || {};
    activeCardFilter = null;
    updateGridTitleForCard();
    if (els.periodGrid) {
      els.periodGrid.querySelectorAll(".stamp-period-card").forEach(function (card) {
        card.classList.remove("is-active");
        card.setAttribute("aria-pressed", "false");
      });
    }
    if (!options.skipRender) {
      renderMainDataGrid(mainGridRows, { resetPage: true });
    }
  }

  async function onPeriodCardClick(cardKey) {
    if (!cardKey) return;
    if (activeCardFilter === cardKey) {
      clearCardFilter();
      return;
    }
    activeCardFilter = cardKey;
    updateGridTitleForCard();
    if (els.periodGrid) {
      els.periodGrid.querySelectorAll(".stamp-period-card").forEach(function (card) {
        const active = card.dataset.cardKey === cardKey;
        card.classList.toggle("is-active", active);
        card.setAttribute("aria-pressed", active ? "true" : "false");
      });
    }
    renderMainDataGrid(mainGridRows, { resetPage: true });
    await openCardDetailPopup(cardKey);
  }

  function renderCardDetailStampRows(rows) {
    if (!els.cardDetailHead || !els.cardDetailBody) return;
    els.cardDetailHead.innerHTML =
      "<tr>" +
      "<th>Certificate</th><th>Cert Date</th><th class=\"text-end\">Duty ₹</th>" +
      "<th class=\"text-end\">Sale ₹</th><th>Txn Date</th><th>Customer</th>" +
      "<th>Mobile</th><th>Payment</th><th class=\"text-end\">Daily #</th>" +
      "</tr>";
    els.cardDetailBody.innerHTML = "";
    rows.forEach(function (row) {
      const tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" + escapeHtml(row.certificate_number || "") + "</td>" +
        "<td>" + escapeHtml(formatDisplayDate(row.certificate_date)) + "</td>" +
        "<td class=\"text-end\">" + escapeHtml(row.stamp_duty_amount || "") + "</td>" +
        "<td class=\"text-end\">" + escapeHtml(row.sale_amount || "") + "</td>" +
        "<td>" + escapeHtml(formatDisplayDate(row.transaction_date)) + "</td>" +
        "<td>" + escapeHtml(row.customer_name || "") + "</td>" +
        "<td>" + escapeHtml(row.mobile_number || "") + "</td>" +
        "<td>" + escapeHtml(row.payment_mode || "") + "</td>" +
        "<td class=\"text-end\">" + escapeHtml(row.transaction_id != null ? String(row.transaction_id) : "") + "</td>";
      els.cardDetailBody.appendChild(tr);
    });
  }

  function renderCardDetailDepositRows(rows) {
    if (!els.cardDetailHead || !els.cardDetailBody) return;
    els.cardDetailHead.innerHTML =
      "<tr>" +
      "<th>Voucher</th><th>Date</th><th>Purpose</th><th>From (Credit)</th>" +
      "<th>To (Debit)</th><th class=\"text-end\">Amount ₹</th><th>Remarks</th><th>Entered By</th>" +
      "</tr>";
    els.cardDetailBody.innerHTML = "";
    rows.forEach(function (row) {
      const tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" + escapeHtml(row.voucher_no || "") + "</td>" +
        "<td>" + escapeHtml(formatDisplayDate(row.work_date)) + "</td>" +
        "<td>" + escapeHtml(row.purpose || "") + "</td>" +
        "<td>" + escapeHtml(row.credit_account || "") + "</td>" +
        "<td>" + escapeHtml(row.debit_account || "") + "</td>" +
        "<td class=\"text-end\">" + escapeHtml(formatMoney(row.amount || "0")) + "</td>" +
        "<td>" + escapeHtml(row.remarks || "") + "</td>" +
        "<td>" + escapeHtml(row.entered_by || "") + "</td>";
      els.cardDetailBody.appendChild(tr);
    });
  }

  async function openCardDetailPopup(cardKey) {
    if (!window.STAMP_CARD_DETAIL_URL || !cardDetailModal) return;
    const meta = CARD_META[cardKey] || { label: cardKey };
    if (els.cardDetailTitle) els.cardDetailTitle.textContent = meta.label;
    if (els.cardDetailSub) els.cardDetailSub.textContent = "Loading...";
    if (els.cardDetailCount) els.cardDetailCount.textContent = "";
    if (els.cardDetailTotal) els.cardDetailTotal.textContent = "";
    if (els.cardDetailBody) {
      els.cardDetailBody.innerHTML =
        "<tr><td colspan=\"10\" class=\"text-muted\">Loading...</td></tr>";
    }
    els.cardDetailEmpty?.classList.add("d-none");
    cardDetailModal.show();

    try {
      const params = buildGridQueryParams();
      params.set("card", cardKey);
      const res = await fetch(window.STAMP_CARD_DETAIL_URL + "?" + params.toString(), {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.error || "Unable to load card details.");
      }
      const rows = data.rows || [];
      if (els.cardDetailTitle) els.cardDetailTitle.textContent = data.label || meta.label;
      if (els.cardDetailSub) {
        els.cardDetailSub.textContent =
          formatDisplayDate(data.period_from) + " to " + formatDisplayDate(data.period_to) +
          " · " + (data.row_count != null ? data.row_count : rows.length) + " record(s)";
      }
      if (els.cardDetailCount) {
        els.cardDetailCount.textContent =
          (data.row_count != null ? data.row_count : rows.length) + " record(s)";
      }
      if (els.cardDetailTotal) {
        els.cardDetailTotal.textContent = "Total: ₹ " + formatMoney(data.total || "0");
      }
      if (!rows.length) {
        if (els.cardDetailHead) els.cardDetailHead.innerHTML = "";
        if (els.cardDetailBody) els.cardDetailBody.innerHTML = "";
        els.cardDetailEmpty?.classList.remove("d-none");
        return;
      }
      els.cardDetailEmpty?.classList.add("d-none");
      if (data.row_type === "deposit") {
        renderCardDetailDepositRows(rows);
      } else {
        renderCardDetailStampRows(rows);
      }
    } catch (err) {
      if (els.cardDetailSub) els.cardDetailSub.textContent = err.message || "Load failed";
      if (els.cardDetailBody) {
        els.cardDetailBody.innerHTML =
          "<tr><td colspan=\"10\" class=\"text-danger\">" +
          escapeHtml(err.message || "Load failed") +
          "</td></tr>";
      }
    }
  }

  function readStoredPageSize() {
    try {
      const raw = localStorage.getItem(PAGE_SIZE_KEY) || "";
      if (raw === "all") return "all";
      const num = Number(raw);
      if (PAGE_SIZES.indexOf(num) !== -1) return num;
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
    const raw = els.pageSize?.value || String(pageState.pageSize);
    if (raw === "all") return "all";
    const num = Number(raw);
    return PAGE_SIZES.indexOf(num) !== -1 ? num : 50;
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
      '"><button type="button" class="page-link stamp-page-btn" data-page="' +
      page +
      '"' +
      (active ? ' aria-current="page"' : "") +
      ">" +
      label +
      "</button></li>"
    );
  }

  function renderPager(total, pageSize, page, totalPages, isAll) {
    pageState.page = page;
    pageState.pageSize = isAll ? "all" : pageSize;
    if (els.pageInfo) {
      if (!total) {
        els.pageInfo.textContent = "Showing 0 of 0";
      } else if (isAll) {
        els.pageInfo.textContent = "Showing all " + total;
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
    const items = [pagerItem("Previous", page - 1, { disabled: page <= 1 })];
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

  function renderMainDataGrid(rows, options) {
    options = options || {};
    mainGridRows = rows || [];
    if (!els.dataGridBody) return;
    const visible = prepareGridRows(mainGridRows);
    els.dataGridBody.innerHTML = "";
    if (!visible.length) {
      els.dataGridEmpty?.classList.remove("d-none");
      if (els.dataGridEmpty) {
        if (activeCardFilter === "shcil_stamp_deposit") {
          els.dataGridEmpty.textContent =
            "SHCILStamp deposits are shown in the detail popup (not stamp sale rows).";
        } else if (activeCardFilter && CARD_META[activeCardFilter]) {
          els.dataGridEmpty.textContent =
            "No stamp records match \"" + CARD_META[activeCardFilter].label + "\" for the current filters.";
        } else {
          els.dataGridEmpty.textContent = "No stamp records match the current filters.";
        }
      }
      if (els.dataGridCount) {
        els.dataGridCount.textContent = mainGridRows.length
          ? "0 of " + mainGridRows.length + " records"
          : "0 records";
      }
      renderPager(0, 25, 1, 1, false);
      updateGridSortHeaders();
      return;
    }
    els.dataGridEmpty?.classList.add("d-none");
    const sizeChoice = currentPageSize();
    const isAll = sizeChoice === "all";
    const pageSize = isAll ? visible.length : sizeChoice;
    const total = visible.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize) || 1);
    let page = options.resetPage ? 1 : pageState.page;
    if (options.focusStampId) {
      const idx = visible.findIndex(function (row) {
        return Number(row.stamp_id) === Number(options.focusStampId);
      });
      if (idx >= 0) page = Math.floor(idx / pageSize) + 1;
    }
    if (page > totalPages) page = totalPages;
    if (page < 1) page = 1;
    const start = (page - 1) * pageSize;
    const pageRows = visible.slice(start, start + pageSize);
    renderPager(total, pageSize, page, totalPages, isAll);
    if (els.dataGridCount) {
      const loadedNote =
        visible.length === mainGridRows.length
          ? total + " record" + (total === 1 ? "" : "s")
          : total + " of " + mainGridRows.length + " records";
      els.dataGridCount.textContent = loadedNote;
    }
    pageRows.forEach(function (row) {
      const tr = document.createElement("tr");
      tr.dataset.stampId = String(row.stamp_id);
      if (row.is_ocr_entry) {
        tr.classList.add("stamp-row-ocr");
      }
      const actionsHtml =
        "<td class=\"text-end stamp-grid-actions-col\">" +
        "<button type=\"button\" class=\"btn btn-outline-primary btn-sm stamp-grid-action-btn me-1 stamp-grid-edit-btn\" title=\"Edit\">" +
        "<i class=\"bi bi-pencil\"></i></button>" +
        "<button type=\"button\" class=\"btn btn-outline-danger btn-sm stamp-grid-action-btn stamp-grid-delete-btn\" title=\"Delete\">" +
        "<i class=\"bi bi-trash\"></i></button>" +
        "</td>";
      tr.innerHTML =
        "<td class=\"stamp-col-cert\" title=\"" + escapeHtml(row.certificate_number || "") + "\">" + escapeHtml(row.certificate_number || "") + "</td>" +
        "<td class=\"stamp-col-date\">" + escapeHtml(formatDisplayDate(row.certificate_date)) + "</td>" +
        "<td class=\"text-end stamp-col-num\">" + escapeHtml(row.stamp_duty_amount || "") + "</td>" +
        "<td class=\"text-end stamp-col-num\">" + escapeHtml(row.sale_amount || "") + "</td>" +
        "<td class=\"stamp-col-date\">" + escapeHtml(formatDisplayDate(row.transaction_date)) + "</td>" +
        "<td class=\"stamp-col-grow\" title=\"" + escapeHtml(sanitizeOcrValue(row.customer_name || "")) + "\">" + escapeHtml(sanitizeOcrValue(row.customer_name || "")) + "</td>" +
        "<td class=\"stamp-col-mobile\">" + escapeHtml(row.mobile_number || "") + "</td>" +
        "<td class=\"stamp-col-grow\" title=\"" + escapeHtml(row.payment_mode || "") + "\">" + escapeHtml(row.payment_mode || "") + "</td>" +
        "<td class=\"text-end stamp-col-daily\">" + escapeHtml(row.transaction_id != null ? String(row.transaction_id) : "") + "</td>" +
        actionsHtml;
      tr.addEventListener("click", function (e) {
        if (e.target.closest(".stamp-grid-action-btn")) return;
        Array.from(els.dataGridBody.querySelectorAll("tr")).forEach(function (r) {
          r.classList.remove("table-active");
        });
        tr.classList.add("table-active");
        setSelectedStamp(row.stamp_id);
        enterSelectMode();
      });
      tr.querySelector(".stamp-grid-edit-btn")?.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        editGridRecord(row.stamp_id);
      });
      tr.querySelector(".stamp-grid-delete-btn")?.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        deleteGridRecord(row.stamp_id);
      });
      els.dataGridBody.appendChild(tr);
    });
    updateGridSortHeaders();
    autoFitGridColumns();
  }

  function editGridRecord(stampId) {
    openRecordFromGrid(stampId);
  }

  async function deleteGridRecord(stampId) {
    if (!stampId || !window.STAMP_DELETE_URL) return;
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!(await JTCSDialog.confirm("Permanently delete this stamp record and all linked transactions? This cannot be undone."))) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({
        message: "Permanently delete this stamp record and all linked transactions? This cannot be undone.",
      });
      if (!creds) return;
    }

    try {
      const body = new FormData();
      body.append("csrf_token", window.STAMP_CSRF || "");
      if (creds) window.JTCSDeleteConfirm.appendCreds(body, creds);
      const res = await fetch(stampApiUrl(window.STAMP_DELETE_URL, stampId), {
        method: "POST",
        body: body,
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.error || "Delete failed.");
      }
      if (selectedStampId === stampId) {
        clearSelectedStamp();
        clearEntryFields();
      }
      await loadMainGrid();
    } catch (err) {
      alert(err.message || String(err));
    }
  }

  function applySessionMobile(mobile) {
    const digits = normalizeMobile(mobile);
    if (!digits) return false;
    mobileConfirmed = true;
    if (els.mobileHidden) els.mobileHidden.value = digits;
    if (els.mobileInput) els.mobileInput.value = digits;
    refreshMobileCustomers(digits);
    return true;
  }

  async function openRecordFromGrid(stampId) {
    if (!stampId) return;
    const row = mainGridRows.find(function (r) { return r.stamp_id === stampId; });
    if (row?.mobile_number) {
      applySessionMobile(row.mobile_number);
    }
    await loadStampRecord(stampId);
    openEntryModal();
    els.certNumber?.focus();
  }

  async function loadMainGrid(options) {
    options = options || { resetPage: true };
    if (!window.STAMP_GRID_URL) return;
    if (els.periodLabel) els.periodLabel.textContent = "Loading...";
    try {
      const params = buildGridQueryParams();
      const res = await fetch(window.STAMP_GRID_URL + "?" + params.toString(), {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.error || "Unable to load stamp grid.");
      }
      renderPeriodSummary(data.period_summary || {});
      renderMainDataGrid(data.rows || [], options);
      loadDutyGrouping();
    } catch (err) {
      if (els.periodLabel) els.periodLabel.textContent = err.message || "Load failed";
      renderPeriodSummary({});
      renderMainDataGrid([], options);
    }
  }

  async function revealStampInGrid(options) {
    options = options || {};
    clearColumnFilters();
    clearCardFilter({ skipRender: true });
    const cert = (options.certificate || "").trim();
    if (cert && els.filterCert) els.filterCert.value = cert;
    const stampId = options.stampId ? parseInt(options.stampId, 10) : 0;
    await loadMainGrid(stampId ? { focusStampId: stampId } : { resetPage: true });
    if (!stampId || !els.dataGridBody) return;
    const row = els.dataGridBody.querySelector('tr[data-stamp-id="' + stampId + '"]');
    if (!row) return;
    Array.from(els.dataGridBody.querySelectorAll("tr")).forEach(function (r) {
      r.classList.remove("table-active");
    });
    row.classList.add("table-active");
    row.scrollIntoView({ block: "nearest", behavior: "smooth" });
    if (!saveMode) {
      setSelectedStamp(stampId);
      enterSelectMode();
    }
  }

  async function revealSavedStampInGrid(stampId) {
    stampId = parseInt(stampId, 10);
    if (!stampId) {
      await loadMainGrid();
      return;
    }
    let cert = (els.certNumber?.value || "").trim();
    if (!cert && window.STAMP_RECORD_URL) {
      try {
        const res = await fetch(stampApiUrl(window.STAMP_RECORD_URL, stampId), {
          headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        const data = await res.json();
        if (data.ok && data.record) {
          cert = (data.record.CertificateNumber || "").trim();
        }
      } catch (e) {
        cert = "";
      }
    }
    await revealStampInGrid({ stampId: stampId, certificate: cert });
  }

  function applyDefaultGridDates() {
    if (els.filterPeriod) els.filterPeriod.value = "custom";
    if (els.filterDateFrom) els.filterDateFrom.value = "";
  }

  function resetGridFilters() {
    applyDefaultGridDates();
    const today = (window.STAMP_DEFAULT_DATE_TO || window.STAMP_DEFAULT_DATE || "").trim();
    if (els.filterDateTo && today) els.filterDateTo.value = today;
    if (els.filterCert) els.filterCert.value = "";
    if (els.filterMobile) els.filterMobile.value = "";
    if (els.filterCustomer) els.filterCustomer.value = "";
    clearColumnFilters();
    clearCardFilter({ skipRender: true });
    gridSortKey = "transaction_date";
    gridSortDir = "desc";
    loadMainGrid();
  }

  function stampApiUrl(template, stampId) {
    return String(template || "").replace("/0", "/" + String(stampId));
  }

  function updateToolbarButtons() {
    const canSave = !!saveMode && mobileConfirmed;
    const canEdit = !!selectedStampId && !saveMode;
    if (els.saveBtn) els.saveBtn.disabled = !canSave;
    if (els.editBtn) els.editBtn.disabled = !canEdit;
  }

  function enterSelectMode() {
    saveMode = false;
    setEditStampIds(null);
    blockedDuplicateCert = null;
    setManualFieldLock(true);
    updateToolbarButtons();
  }

  function enterSaveMode() {
    saveMode = true;
    updateToolbarButtons();
  }

  function setSelectedStamp(stampId) {
    selectedStampId = stampId ? parseInt(stampId, 10) : null;
    updateToolbarButtons();
    if (els.searchGridBody) {
      Array.from(els.searchGridBody.querySelectorAll("tr")).forEach(function (row) {
        row.classList.toggle("table-active", parseInt(row.dataset.stampId, 10) === selectedStampId);
      });
    }
  }

  function resolveEditingStampId() {
    if (editingStampId) return editingStampId;
    if (selectedStampId) return selectedStampId;
    const raw = els.stampIdInput?.value || els.editStampIdInput?.value || "";
    if (raw) {
      const parsed = parseInt(raw, 10);
      if (!Number.isNaN(parsed) && parsed > 0) return parsed;
    }
    return null;
  }

  function setEditStampIds(stampId) {
    const value = stampId ? String(stampId) : "";
    if (els.stampIdInput) els.stampIdInput.value = value;
    if (els.editStampIdInput) els.editStampIdInput.value = value;
    editingStampId = stampId ? parseInt(stampId, 10) : null;
  }

  function ensureStampIdForSubmit() {
    const id = resolveEditingStampId();
    if (id) {
      setEditStampIds(id);
    }
    return id;
  }

  function clearSelectedStamp() {
    selectedStampId = null;
    if (!resolveEditingStampId() && els.stampIdInput) els.stampIdInput.value = "";
    if (!resolveEditingStampId() && els.editStampIdInput) els.editStampIdInput.value = "";
    updateToolbarButtons();
    if (els.searchGridBody) {
      Array.from(els.searchGridBody.querySelectorAll("tr")).forEach(function (row) {
        row.classList.remove("table-active");
      });
    }
  }

  function renderSearchGrid(rows) {
    searchResults = rows || [];
    if (!els.searchPanel || !els.searchGridBody) return;

    els.searchGridBody.innerHTML = "";
    if (!searchResults.length) {
      els.searchPanel.classList.remove("d-none");
      els.searchEmpty?.classList.remove("d-none");
      if (els.searchSummary) els.searchSummary.textContent = "0 records";
      clearSelectedStamp();
      return;
    }

    els.searchEmpty?.classList.add("d-none");
    els.searchPanel.classList.remove("d-none");
    if (els.searchSummary) {
      els.searchSummary.textContent = searchResults.length + " record" + (searchResults.length === 1 ? "" : "s");
    }

    searchResults.forEach(function (row) {
      const tr = document.createElement("tr");
      tr.dataset.stampId = String(row.stamp_id);
      tr.innerHTML =
        "<td>" + escapeHtml(row.certificate_number || "") + "</td>" +
        "<td>" + escapeHtml(formatDisplayDate(row.certificate_date)) + "</td>" +
        "<td>" + escapeHtml(row.first_party || "") + "</td>" +
        "<td class=\"text-end\">" + escapeHtml(row.stamp_duty_amount || "") + "</td>" +
        "<td class=\"text-end\">" + escapeHtml(row.sale_amount || "") + "</td>" +
        "<td>" + escapeHtml(formatDisplayDate(row.transaction_date)) + "</td>" +
        "<td>" + escapeHtml(row.payment_mode || "") + "</td>" +
        "<td>" + escapeHtml(row.customer_name || "") + "</td>" +
        "<td class=\"text-end\">" + escapeHtml(row.transaction_id != null ? String(row.transaction_id) : "") + "</td>";
      tr.addEventListener("click", function () {
        setSelectedStamp(row.stamp_id);
        enterSelectMode();
      });
      tr.addEventListener("dblclick", function () {
        setSelectedStamp(row.stamp_id);
        loadStampRecord(row.stamp_id);
        els.certNumber?.focus();
      });
      els.searchGridBody.appendChild(tr);
    });
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function runSearch() {
    if (!requireMobileSession()) return;
    const query = (els.certNumber?.value || "").trim();
    if (!query) {
      alert("Enter certificate number to search.");
      els.certNumber?.focus();
      return;
    }
    if (!window.STAMP_SEARCH_URL) return;

    if (els.searchSummary) els.searchSummary.textContent = "Searching...";
    try {
      const res = await fetch(window.STAMP_SEARCH_URL + "?q=" + encodeURIComponent(query), {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.error || "Search failed.");
      }
      renderSearchGrid(data.rows || []);
      if ((data.rows || []).length === 1) {
        setSelectedStamp(data.rows[0].stamp_id);
        loadStampRecord(data.rows[0].stamp_id);
      }
    } catch (err) {
      alert(err.message || String(err));
      if (els.searchSummary) els.searchSummary.textContent = "";
    }
  }

  async function loadStampRecord(stampId) {
    if (!stampId || !window.STAMP_RECORD_URL) return;
    try {
      const res = await fetch(stampApiUrl(window.STAMP_RECORD_URL, stampId), {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.error || "Unable to load record.");
      }
      populateRecord(data.record || {});
      setSelectedStamp(stampId);
    } catch (err) {
      alert(err.message || String(err));
    }
  }

  function populateRecord(record) {
    populateFields(record, { preserveSale: true, preserveTransactionDate: true });
    const optionalMap = {
      AccountReference: "AccountReference",
      UniqueDocumentReference: "UniqueDocumentReference",
      DescriptionOfDocument: "DescriptionOfDocument",
      PropertyDescription: "PropertyDescription",
      ConsiderationPrice: "ConsiderationPrice",
      ReferenceNo: "ReferenceNo",
      Remarks: "Remarks",
    };
    Object.keys(optionalMap).forEach(function (key) {
      const input = document.getElementById(optionalMap[key]);
      if (input && record[key] != null) input.value = sanitizeOcrValue(record[key]);
    });
    if (record.TransactionDate) {
      if (els.transactionDate) els.transactionDate.value = record.TransactionDate;
      setTransactionDateManual(true);
    } else {
      defaultTransactionDateFromCert(true);
      setTransactionDateManual(false);
    }
    if (record.Narration) {
      const narration = document.getElementById("Narration");
      if (narration) narration.value = record.Narration;
    }
    if (record.payments && record.payments.length) {
      resetPaymentLines(
        record.payments.map(function (payment) {
          return {
            bankAccountId: payment.bank_account_id,
            amount: payment.amount,
          };
        })
      );
    } else if (record.BankAccountID && !(record.payment_split_count > 1)) {
      resetPaymentLines([
        { bankAccountId: record.BankAccountID, amount: record.SaleAmount || "" },
      ]);
    } else {
      resetPaymentLines();
    }
    if (els.stampIdInput) els.stampIdInput.value = record.stamp_id ? String(record.stamp_id) : "";
    if (els.editStampIdInput) els.editStampIdInput.value = record.stamp_id ? String(record.stamp_id) : "";
    editingStampId = record.stamp_id ? parseInt(record.stamp_id, 10) : null;
    blockedDuplicateCert = null;
    setOcrFieldLock(false);
    setManualFieldLock(false);
    switchingMode = true;
    if (els.modeManual) els.modeManual.checked = true;
    syncEntryModeHidden();
    toggleEntryMode();
    switchingMode = false;
    if (els.partialOcrAlert) {
      els.partialOcrAlert.classList.add("d-none");
      els.partialOcrAlert.textContent = "";
    }
    if (record.is_ocr_entry) {
      // Saved image-import records must stay fully editable on edit.
      setOcrFieldLock(false);
      setManualFieldLock(false);
    } else {
      setManualFieldLock(true);
    }
    applySessionMobile(record.MobileNumber || record.mobile_number || "");
    enterSaveMode();
    ensureTransactionDateEditable();
  }

  async function deleteSelectedRecord() {
    if (!selectedStampId) {
      alert("Select a record from the search grid to delete.");
      return;
    }
    if (!window.STAMP_DELETE_URL) return;
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!(await JTCSDialog.confirm("Permanently delete this stamp record and all linked transactions? This cannot be undone."))) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({
        message: "Permanently delete this stamp record and all linked transactions? This cannot be undone.",
      });
      if (!creds) return;
    }

    try {
      const body = new FormData();
      body.append("csrf_token", window.STAMP_CSRF || "");
      if (creds) window.JTCSDeleteConfirm.appendCreds(body, creds);
      const res = await fetch(stampApiUrl(window.STAMP_DELETE_URL, selectedStampId), {
        method: "POST",
        body: body,
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.error || "Delete failed.");
      }
      clearSelectedStamp();
      clearEntryFields();
      renderSearchGrid([]);
      if (els.searchPanel) els.searchPanel.classList.add("d-none");
      await loadMainGrid();
    } catch (err) {
      alert(err.message || String(err));
    }
  }

  function exportSearchGridExcel() {
    if (!searchResults.length) {
      alert("Search first to export results.");
      return;
    }
    const headers = [
      "Certificate Number",
      "Certificate Date",
      "First Party",
      "Stamp Duty",
      "Sale Amount",
      "Transaction Date",
      "Payment Mode",
      "Customer",
      "Daily Transaction ID",
    ];
    const lines = [headers.join(",")];
    searchResults.forEach(function (row) {
      lines.push([
        row.certificate_number,
        formatDisplayDate(row.certificate_date),
        row.first_party,
        row.stamp_duty_amount,
        row.sale_amount,
        formatDisplayDate(row.transaction_date),
        row.payment_mode,
        row.customer_name,
        row.transaction_id,
      ].map(function (cell) {
        const text = String(cell == null ? "" : cell).replace(/"/g, '""');
        return "\"" + text + "\"";
      }).join(","));
    });
    const blob = new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "stamp-search.csv";
    link.click();
    URL.revokeObjectURL(link.href);
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
    select.className = "form-select stamp-payment-bank";
    select.name = "PaymentBankAccountID[]";
    select.required = true;
    const accounts = window.STAMP_BANK_ACCOUNTS || [];
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
    els.paymentLines?.querySelectorAll(".stamp-payment-amount").forEach(function (input) {
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
        els.paymentSummary.textContent = "Payment total: " + total.toFixed(2) + " (matched)";
      } else {
        els.paymentSummary.textContent =
          "Payment total: " + total.toFixed(2) + " (>= Sale: " + sale.toFixed(2) + ")";
      }
      els.paymentSummary.className = "small text-success ms-auto";
    } else {
      els.paymentSummary.textContent =
        "Payment total: " + total.toFixed(2) + " / Sale: " + sale.toFixed(2) + " (minimum)";
      els.paymentSummary.className = "small text-danger ms-auto";
    }
  }

  function updatePaymentRemoveButtons() {
    const lines = els.paymentLines?.querySelectorAll(".stamp-payment-line") || [];
    const hideRemove = lines.length <= 1;
    lines.forEach(function (line) {
      const btn = line.querySelector(".stamp-payment-remove");
      if (btn) btn.disabled = hideRemove;
    });
  }

  function addPaymentLine(options) {
    options = options || {};
    if (!els.paymentLines) return null;

    const line = document.createElement("div");
    line.className = "stamp-payment-line";

    const bankWrap = document.createElement("div");
    const bankLabel = document.createElement("label");
    bankLabel.className = "form-label";
    bankLabel.textContent = "Payment Mode";
    const select = buildPaymentSelect(options.bankAccountId);
    select.required = true;
    bankWrap.appendChild(bankLabel);
    bankWrap.appendChild(select);

    const amountWrap = document.createElement("div");
    const amountLabel = document.createElement("label");
    amountLabel.className = "form-label";
    amountLabel.textContent = "Amount";
    const amount = document.createElement("input");
    amount.type = "number";
    amount.step = "0.01";
    amount.min = "0";
    amount.className = "form-control stamp-payment-amount";
    amount.name = "PaymentAmount[]";
    amount.required = true;
    amount.value = options.amount != null && options.amount !== "" ? options.amount : "";
    amount.addEventListener("input", updatePaymentSummary);
    amountWrap.appendChild(amountLabel);
    amountWrap.appendChild(amount);

    const actionWrap = document.createElement("div");
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn btn-outline-danger btn-sm stamp-payment-remove";
    removeBtn.innerHTML = "<i class=\"bi bi-trash\"></i>";
    removeBtn.title = "Remove";
    removeBtn.addEventListener("click", function () {
      if ((els.paymentLines?.querySelectorAll(".stamp-payment-line") || []).length <= 1) return;
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
    const lines = els.paymentLines?.querySelectorAll(".stamp-payment-line") || [];
    if (!lines.length) return "At least one payment mode is required.";
    for (let i = 0; i < lines.length; i++) {
      const bank = lines[i].querySelector(".stamp-payment-bank");
      const amount = lines[i].querySelector(".stamp-payment-amount");
      if (!bank?.value) return "Each payment mode must be selected.";
      const val = parseFloat(amount?.value || "0");
      if (Number.isNaN(val) || val <= 0) {
        return "Each payment amount must be greater than zero.";
      }
    }
    const sale = parseFloat(els.saleAmount?.value || "0");
    const total = getPaymentTotal();
    if (total + 0.001 < sale) {
      return "Payment total must be greater than or equal to Sale Amount.";
    }
    return null;
  }

  function syncPaymentLinesToForm() {
    if (!form || !els.paymentLines) return;
    form.querySelectorAll(".stamp-payment-sync").forEach(function (el) {
      el.remove();
    });
    const lines = els.paymentLines.querySelectorAll(".stamp-payment-line");
    lines.forEach(function (line, index) {
      const bank = line.querySelector(".stamp-payment-bank");
      const amount = line.querySelector(".stamp-payment-amount");
      if (!bank || !amount) return;

      bank.disabled = false;
      amount.disabled = false;
      bank.removeAttribute("name");
      amount.removeAttribute("name");

      const wrap = document.createElement("div");
      wrap.className = "stamp-payment-sync d-none";
      wrap.setAttribute("aria-hidden", "true");

      const bankHidden = document.createElement("input");
      bankHidden.type = "hidden";
      bankHidden.name = "PaymentBankAccountID[]";
      bankHidden.value = bank.value || "";
      bankHidden.className = "stamp-payment-sync";

      const amountHidden = document.createElement("input");
      amountHidden.type = "hidden";
      amountHidden.name = "PaymentAmount[]";
      amountHidden.value = amount.value || "0";
      amountHidden.className = "stamp-payment-sync";

      const indexHidden = document.createElement("input");
      indexHidden.type = "hidden";
      indexHidden.name = "PaymentLineIndex[]";
      indexHidden.value = String(index);
      indexHidden.className = "stamp-payment-sync";

      wrap.appendChild(bankHidden);
      wrap.appendChild(amountHidden);
      wrap.appendChild(indexHidden);
      form.appendChild(wrap);
    });
  }

  function focusNextMandatoryField(current) {
    const fields = getMandatoryFields();
    const idx = fields.indexOf(current);
    if (idx >= 0 && idx < fields.length - 1) {
      fields[idx + 1].focus();
      if (fields[idx + 1].select) {
        try { fields[idx + 1].select(); } catch (e) { /* ignore */ }
      }
      return true;
    }
    if (idx === fields.length - 1) {
      form.requestSubmit();
      return true;
    }
    return false;
  }

  function duplicateBlockedMessage() {
    return "This Certificate Number is already sold in full. Open the existing record to edit, or enter a different certificate.";
  }

  function validateMandatoryFields() {
    const certNumber = (document.getElementById("CertificateNumber")?.value || "").trim();
    if (!editingStampId && blockedDuplicateCert && certNumber === blockedDuplicateCert) {
      return duplicateBlockedMessage();
    }
    const fields = activeRequiredFields();
    for (let i = 0; i < fields.length; i++) {
      const field = fields[i];
      const input = document.getElementById(field.id);
      const value = (input && input.value ? input.value : "").trim();
      if (!value) return field.label + " is required.";
    }
    const stampDuty = parseFloat(document.getElementById("StampDutyAmount")?.value || "");
    const saleAmount = parseFloat(document.getElementById("SaleAmount")?.value || "");
    if (Number.isNaN(stampDuty) || stampDuty <= 0) {
      return "Stamp Duty Amount must be greater than zero.";
    }
    if (Number.isNaN(saleAmount)) {
      return "Sale Amount is required.";
    }
    if (saleAmount <= 0) {
      return "Sale Amount must be greater than zero.";
    }
    if (saleAmount <= stampDuty) {
      return "Sale Amount must be greater than Stamp Duty Amount.";
    }
    return validatePaymentLines();
  }

  function isOcrMode() {
    return els.modeOcr && els.modeOcr.checked;
  }

  function normalizeMobile(value) {
    return (value || "").replace(/\D/g, "").slice(-10);
  }

  function validateMobile(value) {
    const mobile = normalizeMobile(value);
    if (!/^[6-9]\d{9}$/.test(mobile)) {
      return "Enter a valid 10-digit mobile number.";
    }
    return null;
  }

  function setMobileError(message) {
    if (!els.mobileError) return;
    if (message) {
      els.mobileError.textContent = message;
      els.mobileError.classList.remove("d-none");
    } else {
      els.mobileError.textContent = "";
      els.mobileError.classList.add("d-none");
    }
  }

  function setOcrFieldLock(locked, options) {
    options = options || {};
    ocrImportedLock = !!locked;
    OCR_LOCKED_SECTION_IDS.forEach(function (sectionId) {
      const section = document.getElementById(sectionId);
      if (!section) return;
      section.classList.toggle("stamp-section-locked", locked);
      section.querySelectorAll("input, select, textarea").forEach(function (el) {
        if (locked) {
          if (el.type === "checkbox" || el.type === "radio") {
            el.disabled = true;
          } else {
            el.readOnly = true;
            el.classList.add("stamp-field-readonly");
            el.tabIndex = -1;
          }
        } else {
          el.disabled = false;
          el.readOnly = false;
          el.classList.remove("stamp-field-readonly");
          if (el.classList.contains("stamp-field-optional")) {
            el.tabIndex = -1;
          } else {
            el.removeAttribute("tabindex");
          }
        }
      });
    });
    OCR_EDITABLE_SECTION_IDS.forEach(function (sectionId) {
      const section = document.getElementById(sectionId);
      if (!section) return;
      section.querySelectorAll("input, select, textarea, button").forEach(function (el) {
        el.disabled = false;
        if (el.tagName !== "BUTTON") {
          el.readOnly = false;
          el.classList.remove("stamp-field-readonly");
        }
      });
    });
    if (locked && !options.preserveAmounts) {
      ensureSaleAmountDefault();
      els.saleAmount?.focus();
    }
    ensureTransactionDateEditable();
  }

  function clearEntryFields() {
    editingStampId = null;
    blockedDuplicateCert = null;
    setTransactionDateManual(false);
    form.querySelectorAll(".stamp-field").forEach(function (input) {
      input.value = "";
    });
    if (els.saleAmount) els.saleAmount.value = "";
    setEditStampIds(null);
    els.ocrImageId.value = "";
    if (els.transactionDate) {
      els.transactionDate.value = "";
      els.transactionDate.setAttribute("name", "TransactionDate");
    }
    form.querySelectorAll(".stamp-txn-date-sync").forEach(function (el) {
      el.remove();
    });
    document.getElementById("Narration").value = "Stamp Sale";
    if (els.partialOcrAlert) {
      els.partialOcrAlert.classList.add("d-none");
      els.partialOcrAlert.textContent = "";
    }
    setOcrReason("");
    clearImage();
    resetPaymentLines();
    setOcrFieldLock(false);
    setManualFieldLock(true);
    clearSelectedStamp();
    enterSaveMode();
  }

  function renderMobileDisplay(mobile) {
    if (!els.mobileDisplay) return;
    els.mobileDisplay.innerHTML = "";
    const label = document.createElement("span");
    label.className = "stamp-mobile-label";
    label.textContent = "Mobile: " + mobile;
    els.mobileDisplay.appendChild(label);
  }

  function refreshMobileCustomers(mobile) {
    renderMobileDisplay(mobile || "");
  }

  function openEntryModal() {
    if (entryModal) {
      entryModal.show();
      return;
    }
    els.mainWorkspace?.classList.remove("d-none");
  }

  function closeEntryModal() {
    if (entryModal) {
      entryModal.hide();
      return;
    }
    els.mainWorkspace?.classList.add("d-none");
  }

  function applyWebsitePrefill() {
    const pre = window.STAMP_WEBSITE_PREFILL || {};
    const first = document.getElementById("FirstPartyName");
    const second = document.getElementById("SecondPartyName");
    const duty = document.getElementById("StampDutyAmount");
    const sale = document.getElementById("SaleAmount");
    const desc = document.getElementById("DescriptionOfDocument");
    if (first && pre.first_party) first.value = pre.first_party;
    if (second && pre.second_party) second.value = pre.second_party;
    if (duty && pre.amount) duty.value = pre.amount;
    if (sale && (pre.sale_amount || pre.amount)) sale.value = pre.sale_amount || pre.amount;
    if (desc && pre.description) desc.value = pre.description;
  }

  function initMobileFromRepost() {
    const pre = window.STAMP_WEBSITE_PREFILL || {};
    const mobile = window.STAMP_REPOST_MOBILE || pre.mobile;
    if (!mobile || !els.mobileHidden) return false;
    mobileConfirmed = true;
    els.mobileHidden.value = normalizeMobile(mobile);
    if (els.mobileInput) els.mobileInput.value = els.mobileHidden.value;
    els.mobileGate?.classList.add("d-none");
    refreshMobileCustomers(els.mobileHidden.value);
    return true;
  }

  function confirmMobile() {
    const error = validateMobile(els.mobileInput?.value);
    if (error) {
      setMobileError(error);
      els.mobileInput?.focus();
      return false;
    }
    const mobile = normalizeMobile(els.mobileInput.value);
    const keepOpenEdit = !!resolveEditingStampId();
    mobileConfirmed = true;
    if (els.mobileHidden) els.mobileHidden.value = mobile;
    setMobileError("");
    els.mobileGate?.classList.add("d-none");
    if (keepOpenEdit) {
      refreshMobileCustomers(mobile);
      openEntryModal();
      enterSaveMode();
      return true;
    }
    clearEntryFields();
    resetPaymentLines();
    if (els.modeManual) els.modeManual.checked = true;
    syncEntryModeHidden();
    toggleEntryMode();
    refreshMobileCustomers(mobile);
    openEntryModal();
    enterSaveMode();
    defaultTransactionDateToday();
    els.certNumber?.focus();
    return true;
  }

  function resetToMobileGate() {
    if (ocrRunning) return;
    mobileConfirmed = false;
    form.reset();
    if (els.mobileInput) els.mobileInput.value = "";
    if (els.mobileHidden) els.mobileHidden.value = "";
    if (els.mobileDisplay) els.mobileDisplay.innerHTML = "";
    setMobileError("");
    closeEntryModal();
    els.mobileGate?.classList.remove("d-none");
    clearEntryFields();
    els.mobileInput?.focus();
  }

  function requireMobileSession() {
    if (mobileConfirmed) return true;
    setMobileError("Enter mobile number and click Continue.");
    closeEntryModal();
    els.mobileGate?.classList.remove("d-none");
    els.mobileInput?.focus();
    return false;
  }

  function isFullOcrSuccess(fields) {
    if (!fields) return false;
    return OCR_REQUIRED_FIELDS.every(function (key) {
      return fields[key] != null && String(fields[key]).trim() !== "";
    });
  }

  function missingOcrFields(fields) {
    return OCR_REQUIRED_FIELDS.filter(function (key) {
      return !fields || fields[key] == null || String(fields[key]).trim() === "";
    });
  }

  function showPartialOcrAlert(message) {
    if (!els.partialOcrAlert) return;
    els.partialOcrAlert.textContent = message;
    els.partialOcrAlert.classList.remove("d-none");
  }

  function stayOnImageMode() {
    switchingMode = true;
    if (els.modeOcr) els.modeOcr.checked = true;
    syncEntryModeHidden();
    els.imageColumn?.classList.remove("d-none");
    els.formLayout?.classList.remove("stamp-layout-manual");
    els.mainWorkspace?.classList.remove("stamp-mode-manual");
    switchingMode = false;
  }

  function fallbackToManual(fields, reason) {
    populateFields(fields || {});
    setOcrFieldLock(false);
    stayOnImageMode();
    els.retryBtn?.classList.remove("d-none");
    setOcrStatus("failed", "Partial OCR");
    setOcrReason(reason);
    showPartialOcrAlert((reason || "OCR incomplete.") + " Complete remaining fields here. Integration from Image stays selected.");
    syncExistingCertificateState(false);
  }

  function setOcrReason(message) {
    if (!els.ocrReason) return;
    if (message) {
      els.ocrReason.textContent = message;
      els.ocrReason.classList.remove("d-none");
    } else {
      els.ocrReason.textContent = "";
      els.ocrReason.classList.add("d-none");
    }
  }

  function logOcr(event, detail) {
    console.log("[Stamp OCR]", event, detail !== undefined ? detail : "");
  }

  function updateEngineBanner(status) {
    if (!status || !els.ocrEngineAlert) return;
    const title = document.getElementById("stampOcrEngineTitle");
    if (title) title.textContent = status.message || "";
    if (els.ocrProviderBadge) {
      els.ocrProviderBadge.textContent = status.active_provider || "None";
      els.ocrProviderBadge.className = "badge " + (status.ready ? "text-bg-success" : "text-bg-secondary");
    }
    if (status.ready) {
      els.ocrEngineAlert.classList.add("d-none");
    } else {
      els.ocrEngineAlert.classList.remove("d-none");
      els.ocrEngineAlert.classList.remove("alert-success");
      els.ocrEngineAlert.classList.add("alert-warning");
    }
  }

  async function refreshOcrStatus() {
    if (!window.STAMP_OCR_STATUS_URL) return window.STAMP_OCR_STATUS;
    try {
      const res = await fetch(window.STAMP_OCR_STATUS_URL);
      const data = await res.json();
      window.STAMP_OCR_STATUS = data;
      updateEngineBanner(data);
      return data;
    } catch (e) {
      return window.STAMP_OCR_STATUS;
    }
  }

  async function installOcrEngine() {
    if (!window.STAMP_OCR_INSTALL_URL) return;
    if (!window.STAMP_IS_ADMIN) {
      setOcrReason("Administrator login required to install OCR engine.");
      return;
    }
    if (!(await JTCSDialog.confirm("Install EasyOCR and dependencies? This may take several minutes."))) return;

    els.installOcrBtn.disabled = true;
    els.installOcrBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Installing...';
    setOcrStatus("reading", "Installing OCR...");
    setOcrReason("Installing easyocr, torch, torchvision, opencv-python, Pillow, numpy...");

    try {
      const res = await fetch(window.STAMP_OCR_INSTALL_URL, {
        method: "POST",
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: "csrf_token=" + encodeURIComponent(window.STAMP_CSRF || ""),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.error || data.message || "Installation failed.");
      }
      await refreshOcrStatus();
      setOcrStatus("completed", "OCR Installed");
      setOcrReason("Restart server if OCR does not work immediately.");
      logOcr("Install Completed", data);
    } catch (err) {
      setOcrStatus("failed", "Install Failed");
      setOcrReason(err.message || String(err));
      logOcr("Install Failed", err.message);
    } finally {
      els.installOcrBtn.disabled = false;
      els.installOcrBtn.innerHTML = '<i class="bi bi-download"></i> Install OCR Engine';
    }
  }

  function setOcrStatus(state, message, confidence) {
    els.ocrStatusText.textContent = message;
    els.ocrStatusText.className = "stamp-ocr-status-text";
    if (state) els.ocrStatusText.classList.add("is-" + state);

    if (state === "completed") {
      els.ocrIcon.innerHTML = '<i class="bi bi-check-circle-fill text-success"></i>';
    } else if (state === "failed") {
      els.ocrIcon.innerHTML = '<i class="bi bi-x-circle-fill text-danger"></i>';
    } else if (state === "reading") {
      els.ocrIcon.innerHTML = '<div class="spinner-border spinner-border-sm text-primary"></div>';
    } else {
      els.ocrIcon.innerHTML = "";
    }

    if (confidence !== undefined && confidence !== null) {
      els.ocrConfidenceWrap.classList.remove("d-none");
      els.ocrConfidence.textContent = Math.round(confidence) + "%";
    } else if (state === "waiting") {
      els.ocrConfidenceWrap.classList.add("d-none");
    }
  }

  function toggleEntryMode() {
    if (!mobileConfirmed) return;
    const manual = !isOcrMode();
    syncEntryModeHidden();
    els.imageColumn?.classList.toggle("d-none", manual);
    els.formLayout?.classList.toggle("stamp-layout-manual", manual);
    els.mainWorkspace?.classList.toggle("stamp-mode-manual", manual);
    els.formFooter?.classList.remove("d-none");
    els.ocrEngineAlert?.classList.toggle("d-none", manual || !!(window.STAMP_OCR_STATUS && window.STAMP_OCR_STATUS.ready));
    if (manual) {
      setManualFieldLock(true);
    } else {
      setManualFieldLock(false);
    }
    if (isOcrMode()) {
      els.photoBox?.focus();
      setOcrStatus("waiting", "Waiting");
    } else if (!ocrImportedLock) {
      els.certNumber?.focus();
    }
  }

  function resetPreview() {
    previewDataUrl = null;
    els.placeholder.classList.remove("d-none");
    els.preview.classList.add("d-none");
    els.preview.removeAttribute("src");
    els.pdfPreview.classList.add("d-none");
    els.photoBox.classList.remove("has-image");
    els.overlay.classList.add("d-none");
  }

  function showImage(dataUrl) {
    previewDataUrl = dataUrl;
    els.placeholder.classList.add("d-none");
    els.pdfPreview.classList.add("d-none");
    els.preview.src = dataUrl;
    els.preview.classList.remove("d-none");
    els.photoBox.classList.add("has-image");
  }

  function showPdf(file) {
    previewDataUrl = null;
    els.placeholder.classList.add("d-none");
    els.preview.classList.add("d-none");
    els.pdfName.textContent = file.name || "document.pdf";
    els.pdfPreview.classList.remove("d-none");
    els.photoBox.classList.add("has-image");
  }

  function isAllowedFile(file) {
    const name = (file.name || "").toLowerCase();
    const type = (file.type || "").toLowerCase();
    const ext = name.includes(".") ? name.slice(name.lastIndexOf(".")) : "";
    return type.startsWith("image/") || type === "application/pdf" ||
      [".png", ".jpg", ".jpeg", ".webp", ".pdf"].includes(ext);
  }

  function ensureSaleAmountDefault() {
    if (els.saleAmount) els.saleAmount.value = "";
    els.paymentLines?.querySelectorAll(".stamp-payment-amount").forEach(function (input) {
      input.value = "";
    });
    updatePaymentSummary();
  }

  function sanitizeOcrValue(value) {
    return String(value == null ? "" : value).replace(/^[\s:>|]+/, "").trim();
  }

  function populateFields(fields, options) {
    options = options || {};
    Object.keys(fieldMap).forEach(function (key) {
      const input = document.getElementById(fieldMap[key]);
      if (input && fields[key] != null) input.value = sanitizeOcrValue(fields[key]);
    });
    if (options.preserveSale && fields.SaleAmount != null && els.saleAmount) {
      els.saleAmount.value = fields.SaleAmount;
    } else {
      ensureSaleAmountDefault();
    }
    if (els.certNumber.value && !document.getElementById("ReferenceNo").value) {
      document.getElementById("ReferenceNo").value = els.certNumber.value;
    }
    if (!options.preserveTransactionDate) {
      defaultTransactionDateToday();
    }
  }

  async function syncExistingCertificateState(showModal) {
    const number = (els.certNumber?.value || "").trim();
    if (!number || number.length < 3) {
      if (!editingStampId) blockedDuplicateCert = null;
      return null;
    }
    try {
      const url = window.STAMP_CHECK_URL + "?number=" + encodeURIComponent(number);
      const res = await fetch(url);
      const data = await res.json();
      if (data.exists && data.stamp_id) {
        const editingId = resolveEditingStampId();
        if (editingId && Number(editingId) === Number(data.stamp_id)) {
          setSelectedStamp(data.stamp_id);
          blockedDuplicateCert = null;
          return data;
        }
        blockedDuplicateCert = number;
        if (!resolveEditingStampId() && els.stampIdInput) els.stampIdInput.value = "";
        if (!resolveEditingStampId() && els.editStampIdInput) els.editStampIdInput.value = "";
        if (!resolveEditingStampId()) clearSelectedStamp();
        if (showModal) showDuplicateModal(data);
        revealStampInGrid({
          stampId: data.stamp_id,
          certificate: data.certificate_number || number,
        });
        return data;
      }
      if (!editingStampId) blockedDuplicateCert = null;
      return null;
    } catch (e) {
      return null;
    }
  }

  async function runOcr() {
    if (!selectedFile || ocrRunning) return;
    if (!requireMobileSession()) return;

    const status = window.STAMP_OCR_STATUS || {};
    if (!status.ready) {
      fallbackToManual(
        {},
        status.message || "OCR Engine Not Installed. Administrator Contact Required."
      );
      return;
    }

    ocrRunning = true;
    els.retryBtn.classList.add("d-none");
    setOcrReason("");
    setOcrStatus("reading", "Reading");
    els.overlay.classList.remove("d-none");
    logOcr("Image Loaded", { name: selectedFile.name, size: selectedFile.size, type: selectedFile.type });
    logOcr("OCR Started", { provider: status.active_provider, file: selectedFile.name });

    function buildExtractBody() {
      const payload = new FormData();
      payload.append("certificate_file", selectedFile);
      payload.append("csrf_token", window.STAMP_CSRF || "");
      return payload;
    }

    function isNetworkError(err) {
      const msg = (err && err.message) || String(err || "");
      return /failed to fetch|networkerror|load failed|abort|the operation was aborted/i.test(msg);
    }

    async function postExtract() {
      const controller = new AbortController();
      const timer = setTimeout(function () { controller.abort(); }, 180000);
      try {
        return await fetch(window.STAMP_EXTRACT_URL, {
          method: "POST",
          body: buildExtractBody(),
          credentials: "same-origin",
          headers: { "X-Requested-With": "XMLHttpRequest" },
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timer);
      }
    }

    try {
      let response;
      try {
        response = await postExtract();
      } catch (firstErr) {
        if (!isNetworkError(firstErr)) throw firstErr;
        logOcr("OCR retry after disconnect", firstErr.message || String(firstErr));
        await new Promise(function (resolve) { setTimeout(resolve, 1500); });
        response = await postExtract();
      }
      const data = await response.json();
      if (data.provider && els.ocrProviderBadge) {
        els.ocrProviderBadge.textContent = data.provider;
      }
      if (data.fields) populateFields(data.fields);
      if (data.ocr_image_id) els.ocrImageId.value = data.ocr_image_id;
      stayOnImageMode();

      if (!response.ok || !data.ok) {
        const reason = data.reason || data.error || "Unknown OCR error.";
        logOcr("OCR Failed Reason", reason);
        if (data.engine_missing) updateEngineBanner(data.status);
        fallbackToManual(data.fields || collectCurrentFields(), reason);
        return;
      }

      logOcr("OCR Provider", data.provider);
      logOcr("OCR Text", data.ocr_text);
      logOcr("OCR Completed", { confidence: data.confidence, fields: data.fields });
      console.log("===== OCR TEXT =====\n" + (data.ocr_text || "") + "\n====================");

      if (!isFullOcrSuccess(data.fields || {})) {
        const missing = missingOcrFields(data.fields || {});
        fallbackToManual(
          data.fields || {},
          "OCR extracted " + (OCR_REQUIRED_FIELDS.length - missing.length) + " of " +
            OCR_REQUIRED_FIELDS.length + " fields. Missing: " + missing.join(", ") + "."
        );
        return;
      }

      if (els.partialOcrAlert) {
        els.partialOcrAlert.classList.add("d-none");
        els.partialOcrAlert.textContent = "";
      }
      setOcrReason("");
      setOcrStatus("completed", "Completed", data.confidence);
      setOcrFieldLock(true);
      ensureSaleAmountDefault();
      showPartialOcrAlert("Certificate data imported from image. You can edit Transaction Date, Amount, Payment & Remarks only.");
      syncExistingCertificateState(false);
    } catch (err) {
      logOcr("OCR Failed Reason", err.message || String(err));
      const network = /failed to fetch|networkerror|load failed|abort/i.test(err.message || String(err));
      fallbackToManual(
        collectCurrentFields(),
        network
          ? "Server disconnected during OCR. Keep this page open and click Retry OCR. Do not start another python run.py."
          : ("OCR failed: " + (err.message || String(err)))
      );
    } finally {
      ocrRunning = false;
      els.overlay.classList.add("d-none");
    }
  }

  function collectCurrentFields() {
    const fields = {};
    Object.keys(fieldMap).forEach(function (key) {
      const input = document.getElementById(fieldMap[key]);
      if (input && input.value) fields[key] = input.value;
    });
    return fields;
  }

  function loadFile(file, autoOcr) {
    if (!requireMobileSession()) return;
    if (!file || !isAllowedFile(file)) {
      setOcrStatus("failed", "Failed");
      setOcrReason("Unsupported file. Use PNG, JPG, JPEG, WEBP, or PDF.");
      return;
    }
    selectedFile = file;
    els.ocrImageId.value = "";
    setOcrStatus("waiting", "Waiting");

    const type = (file.type || "").toLowerCase();
    const ext = (file.name || "").toLowerCase().slice((file.name || "").lastIndexOf("."));

    const after = function () {
      if (autoOcr && isOcrMode()) runOcr();
    };

    if (type === "application/pdf" || ext === ".pdf") {
      showPdf(file);
      after();
    } else {
      const reader = new FileReader();
      reader.onload = function (e) {
        showImage(e.target.result);
        after();
      };
      reader.readAsDataURL(file);
    }
  }

  function clearImage() {
    if (ocrRunning) return;
    selectedFile = null;
    els.fileInput.value = "";
    els.ocrImageId.value = "";
    resetPreview();
    els.retryBtn.classList.add("d-none");
    setOcrStatus("waiting", "Waiting");
  }

  function clearForm() {
    renderSearchGrid([]);
    if (els.searchPanel) els.searchPanel.classList.add("d-none");
    resetToMobileGate();
  }

  async function triggerPaste() {
    if (!requireMobileSession()) return;
    els.photoBox.focus();
    if (navigator.clipboard && navigator.clipboard.read) {
      try {
        const items = await navigator.clipboard.read();
        for (const item of items) {
          const t = item.types.find(function (x) { return x.startsWith("image/"); });
          if (t) {
            const blob = await item.getType(t);
            loadFile(new File([blob], "clipboard.png", { type: blob.type }), true);
            return;
          }
        }
      } catch (e) { /* use Ctrl+V */ }
    }
    setOcrStatus("waiting", "Press Ctrl+V to paste");
  }

  async function checkDuplicate(number) {
    return syncExistingCertificateState(true);
  }

  function showDuplicateModal(data) {
    const txnLine = data.transaction_id
      ? "<li>Status: <strong>Already sold in full</strong> (Transaction #" + data.transaction_id + ")</li>"
      : "<li>Status: Registered (Stamp Record #" + data.stamp_id + ", no transaction posted)</li>";
    els.duplicateBody.innerHTML =
      "<p>Certificate <strong>" + escapeHtml(data.certificate_number || "") + "</strong> cannot be entered again.</p>" +
      "<ul class='mb-0 small'>" + txnLine +
      "<li>Customer: " + escapeHtml(data.customer_name || "—") + "</li>" +
      "<li>Date: " + escapeHtml(formatDisplayDate(data.transaction_date)) + "</li></ul>";
    if (data.stamp_id) {
      const basePath = window.location.pathname.split("?")[0];
      els.duplicateViewBtn.href = basePath + "?load_stamp=" + encodeURIComponent(String(data.stamp_id));
      els.duplicateViewBtn.classList.remove("d-none");
      els.duplicateViewBtn.onclick = function (e) {
        e.preventDefault();
        duplicateModal?.hide();
        revealStampInGrid({
          stampId: data.stamp_id,
          certificate: data.certificate_number || "",
        });
        if (mobileConfirmed) {
          loadStampRecord(data.stamp_id).then(function () {
            openEntryModal();
          });
        }
      };
    }
    duplicateModal?.show();
  }

  function openZoom() {
    if (!previewDataUrl || !zoomModal) return;
    els.zoomImage.src = previewDataUrl;
    zoomScale = 1;
    zoomRotate = 0;
    els.zoomImage.style.transform = "scale(1) rotate(0deg)";
    zoomModal.show();
  }

  function applyZoom() {
    els.zoomImage.style.transform = "scale(" + zoomScale + ") rotate(" + zoomRotate + "deg)";
  }

  function getFocusableFields() {
    return getMandatoryFields();
  }

  document.addEventListener("paste", function (e) {
    if (!isOcrMode() || !mobileConfirmed) return;
    const items = e.clipboardData && e.clipboardData.items;
    if (!items) return;
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.indexOf("image") !== -1) {
        const file = items[i].getAsFile();
        if (file) {
          e.preventDefault();
          loadFile(file, true);
        }
        break;
      }
    }
  });

  els.mobileContinueBtn?.addEventListener("click", function (e) {
    e.preventDefault();
    confirmMobile();
  });
  els.mobileInput?.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      confirmMobile();
    }
  });

  els.mobileInput?.addEventListener("input", function () {
    setMobileError("");
  });

  els.entryCloseBtn?.addEventListener("click", function () {
    if (ocrRunning) return;
    resetToMobileGate();
  });
  els.entryModalEl?.addEventListener("hidden.bs.modal", function () {
    if (!mobileConfirmed) return;
    if (document.activeElement && els.entryModalEl.contains(document.activeElement)) {
      els.mobileInput?.focus();
    }
  });

  els.modeManual?.addEventListener("change", function () {
    if (!mobileConfirmed || switchingMode) return;
    setOcrFieldLock(false);
    clearEntryFields();
    syncEntryModeHidden();
    toggleEntryMode();
  });
  els.modeOcr?.addEventListener("change", function () {
    if (!mobileConfirmed || switchingMode) return;
    setOcrFieldLock(false);
    clearEntryFields();
    syncEntryModeHidden();
    toggleEntryMode();
  });
  els.browseBtn?.addEventListener("click", function (e) { e.preventDefault(); els.fileInput.click(); });
  els.pasteBtn?.addEventListener("click", function (e) { e.preventDefault(); triggerPaste(); });
  els.retryBtn?.addEventListener("click", function (e) { e.preventDefault(); runOcr(); });
  els.clearImageBtn?.addEventListener("click", function (e) { e.preventDefault(); clearImage(); });
  els.installOcrBtn?.addEventListener("click", function (e) {
    e.preventDefault();
    installOcrEngine();
  });
  els.editBtn?.addEventListener("click", function () {
    if (!selectedStampId || els.editBtn?.disabled) return;
    loadStampRecord(selectedStampId).then(function () {
      els.certNumber?.focus();
    });
  });

  els.fileInput?.addEventListener("change", function () {
    if (els.fileInput.files && els.fileInput.files[0]) loadFile(els.fileInput.files[0], true);
  });

  els.photoBox?.addEventListener("click", function () {
    if (!selectedFile) els.fileInput.click();
  });
  els.photoBox?.addEventListener("dblclick", function (e) {
    e.preventDefault();
    if (previewDataUrl) openZoom();
  });
  els.photoBox?.addEventListener("dragover", function (e) {
    if (!isOcrMode()) return;
    e.preventDefault();
    els.photoBox.classList.add("dragover");
  });
  els.photoBox?.addEventListener("dragleave", function () { els.photoBox.classList.remove("dragover"); });
  els.photoBox?.addEventListener("drop", function (e) {
    if (!isOcrMode()) return;
    e.preventDefault();
    els.photoBox.classList.remove("dragover");
    const file = e.dataTransfer.files && e.dataTransfer.files[0];
    if (file) loadFile(file, true);
  });

  els.certNumber?.addEventListener("blur", function () {
    syncExistingCertificateState(true);
  });
  els.transactionDate?.addEventListener("change", function () {
    const certDate = (els.certIssuedDate?.value || "").trim();
    const txnDate = (els.transactionDate?.value || "").trim();
    setTransactionDateManual(!!txnDate && txnDate !== certDate);
  });
  els.certNumber?.addEventListener("input", function () {
    const number = (els.certNumber.value || "").trim();
    if (!number) {
      clearSelectedStamp();
      blockedDuplicateCert = null;
    }
  });
  els.certNumber?.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && e.ctrlKey) {
      e.preventDefault();
      runSearch();
    }
  });

  els.paymentAddBtn?.addEventListener("click", function (e) {
    e.preventDefault();
    addPaymentLine();
  });

  els.saleAmount?.addEventListener("input", updatePaymentSummary);
  els.saleAmount?.addEventListener("change", function () {
    const raw = (els.saleAmount?.value || "").trim();
    if (!raw) {
      updatePaymentSummary();
      return;
    }
    const stampDuty = parseFloat(document.getElementById("StampDutyAmount")?.value || "0");
    const sale = parseFloat(raw);
    if (Number.isNaN(sale) || sale <= 0 || (!Number.isNaN(stampDuty) && stampDuty > 0 && sale <= stampDuty)) {
      els.saleAmount.value = "";
      alert("Sale Amount must be greater than Stamp Duty Amount.");
      els.saleAmount?.focus();
      updatePaymentSummary();
      return;
    }
    updatePaymentSummary();
  });
  document.getElementById("StampDutyAmount")?.addEventListener("change", function () {
    const stampDuty = parseFloat(this.value || "0");
    const saleRaw = (els.saleAmount?.value || "").trim();
    const sale = parseFloat(saleRaw);
    if (saleRaw && sale > 0 && !Number.isNaN(stampDuty) && sale <= stampDuty) {
      if (els.saleAmount) els.saleAmount.value = "";
      updatePaymentSummary();
    }
  });

  document.getElementById("stampZoomInBtn")?.addEventListener("click", function () {
    zoomScale = Math.min(zoomScale + 0.15, 5);
    applyZoom();
  });
  document.getElementById("stampZoomOutBtn")?.addEventListener("click", function () {
    zoomScale = Math.max(zoomScale - 0.15, 0.2);
    applyZoom();
  });
  document.getElementById("stampRotateLeftBtn")?.addEventListener("click", function () {
    zoomRotate -= 90;
    applyZoom();
  });
  document.getElementById("stampRotateRightBtn")?.addEventListener("click", function () {
    zoomRotate += 90;
    applyZoom();
  });
  document.getElementById("stampDownloadBtn")?.addEventListener("click", function () {
    if (!previewDataUrl) return;
    const a = document.createElement("a");
    a.href = previewDataUrl;
    a.download = selectedFile?.name || "certificate.png";
    a.click();
  });
  els.zoomBody?.addEventListener("wheel", function (e) {
    e.preventDefault();
    zoomScale = Math.max(0.2, Math.min(5, zoomScale + (e.deltaY < 0 ? 0.1 : -0.1)));
    applyZoom();
  }, { passive: false });

  function syncTransactionDateForSubmit() {
    if (!form || !els.transactionDate) return;
    ensureTransactionDateEditable();
    let value = (els.transactionDate.value || "").trim();
    if (!value && els.certIssuedDate) {
      value = (els.certIssuedDate.value || "").trim();
      els.transactionDate.value = value;
    }
    form.querySelectorAll(".stamp-txn-date-sync").forEach(function (el) {
      el.remove();
    });
    els.transactionDate.removeAttribute("name");
    const hidden = document.createElement("input");
    hidden.type = "hidden";
    hidden.name = "TransactionDate";
    hidden.value = value;
    hidden.className = "stamp-txn-date-sync";
    form.appendChild(hidden);
  }

  function enableFormFieldsForSubmit() {
    form.querySelectorAll("input, select, textarea").forEach(function (el) {
      el.disabled = false;
      el.readOnly = false;
    });
    ensureTransactionDateEditable();
  }

  form.addEventListener("submit", function (e) {
    const sessionMobile = normalizeMobile(els.mobileHidden?.value || els.mobileInput?.value || "");
    if (sessionMobile && els.mobileHidden) {
      els.mobileHidden.value = sessionMobile;
      mobileConfirmed = true;
    }
    if (!normalizeMobile(els.mobileHidden?.value || "")) {
      e.preventDefault();
      setMobileError("Enter mobile number before saving.");
      els.mobileGate?.classList.remove("d-none");
      els.mobileInput?.focus();
      return;
    }
    enableFormFieldsForSubmit();
    syncTransactionDateForSubmit();
    syncPaymentLinesToForm();
    ensureStampIdForSubmit();
    const validationError = validateMandatoryFields();
    if (validationError) {
      e.preventDefault();
      alert(validationError);
    }
  });

  form.addEventListener("keydown", function (e) {
    const tag = (e.target.tagName || "").toLowerCase();
    if (tag === "textarea") return;

    if (e.key === "Enter") {
      e.preventDefault();
      if (!focusNextMandatoryField(e.target)) {
        const fields = getMandatoryFields();
        if (fields.length) fields[0].focus();
      }
      return;
    }

    if (e.key === "Tab" && !e.shiftKey) {
      const fields = getMandatoryFields();
      const idx = fields.indexOf(e.target);
      if (idx >= 0 && idx < fields.length - 1) {
        e.preventDefault();
        fields[idx + 1].focus();
      }
    }

    if (e.key === "Tab" && e.shiftKey) {
      const fields = getMandatoryFields();
      const idx = fields.indexOf(e.target);
      if (idx > 0) {
        e.preventDefault();
        fields[idx - 1].focus();
      }
    }
  });

  document.addEventListener("keydown", function (e) {
    // Ctrl+S Save is handled globally by hotkey.js (stampSaveBtn)
    if (e.key === "F2") {
      e.preventDefault();
      if (!els.editBtn?.disabled && selectedStampId) {
        loadStampRecord(selectedStampId);
        els.certNumber?.focus();
      }
      return;
    }
    if (e.key === "Escape") {
      if (els.zoomModalEl?.classList.contains("show")) zoomModal?.hide();
      else if (isOcrMode() && selectedFile) clearImage();
    }
  });

  els.filterApplyBtn?.addEventListener("click", function (e) {
    e.preventDefault();
    loadMainGrid();
  });
  els.filterResetBtn?.addEventListener("click", function (e) {
    e.preventDefault();
    resetGridFilters();
  });
  els.dutyGroupApplyBtn?.addEventListener("click", function (e) {
    e.preventDefault();
    loadDutyGrouping();
  });
  els.dutyGroupClearBtn?.addEventListener("click", function (e) {
    e.preventDefault();
    if (els.dutyGroupFrom) els.dutyGroupFrom.value = "";
    if (els.dutyGroupTo) els.dutyGroupTo.value = "";
    loadDutyGrouping();
  });
  [els.dutyGroupFrom, els.dutyGroupTo].forEach(function (input) {
    input?.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        loadDutyGrouping();
      }
    });
  });
  if (els.pageSize) {
    const storedSize = readStoredPageSize();
    els.pageSize.value = String(storedSize);
    pageState.pageSize = storedSize;
    els.pageSize.addEventListener("change", function () {
      const size = currentPageSize();
      pageState.pageSize = size;
      persistPageSize(size);
      renderMainDataGrid(mainGridRows, { resetPage: true });
    });
  }
  if (els.pagerNav) {
    els.pagerNav.addEventListener("click", function (event) {
      const btn = event.target.closest(".stamp-page-btn");
      if (!btn || !els.pagerNav.contains(btn)) return;
      const page = Number(btn.getAttribute("data-page") || "");
      if (!Number.isFinite(page) || page < 1) return;
      pageState.page = page;
      renderMainDataGrid(mainGridRows);
    });
  }
  els.filterPeriod?.addEventListener("change", function () {
    applyPeriodPreset(els.filterPeriod.value || "month");
    loadMainGrid();
  });
  els.filterDateFrom?.addEventListener("change", markPeriodAsCustom);
  els.filterDateTo?.addEventListener("change", markPeriodAsCustom);
  ["stampFilterDateFrom", "stampFilterDateTo", "stampFilterCert", "stampFilterMobile", "stampFilterCustomer"].forEach(function (id) {
    document.getElementById(id)?.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        loadMainGrid();
      }
    });
  });

  const COL_WIDTH_KEY = "stamp-grid-col-widths-v2";
  let columnResizeMoved = false;

  function readStoredColWidths() {
    try {
      const raw = localStorage.getItem(COL_WIDTH_KEY);
      const parsed = raw ? JSON.parse(raw) : null;
      if (parsed && typeof parsed === "object") return parsed;
    } catch (err) {
      /* ignore */
    }
    return {};
  }

  function persistColWidths(widths) {
    try {
      localStorage.setItem(COL_WIDTH_KEY, JSON.stringify(widths));
    } catch (err) {
      /* ignore */
    }
  }

  function applyColumnWidth(index, widthPx) {
    const table = document.getElementById("stampDataGrid");
    if (!table) return;
    const width = Math.max(52, Math.round(widthPx));
    table.querySelectorAll("thead tr").forEach(function (tr) {
      const th = tr.children[index];
      if (th) {
        th.style.width = width + "px";
        th.style.minWidth = width + "px";
        th.style.maxWidth = width + "px";
      }
    });
  }

  function clearColumnWidths() {
    const table = document.getElementById("stampDataGrid");
    if (!table) return;
    table.querySelectorAll("thead th").forEach(function (th) {
      th.style.width = "";
      th.style.minWidth = "";
      th.style.maxWidth = "";
    });
    table.style.tableLayout = "auto";
    table.style.width = "max-content";
    table.style.minWidth = "0";
  }

  function autoFitGridColumns() {
    const table = document.getElementById("stampDataGrid");
    const headerRow = table?.querySelector("thead tr");
    if (!table || !headerRow) return;
    const stored = readStoredColWidths();
    clearColumnWidths();
    const colCount = headerRow.children.length;
    const natural = [];
    for (let i = 0; i < colCount; i++) {
      let max = 0;
      table.querySelectorAll("thead tr").forEach(function (tr) {
        const cell = tr.children[i];
        if (cell) max = Math.max(max, cell.scrollWidth);
      });
      table.querySelectorAll("tbody tr").forEach(function (tr) {
        const td = tr.children[i];
        if (td) max = Math.max(max, td.scrollWidth);
      });
      natural[i] = Math.max(52, max + 8);
    }
    for (let i = 0; i < colCount; i++) {
      applyColumnWidth(i, stored[String(i)] || natural[i]);
    }
    table.style.tableLayout = "fixed";
    table.style.width = "max-content";
  }

  function initColumnResize() {
    const table = document.getElementById("stampDataGrid");
    const headerRow = table?.querySelector("thead tr");
    if (!table || !headerRow) return;
    Array.from(headerRow.children).forEach(function (th, index) {
      if (th.querySelector(".stamp-col-resizer")) return;
      const handle = document.createElement("span");
      handle.className = "stamp-col-resizer";
      handle.title = "Drag to resize column";
      th.appendChild(handle);
      handle.addEventListener("mousedown", function (event) {
        event.preventDefault();
        event.stopPropagation();
        columnResizeMoved = false;
        const startX = event.pageX;
        const startWidth = th.getBoundingClientRect().width;
        handle.classList.add("is-active");
        document.body.classList.add("stamp-col-resizing");
        function onMove(moveEvent) {
          const next = startWidth + (moveEvent.pageX - startX);
          if (Math.abs(moveEvent.pageX - startX) > 3) columnResizeMoved = true;
          applyColumnWidth(index, next);
        }
        function onUp() {
          document.removeEventListener("mousemove", onMove);
          document.removeEventListener("mouseup", onUp);
          handle.classList.remove("is-active");
          document.body.classList.remove("stamp-col-resizing");
          const widths = readStoredColWidths();
          widths[String(index)] = Math.round(th.getBoundingClientRect().width);
          persistColWidths(widths);
        }
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
      });
    });
    autoFitGridColumns();
  }

  const stampGridHead = document.querySelector("#stampDataGrid thead");
  stampGridHead?.addEventListener("click", function (event) {
    if (event.target.closest(".stamp-col-filter")) return;
    if (event.target.closest(".stamp-col-resizer")) return;
    if (columnResizeMoved) {
      columnResizeMoved = false;
      return;
    }
    const th = event.target.closest("th.stamp-sortable");
    if (!th) return;
    onGridSortHeader(th.dataset.sortKey);
  });
  stampGridHead?.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    const th = event.target.closest("th.stamp-sortable");
    if (!th) return;
    event.preventDefault();
    onGridSortHeader(th.dataset.sortKey);
  });
  stampGridHead?.addEventListener("input", function (event) {
    const input = event.target.closest(".stamp-col-filter");
    if (!input) return;
    readGridFiltersFromDom();
    // Certificate column filter must query the server — the grid only holds a page of rows
    // (period can have 1000+ stamps), so client-only filtering misses JTCS matches.
    if (input.dataset.filterKey === "certificate_number") {
      if (els.filterCert && !(els.filterCert.value || "").trim()) {
        els.filterCert.value = gridFilters.certificate_number || "";
      }
      scheduleCertificateServerReload();
      return;
    }
    if (input.dataset.filterKey === "customer_name") {
      scheduleCertificateServerReload();
      return;
    }
    renderMainDataGrid(mainGridRows, { resetPage: true });
  });
  stampGridHead?.addEventListener("keydown", function (event) {
    const input = event.target.closest(".stamp-col-filter");
    if (
      !input ||
      (input.dataset.filterKey !== "certificate_number" && input.dataset.filterKey !== "customer_name")
    ) {
      return;
    }
    if (event.key !== "Enter") return;
    event.preventDefault();
    if (certFilterReloadTimer) {
      clearTimeout(certFilterReloadTimer);
      certFilterReloadTimer = null;
    }
    readGridFiltersFromDom();
    if (input.dataset.filterKey === "certificate_number" && els.filterCert) {
      els.filterCert.value = gridFilters.certificate_number || "";
    }
    loadMainGrid();
  });

  updateEngineBanner(window.STAMP_OCR_STATUS);
  refreshOcrStatus();
  resetPaymentLines();
  const autoStampId = parseInt(window.STAMP_AUTO_LOAD_STAMP_ID, 10) || 0;
  const openedFromRepost = initMobileFromRepost();
  if (openedFromRepost) {
    if (autoStampId) {
      setEditStampIds(autoStampId);
      setSelectedStamp(autoStampId);
    }
    openEntryModal();
    if (autoStampId) {
      loadStampRecord(autoStampId).then(function () {
        revealStampInGrid({
          stampId: autoStampId,
          certificate: (els.certNumber?.value || "").trim(),
        });
      });
    } else {
      enterSaveMode();
      applyWebsitePrefill();
    }
  } else {
    resetToMobileGate();
    updateToolbarButtons();
  }
  if (els.filterPeriod) {
    applyDefaultGridDates();
  }
  initColumnResize();
  if (autoStampId && openedFromRepost) {
    /* Grid is loaded by revealStampInGrid after the record fetch. */
  } else if (autoStampId) {
    revealSavedStampInGrid(autoStampId);
  } else {
    loadMainGrid();
  }

  var shcilCreds = { userId: "", password: "" };

  function setShcilLoginStatus(message, kind) {
    var box = document.getElementById("stampShcilLoginStatus");
    if (!box) return;
    box.textContent = message || "";
    box.classList.toggle("d-none", !message);
    box.classList.remove("is-info", "is-ok", "is-error");
    if (message) box.classList.add(kind === "error" ? "is-error" : kind === "ok" ? "is-ok" : "is-info");
  }

  function hideShcilCreds() {
    var box = document.getElementById("stampShcilCreds");
    if (box) box.classList.add("d-none");
  }

  function showShcilCreds(userId, password, loginUrl) {
    shcilCreds.userId = userId || "";
    shcilCreds.password = password || "";
    var box = document.getElementById("stampShcilCreds");
    var userEl = document.getElementById("stampShcilUserIdText");
    var passEl = document.getElementById("stampShcilPasswordText");
    var link = document.getElementById("stampShcilOpenLink");
    if (userEl) userEl.textContent = shcilCreds.userId;
    if (passEl) passEl.textContent = shcilCreds.password;
    if (link && loginUrl) link.href = loginUrl;
    if (box) box.classList.remove("d-none");
  }

  function copyShcilValue(text) {
    var value = String(text || "");
    if (!value) return Promise.resolve();
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(value);
    }
    return new Promise(function (resolve, reject) {
      var input = document.createElement("textarea");
      input.value = value;
      input.setAttribute("readonly", "");
      input.style.position = "fixed";
      input.style.left = "-9999px";
      document.body.appendChild(input);
      input.select();
      try {
        document.execCommand("copy");
        resolve();
      } catch (err) {
        reject(err);
      }
      document.body.removeChild(input);
    });
  }

  function openShcilPopup(loginUrl, role) {
    var dest = loginUrl || window.STAMP_SHCIL_LOGIN_URL || "";
    if (!dest) return null;
    return window.open(
      dest,
      "jtcsShcilLogin_" + String(role || "deo"),
      "width=1200,height=840,scrollbars=yes,resizable=yes"
    );
  }

  async function openShcilLogin(role, btn) {
    var csrf = window.STAMP_CSRF || "";
    var url = window.STAMP_OPEN_LOGIN_URL || "/shcil/stamp-activity/open-login";
    var loginUrl = window.STAMP_SHCIL_LOGIN_URL || "";
    var clientHint = !!window.STAMP_SHCIL_CLIENT_LOGIN;
    var popup = null;
    if (btn) btn.disabled = true;
    hideShcilCreds();
    if (clientHint) {
      popup = openShcilPopup(loginUrl, role);
      setShcilLoginStatus("Opening SHCIL " + String(role || "").toUpperCase() + " login in this browser...", "info");
    } else {
      setShcilLoginStatus("Opening SHCIL " + String(role || "").toUpperCase() + " login and filling User ID / password...", "info");
    }
    try {
      var res = await fetch(url, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRFToken": csrf,
          "X-CSRF-Token": csrf,
        },
        body: JSON.stringify({ role: role, csrf_token: csrf }),
      });
      var data = await res.json();
      if (!res.ok || data.ok === false) throw new Error(data.error || "Unable to open SHCIL login.");
      var dest = data.login_url || loginUrl;
      if (data.mode === "client") {
        if (!popup || popup.closed) popup = openShcilPopup(dest, role);
        else {
          try { popup.location.href = dest; } catch (e) {}
        }
        showShcilCreds(data.user_id, data.password, dest);
        copyShcilValue(data.user_id).catch(function () {});
        var extra = popup ? "" : " Popup blocked — use “Open SHCIL login page” below.";
        setShcilLoginStatus((data.message || "SHCIL login opened.") + extra, popup ? "ok" : "error");
      } else {
        if (popup && !popup.closed) {
          try { popup.close(); } catch (e) {}
        }
        hideShcilCreds();
        setShcilLoginStatus(data.message || "User ID and password filled. Close the SHCIL window yourself when finished.", "ok");
      }
    } catch (err) {
      if (clientHint && loginUrl && (!popup || popup.closed)) {
        popup = openShcilPopup(loginUrl, role);
      }
      setShcilLoginStatus((err && err.message) || "Unable to open SHCIL login.", "error");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  document.getElementById("stampShcilCopyUserBtn")?.addEventListener("click", function () {
    copyShcilValue(shcilCreds.userId).catch(function () {});
  });
  document.getElementById("stampShcilCopyPassBtn")?.addEventListener("click", function () {
    copyShcilValue(shcilCreds.password).catch(function () {});
  });

  document.getElementById("stampLoginDeoBtn")?.addEventListener("click", function () {
    openShcilLogin("deo", this);
  });
  document.getElementById("stampLoginAdminBtn")?.addEventListener("click", function () {
    openShcilLogin("admin", this);
  });
})();
