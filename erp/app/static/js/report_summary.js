(function () {
  "use strict";

  const cfg = window.LEDGER_REPORT || {};
  const results = document.getElementById("summaryResults");
  const searchBox = document.getElementById("summarySearch");
  const searchBtn = document.getElementById("summarySearchBtn");
  const kindBox = document.getElementById("summaryLedgerKind");
  const meta = document.getElementById("summarySearchMeta");
  const body = document.getElementById("ledgerPreviewBody");
  const dateFrom = document.getElementById("ledgerDateFrom");
  const dateTo = document.getElementById("ledgerDateTo");
  const modeControls = document.getElementById("summaryModes");
  const ledgerControls = document.getElementById("summaryLedgerControls");
  const dateControls = document.getElementById("summaryDateControls");
  const dateInput = document.getElementById("summaryExactDate");
  const dateSearchBtn = document.getElementById("summaryDateSearchBtn");
  const followupControls = document.getElementById("summaryFollowupControls");
  let selectedLedger = null;
  let currentMode = "ledgerwise";

  function esc(value) {
    return String(value == null ? "" : value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function queryDates() {
    const p = new URLSearchParams();
    if (dateFrom.value) p.set("date_from", dateFrom.value);
    if (dateTo.value) p.set("date_to", dateTo.value);
    return p.toString();
  }

  function money(value) {
    const n = Number(value || 0);
    return "₹ " + n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  async function json(url) {
    const response = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
    const data = await response.json().catch(function () { return {}; });
    if (!response.ok || data.ok === false) throw new Error(data.error || "Unable to load summary data.");
    return data;
  }

  function renderLedgerRows(rows) {
    if (!rows.length) return '<div class="p-3 small text-muted">No matching ledgers.</div>';
    return rows.map(function (row) {
      return '<button type="button" class="summary-result" data-summary-kind="' + esc(row.kind) + '" data-summary-id="' + esc(row.id) + '">' +
        '<span class="badge text-bg-light border me-1">' + esc(row.kind) + '</span><strong>' + esc(row.label) + '</strong>' +
        '<div class="small text-muted">' + esc(row.subtitle || row.meta || "") + (row.txn_count != null ? " · " + esc(row.txn_count) + " entries" : "") + '</div></button>';
    }).join("");
  }

  function renderReference(data) {
    const chunks = [];
    (data.invoices || []).forEach(function (invoice) {
      const lines = (invoice.lines || []).map(function (line) {
        const qty = line.Qty == null ? "" : " · Qty " + line.Qty + (line.Unit ? " " + line.Unit : "");
        return "<tr><td>Item</td><td>" + esc(line.ItemName || line.Particulars || "—") +
          "</td><td>" + esc(line.Particulars || "") + esc(qty) + "</td><td class=\"text-end\">" + money(line.TaxableValue) + "</td></tr>";
      }).join("");
      chunks.push('<div class="mb-3"><div class="fw-semibold">Invoice ' + esc(invoice.InvoiceNo) +
        '</div><div class="small">' + esc(invoice.InvoiceDate) + " · " + esc(invoice.CustomerName) + " · " + money(invoice.InvoiceValue) +
        (invoice.TallyBillNo ? " · Ref " + esc(invoice.TallyBillNo) : "") + '</div><div class="table-responsive mt-2"><table class="table table-sm summary-ref-table"><thead><tr><th>Linked as</th><th>Item</th><th>Details</th><th class="text-end">Amount</th></tr></thead><tbody>' +
        '<tr><td>Customer ledger</td><td>' + esc(invoice.CustomerName) + '</td><td>Invoice / bill reference</td><td class="text-end">' + money(invoice.InvoiceValue) + '</td></tr>' + lines +
        '</tbody></table></div></div>');
    });
    const daily = data.daily_transactions || [];
    if (daily.length) {
      chunks.push('<h3 class="h6 mt-3">Daily transaction links</h3><div class="table-responsive"><table class="table table-sm summary-ref-table"><thead><tr><th>Date</th><th>Work / Ledger</th><th>Customer</th><th>Reference / Details</th><th class="text-end">Income</th><th class="text-end">Expense</th></tr></thead><tbody>' +
        daily.map(function (row) { return '<tr><td>' + esc(row.TransactionDate) + '</td><td>' + esc(row.WorkType) + (row.SubWorkType ? " / " + esc(row.SubWorkType) : "") + '</td><td>' + esc(row.CustomerName || "—") + '</td><td>' + esc(row.ReferenceNo || "") + (row.Description ? " · " + esc(row.Description) : "") + '</td><td class="text-end">' + money(row.IncomeAmount) + '</td><td class="text-end">' + money(row.ExpenseAmount) + '</td></tr>'; }).join("") +
        '</tbody></table></div>');
    }
    const banks = data.bank_transactions || [];
    if (banks.length) {
      chunks.push('<h3 class="h6 mt-3">Bank / cash ledger links</h3><div class="table-responsive"><table class="table table-sm summary-ref-table"><thead><tr><th>Date</th><th>Bank / Cash</th><th>Description</th><th class="text-end">Debit</th><th class="text-end">Credit</th></tr></thead><tbody>' +
        banks.map(function (row) { return '<tr><td>' + esc(row.TransactionDate) + '</td><td>' + esc(row.BankName) + '</td><td>' + esc(row.Description || row.ReferenceNo || "—") + '</td><td class="text-end">' + money(row.Debit) + '</td><td class="text-end">' + money(row.Credit) + '</td></tr>'; }).join("") +
        '</tbody></table></div>');
    }
    const links = (data.related_ledgers || []).map(function (row) {
      return '<button type="button" class="btn btn-outline-primary btn-sm me-1 mb-1" data-summary-kind="' + esc(row.kind) + '" data-summary-id="' + esc(row.id) + '">Open ' + esc(row.kind) + ' ledger: ' + esc(row.label) + '</button>';
    }).join("");
    if (links) chunks.push('<div class="border-top pt-2 mt-3"><div class="small text-muted mb-1">Open related ledgers for full date-wise entries</div>' + links + '</div>');
    return chunks.length ? chunks.join("") : '<div class="text-muted small">No matching invoice, item, or transaction reference found in the selected dates.</div>';
  }

  function tableSection(title, rows, columns, tableId) {
    if (!rows.length) return '<section class="mb-3"><h3 class="h6">' + esc(title) + '</h3><div class="small text-muted">No records for this date.</div></section>';
    const heads = columns.map(function (column) {
      return '<th data-summary-sort="' + esc(column.key) + '">' + esc(column.label) + ' <span class="text-muted">↕</span></th>';
    }).join("");
    const bodyRows = rows.map(function (row) {
      return '<tr>' + columns.map(function (column) {
        const value = row[column.key];
        return '<td' + (column.money ? ' class="text-end"' : '') + '>' + esc(column.money ? money(value) : (value || "—")) + '</td>';
      }).join("") + '</tr>';
    }).join("");
    return '<section class="mb-4"><div class="d-flex justify-content-between align-items-center gap-2"><h3 class="h6 mb-1">' + esc(title) + ' <span class="text-muted">(' + rows.length + ')</span></h3><input type="search" class="form-control form-control-sm summary-table-filter" style="max-width:260px" placeholder="Filter this table" data-table-filter="' + esc(tableId) + '"></div><div class="table-responsive"><table class="table table-sm table-striped table-hover summary-ref-table" id="' + esc(tableId) + '"><thead class="table-primary"><tr>' + heads + '</tr></thead><tbody>' + bodyRows + '</tbody></table></div></section>';
  }

  function amount(value) { return Number(value || 0); }

  function groupDailyRows(rows, key) {
    const groups = new Map();
    rows.forEach(function (row) {
      const label = String(row[key] || "Unspecified").trim() || "Unspecified";
      if (!groups.has(label)) groups.set(label, { label: label, count: 0, income: 0, debit: 0, sale: 0, purchase: 0, total: 0 });
      const group = groups.get(label);
      group.count += 1;
      group.income += amount(row.IncomeAmount);
      group.debit += amount(row.ExpenseAmount);
      group.sale += amount(row.SaleAmount);
      group.purchase += amount(row.PurchaseAmount);
      group.total += amount(row.TotalAmount);
    });
    return Array.from(groups.values()).sort(function (a, b) { return b.total - a.total || a.label.localeCompare(b.label); });
  }

  function renderGroupedSummary(title, groups) {
    const rankable = groups.filter(function (group) { return group.total > 0; });
    const top = rankable[0];
    const bottom = rankable[rankable.length - 1];
    const table = '<div class="table-responsive"><table class="table table-sm table-striped summary-ref-table summary-group-table mb-0"><thead class="table-primary"><tr><th>' + esc(title) + '</th><th>Entries</th><th>Income / Credit</th><th>Expense / Debit</th><th>Sale</th><th>Purchase</th><th>Total</th></tr></thead><tbody>' +
      (groups.length ? groups.map(function (group) {
        return '<tr><td class="fw-semibold">' + esc(group.label) + '</td><td>' + group.count + '</td><td class="money">' + money(group.income) + '</td><td class="money">' + money(group.debit) + '</td><td class="money">' + money(group.sale) + '</td><td class="money">' + money(group.purchase) + '</td><td class="money fw-semibold">' + money(group.total) + '</td></tr>';
      }).join("") : '<tr><td colspan="7" class="text-muted">No records for this date.</td></tr>') + '</tbody></table></div>';
    const rank = '<div class="summary-rank mt-2">' +
      (top ? '<span class="me-3">Top ' + esc(title.toLowerCase()) + ': <strong>' + esc(top.label) + '</strong> · ' + money(top.total) + '</span>' : '<span class="text-muted">No amount to rank</span>') +
      (bottom && bottom !== top ? '<span>Lowest: <strong>' + esc(bottom.label) + '</strong> · ' + money(bottom.total) + '</span>' : '') +
      '<span class="text-muted ms-2">(ranked by Total)</span></div>';
    return '<section class="mb-3"><div class="d-flex justify-content-between align-items-center mb-1"><h3 class="h6 mb-0">' + esc(title) + ' summary</h3><span class="small text-muted">' + groups.length + ' group(s)</span></div><div class="summary-group-card p-2">' + table + rank + '</div></section>';
  }

  function renderDatewise(data) {
    const daily = data.daily_transactions || [];
    const bank = data.bank_transactions || [];
    const totals = data.totals || {};
    const workGroups = groupDailyRows(daily, "WorkType");
    const categoryGroups = groupDailyRows(daily, "SubWorkType");
    const descriptionGroups = groupDailyRows(daily, "Description");
    const cards = '<div class="row g-2 mb-3">' +
      [['Daily debit', totals.daily_debit], ['Daily credit', totals.daily_credit], ['Bank/cash debit', totals.bank_debit], ['Bank/cash credit', totals.bank_credit]].map(function (item) {
        return '<div class="col-6 col-xl-3"><div class="border rounded p-2 bg-white"><div class="small text-muted">' + item[0] + '</div><strong>' + money(item[1]) + '</strong></div></div>';
      }).join("") + '</div>';
    const dailyColumns = [
      { key: "TransactionID", label: "Daily Txn ID" }, { key: "TransactionDate", label: "Date" }, { key: "WorkType", label: "Work" },
      { key: "SubWorkType", label: "Category" }, { key: "CustomerName", label: "Party / Customer" },
      { key: "ReferenceNo", label: "Voucher / Reference" }, { key: "Description", label: "Description" },
      { key: "IncomeAmount", label: "Income / Credit", money: true }, { key: "ExpenseAmount", label: "Expense / Debit", money: true },
      { key: "SaleAmount", label: "Sale", money: true }, { key: "PurchaseAmount", label: "Purchase", money: true },
      { key: "TotalAmount", label: "Total", money: true }, { key: "BankTransactionID", label: "Bank Txn ID" },
    ];
    const bankColumns = [
      { key: "JtcsBankTransactionID", label: "Bank Txn ID" }, { key: "TransactionID", label: "Linked Daily Txn ID" },
      { key: "TransactionDate", label: "Date" }, { key: "BankName", label: "Bank / Cash ledger" },
      { key: "MaskedAccountNumber", label: "Account" }, { key: "LedgerKind", label: "Type" },
      { key: "WorkType", label: "Work" }, { key: "CustomerName", label: "Party / Customer" },
      { key: "ReferenceNo", label: "Voucher / Reference" }, { key: "Description", label: "Description" },
      { key: "Remarks", label: "Remarks" }, { key: "Debit", label: "Debit", money: true },
      { key: "Credit", label: "Credit", money: true }, { key: "ClosingBalance", label: "Closing balance", money: true },
    ];
    return '<div class="p-3"><div class="small text-muted mb-1">' + daily.length + ' daily transaction(s) · ' + bank.length + ' bank/cash row(s)</div><h3 class="h6">Cash and bank reconciliation — ' + esc(data.date) + '</h3>' + cards +
      renderGroupedSummary("Work", workGroups) + renderGroupedSummary("Category", categoryGroups) + renderGroupedSummary("Description", descriptionGroups) +
      tableSection("Daily transactions", daily, dailyColumns, "summaryDailyRows") +
      tableSection("Bank / cash ledger transactions", bank, bankColumns, "summaryBankRows") + '</div>';
  }

  function sortSummaryTable(table, key) {
    const header = table.querySelector('th[data-summary-sort="' + CSS.escape(key) + '"]');
    if (!header) return;
    const direction = header.dataset.sortDirection === "asc" ? "desc" : "asc";
    table.querySelectorAll("th[data-summary-sort]").forEach(function (th) { delete th.dataset.sortDirection; });
    header.dataset.sortDirection = direction;
    const columnIndex = Array.prototype.indexOf.call(header.parentElement.children, header);
    const rows = Array.from(table.tBodies[0].rows);
    rows.sort(function (a, b) {
      const left = (a.cells[columnIndex]?.textContent || "").trim();
      const right = (b.cells[columnIndex]?.textContent || "").trim();
      const leftNum = Number(left.replace(/[^0-9.-]/g, ""));
      const rightNum = Number(right.replace(/[^0-9.-]/g, ""));
      const bothNumeric = left !== "" && right !== "" && Number.isFinite(leftNum) && Number.isFinite(rightNum);
      const compared = bothNumeric ? leftNum - rightNum : left.localeCompare(right, undefined, { numeric: true, sensitivity: "base" });
      return direction === "asc" ? compared : -compared;
    });
    rows.forEach(function (row) { table.tBodies[0].appendChild(row); });
  }

  function setMode(mode) {
    currentMode = mode;
    document.querySelector(".summary-layout")?.classList.remove("is-datewise");
    const isDate = mode === "datewise";
    const isFollowup = mode === "followupwise";
    ledgerControls.classList.toggle("d-none", isDate || isFollowup);
    dateControls.classList.toggle("d-none", !isDate);
    followupControls.classList.toggle("d-none", !isFollowup);
    selectedLedger = null;
    const descriptions = {
      ledgerwise: "Ledger-wise view: search a ledger and inspect its date-wise transactions.",
      miscwise: "Misc-wise view: search a ledger to inspect its date-wise details.",
      stamp: "Stamp view: search a ledger to inspect date-wise Stamp records.",
      ecourt: "e-Court view: search a ledger to inspect date-wise e-Court records.",
      datewise: "Date-wise view: choose one date to see all daily and bank/cash entries.",
      followupwise: "Choose All, DSC, GST, TDS or ITR. Follow-up behavior will be added after your instructions.",
    };
    meta.textContent = descriptions[mode] || descriptions.ledgerwise;
    results.innerHTML = "";
    body.innerHTML = '<div class="text-muted small text-center py-5">' + esc(descriptions[mode] || descriptions.ledgerwise) + '</div>';
  }

  async function runDateSearch() {
    if (!dateInput.value) {
      meta.textContent = "Choose a date first.";
      return;
    }
    meta.textContent = "Loading transactions for " + dateInput.value + "…";
    document.querySelector(".summary-layout")?.classList.add("is-datewise");
    body.innerHTML = '<div class="text-muted small text-center py-5">Loading date-wise entries…</div>';
    try {
      const data = await json(cfg.dateUrl + "?date=" + encodeURIComponent(dateInput.value));
      results.innerHTML = '';
      body.classList.remove("text-muted", "small", "text-center", "py-5");
      body.innerHTML = renderDatewise(data);
      meta.textContent = "Showing all posted daily transactions and bank/cash ledger rows for " + dateInput.value + ".";
    } catch (error) {
      showError(error);
      meta.textContent = "Date-wise search failed.";
    }
  }

  async function showLedger(kind, id) {
    selectedLedger = { kind: kind, id: id };
    body.innerHTML = '<div class="text-muted small text-center py-5">Loading ledger…</div>';
    const url = cfg.previewUrl.replace("/bank/0", "/" + encodeURIComponent(kind) + "/" + encodeURIComponent(id)) + (queryDates() ? "?" + queryDates() : "");
    const data = await json(url);
    body.innerHTML = data.html || '<div class="text-muted p-3">No ledger detail.</div>';
    window.JTCSLedgerPreview?.setReloader(function () { showLedger(kind, id).catch(showError); });
    window.JTCSLedgerPreview?.afterRender();
  }

  function showError(error) {
    body.innerHTML = '<div class="alert alert-danger m-2">' + esc(error.message || "Unable to show summary.") + '</div>';
  }

  async function runSearch() {
    const term = (searchBox.value || "").trim();
    if (!term) {
      meta.textContent = "Enter a ledger, invoice, bill number, customer, or item.";
      return;
    }
    results.innerHTML = '<div class="p-3 small text-muted">Searching…</div>';
    meta.textContent = "Searching ledgers and linked records…";
    const params = new URLSearchParams({ search: term, kind: kindBox.value });
    const refParams = new URLSearchParams({ search: term });
    if (dateFrom.value) refParams.set("date_from", dateFrom.value);
    if (dateTo.value) refParams.set("date_to", dateTo.value);
    try {
      const [ledgerData, refData] = await Promise.all([
        json(cfg.searchUrl + "?" + params.toString()),
        json(cfg.referenceUrl + "?" + refParams.toString()),
      ]);
      const ledgerRows = ledgerData.rows || [];
      const refCount = (refData.invoices || []).length + (refData.daily_transactions || []).length + (refData.bank_transactions || []).length;
      meta.textContent = ledgerRows.length + " ledger match(es) · " + refCount + " linked reference row(s)";
      results.innerHTML = '<div class="px-2 pt-2 small fw-semibold text-uppercase text-muted">Ledgers</div>' + renderLedgerRows(ledgerRows) +
        '<button type="button" class="summary-result" id="summaryReferenceResult"><strong>Related invoice / item / transaction details</strong><div class="small text-muted">' + refCount + ' reference match(es) for “' + esc(term) + '”</div></button>';
      results.dataset.reference = JSON.stringify(refData);
      if (ledgerRows.length) await showLedger(ledgerRows[0].kind, ledgerRows[0].id);
      else {
        body.innerHTML = '<div class="p-3"><h3 class="h6">Related details for “' + esc(term) + '”</h3>' + renderReference(refData) + '</div>';
      }
    } catch (error) {
      results.innerHTML = '<div class="p-3 text-danger">' + esc(error.message) + '</div>';
      meta.textContent = "Search failed.";
    }
  }

  searchBtn?.addEventListener("click", runSearch);
  dateSearchBtn?.addEventListener("click", runDateSearch);
  modeControls?.addEventListener("change", function (event) {
    const radio = event.target.closest('input[name="summaryMode"]');
    if (radio) setMode(radio.value);
  });
  body?.addEventListener("click", function (event) {
    const header = event.target.closest("th[data-summary-sort]");
    if (header) sortSummaryTable(header.closest("table"), header.dataset.summarySort);
  });
  body?.addEventListener("input", function (event) {
    const input = event.target.closest("[data-table-filter]");
    if (!input) return;
    const table = document.getElementById(input.dataset.tableFilter);
    if (!table) return;
    const needle = input.value.trim().toLowerCase();
    Array.from(table.tBodies[0].rows).forEach(function (row) {
      row.hidden = !!needle && !row.textContent.toLowerCase().includes(needle);
    });
  });
  searchBox?.addEventListener("keydown", function (event) { if (event.key === "Enter") { event.preventDefault(); runSearch(); } });
  results?.addEventListener("click", function (event) {
    const ledgerButton = event.target.closest("[data-summary-kind][data-summary-id]");
    if (ledgerButton) {
      showLedger(ledgerButton.dataset.summaryKind, ledgerButton.dataset.summaryId).catch(showError);
      return;
    }
    if (event.target.closest("#summaryReferenceResult")) {
      let data = {};
      try { data = JSON.parse(results.dataset.reference || "{}"); } catch (_err) { /* ignored */ }
      body.innerHTML = '<div class="p-3"><h3 class="h6">Linked records for “' + esc(searchBox.value) + '”</h3>' + renderReference(data) + '</div>';
    }
  });
  body?.addEventListener("click", function (event) {
    const ledgerButton = event.target.closest("[data-summary-kind][data-summary-id]");
    if (ledgerButton) {
      showLedger(ledgerButton.dataset.summaryKind, ledgerButton.dataset.summaryId).catch(showError);
    }
  });
  dateFrom?.addEventListener("change", function () { if (selectedLedger) showLedger(selectedLedger.kind, selectedLedger.id).catch(showError); });
  dateTo?.addEventListener("change", function () { if (selectedLedger) showLedger(selectedLedger.kind, selectedLedger.id).catch(showError); });
})();
