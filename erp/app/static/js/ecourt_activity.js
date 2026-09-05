(function () {
  function displayDate(value) {
    if (typeof window.formatDisplayDate === "function") {
      return window.formatDisplayDate(value);
    }
    return value || "—";
  }

  const els = {
    openImportBtn: document.getElementById("ecourtOpenImportBtn"),
    backBtn: document.getElementById("ecourtBackBtn"),
    openManualBtn: document.getElementById("ecourtOpenManualBtn"),
    importModalEl: document.getElementById("ecourtImportModal"),
    manualModalEl: document.getElementById("ecourtManualModal"),
    uploadPanel: document.getElementById("ecourtUploadPanel"),
    previewPanel: document.getElementById("ecourtPreviewPanel"),
    pdfInput: document.getElementById("ecourtPdfInput"),
    readPdfBtn: document.getElementById("ecourtReadPdfBtn"),
    uploadStatus: document.getElementById("ecourtUploadStatus"),
    previewMeta: document.getElementById("ecourtPreviewMeta"),
    previewBody: document.getElementById("ecourtPreviewBody"),
    previewCount: document.getElementById("ecourtPreviewCount"),
    previewSummary: document.getElementById("ecourtPreviewSummary"),
    jumpNextBlockBtn: document.getElementById("ecourtJumpNextBlockBtn"),
    addRowBtn: document.getElementById("ecourtAddRowBtn"),
    confirmImportBtn: document.getElementById("ecourtConfirmImportBtn"),
    importId: document.getElementById("ecourtImportId"),
    summaryBanner: document.getElementById("ecourtSummaryBanner"),
    periodGrid: document.getElementById("ecourtPeriodGrid"),
    periodLabel: document.getElementById("ecourtPeriodLabel"),
    gridBody: document.getElementById("ecourtGridBody"),
    gridCount: document.getElementById("ecourtGridCount"),
    gridEmpty: document.getElementById("ecourtGridEmpty"),
    duplicateModalEl: document.getElementById("ecourtDuplicateModal"),
    duplicateSummary: document.getElementById("ecourtDuplicateSummary"),
    duplicateBody: document.getElementById("ecourtDuplicateBody"),
    sellSelectedBtn: document.getElementById("ecourtSellSelectedBtn"),
    saleModalEl: document.getElementById("ecourtSaleModal"),
    saleForm: document.getElementById("ecourtSaleForm"),
    saleDate: document.getElementById("ecourtSaleDate"),
    saleAmount: document.getElementById("ecourtSaleAmount"),
    saleReceiptBody: document.getElementById("ecourtSaleReceiptBody"),
    paymentLines: document.getElementById("ecourtPaymentLines"),
    paymentSummary: document.getElementById("ecourtPaymentSummary"),
    addPaymentBtn: document.getElementById("ecourtAddPaymentBtn"),
    confirmSaleBtn: document.getElementById("ecourtConfirmSaleBtn"),
    manualForm: document.getElementById("ecourtManualForm"),
    manualSaveBtn: document.getElementById("ecourtManualSaveBtn"),
    manualPreviewBody: document.getElementById("ecourtManualPreviewBody"),
  };

  if (!els.gridBody || !window.ECOURT_URLS) return;

  const importModal = els.importModalEl && window.bootstrap
    ? window.bootstrap.Modal.getOrCreateInstance(els.importModalEl)
    : null;
  const manualModal = els.manualModalEl && window.bootstrap
    ? window.bootstrap.Modal.getOrCreateInstance(els.manualModalEl)
    : null;
  const duplicateModal = els.duplicateModalEl && window.bootstrap
    ? window.bootstrap.Modal.getOrCreateInstance(els.duplicateModalEl)
    : null;
  const saleModal = els.saleModalEl && window.bootstrap
    ? window.bootstrap.Modal.getOrCreateInstance(els.saleModalEl)
    : null;

  let pendingSaleReceipts = [];

  let currentImportId = window.ECOURT_LATEST_IMPORT_ID || null;
  let previewMeta = null;
  let previewRows = [];
  let existingImportedReceipts = new Set();
  let existingImportedReceiptDetails = new Map();
  const MIN_IMPORT_AMOUNT = 1;
  const MAX_IMPORT_AMOUNT = 500;
  const SMALL_AMOUNT_MAX = 10;
  const HIGH_AMOUNT_MIN = 11;
  const BLOCK_SIZE = 20;
  let nextBlockRowIndex = BLOCK_SIZE;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function normalizeAmount(value) {
    const num = parseFloat(String(value || "").replace(/,/g, "").trim());
    return Number.isFinite(num) ? num.toFixed(2) : "";
  }

  function isImportableAmount(value) {
    const num = parseFloat(String(value || "").replace(/,/g, "").trim());
    return Number.isFinite(num) && num >= MIN_IMPORT_AMOUNT && num <= MAX_IMPORT_AMOUNT;
  }

  function isHighAmountRow(row) {
    if (!row) return false;
    if (row.high_amount || row.auto_stationery) return true;
    const num = parseFloat(String(row.amount || "").replace(/,/g, "").trim());
    return Number.isFinite(num) && num >= HIGH_AMOUNT_MIN && num <= MAX_IMPORT_AMOUNT;
  }

  function isBlockStartRow(index) {
    const row = previewRows[index];
    if (!row || isHighAmountRow(row)) return false;
    let smallIndex = -1;
    for (let i = 0; i <= index; i++) {
      if (!isHighAmountRow(previewRows[i])) smallIndex++;
    }
    return smallIndex >= 0 && smallIndex % BLOCK_SIZE === 0;
  }

  function isCompleteImportRow(row) {
    if (row.already_imported) return false;
    return (
      (row.receipt_no || "").trim() &&
      (row.receipt_date || "").trim() &&
      isImportableAmount(row.amount) &&
      (row.stationerynumber || "").trim()
    );
  }

  function loadExistingFromParseResponse(data) {
    existingImportedReceipts = new Set();
    existingImportedReceiptDetails = new Map();

    const records = data.existing_imported_receipts || [];
    if (records.length) {
      records.forEach(function (rec) {
        const key = (rec.receipt_no || "").trim().toUpperCase();
        if (!key) return;
        existingImportedReceipts.add(key);
        existingImportedReceiptDetails.set(key, (rec.stationerynumber || "").trim());
      });
      return records.length;
    }

    const numbers = data.existing_receipt_numbers || [];
    if (numbers.length) {
      numbers.forEach(function (receiptNo) {
        const key = (receiptNo || "").trim().toUpperCase();
        if (key) existingImportedReceipts.add(key);
      });
      return numbers.length;
    }

    const legacyPairs = data.existing_import_pairs || [];
    if (legacyPairs.length) {
      legacyPairs.forEach(function (pair) {
        const key = (pair.receipt_no || "").trim().toUpperCase();
        if (!key) return;
        existingImportedReceipts.add(key);
        existingImportedReceiptDetails.set(key, (pair.stationerynumber || "").trim());
      });
      return legacyPairs.length;
    }

    return 0;
  }

  function getImportedStationery(receiptNo) {
    return existingImportedReceiptDetails.get((receiptNo || "").trim().toUpperCase()) || "";
  }

  function isReceiptAlreadyImported(receiptNo) {
    return existingImportedReceipts.has((receiptNo || "").trim().toUpperCase());
  }

  function sortPreviewRowsDuplicatesLast(rows) {
    const active = [];
    const imported = [];
    (rows || []).forEach(function (row) {
      if (row.already_imported) imported.push(row);
      else active.push(row);
    });
    return active.concat(imported);
  }

  function refreshDuplicatePreviewRows() {
    previewRows.forEach(function (row) {
      const receipt = (row.receipt_no || "").trim();
      const isDuplicate = !!(receipt && isReceiptAlreadyImported(receipt));
      if (isDuplicate) {
        row.already_imported = true;
        row.receipt_status = "Already imported";
        row.stationerynumber = getImportedStationery(receipt) || row.stationerynumber || "";
      } else if (row.already_imported) {
        row.already_imported = false;
        row.receipt_status = row._original_status || row.receipt_status || "Not Locked";
      }
    });
    previewRows = sortPreviewRowsDuplicatesLast(previewRows);
  }

  function filterEligiblePreviewRows(rows) {
    return (rows || []).filter(function (row) {
      return isImportableAmount(row.amount);
    });
  }

  function syncPreviewRowsFromDom() {
    if (!els.previewBody) return;
    const synced = [];
    els.previewBody.querySelectorAll("tr").forEach(function (tr, index) {
      const previous = previewRows[index] || {};
      const row = {
        already_imported: !!previous.already_imported,
        _original_status: previous._original_status || "Not Locked",
        stationerynumber: previous.stationerynumber || "",
        auto_stationery: !!previous.auto_stationery,
        high_amount: !!previous.high_amount || isHighAmountRow(previous),
      };
      tr.querySelectorAll("[data-field]").forEach(function (input) {
        row[input.dataset.field] = input.value.trim();
      });
      if ((row.receipt_no || "").trim()) {
        row.receipt_no = (row.receipt_no || "").trim().toUpperCase();
      }
      if (row.high_amount || isHighAmountRow(row)) {
        row.high_amount = true;
        row.auto_stationery = true;
      }
      if (row.already_imported) {
        row.stationerynumber = getImportedStationery(row.receipt_no) || row.stationerynumber || "";
        row.receipt_status = "Already imported";
      }
      synced.push(row);
    });
    if (synced.length) previewRows = synced;
  }

  function countImportableRows(rows) {
    return (rows || []).filter(isCompleteImportRow).length;
  }

  function countPendingStationery(rows) {
    return (rows || []).filter(function (row) {
      return (
        (row.receipt_no || "").trim() &&
        isImportableAmount(row.amount) &&
        !(row.stationerynumber || "").trim()
      );
    }).length;
  }

  function validateForImport(rows) {
    const errors = [];
    const importRows = [];
    const stationeryBlockMap = {};

    const smallIndexed = [];
    const highIndexed = [];
    (rows || []).forEach(function (row, index) {
      if (row.already_imported) return;
      if (isHighAmountRow(row)) highIndexed.push({ row: row, rowNum: index + 1 });
      else smallIndexed.push({ row: row, rowNum: index + 1 });
    });

    for (let blockStart = 0; blockStart < smallIndexed.length; blockStart += BLOCK_SIZE) {
      const block = smallIndexed.slice(blockStart, blockStart + BLOCK_SIZE);
      const blockNum = Math.floor(blockStart / BLOCK_SIZE) + 1;
      const rowStart = block[0] ? block[0].rowNum : blockStart + 1;
      const rowEnd = block.length ? block[block.length - 1].rowNum : rowStart;
      const blockStationeries = new Set();
      const blockComplete = [];
      const partialRowNums = [];
      let hasAnyData = false;
      let blockHasStationery = false;

      block.forEach(function (item) {
        const row = item.row;
        const rowNum = item.rowNum;
        const receiptNo = (row.receipt_no || "").trim();
        const receiptDate = (row.receipt_date || "").trim();
        const amount = row.amount;
        const stationery = (row.stationerynumber || "").trim();

        if (!receiptNo && !receiptDate && !amount && !stationery) return;

        hasAnyData = true;
        if (stationery) blockHasStationery = true;
        if (!isCompleteImportRow(row)) {
          partialRowNums.push(rowNum);
          return;
        }
        blockComplete.push(row);
        blockStationeries.add(stationery);
      });

      if (!hasAnyData || !blockHasStationery) continue;

      if (partialRowNums.length) {
        errors.push(
          "Block " + blockNum + " (rows " + rowStart + "-" + rowEnd + "): rows " +
          partialRowNums.join(", ") + " have blank receipt no, date, amount or stationery number."
        );
      } else if (blockComplete.length && blockStationeries.size > 1) {
        errors.push(
          "Block " + blockNum + " (rows " + rowStart + "-" + rowEnd + "): " +
          "all rows must have the same stationery number."
        );
      } else if (blockComplete.length && blockStationeries.size === 1) {
        const stationery = Array.from(blockStationeries)[0];
        if (stationeryBlockMap[stationery]) {
          errors.push(
            "Duplicate stationery number '" + stationery + "' in block " + blockNum +
            " and block " + stationeryBlockMap[stationery] + "."
          );
        } else {
          stationeryBlockMap[stationery] = blockNum;
        }
        blockComplete.forEach(function (row) {
          importRows.push(row);
        });
      }
    }

    const highStationeries = new Set();
    const highComplete = [];
    const highPartial = [];
    highIndexed.forEach(function (item) {
      const row = item.row;
      const receiptNo = (row.receipt_no || "").trim();
      const receiptDate = (row.receipt_date || "").trim();
      const amount = row.amount;
      const stationery = (row.stationerynumber || "").trim();
      if (!receiptNo && !receiptDate && !amount && !stationery) return;
      if (!isCompleteImportRow(row)) {
        highPartial.push(item.rowNum);
        return;
      }
      highComplete.push(row);
      highStationeries.add(stationery);
    });

    if (highPartial.length) {
      errors.push(
        "High-amount rows " + highPartial.join(", ") +
        ": blank receipt no, date, amount or stationery number."
      );
    } else if (highComplete.length) {
      if (highStationeries.size > 1) {
        errors.push(
          "All amount " + HIGH_AMOUNT_MIN + "–" + MAX_IMPORT_AMOUNT +
          " rows must share one auto stationery number."
        );
      } else {
        const stationery = Array.from(highStationeries)[0];
        if (stationeryBlockMap[stationery]) {
          errors.push(
            "Duplicate stationery number '" + stationery +
            "' used by high-amount rows and small-amount block " +
            stationeryBlockMap[stationery] + "."
          );
        } else {
          highComplete.forEach(function (row) {
            importRows.push(row);
          });
        }
      }
    }

    const seenComposite = new Set();
    const seenReceipts = new Set();
    importRows.forEach(function (row) {
      if (row.already_imported) return;
      const key = [
        (row.receipt_no || "").trim().toUpperCase(),
        (row.receipt_date || "").trim(),
        normalizeAmount(row.amount),
        (row.stationerynumber || "").trim(),
      ].join("|");
      if (seenComposite.has(key)) {
        errors.push("Duplicate receipt no + date + amount + stationery number found.");
      }
      seenComposite.add(key);

      const receipt = (row.receipt_no || "").trim().toUpperCase();
      if (seenReceipts.has(receipt)) {
        errors.push("Duplicate receipt number " + receipt + ".");
      }
      seenReceipts.add(receipt);
    });

    return { ok: errors.length === 0, errors: errors, importRows: importRows };
  }

  function scrollToBlockRow(index) {
    const tr = els.previewBody?.querySelector('tr[data-index="' + index + '"]');
    if (!tr) return;
    tr.scrollIntoView({ behavior: "smooth", block: "center" });
    tr.querySelector('[data-field="stationerynumber"]')?.focus();
  }

  function updateJumpNextBlockBtn() {
    if (!els.jumpNextBlockBtn) return;
    while (
      nextBlockRowIndex < previewRows.length &&
      (isHighAmountRow(previewRows[nextBlockRowIndex]) ||
        previewRows[nextBlockRowIndex].already_imported)
    ) {
      nextBlockRowIndex++;
    }
    if (nextBlockRowIndex >= previewRows.length) {
      els.jumpNextBlockBtn.classList.add("d-none");
      return;
    }
    els.jumpNextBlockBtn.classList.remove("d-none");
    els.jumpNextBlockBtn.textContent = "Go to row " + (nextBlockRowIndex + 1);
  }

  function updatePreviewCountText() {
    if (!els.previewCount) return;
    const importable = countImportableRows(previewRows);
    const importedCount = (previewRows || []).filter(function (row) {
      return row.already_imported;
    }).length;
    let text = importable + " row" + (importable === 1 ? "" : "s") + " ready to import";
    if (previewRows.length > importable) {
      text += " (only rows with stationery number filled)";
    }
    if (importedCount) {
      text += " — " + importedCount + " already imported (shown at bottom, red, disabled)";
    }
    els.previewCount.textContent = text;
    updateJumpNextBlockBtn();
  }

  function resetImportModal() {
    previewRows = [];
    previewMeta = null;
    existingImportedReceipts = new Set();
    existingImportedReceiptDetails = new Map();
    nextBlockRowIndex = BLOCK_SIZE;
    if (els.pdfInput) els.pdfInput.value = "";
    if (els.uploadStatus) els.uploadStatus.textContent = "";
    if (els.previewPanel) els.previewPanel.classList.add("d-none");
    renderPreviewGrid();
  }

  function openImportModal() {
    resetImportModal();
    importModal?.show();
  }

  function closeImportModal() {
    importModal?.hide();
    resetImportModal();
  }

  function findStationeryGroup(groups, query) {
    const normalized = (query || "").trim().toUpperCase();
    if (!normalized) return null;
    const exact = (groups || []).find(function (group) {
      return (group.stationerynumber || "").toUpperCase() === normalized;
    });
    if (exact) return exact;
    const partial = (groups || []).filter(function (group) {
      const stationery = (group.stationerynumber || "").toUpperCase();
      return stationery.includes(normalized) || stationery.endsWith(normalized);
    });
    if (partial.length === 1) return partial[0];
    return partial.find(function (group) {
      return (group.stationerynumber || "").toUpperCase().endsWith(normalized);
    }) || null;
  }

  function showDuplicateReport(duplicates, importedCount) {
    if (!duplicates || !duplicates.length || !els.duplicateBody) return;
    els.duplicateBody.innerHTML = "";
    duplicates.forEach(function (row) {
      const tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" + escapeHtml(row.stationerynumber || "") + "</td>" +
        "<td>" + escapeHtml(row.receipt_no || "") + "</td>" +
        "<td class=\"small text-muted\">" + escapeHtml(row.reason || "Already exists") + "</td>";
      els.duplicateBody.appendChild(tr);
    });
    if (els.duplicateSummary) {
      els.duplicateSummary.textContent =
        importedCount + " receipt(s) imported. " + duplicates.length +
        " duplicate receipt + stationery combination(s) were not imported.";
    }
    duplicateModal?.show();
  }

  function parseAmount(value) {
    const num = parseFloat(String(value || "").replace(/,/g, "").trim());
    return Number.isFinite(num) ? num : 0;
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

  function buildPaymentSelect(selectedValue) {
    const select = document.createElement("select");
    select.className = "form-select form-select-sm ecourt-payment-bank";
    select.name = "PaymentBankAccountID[]";
    select.required = true;
    const accounts = (window.ECOURT_BANK_ACCOUNTS || []).filter(function (item) {
      const flag = item && item.qr_bill_received;
      return flag === true || flag === 1 || flag === "1";
    });
    if (!accounts.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "No bank account configured";
      select.appendChild(opt);
      select.disabled = true;
      return select;
    }
    accounts.forEach(function (item) {
      const opt = document.createElement("option");
      opt.value = String(item.bank_account_id || "");
      opt.textContent = paymentModeLabel(item);
      select.appendChild(opt);
    });
    if (
      selectedValue &&
      Array.from(select.options).some(function (opt) {
        return opt.value === String(selectedValue);
      })
    ) {
      select.value = String(selectedValue);
    } else {
      const cashOption = Array.from(select.options).find(function (opt) {
        return opt.value && opt.textContent.trim() === "Cash";
      });
      if (cashOption) select.value = cashOption.value;
    }
    return select;
  }

  function getPaymentTotalFrom(container) {
    let total = 0;
    container?.querySelectorAll(".ecourt-payment-amount").forEach(function (input) {
      total += parseAmount(input.value);
    });
    return total;
  }

  function updatePaymentSummary() {
    if (!els.paymentSummary) return;
    const sale = parseAmount(els.saleAmount?.value);
    const total = getPaymentTotalFrom(els.paymentLines);
    if (!sale && !total) {
      els.paymentSummary.textContent = "";
      els.paymentSummary.className = "small text-muted ms-auto";
      return;
    }
    if (total + 0.001 >= sale) {
      els.paymentSummary.textContent = "Payment total: " + total.toFixed(2);
      els.paymentSummary.className = "small text-success ms-auto";
    } else {
      els.paymentSummary.textContent =
        "Payment total: " + total.toFixed(2) + " / Sale: " + sale.toFixed(2);
      els.paymentSummary.className = "small text-danger ms-auto";
    }
  }

  function updatePaymentRemoveButtonsFor(container) {
    const lines = container?.querySelectorAll(".ecourt-payment-line") || [];
    const hideRemove = lines.length <= 1;
    lines.forEach(function (line) {
      const btn = line.querySelector(".ecourt-payment-remove");
      if (btn) btn.disabled = hideRemove;
    });
  }

  function updatePaymentRemoveButtons() {
    updatePaymentRemoveButtonsFor(els.paymentLines);
  }

  function addPaymentLineTo(container, options, onAmountInput) {
    options = options || {};
    if (!container) return null;
    const line = document.createElement("div");
    line.className = "ecourt-payment-line";
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
    amountLabel.textContent = "Amount";
    const amount = document.createElement("input");
    amount.type = "number";
    amount.step = "0.01";
    amount.min = "0";
    amount.className = "form-control form-control-sm ecourt-payment-amount";
    amount.name = "PaymentAmount[]";
    amount.required = true;
    amount.value = options.amount != null && options.amount !== "" ? options.amount : "0";
    amount.addEventListener("input", onAmountInput || updatePaymentSummary);
    amountWrap.appendChild(amountLabel);
    amountWrap.appendChild(amount);
    const actionWrap = document.createElement("div");
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn btn-outline-danger btn-sm ecourt-payment-remove";
    removeBtn.innerHTML = "<i class=\"bi bi-trash\"></i>";
    removeBtn.addEventListener("click", function () {
      if ((container.querySelectorAll(".ecourt-payment-line") || []).length <= 1) return;
      line.remove();
      updatePaymentRemoveButtonsFor(container);
      (onAmountInput || updatePaymentSummary)();
    });
    actionWrap.appendChild(removeBtn);
    line.appendChild(bankWrap);
    line.appendChild(amountWrap);
    line.appendChild(actionWrap);
    container.appendChild(line);
    updatePaymentRemoveButtonsFor(container);
    (onAmountInput || updatePaymentSummary)();
    return line;
  }

  function addPaymentLine(options) {
    return addPaymentLineTo(els.paymentLines, options, updatePaymentSummary);
  }

  function resetPaymentLines(totalAmount) {
    if (!els.paymentLines) return;
    els.paymentLines.innerHTML = "";
    addPaymentLine({ amount: totalAmount.toFixed(2) });
  }

  function validatePaymentLinesIn(container, saleAmount) {
    const lines = container?.querySelectorAll(".ecourt-payment-line") || [];
    if (!lines.length) return "At least one payment mode is required.";
    for (let i = 0; i < lines.length; i++) {
      const bank = lines[i].querySelector(".ecourt-payment-bank");
      const amount = lines[i].querySelector(".ecourt-payment-amount");
      if (!bank?.value) return "Each payment mode must be selected.";
      if (parseAmount(amount?.value) <= 0) {
        return "Each payment amount must be greater than zero.";
      }
    }
    if (getPaymentTotalFrom(container) + 0.001 < saleAmount) {
      return "Payment total must be at least the sale amount.";
    }
    return "";
  }

  function validatePaymentLines() {
    return validatePaymentLinesIn(els.paymentLines, parseAmount(els.saleAmount?.value));
  }

  function refreshManualPreview() {
    if (!els.manualPreviewBody) return;
    const receiptNo = (document.getElementById("ecourtReceiptNo")?.value || "").trim();
    const stationeryNo = (document.getElementById("ecourtStationeryNo")?.value || "").trim();
    const receiptDate = (document.getElementById("ecourtManualDate")?.value || "").trim();
    const amount = (document.getElementById("ecourtManualAmount")?.value || "").trim();
    if (!receiptNo && !stationeryNo && !amount) {
      els.manualPreviewBody.innerHTML =
        "<tr class=\"ecourt-manual-preview-empty\"><td colspan=\"5\" class=\"small text-muted\">" +
        "Fill details above. Save imports into the stationery grid (same as PDF Import).</td></tr>";
      return;
    }
    els.manualPreviewBody.innerHTML =
      "<tr>" +
      "<td>" + escapeHtml(receiptNo || "—") + "</td>" +
      "<td>" + escapeHtml(stationeryNo || "—") + "</td>" +
      "<td>" + escapeHtml(displayDate(receiptDate)) + "</td>" +
      "<td class=\"text-end\">" + escapeHtml(amount || "—") + "</td>" +
      "<td class=\"text-end\"><button type=\"button\" class=\"btn btn-warning btn-sm ecourt-manual-preview-edit\">Edit</button></td>" +
      "</tr>";
  }

  function updateSellSelectedButton() {
    const count = els.gridBody?.querySelectorAll(".ecourt-receipt-select:checked").length || 0;
    els.sellSelectedBtn?.classList.toggle("d-none", count === 0);
    if (els.sellSelectedBtn && count > 0) {
      els.sellSelectedBtn.innerHTML =
        "<i class=\"bi bi-cart-check\"></i> Sell Selected (" + count + ")";
    }
  }

  function collectReceiptsFromRows(rows) {
    return (rows || []).map(function (row) {
      return {
        receipt_no: row.receipt_no || "",
        stationerynumber: row.stationerynumber || "",
        receipt_date: row.receipt_date || "",
        amount: row.amount || "",
      };
    });
  }

  let pendingManualCreate = false;
  let pendingManualMeta = null;

  function openSaleModal(receipts) {
    const list = (receipts || []).filter(function (row) {
      return (row.receipt_no || "").trim();
    });
    if (!list.length) {
      alert("Select at least one unsold receipt.");
      return;
    }
    pendingSaleReceipts = list;
    pendingManualCreate = false;
    pendingManualMeta = null;
    if (els.saleReceiptBody) {
      els.saleReceiptBody.innerHTML = "";
      list.forEach(function (row) {
        const tr = document.createElement("tr");
        tr.innerHTML =
          "<td>" + escapeHtml(row.receipt_no) + "</td>" +
          "<td>" + escapeHtml(row.stationerynumber) + "</td>" +
          "<td>" + escapeHtml(displayDate(row.receipt_date)) + "</td>" +
          "<td class=\"text-end\">" + escapeHtml(row.amount) + "</td>";
        els.saleReceiptBody.appendChild(tr);
      });
      if (els.saleAmount) els.saleAmount.value = "0";
      resetPaymentLines(0);
    }
    if (els.saleDate) {
      els.saleDate.value = window.ECOURT_DEFAULT_DATE || new Date().toISOString().slice(0, 10);
    }
    saleModal?.show();
  }

  function getUnsoldReceiptsFromGroup(group) {
    return (group.receipts || []).filter(function (row) {
      return row.sale_status !== "Sold";
    });
  }

  function hideSaleModalThen(done) {
    const el = els.saleModalEl;
    if (!saleModal || !el) {
      return Promise.resolve().then(done);
    }
    return new Promise(function (resolve) {
      const onHidden = function () {
        el.removeEventListener("hidden.bs.modal", onHidden);
        Promise.resolve()
          .then(done)
          .then(resolve, resolve);
      };
      el.addEventListener("hidden.bs.modal", onHidden);
      saleModal.hide();
    });
  }

  let pendingFocusAfterSale = null;

  function receiptKey(value) {
    return String(value || "").trim().toUpperCase();
  }

  function listVisualReceipts(data) {
    const prepared = prepareTreeGroups(((data || lastTreeData || {}).groups) || []);
    const items = [];
    prepared.forEach(function (item) {
      const stationery = ((item.group && item.group.stationerynumber) || "").trim();
      (item.receipts || []).forEach(function (row) {
        const receiptNo = receiptKey(row.receipt_no);
        if (!receiptNo) return;
        items.push({
          receipt_no: receiptNo,
          stationery: (row.stationerynumber || stationery || "").trim(),
          sold: row.sale_status === "Sold",
        });
      });
    });
    if (items.length) return items;
    return Array.from(els.gridBody?.querySelectorAll("tr.ecourt-tree-child") || [])
      .map(function (tr) {
        return {
          receipt_no: receiptKey(tr.dataset.receiptNo),
          stationery: (tr.dataset.stationery || "").trim(),
          sold: tr.classList.contains("ecourt-row-sold"),
        };
      })
      .filter(function (item) {
        return !!item.receipt_no;
      });
  }

  function findNeighborUnsold(soldReceipts) {
    const soldSet = {};
    (soldReceipts || []).forEach(function (row) {
      const key = receiptKey(row && row.receipt_no);
      if (key) soldSet[key] = true;
    });
    const items = listVisualReceipts(lastTreeData);
    let firstSold = -1;
    let lastSold = -1;
    items.forEach(function (item, index) {
      if (!soldSet[item.receipt_no]) return;
      lastSold = index;
      if (firstSold < 0) firstSold = index;
    });
    function isUnsoldKeep(item) {
      return item && !item.sold && !soldSet[item.receipt_no];
    }
    if (lastSold >= 0) {
      for (let i = lastSold + 1; i < items.length; i++) {
        if (isUnsoldKeep(items[i])) return items[i];
      }
    }
    if (firstSold > 0) {
      for (let i = firstSold - 1; i >= 0; i--) {
        if (isUnsoldKeep(items[i])) return items[i];
      }
    }
    return null;
  }

  function expandStationeryGroup(stationery) {
    if (!stationery || !els.gridBody) return null;
    const parent = els.gridBody.querySelector(
      'tr.ecourt-tree-parent[data-stationery="' + String(stationery).replace(/"/g, "") + '"]'
    );
    if (!parent) return null;
    const gi = parent.dataset.group;
    els.gridBody.querySelectorAll(".ecourt-tree-child-" + gi).forEach(function (tr) {
      tr.classList.remove("d-none");
    });
    const toggle = parent.querySelector(".ecourt-tree-toggle");
    if (toggle) toggle.textContent = "−";
    return parent;
  }

  function findChildRowByReceipt(receiptNo) {
    const key = String(receiptNo || "").trim().toUpperCase();
    if (!key || !els.gridBody) return null;
    const rows = els.gridBody.querySelectorAll("tr.ecourt-tree-child");
    for (let i = 0; i < rows.length; i++) {
      if ((rows[i].dataset.receiptNo || "").trim().toUpperCase() === key) return rows[i];
    }
    return null;
  }

  function scrollGridRowIntoView(row) {
    const wrap = els.gridBody?.closest(".ecourt-grid-wrap");
    if (!row) return;
    if (!wrap) return;
    const wrapRect = wrap.getBoundingClientRect();
    const rowRect = row.getBoundingClientRect();
    const thead = wrap.querySelector("thead");
    const headerH = thead ? thead.offsetHeight : 0;
    const mid = headerH + Math.max(40, (wrap.clientHeight - headerH - rowRect.height) / 2);
    wrap.scrollTop += rowRect.top - wrapRect.top - mid;
  }

  function focusGridReceipt(target) {
    if (!target || !target.receipt_no || !els.gridBody) return false;
    expandStationeryGroup(target.stationery);
    const row = findChildRowByReceipt(target.receipt_no);
    if (!row) return false;
    row.classList.remove("d-none");
    els.gridBody.querySelectorAll(".ecourt-row-keep-focus").forEach(function (el) {
      el.classList.remove("ecourt-row-keep-focus");
    });
    row.classList.add("ecourt-row-keep-focus");
    scrollGridRowIntoView(row);
    const sellBtn = row.querySelector(".ecourt-sell-one-btn");
    if (sellBtn) sellBtn.focus({ preventScroll: true });
    pendingFocusAfterSale = null;
    return true;
  }

  function restoreGridAfterSale(options) {
    options = options || {};
    const wrap = els.gridBody?.closest(".ecourt-grid-wrap");
    const apply = function () {
      const target = options.focusAfterSale || pendingFocusAfterSale;
      if (target && focusGridReceipt(target)) {
        if (options.restorePageScroll) {
          window.scrollTo(options.restorePageScroll.x, options.restorePageScroll.y);
        }
        return;
      }
      const sold = options.soldReceipts || [];
      const stationery =
        (sold[0] && sold[0].stationerynumber) || (options.expandStationery || "");
      const parent = expandStationeryGroup(stationery);
      const scroll = options.restoreScroll;
      if (wrap && scroll) {
        wrap.scrollTop = scroll.wrapTop || 0;
        wrap.scrollLeft = scroll.wrapLeft || 0;
      }
      if (parent) scrollGridRowIntoView(parent);
      if (options.restorePageScroll) {
        window.scrollTo(options.restorePageScroll.x, options.restorePageScroll.y);
      }
    };
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        apply();
        window.setTimeout(apply, 60);
      });
    });
  }

  function getCheckedReceipts() {
    const selected = [];
    els.gridBody?.querySelectorAll(".ecourt-receipt-select:checked").forEach(function (input) {
      selected.push({
        receipt_no: input.dataset.receiptNo || "",
        stationerynumber: input.dataset.stationery || "",
        receipt_date: input.dataset.receiptDate || "",
        amount: input.dataset.amount || "",
      });
    });
    return selected;
  }

  async function submitSaleForm(e) {
    e.preventDefault();
    const sale = parseAmount(els.saleAmount?.value);
    if (sale <= 1) {
      alert("Sale amount must be greater than 1.");
      return;
    }
    const paymentError = validatePaymentLines();
    if (paymentError) {
      alert(paymentError);
      return;
    }
    if (!pendingSaleReceipts.length) {
      alert("No receipts selected.");
      return;
    }
    const body = new FormData(els.saleForm);
    pendingSaleReceipts.forEach(function (row) {
      body.append("ReceiptNo[]", row.receipt_no);
    });
    if (pendingManualCreate && pendingManualMeta) {
      body.set("ManualCreate", "1");
      body.set("ReceiptBuyAmount", String(pendingManualMeta.buy_amount || ""));
      body.set("ManualStationeryNumber", String(pendingManualMeta.stationerynumber || ""));
      body.set("ManualReceiptDate", String(pendingManualMeta.receipt_date || ""));
      if (pendingManualMeta.remarks) {
        body.set("ManualRemarks", String(pendingManualMeta.remarks));
      }
    }
    if (els.confirmSaleBtn) els.confirmSaleBtn.disabled = true;
    try {
      const res = await fetch(window.ECOURT_URLS.sell, {
        method: "POST",
        body: body,
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Sale failed.");
      const soldReceipts = pendingSaleReceipts.slice();
      const neighbor = findNeighborUnsold(soldReceipts);
      pendingFocusAfterSale = neighbor;
      const wrap = els.gridBody?.closest(".ecourt-grid-wrap");
      const scrollState = {
        wrapTop: wrap ? wrap.scrollTop : 0,
        wrapLeft: wrap ? wrap.scrollLeft : 0,
      };
      const pageScroll = { x: window.scrollX, y: window.scrollY };
      pendingSaleReceipts = [];
      pendingManualCreate = false;
      pendingManualMeta = null;
      els.saleForm?.reset();
      await hideSaleModalThen(function () {
        return loadImportTree(null, {
          expandStationery:
            (neighbor && neighbor.stationery) ||
            (soldReceipts[0] && soldReceipts[0].stationerynumber) ||
            "",
          focusAfterSale: neighbor,
          soldReceipts: soldReceipts,
          restoreScroll: scrollState,
          restorePageScroll: pageScroll,
        });
      });
      if (neighbor) focusGridReceipt(neighbor);
      window.scrollTo(pageScroll.x, pageScroll.y);
    } catch (err) {
      alert(err.message || String(err));
    } finally {
      if (els.confirmSaleBtn) els.confirmSaleBtn.disabled = false;
    }
  }

  function setSummary(data) {
    if (!els.summaryBanner) return;
    if (!data || !data.summary_status) {
      els.summaryBanner.classList.add("d-none");
      return;
    }
    const status = data.summary_status;
    els.summaryBanner.classList.remove("d-none", "status-sold", "status-not-sold", "status-partial");
    if (status === "Sold") els.summaryBanner.classList.add("status-sold");
    else if (status === "Not Sold") els.summaryBanner.classList.add("status-not-sold");
    else els.summaryBanner.classList.add("status-partial");
    els.summaryBanner.textContent =
      "Stationery " + data.stationery_no + ": " + status +
      " (" + data.sold_count + " sold / " + data.total_receipts + " total)";
  }

  function isManualReceiptRow(row) {
    const status = String((row && row.receipt_status) || "").trim().toLowerCase();
    return status === "manual entry" || status === "manual";
  }

  function renderImportTree(data, options) {
    options = options || {};
    lastTreeOptions = options;
    const prepared = prepareTreeGroups(data.groups || []);
    if (!els.gridBody) return;

    els.gridBody.innerHTML = "";
    if (!prepared.length) {
      if (els.gridEmpty) els.gridEmpty.classList.remove("d-none");
      if (els.gridCount) els.gridCount.textContent = "0 records";
      updateGridSortHeaders();
      return;
    }

    if (els.gridEmpty) els.gridEmpty.classList.add("d-none");
    if (els.gridCount) {
      const visibleReceipts = prepared.reduce(function (sum, item) {
        return sum + (item.receipts || []).length;
      }, 0);
      els.gridCount.textContent =
        visibleReceipts + " receipts in " + prepared.length + " stationery" +
        (hasActiveGridFilters() ? " (filtered)" : "");
    }

    const expandStationery = (options.expandStationery || "").trim();
    const expandAll = !!options.expandAll;

    prepared.forEach(function (item, gi) {
      const group = item.group;
      const receipts = item.receipts || [];
      const expanded = expandAll || (expandStationery && group.stationerynumber === expandStationery);
      const summary = group.summary_status || "";
      const isSold = summary === "Sold";
      const isPartial = summary === "Partially Sold";
      const unsoldCount = group.not_sold_count || 0;
      let badgeClass = "ecourt-badge-not-sold";
      if (isSold) badgeClass = "ecourt-badge-sold";
      else if (isPartial) badgeClass = "bg-warning text-dark";

      const parentTr = document.createElement("tr");
      parentTr.className = "ecourt-tree-parent";
      parentTr.dataset.group = String(gi);
      parentTr.dataset.stationery = group.stationerynumber || "";

      let parentCheckbox = "";
      if (isSold || isPartial) {
        parentCheckbox =
          "<input type=\"checkbox\" class=\"form-check-input ecourt-stationery-select\" checked disabled " +
          "title=\"Stationery " + (isPartial ? "partially sold" : "fully sold") + "\">";
      } else {
        parentCheckbox =
          "<input type=\"checkbox\" class=\"form-check-input ecourt-stationery-select\" disabled " +
          "title=\"Use Sell All for this stationery\">";
      }

      const sellAllBtn = unsoldCount > 0
        ? "<button type=\"button\" class=\"btn btn-success btn-sm ecourt-sell-all-btn\" " +
          "data-stationery=\"" + escapeHtml(group.stationerynumber || "") + "\">" +
          "Sell All (" + unsoldCount + ")</button>"
        : "";
      const editParentBtn =
        "<button type=\"button\" class=\"btn btn-warning btn-sm ecourt-edit-btn\" " +
        "data-stationery=\"" + escapeHtml(group.stationerynumber || "") + "\" " +
        "title=\"Edit Manual Entry\">Edit</button>";
      const unsellParentBtn = (isSold || isPartial)
        ? "<button type=\"button\" class=\"btn btn-outline-warning btn-sm ecourt-unsell-btn\" " +
          "data-stationery=\"" + escapeHtml(group.stationerynumber || "") + "\" " +
          "title=\"Roll back sold receipts for this stationery\">Unsold</button>"
        : "";
      const deleteParentBtn = summary === "Not Sold"
        ? "<button type=\"button\" class=\"btn btn-outline-danger btn-sm ecourt-delete-stationery-btn\" " +
          "data-stationery=\"" + escapeHtml(group.stationerynumber || "") + "\" " +
          "title=\"Delete this Not Sold stationery\">Delete</button>"
        : "<button type=\"button\" class=\"btn btn-outline-secondary btn-sm\" disabled " +
          "title=\"Delete only for Not Sold\">Delete</button>";

      const isManualGroup = (receipts || []).some(function (row) {
        return isManualReceiptRow(row);
      });
      parentTr.className =
        "ecourt-tree-parent" +
        (isManualGroup ? " ecourt-row-manual" : " ecourt-row-imported") +
        (isSold ? " ecourt-row-sold" : "");

      let buyValueCell = "";
      let sellValueCell = "";
      let soldRemainingCell = "";
      let parentDateCell = escapeHtml(displayDate(groupReceiptDate(group)));
      let parentSoldDateCell = "";
      // Fully sold → account on parent row; partial → only inside + children.
      let parentAccountCell = "";
      if (isSold) {
        buyValueCell = escapeHtml(group.total_buy_value || "");
        sellValueCell = escapeHtml(group.total_sell_value || "");
        parentSoldDateCell = escapeHtml(displayDate(groupSellDate(group)));
        parentAccountCell = escapeHtml(group.account_number || "");
      } else if (isPartial) {
        buyValueCell = escapeHtml(group.sold_buy_value || group.total_buy_value || "");
        sellValueCell = escapeHtml(group.sold_sell_value || "");
        soldRemainingCell = escapeHtml(groupSoldRemainingText(group));
        parentSoldDateCell = escapeHtml(displayDate(groupSellDate(group)));
      } else {
        // Not Sold — show import buy value (sell stays blank until sold).
        buyValueCell = escapeHtml(group.total_buy_value || "");
      }

      parentTr.innerHTML =
        "<td class=\"text-center\">" + parentCheckbox + "</td>" +
        "<td><button type=\"button\" class=\"btn btn-link btn-sm p-0 ecourt-tree-toggle\" data-group=\"" + gi + "\">" +
        (expanded ? "−" : "+") + "</button></td>" +
        "<td><strong>" + escapeHtml(group.stationerynumber) + "</strong> " +
        "<span class=\"text-muted\">(" + group.total_receipts + " receipts)</span></td>" +
        "<td>" + parentDateCell + "</td>" +
        "<td>" + parentSoldDateCell + "</td>" +
        "<td class=\"text-end\"><strong>" + buyValueCell + "</strong></td>" +
        "<td class=\"text-end\"><strong>" + sellValueCell + "</strong></td>" +
        "<td class=\"text-center\">" + soldRemainingCell + "</td>" +
        "<td>" + parentAccountCell + "</td>" +
        "<td><span class=\"badge " + badgeClass + "\">" + escapeHtml(summary) + "</span></td>" +
        "<td class=\"text-end ecourt-actions-cell\">" +
        (sellAllBtn ? sellAllBtn + " " : "") +
        editParentBtn + " " +
        (unsellParentBtn ? unsellParentBtn + " " : "") +
        deleteParentBtn +
        "</td>";
      els.gridBody.appendChild(parentTr);

      receipts.forEach(function (row) {
        const childTr = document.createElement("tr");
        const sold = row.sale_status === "Sold";
        const manualRow = isManualReceiptRow(row);
        childTr.className =
          "ecourt-tree-child ecourt-tree-child-" + gi +
          (expanded ? "" : " d-none") +
          (manualRow ? " ecourt-row-manual" : " ecourt-row-imported") +
          (sold ? " ecourt-row-sold" : "");
        childTr.dataset.receiptNo = row.receipt_no || "";
        childTr.dataset.stationery = row.stationerynumber || group.stationerynumber || "";

        let selectCell = "<td></td>";
        let actionCell = "";
        const editChildBtn =
          "<button type=\"button\" class=\"btn btn-warning btn-sm ecourt-edit-btn\" " +
          "data-receipt-no=\"" + escapeHtml(row.receipt_no) + "\" " +
          "data-stationery=\"" + escapeHtml(row.stationerynumber || group.stationerynumber || "") + "\" " +
          "data-receipt-date=\"" + escapeHtml(row.receipt_date || "") + "\" " +
          "data-amount=\"" + escapeHtml(row.amount || "") + "\" " +
          "data-sale-status=\"" + escapeHtml(row.sale_status || "") + "\" " +
          "title=\"Edit Manual Entry\">Edit</button>";
        if (!sold) {
          selectCell =
            "<td class=\"text-center\">" +
            "<input type=\"checkbox\" class=\"form-check-input ecourt-receipt-select\" " +
            "data-receipt-no=\"" + escapeHtml(row.receipt_no) + "\" " +
            "data-stationery=\"" + escapeHtml(row.stationerynumber || group.stationerynumber || "") + "\" " +
            "data-receipt-date=\"" + escapeHtml(row.receipt_date) + "\" " +
            "data-amount=\"" + escapeHtml(row.amount) + "\">" +
            "</td>";
          actionCell =
            "<td class=\"text-end ecourt-actions-cell\">" +
            "<button type=\"button\" class=\"btn btn-outline-success btn-sm ecourt-sell-one-btn\" " +
            "data-receipt-no=\"" + escapeHtml(row.receipt_no) + "\" " +
            "data-stationery=\"" + escapeHtml(row.stationerynumber || group.stationerynumber || "") + "\" " +
            "data-receipt-date=\"" + escapeHtml(row.receipt_date) + "\" " +
            "data-amount=\"" + escapeHtml(row.amount) + "\">Sell</button> " +
            editChildBtn +
            "</td>";
        } else {
          selectCell =
            "<td class=\"text-center\">" +
            "<input type=\"checkbox\" class=\"form-check-input\" checked disabled title=\"Already sold\">" +
            "</td>";
          actionCell =
            "<td class=\"text-end ecourt-actions-cell\">" +
            editChildBtn + " " +
            "<button type=\"button\" class=\"btn btn-outline-warning btn-sm ecourt-unsell-btn\" " +
            "data-receipt-no=\"" + escapeHtml(row.receipt_no) + "\" " +
            "title=\"Roll back this sold receipt\">Unsold</button></td>";
        }

        const childAccountCell = sold
          ? escapeHtml(row.account_number || "")
          : "";
        const childSoldDate = sold
          ? escapeHtml(displayDate(row.transaction_date || row.display_date || ""))
          : "";

        childTr.innerHTML =
          selectCell +
          "<td></td>" +
          "<td>" + escapeHtml(row.receipt_no) + "</td>" +
          "<td>" + escapeHtml(displayDate(row.receipt_date || "")) + "</td>" +
          "<td>" + childSoldDate + "</td>" +
          "<td class=\"text-end\">" + escapeHtml(row.amount) + "</td>" +
          "<td></td>" +
          "<td></td>" +
          "<td>" + childAccountCell + "</td>" +
          "<td><span class=\"badge " + (sold ? "ecourt-badge-sold" : "ecourt-badge-not-sold") + "\">" +
          escapeHtml(row.sale_status) + "</span></td>" +
          actionCell;
        els.gridBody.appendChild(childTr);
      });

      if (expandStationery && group.stationerynumber === expandStationery) {
        setSummary({
          stationery_no: group.stationerynumber,
          summary_status: group.summary_status,
          sold_count: group.sold_count,
          total_receipts: group.total_receipts,
        });
        if (!options.focusAfterSale && !options.restoreScroll && !pendingFocusAfterSale) {
          parentTr.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }
    });
    updateSellSelectedButton();
    updateGridSortHeaders();
    const focusTarget = options.focusAfterSale || pendingFocusAfterSale;
    if (focusTarget || options.restoreScroll || options.soldReceipts) {
      restoreGridAfterSale(Object.assign({}, options, { focusAfterSale: focusTarget }));
    }
  }

  function toggleTreeGroup(groupIndex) {
    const children = els.gridBody?.querySelectorAll(".ecourt-tree-child-" + groupIndex);
    const btn = els.gridBody?.querySelector('.ecourt-tree-toggle[data-group="' + groupIndex + '"]');
    if (!children || !children.length || !btn) return;
    const willExpand = children[0].classList.contains("d-none");
    children.forEach(function (tr) {
      tr.classList.toggle("d-none", !willExpand);
    });
    btn.textContent = willExpand ? "−" : "+";
  }

  let lastTreeData = null;
  let lastTreeOptions = {};
  let gridSortKey = "";
  let gridSortDir = "asc";
  const gridFilters = {
    name: "",
    date: "",
    sold_date: "",
    buy: "",
    sell: "",
    sold_remaining: "",
    account: "",
    sale_status: "",
  };

  function groupSellDate(group) {
    if (!group) return "";
    return (
      group.transaction_date ||
      group.sell_date ||
      ""
    );
  }

  function groupReceiptDate(group) {
    if (!group) return "";
    let best = "";
    (group.receipts || []).forEach(function (row) {
      const value = (row.receipt_date || "").trim();
      if (value && (!best || value > best)) best = value;
    });
    return best;
  }

  function receiptDisplayDate(row) {
    if (!row) return "";
    return row.receipt_date || row.display_date || "";
  }

  function receiptSoldDate(row) {
    if (!row || row.sale_status !== "Sold") return "";
    return row.transaction_date || "";
  }

  function groupBuyValue(group) {
    if (group.summary_status === "Sold") return group.total_buy_value || "";
    if (group.summary_status === "Partially Sold") {
      return group.sold_buy_value || group.total_buy_value || "";
    }
    // Not Sold
    return group.total_buy_value || "";
    return "";
  }

  function groupSellValue(group) {
    if (group.summary_status === "Sold") return group.total_sell_value || "";
    if (group.summary_status === "Partially Sold") return group.sold_sell_value || "";
    return "";
  }

  function groupSoldRemainingText(group) {
    const unsold = group.not_sold_count || 0;
    if (group.summary_status === "Partially Sold") {
      return (
        String(group.sold_count || 0) +
        " / " +
        String(group.remaining_receipts != null ? group.remaining_receipts : unsold)
      );
    }
    if (group.summary_status === "Sold") {
      return String(group.sold_count || group.total_receipts || 0) + " / 0";
    }
    return "0 / " + String(unsold || group.total_receipts || 0);
  }

  function groupSortDate(group) {
    return groupReceiptDate(group) || groupSellDate(group) || "";
  }

  function matchesFilter(haystack, needle) {
    if (!needle) return true;
    return String(haystack == null ? "" : haystack)
      .toLowerCase()
      .indexOf(String(needle).toLowerCase()) !== -1;
  }

  function hasActiveGridFilters() {
    return Object.keys(gridFilters).some(function (key) {
      return !!(gridFilters[key] || "").trim();
    });
  }

  function parentMatchesFilters(group) {
    const dateText = groupReceiptDate(group);
    const soldDateText = groupSellDate(group);
    return (
      matchesFilter(group.stationerynumber, gridFilters.name) &&
      matchesFilter(displayDate(dateText) + " " + dateText, gridFilters.date) &&
      matchesFilter(displayDate(soldDateText) + " " + soldDateText, gridFilters.sold_date) &&
      matchesFilter(groupBuyValue(group), gridFilters.buy) &&
      matchesFilter(groupSellValue(group), gridFilters.sell) &&
      matchesFilter(groupSoldRemainingText(group), gridFilters.sold_remaining) &&
      matchesFilter(group.account_number || "", gridFilters.account) &&
      matchesFilter(group.summary_status, gridFilters.sale_status)
    );
  }

  function childMatchesFilters(row) {
    const dateText = receiptDisplayDate(row);
    const soldDateText = receiptSoldDate(row);
    return (
      matchesFilter(row.receipt_no, gridFilters.name) &&
      matchesFilter(displayDate(dateText) + " " + dateText, gridFilters.date) &&
      matchesFilter(displayDate(soldDateText) + " " + soldDateText, gridFilters.sold_date) &&
      matchesFilter(row.amount, gridFilters.buy) &&
      matchesFilter("", gridFilters.sell) &&
      matchesFilter("", gridFilters.sold_remaining) &&
      matchesFilter(row.account_number || "", gridFilters.account) &&
      matchesFilter(row.sale_status, gridFilters.sale_status)
    );
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
    const sa = String(a).toLowerCase();
    const sb = String(b).toLowerCase();
    if (sa < sb) return dir === "asc" ? -1 : 1;
    if (sa > sb) return dir === "asc" ? 1 : -1;
    return 0;
  }

  function groupSortValue(group, key) {
    if (key === "name") return (group.stationerynumber || "").toLowerCase();
    if (key === "date") return groupReceiptDate(group) || "";
    if (key === "sold_date") return groupSellDate(group) || "";
    if (key === "buy") return parseFloat(groupBuyValue(group)) || 0;
    if (key === "sell") return parseFloat(groupSellValue(group)) || 0;
    if (key === "sold_remaining") return Number(group.sold_count || 0);
    if (key === "account") return (group.account_number || "").toLowerCase();
    if (key === "sale_status") return (group.summary_status || "").toLowerCase();
    return "";
  }

  function childSortValue(row, key) {
    if (key === "name") return (row.receipt_no || "").toLowerCase();
    if (key === "date") return receiptDisplayDate(row) || "";
    if (key === "sold_date") return receiptSoldDate(row) || "";
    if (key === "buy") return parseFloat(row.amount) || 0;
    if (key === "sell") return 0;
    if (key === "sold_remaining") return row.sale_status === "Sold" ? 1 : 0;
    if (key === "account") return (row.account_number || "").toLowerCase();
    if (key === "sale_status") return (row.sale_status || "").toLowerCase();
    return "";
  }

  function prepareTreeGroups(groups) {
    const prepared = [];
    (groups || []).forEach(function (group) {
      const allReceipts = Array.isArray(group.receipts) ? group.receipts.slice() : [];
      let receipts = allReceipts;
      if (hasActiveGridFilters()) {
        const parentOk = parentMatchesFilters(group);
        const matchingChildren = allReceipts.filter(childMatchesFilters);
        if (!parentOk && !matchingChildren.length) return;
        receipts = parentOk ? allReceipts : matchingChildren;
      }
      if (gridSortKey) {
        receipts = receipts.slice().sort(function (a, b) {
          return compareSortValues(
            childSortValue(a, gridSortKey),
            childSortValue(b, gridSortKey),
            gridSortDir
          );
        });
      }
      prepared.push({ group: group, receipts: receipts });
    });

    if (gridSortKey) {
      prepared.sort(function (a, b) {
        return compareSortValues(
          groupSortValue(a.group, gridSortKey),
          groupSortValue(b.group, gridSortKey),
          gridSortDir
        );
      });
    } else {
      // Default: Not Sold (to sell) on top, then date ascending. Column sort/filter unchanged.
      prepared.sort(function (a, b) {
        const rankA = defaultSellPriority(a.group.summary_status);
        const rankB = defaultSellPriority(b.group.summary_status);
        if (rankA !== rankB) return rankA - rankB;
        return compareSortValues(
          groupReceiptDate(a.group) || "",
          groupReceiptDate(b.group) || "",
          "asc"
        );
      });
    }
    return prepared;
  }

  function defaultSellPriority(status) {
    if (status === "Not Sold") return 0;
    if (status === "Partially Sold") return 1;
    return 2;
  }

  function updateGridSortHeaders() {
    document.querySelectorAll("#ecourtGrid thead th.ecourt-sortable").forEach(function (th) {
      const key = th.dataset.sortKey;
      const icon = th.querySelector(".ecourt-sort-icon");
      const active = key === gridSortKey;
      th.classList.toggle("ecourt-sorted", active);
      th.setAttribute(
        "aria-sort",
        active ? (gridSortDir === "asc" ? "ascending" : "descending") : "none"
      );
      if (icon) {
        icon.textContent = active ? (gridSortDir === "asc" ? " ▲" : " ▼") : "";
      }
    });
  }

  function refreshImportTree() {
    if (!lastTreeData) return;
    renderImportTree(lastTreeData, lastTreeOptions || {});
  }

  function onGridSortHeader(sortKey) {
    if (!sortKey) return;
    if (gridSortKey === sortKey) {
      gridSortDir = gridSortDir === "asc" ? "desc" : "asc";
    } else {
      gridSortKey = sortKey;
      gridSortDir = "asc";
    }
    refreshImportTree();
  }

  function readGridFiltersFromDom() {
    document.querySelectorAll("#ecourtGrid .ecourt-col-filter").forEach(function (input) {
      const key = input.dataset.filterKey;
      if (!key) return;
      gridFilters[key] = (input.value || "").trim();
    });
  }

  function findGroupByStationery(stationery) {
    const needle = (stationery || "").trim();
    return (lastTreeData?.groups || []).find(function (group) {
      return (group.stationerynumber || "") === needle;
    }) || null;
  }

  async function readJsonResponse(res, fallbackError) {
    const text = await res.text();
    try {
      return text ? JSON.parse(text) : {};
    } catch (_err) {
      throw new Error(
        fallbackError ||
          ("Server returned a non-JSON response (HTTP " + res.status + ").")
      );
    }
  }

  async function loadImportTree(importId, options) {
    const params = new URLSearchParams();
    if (importId) params.set("import_id", String(importId));
    try {
      const res = await fetch(window.ECOURT_URLS.importLines + "?" + params.toString(), {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await readJsonResponse(res, "Could not load imported data.");
      if (!res.ok || !data.ok) throw new Error(data.error || "Could not load imported data.");
      lastTreeData = data;
      renderImportTree(data, options || {});
      loadActivitySummary();
      return data;
    } catch (err) {
      alert(err.message || String(err));
      return null;
    }
  }

  function formatMoney(value) {
    const num = parseFloat(value || "0");
    if (Number.isNaN(num)) return "0.00";
    return num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function renderActivitySummary(summary) {
    if (!els.periodGrid) return;
    summary = summary || {};
    const cards = [
      { key: "fee_sale_amount", label: "Fee Sale Amount", className: "is-sale" },
      { key: "payment_received_amount", label: "Payment Received Amount", className: "is-payment" },
      { key: "received_cash", label: "Received in Cash", className: "is-cash" },
      { key: "received_non_cash", label: "Received Other Than Cash", className: "is-noncash" },
      { key: "shcil_ecourt_deposit", label: "Deposited in SHCILECourt", className: "is-shcil" },
    ];
    els.periodGrid.innerHTML = "";
    cards.forEach(function (cardDef) {
      const card = document.createElement("div");
      card.className = "ecourt-period-card " + cardDef.className;
      card.innerHTML =
        "<div class=\"period-card-label\">" + escapeHtml(cardDef.label) + "</div>" +
        "<div class=\"period-card-value\">₹ " + escapeHtml(formatMoney(summary[cardDef.key] || "0")) + "</div>";
      els.periodGrid.appendChild(card);
    });
    if (els.periodLabel) {
      const count = summary.sale_count != null ? summary.sale_count : 0;
      els.periodLabel.textContent = count + " sale posting(s)";
    }
  }

  async function loadActivitySummary() {
    if (!window.ECOURT_URLS.summary) return;
    if (els.periodLabel) els.periodLabel.textContent = "Loading...";
    try {
      const res = await fetch(window.ECOURT_URLS.summary, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.error || "Unable to load summary.");
      }
      renderActivitySummary(data.summary || {});
    } catch (err) {
      if (els.periodLabel) els.periodLabel.textContent = err.message || "Load failed";
      renderActivitySummary({});
    }
  }

  function previewInput(name, value, extraClass, disabled) {
    const dis = disabled ? " disabled readonly" : "";
    return (
      "<input type=\"text\" class=\"form-control form-control-sm ecourt-preview-input " + (extraClass || "") + "\" " +
      "data-field=\"" + name + "\" value=\"" + escapeHtml(value) + "\"" + dis + ">"
    );
  }

  function rowApplyPanel() {
    return (
      "<div class=\"ecourt-apply-next20 d-none mt-1\">" +
      "<label class=\"ecourt-apply-next20-label mb-1\">" +
      "<input type=\"checkbox\" class=\"form-check-input ecourt-apply-next20-check me-1\">" +
      "Apply next 20 for this amount?" +
      "</label>" +
      "<button type=\"button\" class=\"btn btn-outline-primary btn-sm ecourt-apply-next20-btn\">Apply</button>" +
      "</div>"
    );
  }

  function toggleRowApplyPanel(tr, index) {
    const input = tr?.querySelector('[data-field="stationerynumber"]');
    const panel = tr?.querySelector(".ecourt-apply-next20");
    if (!input || !panel) return;
    const show = isBlockStartRow(index) && !isHighAmountRow(previewRows[index]) && (input.value || "").trim();
    panel.classList.toggle("d-none", !show);
  }

  function applyNext20SameAmount(startIndex) {
    if (!isBlockStartRow(startIndex)) {
      alert("Enter stationery on row 1, 21, 41… (every 20th small-amount row) and apply from there.");
      return;
    }

    syncPreviewRowsFromDom();
    if (!previewRows.length) return;

    const startTr = els.previewBody?.querySelector('tr[data-index="' + startIndex + '"]');
    const checkbox = startTr?.querySelector(".ecourt-apply-next20-check");
    if (!checkbox?.checked) {
      alert("Tick 'Apply next 20 for this amount?' first.");
      return;
    }

    const startRow = previewRows[startIndex];
    if (!startRow || isHighAmountRow(startRow)) return;

    const amount = normalizeAmount(startRow.amount);
    const stationery = (startRow.stationerynumber || "").trim();
    if (!stationery) {
      alert("Enter stationery number in this row.");
      return;
    }
    if (!amount) {
      alert("Row amount is required.");
      return;
    }

    let applied = 0;
    for (let i = startIndex; i < previewRows.length && applied < BLOCK_SIZE; i++) {
      if (previewRows[i].already_imported) continue;
      if (isHighAmountRow(previewRows[i])) break;
      if (normalizeAmount(previewRows[i].amount) !== amount) break;
      previewRows[i].stationerynumber = stationery;
      applied++;
    }

    refreshDuplicatePreviewRows();
    renderPreviewGrid();
    nextBlockRowIndex = startIndex + BLOCK_SIZE;
    if (els.uploadStatus) {
      els.uploadStatus.textContent =
        "Applied stationery " + stationery + " to " + applied + " row(s) from row " + (startIndex + 1) + ".";
    }
    if (nextBlockRowIndex < previewRows.length && !isHighAmountRow(previewRows[nextBlockRowIndex])) {
      scrollToBlockRow(nextBlockRowIndex);
    }
  }

  function renderPreviewGrid() {
    if (!els.previewBody) return;
    refreshDuplicatePreviewRows();
    els.previewBody.innerHTML = "";
    previewRows.forEach(function (row, index) {
      const tr = document.createElement("tr");
      tr.dataset.index = String(index);
      const imported = !!row.already_imported || isReceiptAlreadyImported(row.receipt_no);
      const highAmount = isHighAmountRow(row);
      if (highAmount) {
        row.high_amount = true;
        row.auto_stationery = true;
      }
      if (imported) {
        row.already_imported = true;
        row.stationerynumber = getImportedStationery(row.receipt_no) || row.stationerynumber || "";
        row.receipt_status = "Already imported";
      }
      if (imported) {
        tr.classList.add("ecourt-preview-row-imported");
      } else if (isBlockStartRow(index)) {
        tr.classList.add("ecourt-block-start-row");
      }

      const stationeryDisabled = imported || highAmount;
      const applyHtml = !imported && isBlockStartRow(index) ? rowApplyPanel() : "";
      const statusValue = imported ? "Already imported" : (row.receipt_status || "");
      const stationeryCell =
        "<td class=\"ecourt-stationery-cell\">" +
        previewInput("stationerynumber", row.stationerynumber, "", stationeryDisabled) +
        applyHtml +
        "</td>";

      const deleteCell = imported
        ? "<td class=\"text-center text-muted small\">—</td>"
        : "<td class=\"text-center\">" +
          "<button type=\"button\" class=\"btn btn-link btn-sm text-danger p-0 ecourt-delete-row\" title=\"Remove row\">" +
          "<i class=\"bi bi-trash\"></i></button></td>";

      tr.innerHTML =
        "<td class=\"text-muted\">" + (index + 1) + "</td>" +
        "<td>" + previewInput("receipt_no", row.receipt_no, "", imported) + "</td>" +
        "<td>" + previewInput("receipt_date", row.receipt_date, "", imported) + "</td>" +
        "<td>" + previewInput("amount", row.amount, "text-end", imported) + "</td>" +
        "<td>" + previewInput("payment_mode", row.payment_mode, "", imported) + "</td>" +
        "<td>" + previewInput("receipt_status", statusValue, "", true) + "</td>" +
        "<td>" + previewInput("remarks", row.remarks, "", imported) + "</td>" +
        stationeryCell +
        deleteCell;
      els.previewBody.appendChild(tr);

      if (!imported && isBlockStartRow(index)) {
        toggleRowApplyPanel(tr, index);
      }
    });
    updatePreviewCountText();
    if (previewRows.length) {
      els.previewPanel?.classList.remove("d-none");
    } else {
      els.previewPanel?.classList.add("d-none");
    }
  }

  function collectPreviewRows() {
    syncPreviewRowsFromDom();
    return validateForImport(previewRows).importRows;
  }

  function setPreviewMeta(data) {
    previewMeta = {
      file_name: data.file_name || "",
      report_from: data.report_from || "",
      report_to: data.report_to || "",
      state_name: data.state_name || "",
      total_amount: data.total_amount || "",
      record_count: data.record_count || 0,
      pdf_record_count: data.pdf_record_count || data.record_count || 0,
    };
    if (els.previewMeta) {
      const parts = [];
      if (data.file_name) parts.push(data.file_name);
      if (data.report_from || data.report_to) {
        parts.push((data.report_from || "—") + " to " + (data.report_to || "—"));
      }
      if (data.state_name) parts.push(data.state_name);
      if (data.total_amount) parts.push("PDF Total: " + data.total_amount);
      els.previewMeta.textContent = parts.join(" | ");
    }
    if (els.previewSummary) {
      const count = data.record_count || 0;
      const pdfCount = data.pdf_record_count || count;
      let summary = count + " row(s) loaded for review";
      if (pdfCount && pdfCount !== count) summary += " (PDF count " + pdfCount + ")";
      summary += " — ≤" + SMALL_AMOUNT_MAX + ": stationery on 1/21/41…; " +
        HIGH_AMOUNT_MIN + "–" + MAX_IMPORT_AMOUNT + ": auto stationery";
      els.previewSummary.textContent = summary;
    }
  }

  async function readPdf() {
    const file = els.pdfInput?.files && els.pdfInput.files[0];
    if (!file) {
      alert("Select a PDF file.");
      return;
    }
    const body = new FormData();
    body.append("receipt_pdf", file);
    body.append("csrf_token", window.ECOURT_URLS.csrf || "");
    if (els.uploadStatus) els.uploadStatus.textContent = "Reading PDF...";
    if (els.readPdfBtn) els.readPdfBtn.disabled = true;
    try {
      const res = await fetch(window.ECOURT_URLS.parsePdf, {
        method: "POST",
        body: body,
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "PDF read failed.");
      previewRows = filterEligiblePreviewRows((data.rows || []).map(function (row) {
        const highAmount = !!(row.high_amount || row.auto_stationery) ||
          (parseFloat(String(row.amount || "").replace(/,/g, "").trim()) >= HIGH_AMOUNT_MIN &&
            parseFloat(String(row.amount || "").replace(/,/g, "").trim()) <= MAX_IMPORT_AMOUNT);
        return {
          receipt_no: (row.receipt_no || "").trim().toUpperCase(),
          receipt_date: row.receipt_date || "",
          amount: row.amount || "",
          payment_mode: row.payment_mode || "",
          receipt_status: row.receipt_status || "",
          remarks: row.remarks || "",
          stationerynumber: row.stationerynumber || "",
          auto_stationery: !!row.auto_stationery || highAmount,
          high_amount: !!row.high_amount || highAmount,
          already_imported: false,
          _original_status: row.receipt_status || "Not Locked",
        };
      }));
      const existingCount = loadExistingFromParseResponse(data);
      refreshDuplicatePreviewRows();
      nextBlockRowIndex = BLOCK_SIZE;
      setPreviewMeta(data);
      renderPreviewGrid();
      els.previewPanel?.classList.remove("d-none");
      if (els.uploadStatus) {
        let statusMsg = data.message ||
          "PDF read complete. ≤" + SMALL_AMOUNT_MAX + ": enter stationery on 1/21/41…; " +
          HIGH_AMOUNT_MIN + "–" + MAX_IMPORT_AMOUNT + ": auto stationery.";
        if (data.excluded_high_amount) {
          statusMsg += " Amount outside " + MIN_IMPORT_AMOUNT + "–" + MAX_IMPORT_AMOUNT + " rows hidden.";
        }
        const importedRows = previewRows.filter(function (row) {
          return row.already_imported;
        }).length;
        if (importedRows) {
          statusMsg += " " + importedRows + " already imported receipt(s) moved to bottom (red).";
        } else if (existingCount) {
          statusMsg += " " + existingCount + " receipt number(s) matched in database.";
        }
        els.uploadStatus.textContent = statusMsg;
      }
    } catch (err) {
      alert(err.message || String(err));
      if (els.uploadStatus) els.uploadStatus.textContent = "";
    } finally {
      if (els.readPdfBtn) els.readPdfBtn.disabled = false;
    }
  }

  async function confirmImport() {
    syncPreviewRowsFromDom();
    const validation = validateForImport(previewRows);

    if (!validation.ok) {
      alert("Import validation failed:\n\n" + validation.errors.join("\n"));
      return;
    }

    const rows = validation.importRows.filter(function (row) {
      return !row.already_imported && !isReceiptAlreadyImported(row.receipt_no);
    });

    if (!rows.length) {
      alert(
        "No rows ready to import. For amount ≤" + SMALL_AMOUNT_MAX +
        " enter stationery on 1/21/41… and Apply next 20; amount " +
        HIGH_AMOUNT_MIN + "–" + MAX_IMPORT_AMOUNT + " use auto stationery."
      );
      return;
    }
    if (!previewMeta) {
      alert("Read a PDF first.");
      return;
    }

    const confirmMsg =
      "Import " + rows.length + " receipt(s)?\n\n" +
      "Only rows with stationery number filled will be saved.\n" +
      "Blank stationery rows are not imported.";
    if (!(await JTCSDialog.confirm(confirmMsg))) return;

    if (els.confirmImportBtn) els.confirmImportBtn.disabled = true;
    try {
      const res = await fetch(window.ECOURT_URLS.importRows, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": window.ECOURT_URLS.csrf || "",
        },
        body: JSON.stringify({
          file_name: previewMeta.file_name,
          report_from: previewMeta.report_from,
          report_to: previewMeta.report_to,
          state_name: previewMeta.state_name,
          total_amount: previewMeta.total_amount,
          rows: rows.map(function (row) {
            return {
              receipt_no: row.receipt_no,
              receipt_date: row.receipt_date,
              amount: row.amount,
              payment_mode: row.payment_mode,
              receipt_status: row.receipt_status,
              remarks: row.remarks,
              stationerynumber: row.stationerynumber,
              already_imported: false,
            };
          }),
          skipped_count: previewRows.length - rows.length,
        }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Import failed.");
      currentImportId = data.import_id;
      if (els.importId) els.importId.value = String(data.import_id);
      if (els.uploadStatus) {
        let msg = data.message + " Total: " + (data.total_amount || "—");
        if (data.skipped_count) msg += " (" + data.skipped_count + " preview rows skipped)";
        if (data.duplicate_count) msg += " (" + data.duplicate_count + " duplicate(s) not imported)";
        els.uploadStatus.textContent = msg;
      }
      previewRows = [];
      previewMeta = null;
      renderPreviewGrid();
      closeImportModal();
      await loadImportTree(null);
      if (data.skipped_duplicates && data.skipped_duplicates.length) {
        showDuplicateReport(data.skipped_duplicates, data.record_count || 0);
      }
      document.getElementById("ecourtGrid")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      alert(err.message || String(err));
    } finally {
      if (els.confirmImportBtn) els.confirmImportBtn.disabled = false;
    }
  }

  async function submitUnsell(receiptNumbers) {
    const receipts = (receiptNumbers || [])
      .map(function (value) { return String(value || "").trim().toUpperCase(); })
      .filter(Boolean);
    if (!receipts.length) {
      alert("No sold receipts selected to unsell.");
      return;
    }
    const confirmed = await JTCSDialog.confirm(
      "Mark as Unsold?\n\nThis rolls back the sale batch (daily + bank ledger).\n" +
      "Receipts sold together in the same sale will also become Unsold.\n\n" +
      "Selected: " + receipts.length + " receipt(s)."
    );
    if (!confirmed) return;

    try {
      const res = await fetch(window.ECOURT_URLS.unsell, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": window.ECOURT_URLS.csrf || "",
        },
        body: JSON.stringify({ receipt_numbers: receipts }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Unable to unsell.");
      alert(data.message || "Unsold successfully.");
      await loadImportTree(null);
    } catch (err) {
      alert(err.message || String(err));
    }
  }

  async function submitDeleteStationery(stationeryNo) {
    const stationery = String(stationeryNo || "").trim();
    if (!stationery) {
      alert("Stationery number is required.");
      return;
    }
    const message =
      "Permanently delete stationery " + stationery + " and all linked records? This cannot be undone.";
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!(await JTCSDialog.confirm(message))) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: message });
      if (!creds) return;
    }
    try {
      const res = await fetch(window.ECOURT_URLS.deleteStationery, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": window.ECOURT_URLS.csrf || "",
        },
        body: JSON.stringify(
          creds
            ? window.JTCSDeleteConfirm.withCreds({ stationerynumber: stationery }, creds)
            : { stationerynumber: stationery }
        ),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Unable to delete.");
      alert(data.message || "Permanently deleted.");
      await loadImportTree(null);
    } catch (err) {
      alert(err.message || String(err));
    }
  }

  function collectSoldReceiptsFromGroup(group) {
    return (group?.receipts || [])
      .filter(function (row) { return row.sale_status === "Sold"; })
      .map(function (row) { return row.receipt_no; })
      .filter(Boolean);
  }

  els.openImportBtn?.addEventListener("click", function () {
    const importUrl = window.ECOURT_URLS?.importPage;
    if (importUrl) {
      window.location.href = importUrl;
      return;
    }
    openImportModal();
  });
  els.backBtn?.addEventListener("click", function () {
    const fallback = window.ECOURT_URLS?.back || "/";
    if (window.history.length > 1) {
      history.back();
      return;
    }
    window.location.href = fallback;
  });
  function fillManualForm(prefill) {
    prefill = prefill || {};
    const receiptEl = document.getElementById("ecourtReceiptNo");
    const dateEl = document.getElementById("ecourtManualDate");
    const amountEl = document.getElementById("ecourtManualAmount");
    const stationeryEl = document.getElementById("ecourtStationeryNo");
    const remarksEl = document.getElementById("ecourtManualRemarks");
    if (receiptEl) receiptEl.value = prefill.receipt_no || "";
    if (dateEl) {
      dateEl.value =
        prefill.receipt_date ||
        window.ECOURT_DEFAULT_DATE ||
        new Date().toISOString().slice(0, 10);
    }
    if (amountEl) amountEl.value = prefill.amount || "";
    if (stationeryEl) stationeryEl.value = prefill.stationerynumber || "";
    if (remarksEl) remarksEl.value = prefill.remarks || "";
  }

  function openManualEntry(prefill) {
    els.manualForm?.reset();
    fillManualForm(prefill || {});
    refreshManualPreview();
    manualModal?.show();
    const focusEl = document.getElementById(
      (prefill && prefill.receipt_no) ? "ecourtStationeryNo" : "ecourtReceiptNo"
    );
    setTimeout(function () {
      focusEl?.focus();
      focusEl?.select?.();
    }, 150);
  }

  els.openManualBtn?.addEventListener("click", function () {
    openManualEntry({});
  });
  els.manualForm?.addEventListener("input", function (e) {
    if (
      e.target &&
      (e.target.id === "ecourtReceiptNo" ||
        e.target.id === "ecourtStationeryNo" ||
        e.target.id === "ecourtManualDate" ||
        e.target.id === "ecourtManualAmount")
    ) {
      refreshManualPreview();
    }
  });
  els.manualPreviewBody?.addEventListener("click", function (e) {
    const editPreview = e.target.closest(".ecourt-manual-preview-edit");
    if (!editPreview) return;
    e.preventDefault();
    document.getElementById("ecourtStationeryNo")?.focus();
  });
  els.readPdfBtn?.addEventListener("click", readPdf);
  els.jumpNextBlockBtn?.addEventListener("click", function () {
    scrollToBlockRow(nextBlockRowIndex);
  });
  els.confirmImportBtn?.addEventListener("click", confirmImport);
  els.addRowBtn?.addEventListener("click", function () {
    previewRows.push({
      receipt_no: "",
      receipt_date: "",
      amount: "",
      payment_mode: "",
      receipt_status: "",
      remarks: "",
      stationerynumber: "",
    });
    renderPreviewGrid();
  });
  els.gridBody?.addEventListener("click", function (e) {
    const toggle = e.target.closest(".ecourt-tree-toggle");
    if (toggle) {
      e.preventDefault();
      const gi = Number(toggle.dataset.group);
      if (!Number.isNaN(gi)) toggleTreeGroup(gi);
      return;
    }

    const sellAllBtn = e.target.closest(".ecourt-sell-all-btn");
    if (sellAllBtn) {
      e.preventDefault();
      const group = findGroupByStationery(sellAllBtn.dataset.stationery || "");
      if (!group) return;
      openSaleModal(collectReceiptsFromRows(getUnsoldReceiptsFromGroup(group)));
      return;
    }

    const sellOneBtn = e.target.closest(".ecourt-sell-one-btn");
    if (sellOneBtn) {
      e.preventDefault();
      openSaleModal([
        {
          receipt_no: sellOneBtn.dataset.receiptNo || "",
          stationerynumber: sellOneBtn.dataset.stationery || "",
          receipt_date: sellOneBtn.dataset.receiptDate || "",
          amount: sellOneBtn.dataset.amount || "",
        },
      ]);
      return;
    }

    const editBtn = e.target.closest(".ecourt-edit-btn");
    if (editBtn) {
      e.preventDefault();
      const receiptNo = (editBtn.dataset.receiptNo || "").trim();
      if (receiptNo) {
        openManualEntry({
          receipt_no: receiptNo,
          stationerynumber: editBtn.dataset.stationery || "",
          receipt_date: editBtn.dataset.receiptDate || "",
          amount: editBtn.dataset.amount || "",
        });
        return;
      }
      const group = findGroupByStationery(editBtn.dataset.stationery || "");
      if (!group) return;
      const pick =
        (group.receipts || []).find(function (row) {
          return row.sale_status !== "Sold";
        }) || (group.receipts || [])[0];
      openManualEntry({
        receipt_no: pick ? pick.receipt_no || "" : "",
        stationerynumber: group.stationerynumber || "",
        receipt_date: pick ? pick.receipt_date || "" : "",
        amount: pick ? pick.amount || "" : "",
      });
      return;
    }

    const unsellBtn = e.target.closest(".ecourt-unsell-btn");
    if (unsellBtn) {
      e.preventDefault();
      const receiptNo = (unsellBtn.dataset.receiptNo || "").trim();
      if (receiptNo) {
        submitUnsell([receiptNo]);
        return;
      }
      const group = findGroupByStationery(unsellBtn.dataset.stationery || "");
      if (!group) return;
      submitUnsell(collectSoldReceiptsFromGroup(group));
      return;
    }

    const deleteBtn = e.target.closest(".ecourt-delete-stationery-btn");
    if (deleteBtn) {
      e.preventDefault();
      submitDeleteStationery(deleteBtn.dataset.stationery || "");
    }
  });

  els.gridBody?.addEventListener("change", function (e) {
    if (e.target.matches(".ecourt-receipt-select")) {
      updateSellSelectedButton();
    }
  });

  els.sellSelectedBtn?.addEventListener("click", function () {
    openSaleModal(getCheckedReceipts());
  });
  els.addPaymentBtn?.addEventListener("click", function () {
    addPaymentLine({ amount: "0" });
  });
  els.saleAmount?.addEventListener("input", updatePaymentSummary);
  els.saleForm?.addEventListener("submit", submitSaleForm);

  els.previewBody?.addEventListener("click", function (e) {
    if (e.target.closest(".ecourt-apply-next20-btn")) {
      e.preventDefault();
      const tr = e.target.closest("tr");
      const index = Number(tr?.dataset.index);
      if (Number.isNaN(index)) return;
      applyNext20SameAmount(index);
      return;
    }
    const btn = e.target.closest(".ecourt-delete-row");
    if (!btn) return;
    const tr = btn.closest("tr");
    const index = Number(tr?.dataset.index);
    if (Number.isNaN(index)) return;
    previewRows.splice(index, 1);
    renderPreviewGrid();
  });
  els.previewBody?.addEventListener("input", function (e) {
    if (e.target.matches('[data-field="stationerynumber"], [data-field="amount"], [data-field="receipt_no"]')) {
      syncPreviewRowsFromDom();
      if (e.target.matches('[data-field="amount"]')) {
        previewRows = filterEligiblePreviewRows(previewRows);
        renderPreviewGrid();
        return;
      }
      if (e.target.matches('[data-field="stationerynumber"]')) {
        const tr = e.target.closest("tr");
        const index = Number(tr?.dataset.index);
        if (!Number.isNaN(index) && previewRows[index]) {
          previewRows[index].stationerynumber = e.target.value.trim();
          if (isBlockStartRow(index)) {
            toggleRowApplyPanel(tr, index);
          }
        }
        updatePreviewCountText();
        return;
      }
      updatePreviewCountText();
    }
  });
  function findReceiptInTree(receiptNo) {
    const normalized = (receiptNo || "").trim().toUpperCase();
    if (!normalized || !lastTreeData?.groups) return null;
    for (let gi = 0; gi < lastTreeData.groups.length; gi++) {
      const group = lastTreeData.groups[gi];
      for (let ri = 0; ri < (group.receipts || []).length; ri++) {
        const row = group.receipts[ri];
        if ((row.receipt_no || "").toUpperCase() === normalized) {
          if (row.sale_status === "Sold") {
            return { error: "Receipt already sold." };
          }
          return {
            receipt_no: row.receipt_no,
            stationerynumber: row.stationerynumber || group.stationerynumber || "",
            receipt_date: row.receipt_date || "",
            amount: row.amount || "",
          };
        }
      }
    }
    return null;
  }

  els.manualForm?.addEventListener("submit", async function (e) {
    e.preventDefault();
    const receiptNo = (document.getElementById("ecourtReceiptNo")?.value || "").trim();
    const stationeryNo = (document.getElementById("ecourtStationeryNo")?.value || "").trim();
    const amountRaw = (document.getElementById("ecourtManualAmount")?.value || "").trim();
    const receiptDate = (document.getElementById("ecourtManualDate")?.value || "").trim();

    if (!receiptNo) {
      alert("Receipt number is required.");
      return;
    }
    if (!receiptDate) {
      alert("Receipt date is required.");
      document.getElementById("ecourtManualDate")?.focus();
      return;
    }
    const amount = parseAmount(amountRaw);
    if (amount < 1) {
      alert("Amount is required (must be at least 1).");
      document.getElementById("ecourtManualAmount")?.focus();
      return;
    }
    if (!stationeryNo) {
      alert("Stationery Number is required.");
      document.getElementById("ecourtStationeryNo")?.focus();
      return;
    }

    const body = new FormData(els.manualForm);
    body.set("ReceiptNo", receiptNo.toUpperCase());
    body.set("Amount", String(amount));
    body.set("StationeryNumber", stationeryNo);
    body.set("ReceiptDate", receiptDate);

    if (els.manualSaveBtn) els.manualSaveBtn.disabled = true;
    try {
      const res = await fetch(window.ECOURT_URLS.manual, {
        method: "POST",
        body: body,
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await readJsonResponse(res, "Unable to save manual entry.");
      if (!res.ok || !data.ok) throw new Error(data.error || "Manual entry failed.");
      alert(data.message || "Import Successfully");
      els.manualForm.reset();
      refreshManualPreview();
      manualModal?.hide();
      await loadImportTree(null, {
        expandStationery: stationeryNo,
      });
    } catch (err) {
      alert(err.message || String(err));
    } finally {
      if (els.manualSaveBtn) els.manualSaveBtn.disabled = false;
    }
  });

  const ecourtGridHead = document.querySelector("#ecourtGrid thead");
  ecourtGridHead?.addEventListener("click", function (event) {
    if (event.target.closest(".ecourt-col-filter")) return;
    const th = event.target.closest("th.ecourt-sortable");
    if (!th) return;
    onGridSortHeader(th.dataset.sortKey);
  });
  ecourtGridHead?.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    const th = event.target.closest("th.ecourt-sortable");
    if (!th) return;
    event.preventDefault();
    onGridSortHeader(th.dataset.sortKey);
  });
  ecourtGridHead?.addEventListener("input", function (event) {
    const input = event.target.closest(".ecourt-col-filter");
    if (!input) return;
    readGridFiltersFromDom();
    refreshImportTree();
  });

  loadImportTree(null);
})();
