(function () {
  "use strict";

  const api = window.IEN_API;
  if (!api) return;

  const els = {
    refreshBtn: document.getElementById("ienRefreshBtn"),
    body: document.getElementById("ienDataGridBody"),
    empty: document.getElementById("ienGridEmpty"),
    count: document.getElementById("ienGridCount"),
    search: document.getElementById("ienGridSearch"),
    filterKind: document.getElementById("ienGridFilterKind"),
    dateFrom: document.getElementById("ienGridDateFrom"),
    dateTo: document.getElementById("ienGridDateTo"),
    applyBtn: document.getElementById("ienApplyFilterBtn"),
    clearBtn: document.getElementById("ienClearFilterBtn"),
    pageSize: document.getElementById("ienPageSize"),
    pageInfo: document.getElementById("ienPageInfo"),
    pagerNav: document.getElementById("ienPagerNav"),
    statIncomeAmount: document.getElementById("ienStatIncomeAmount"),
    statIncomeCount: document.getElementById("ienStatIncomeCount"),
    statExpenseAmount: document.getElementById("ienStatExpenseAmount"),
    statExpenseCount: document.getElementById("ienStatExpenseCount"),
  };

  let allRows = Array.isArray(window.IEN_INITIAL_ROWS) ? window.IEN_INITIAL_ROWS.slice() : [];
  let sortState = { key: "work_date", dir: "desc" };
  let pageState = { page: 1 };
  let searchTimer = null;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatAmount(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return "0.00";
    return num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function formatDisplayDate(value) {
    if (window.formatDisplaySmart) return window.formatDisplaySmart(value);
    if (window.formatDisplayDate) return window.formatDisplayDate(value);
    return value || "";
  }

  function ledgerBadge(kind) {
    if (kind === "Expense") return '<span class="badge text-bg-danger">Expense</span>';
    return '<span class="badge text-bg-success">Income</span>';
  }

  function filteredRows() {
    const search = (els.search?.value || "").trim().toLowerCase();
    const kind = (els.filterKind?.value || "").trim();
    const dateFrom = (els.dateFrom?.value || "").trim();
    const dateTo = (els.dateTo?.value || "").trim();
    let rows = allRows.slice();
    if (kind) rows = rows.filter(function (r) { return r.ledger_kind === kind; });
    if (dateFrom) rows = rows.filter(function (r) { return (r.work_date || "") >= dateFrom; });
    if (dateTo) rows = rows.filter(function (r) { return (r.work_date || "") <= dateTo; });
    if (search) {
      rows = rows.filter(function (r) {
        const hay = [
          r.bill_no, r.ledger_kind, r.work_name, r.account_label,
          r.customer_name, r.mobile_number, r.remarks, r.amount,
        ].join(" ").toLowerCase();
        return hay.indexOf(search) >= 0;
      });
    }
    const key = sortState.key || "work_date";
    const dir = sortState.dir === "asc" ? 1 : -1;
    rows.sort(function (a, b) {
      let av = a[key];
      let bv = b[key];
      if (key === "amount") {
        av = Number(av) || 0;
        bv = Number(bv) || 0;
        return (av - bv) * dir;
      }
      av = String(av == null ? "" : av).toLowerCase();
      bv = String(bv == null ? "" : bv).toLowerCase();
      if (av < bv) return -1 * dir;
      if (av > bv) return 1 * dir;
      return 0;
    });
    return rows;
  }

  function updateStats(rows) {
    let incomeAmt = 0;
    let incomeCount = 0;
    let expenseAmt = 0;
    let expenseCount = 0;
    rows.forEach(function (row) {
      const amt = Number(row.amount) || 0;
      if (row.ledger_kind === "Expense") {
        expenseAmt += amt;
        expenseCount += 1;
      } else {
        incomeAmt += amt;
        incomeCount += 1;
      }
    });
    if (els.statIncomeAmount) els.statIncomeAmount.textContent = formatAmount(incomeAmt);
    if (els.statIncomeCount) els.statIncomeCount.textContent = String(incomeCount);
    if (els.statExpenseAmount) els.statExpenseAmount.textContent = formatAmount(expenseAmt);
    if (els.statExpenseCount) els.statExpenseCount.textContent = String(expenseCount);
  }

  function renderPager(total, pageSize, page, totalPages) {
    if (els.pageInfo) {
      const start = total ? (page - 1) * pageSize + 1 : 0;
      const end = Math.min(page * pageSize, total);
      els.pageInfo.textContent = total ? start + "–" + end + " of " + total : "0 records";
    }
    if (!els.pagerNav) return;
    els.pagerNav.innerHTML = "";
    if (totalPages <= 1) return;
    const ul = document.createElement("ul");
    ul.className = "pagination pagination-sm mb-0";
    function addBtn(label, target, disabled, active) {
      const li = document.createElement("li");
      li.className = "page-item" + (disabled ? " disabled" : "") + (active ? " active" : "");
      const a = document.createElement("button");
      a.type = "button";
      a.className = "page-link";
      a.textContent = label;
      a.addEventListener("click", function () {
        if (disabled) return;
        pageState.page = target;
        renderGrid();
      });
      li.appendChild(a);
      ul.appendChild(li);
    }
    addBtn("‹", Math.max(1, page - 1), page <= 1, false);
    addBtn(String(page), page, false, true);
    addBtn("›", Math.min(totalPages, page + 1), page >= totalPages, false);
    els.pagerNav.appendChild(ul);
  }

  function renderGrid(options) {
    if (!els.body) return;
    if (options && options.resetPage) pageState.page = 1;
    const filtered = filteredRows();
    updateStats(allRows);
    const pageSize = Math.max(1, parseInt((els.pageSize && els.pageSize.value) || "50", 10) || 50);
    const total = filtered.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    let page = pageState.page || 1;
    if (page > totalPages) page = totalPages;
    pageState.page = page;
    if (els.count) els.count.textContent = total + " record(s)";
    if (els.empty) els.empty.classList.toggle("d-none", total > 0);

    const start = total ? (page - 1) * pageSize : 0;
    const pageRows = filtered.slice(start, start + pageSize);
    renderPager(total, pageSize, page, totalPages);

    els.body.innerHTML = pageRows
      .map(function (row) {
        return (
          "<tr>" +
          "<td>" + escapeHtml(row.bill_no) + "</td>" +
          "<td>" + ledgerBadge(row.ledger_kind) + "</td>" +
          "<td>" + escapeHtml(formatDisplayDate(row.work_date)) + "</td>" +
          "<td>" + escapeHtml(row.work_name || "") + "</td>" +
          "<td>" + escapeHtml(row.account_label || "—") + "</td>" +
          '<td class="text-end">' + escapeHtml(formatAmount(row.amount)) + "</td>" +
          "<td>" + escapeHtml(row.customer_name || "") + "</td>" +
          "<td>" + escapeHtml(row.mobile_number || "") + "</td>" +
          "<td>" + escapeHtml(row.remarks || "") + "</td>" +
          "<td>" + escapeHtml(formatDisplayDate(row.created_date)) + "</td>" +
          "</tr>"
        );
      })
      .join("");
  }

  function loadGrid() {
    return fetch(api.grid, { headers: { Accept: "application/json" } })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "Unable to load grid.");
        allRows = data.rows || [];
        renderGrid({ resetPage: true });
      })
      .catch(function (err) {
        alert(err.message || String(err));
      });
  }

  els.refreshBtn?.addEventListener("click", loadGrid);
  els.applyBtn?.addEventListener("click", function () { renderGrid({ resetPage: true }); });
  els.clearBtn?.addEventListener("click", function () {
    if (els.search) els.search.value = "";
    if (els.filterKind) els.filterKind.value = "";
    if (els.dateFrom) els.dateFrom.value = "";
    if (els.dateTo) els.dateTo.value = "";
    sortState = { key: "work_date", dir: "desc" };
    renderGrid({ resetPage: true });
  });
  els.filterKind?.addEventListener("change", function () { renderGrid({ resetPage: true }); });
  els.dateFrom?.addEventListener("change", function () { renderGrid({ resetPage: true }); });
  els.dateTo?.addEventListener("change", function () { renderGrid({ resetPage: true }); });
  els.pageSize?.addEventListener("change", function () { renderGrid({ resetPage: true }); });
  els.search?.addEventListener("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () { renderGrid({ resetPage: true }); }, 250);
  });

  document.querySelectorAll("#ienStatsRow [data-kind-filter]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const kind = btn.getAttribute("data-kind-filter") || "";
      if (els.filterKind) {
        els.filterKind.value = els.filterKind.value === kind ? "" : kind;
      }
      renderGrid({ resetPage: true });
    });
  });

  document.querySelectorAll("#ienDataGrid .ien-sortable").forEach(function (th) {
    th.style.cursor = "pointer";
    th.addEventListener("click", function () {
      const key = th.getAttribute("data-sort-key");
      if (!key) return;
      if (sortState.key === key) {
        sortState.dir = sortState.dir === "asc" ? "desc" : "asc";
      } else {
        sortState.key = key;
        sortState.dir = key === "amount" || key === "work_date" || key === "created_date" ? "desc" : "asc";
      }
      renderGrid({ resetPage: true });
    });
  });

  renderGrid({ resetPage: true });
})();
