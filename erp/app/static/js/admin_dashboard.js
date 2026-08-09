(function () {
  const cfg = window.ADMIN_DASHBOARD;
  if (!cfg) return;

  const els = {
    banksList: document.getElementById("adashBanksList"),
    sideCards: document.querySelector(".adash-side-cards"),
    modalEl: document.getElementById("adashBankSourceModal"),
    title: document.getElementById("adashBankSourceTitle"),
    sub: document.getElementById("adashBankSourceSub"),
    meta: document.getElementById("adashBankSourceMeta"),
    closing: document.getElementById("adashBankSourceClosing"),
    body: document.getElementById("adashSourceGridBody"),
    empty: document.getElementById("adashSourceEmpty"),
    count: document.getElementById("adashSourceCount"),
    grid: document.getElementById("adashSourceGrid"),
    metricModalEl: document.getElementById("adashMetricModal"),
    metricTitle: document.getElementById("adashMetricTitle"),
    metricSub: document.getElementById("adashMetricSub"),
    metricFormula: document.getElementById("adashMetricFormula"),
    metricTotal: document.getElementById("adashMetricTotal"),
    metricBody: document.getElementById("adashMetricGridBody"),
    metricEmpty: document.getElementById("adashMetricEmpty"),
    metricCount: document.getElementById("adashMetricCount"),
    metricGrid: document.getElementById("adashMetricGrid"),
  };

  const modal = els.modalEl && window.bootstrap ? new bootstrap.Modal(els.modalEl) : null;
  const metricModal =
    els.metricModalEl && window.bootstrap ? new bootstrap.Modal(els.metricModalEl) : null;

  let allRows = [];
  let gridSortKey = "entry_date";
  let gridSortDir = "asc";
  const gridFilters = {};

  let metricRows = [];
  let metricSortKey = "entry_date";
  let metricSortDir = "desc";
  const metricFilters = {};

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatMoney(value) {
    const num = Number(value || 0);
    return num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function apiUrl(accountId) {
    return String(cfg.bankSourceUrl || "").replace("/0", "/" + String(accountId));
  }

  async function parseJsonResponse(res) {
    const contentType = res.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      throw new Error("Server returned an unexpected response. Refresh and try again.");
    }
    const data = await res.json();
    if (!res.ok || data.ok === false) {
      throw new Error(data.error || ("Request failed (HTTP " + res.status + ")."));
    }
    return data;
  }

  function readFiltersFromDom(selector, store) {
    Object.keys(store).forEach(function (key) {
      delete store[key];
    });
    document.querySelectorAll(selector).forEach(function (input) {
      const key = input.dataset.filterKey;
      if (!key) return;
      store[key] = (input.value || "").trim().toLowerCase();
    });
  }

  function hasActiveFilters(store) {
    return Object.keys(store).some(function (key) {
      return !!store[key];
    });
  }

  function rowFilterValue(row, key, moneyKeys) {
    if (moneyKeys[key]) {
      return formatMoney(row[key]);
    }
    return String(row[key] == null ? "" : row[key]);
  }

  function rowMatchesFilters(row, store, moneyKeys) {
    if (!hasActiveFilters(store)) return true;
    return Object.keys(store).every(function (key) {
      const needle = store[key];
      if (!needle) return true;
      return rowFilterValue(row, key, moneyKeys).toLowerCase().indexOf(needle) !== -1;
    });
  }

  function sortValue(row, key, moneyKeys) {
    if (moneyKeys[key]) {
      return Number(row[key] || 0);
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

  function prepareRows(rows, store, sortKey, sortDir, moneyKeys) {
    let prepared = (rows || []).filter(function (row) {
      return rowMatchesFilters(row, store, moneyKeys);
    });
    if (sortKey) {
      prepared = prepared.slice().sort(function (a, b) {
        return compareSortValues(
          sortValue(a, sortKey, moneyKeys),
          sortValue(b, sortKey, moneyKeys),
          sortDir
        );
      });
    }
    return prepared;
  }

  function updateSortHeaders(gridSelector, sortKey, sortDir) {
    document.querySelectorAll(gridSelector + " thead th.adash-sortable").forEach(function (th) {
      const key = th.dataset.sortKey;
      const icon = th.querySelector(".adash-sort-icon");
      const active = key === sortKey;
      th.classList.toggle("adash-sorted", active);
      th.setAttribute(
        "aria-sort",
        active ? (sortDir === "asc" ? "ascending" : "descending") : "none"
      );
      if (icon) {
        icon.textContent = active ? (sortDir === "asc" ? " ▲" : " ▼") : "";
      }
    });
  }

  const bankMoneyKeys = { debit: true, credit: true, running_balance: true, net: true };
  const metricMoneyKeys = { amount: true };

  function renderSourceRows() {
    const visible = prepareRows(allRows, gridFilters, gridSortKey, gridSortDir, bankMoneyKeys);
    if (!els.body) return;
    els.body.innerHTML = "";
    if (!visible.length) {
      if (els.empty) els.empty.classList.remove("d-none");
      if (els.count) {
        els.count.textContent = allRows.length
          ? "0 of " + allRows.length + " rows"
          : "0 rows";
      }
      updateSortHeaders("#adashSourceGrid", gridSortKey, gridSortDir);
      return;
    }
    if (els.empty) els.empty.classList.add("d-none");
    if (els.count) {
      els.count.textContent =
        visible.length === allRows.length
          ? visible.length + " row" + (visible.length === 1 ? "" : "s")
          : visible.length + " of " + allRows.length + " rows";
    }

    visible.forEach(function (row) {
      const tr = document.createElement("tr");
      if (row.is_opening) tr.className = "adash-opening-row";
      const debitVal = Number(row.debit || 0);
      const creditVal = Number(row.credit || 0);
      const debitClass = debitVal > 0 ? " text-end adash-debit-in" : " text-end";
      const creditClass = creditVal > 0 ? " text-end adash-credit-out" : " text-end";
      tr.innerHTML =
        "<td>" + escapeHtml(row.entry_date) + "</td>" +
        "<td>" + escapeHtml(row.description) + "</td>" +
        "<td>" + escapeHtml(row.source_module) + "</td>" +
        "<td>" + escapeHtml(row.source_type) + "</td>" +
        "<td>" + escapeHtml(row.reference) + "</td>" +
        '<td class="' + debitClass.trim() + '">₹ ' + escapeHtml(formatMoney(row.debit)) + "</td>" +
        '<td class="' + creditClass.trim() + '">₹ ' + escapeHtml(formatMoney(row.credit)) + "</td>" +
        '<td class="text-end">₹ ' + escapeHtml(formatMoney(row.running_balance)) + "</td>" +
        "<td>" + escapeHtml(row.entered_by || "") + "</td>";
      els.body.appendChild(tr);
    });
    updateSortHeaders("#adashSourceGrid", gridSortKey, gridSortDir);
  }

  function refreshSourceGrid() {
    readFiltersFromDom("#adashSourceGrid .adash-col-filter", gridFilters);
    renderSourceRows();
  }

  function onGridSortHeader(sortKey) {
    if (!sortKey) return;
    if (gridSortKey === sortKey) {
      gridSortDir = gridSortDir === "asc" ? "desc" : "asc";
    } else {
      gridSortKey = sortKey;
      gridSortDir = "asc";
    }
    refreshSourceGrid();
  }

  function renderMetricRows() {
    const visible = prepareRows(
      metricRows,
      metricFilters,
      metricSortKey,
      metricSortDir,
      metricMoneyKeys
    );
    if (!els.metricBody) return;
    els.metricBody.innerHTML = "";
    if (!visible.length) {
      if (els.metricEmpty) els.metricEmpty.classList.remove("d-none");
      if (els.metricCount) {
        els.metricCount.textContent = metricRows.length
          ? "0 of " + metricRows.length + " entries"
          : "0 entries";
      }
      updateSortHeaders("#adashMetricGrid", metricSortKey, metricSortDir);
      return;
    }
    if (els.metricEmpty) els.metricEmpty.classList.add("d-none");
    if (els.metricCount) {
      els.metricCount.textContent =
        visible.length === metricRows.length
          ? visible.length + " entr" + (visible.length === 1 ? "y" : "ies")
          : visible.length + " of " + metricRows.length + " entries";
    }

    visible.forEach(function (row) {
      const tr = document.createElement("tr");
      const amount = Number(row.amount || 0);
      const amountClass = amount < 0 ? "text-end adash-amount-neg" : "text-end";
      const openCell =
        row.can_open && row.source_url
          ? '<a class="btn btn-outline-primary btn-sm" href="' +
            escapeHtml(row.source_url) +
            '" target="_blank" rel="noopener noreferrer" title="Open source entry"><i class="bi bi-box-arrow-up-right"></i></a>'
          : '<span class="text-muted">—</span>';
      tr.innerHTML =
        "<td>" + escapeHtml(row.entry_date) + "</td>" +
        "<td>" + escapeHtml(row.source || "") + "</td>" +
        "<td>" + escapeHtml(row.reference || "") + "</td>" +
        "<td>" + escapeHtml(row.work || "") + "</td>" +
        "<td>" + escapeHtml(row.customer || "") + "</td>" +
        "<td>" + escapeHtml(row.description || "") + "</td>" +
        '<td class="' + amountClass + '">₹ ' + escapeHtml(formatMoney(row.amount)) + "</td>" +
        "<td>" + openCell + "</td>";
      els.metricBody.appendChild(tr);
    });
    updateSortHeaders("#adashMetricGrid", metricSortKey, metricSortDir);
  }

  function refreshMetricGrid() {
    readFiltersFromDom("#adashMetricGrid .adash-col-filter", metricFilters);
    renderMetricRows();
  }

  function onMetricSortHeader(sortKey) {
    if (!sortKey) return;
    if (metricSortKey === sortKey) {
      metricSortDir = metricSortDir === "asc" ? "desc" : "asc";
    } else {
      metricSortKey = sortKey;
      metricSortDir = sortKey === "amount" || sortKey === "entry_date" ? "desc" : "asc";
    }
    refreshMetricGrid();
  }

  async function openBankSource(accountId, label) {
    if (!accountId) return;
    if (els.title) els.title.textContent = label || "Bank Source Ledger";
    if (els.sub) els.sub.textContent = "Loading source ledger…";
    if (els.meta) els.meta.textContent = "";
    if (els.closing) els.closing.textContent = "";
    if (els.body) els.body.innerHTML = "";
    if (els.empty) els.empty.classList.add("d-none");
    if (modal) modal.show();

    const url = new URL(apiUrl(accountId), window.location.origin);
    if (cfg.asOf) url.searchParams.set("as_of", cfg.asOf);
    const res = await fetch(url.toString(), { headers: { Accept: "application/json" } });
    const data = await parseJsonResponse(res);

    allRows = data.rows || [];
    gridSortKey = "entry_date";
    gridSortDir = "asc";
    document.querySelectorAll("#adashSourceGrid .adash-col-filter").forEach(function (input) {
      input.value = "";
    });

    if (els.title) els.title.textContent = data.label || label || "Bank Source Ledger";
    if (els.sub) {
      els.sub.textContent = "As of " + (data.as_of || cfg.asOf || "") + " · where this closing balance comes from";
    }
    if (els.meta) {
      els.meta.textContent =
        "Opening ₹ " + formatMoney(data.opening_balance) +
        " · Movements through " + (data.as_of || "");
    }
    if (els.closing) {
      els.closing.textContent = "Closing ₹ " + formatMoney(data.closing_balance);
    }
    refreshSourceGrid();
  }

  async function openMetricDetails(metricKey, label) {
    if (!metricKey || !cfg.metricDetailsUrl) return;
    if (els.metricTitle) els.metricTitle.textContent = label || "Metric Entries";
    if (els.metricSub) els.metricSub.textContent = "Loading entries…";
    if (els.metricFormula) els.metricFormula.textContent = "";
    if (els.metricTotal) els.metricTotal.textContent = "";
    if (els.metricBody) els.metricBody.innerHTML = "";
    if (els.metricEmpty) els.metricEmpty.classList.add("d-none");
    if (metricModal) metricModal.show();

    const url = new URL(cfg.metricDetailsUrl, window.location.origin);
    url.searchParams.set("metric", metricKey);
    if (cfg.dateFrom) url.searchParams.set("from", cfg.dateFrom);
    if (cfg.dateTo) url.searchParams.set("to", cfg.dateTo);

    const res = await fetch(url.toString(), { headers: { Accept: "application/json" } });
    const data = await parseJsonResponse(res);

    metricRows = data.rows || [];
    metricSortKey = "entry_date";
    metricSortDir = "desc";
    document.querySelectorAll("#adashMetricGrid .adash-col-filter").forEach(function (input) {
      input.value = "";
    });

    if (els.metricTitle) els.metricTitle.textContent = data.metric_label || label || "Metric Entries";
    if (els.metricSub) {
      els.metricSub.textContent =
        "Period " + (data.date_from || cfg.dateFrom || "") +
        " — " + (data.date_to || cfg.dateTo || "") +
        " · entry-level source for this total";
    }
    if (els.metricFormula) {
      els.metricFormula.textContent = data.formula || "Contributing entries for this metric";
    }
    if (els.metricTotal) {
      els.metricTotal.textContent = "Total ₹ " + formatMoney(data.total);
    }
    refreshMetricGrid();
  }

  if (els.banksList) {
    els.banksList.addEventListener("click", function (ev) {
      const btn = ev.target.closest(".adash-bank-row");
      if (!btn || !els.banksList.contains(btn)) return;
      openBankSource(btn.dataset.accountId, btn.dataset.label).catch(function (err) {
        alert(err.message || "Unable to load bank source.");
      });
    });
  }

  if (els.sideCards) {
    els.sideCards.addEventListener("click", function (ev) {
      const btn = ev.target.closest(".adash-mini-card[data-metric]");
      if (!btn || !els.sideCards.contains(btn)) return;
      openMetricDetails(btn.dataset.metric, btn.dataset.label).catch(function (err) {
        alert(err.message || "Unable to load metric entries.");
      });
    });
  }

  if (els.grid) {
    els.grid.addEventListener("click", function (ev) {
      const th = ev.target.closest("th.adash-sortable");
      if (th && els.grid.contains(th)) {
        onGridSortHeader(th.dataset.sortKey);
      }
    });
    els.grid.addEventListener("keydown", function (ev) {
      if (ev.key !== "Enter" && ev.key !== " ") return;
      const th = ev.target.closest("th.adash-sortable");
      if (!th || !els.grid.contains(th)) return;
      ev.preventDefault();
      onGridSortHeader(th.dataset.sortKey);
    });
    els.grid.addEventListener("input", function (ev) {
      if (ev.target.classList.contains("adash-col-filter")) {
        refreshSourceGrid();
      }
    });
  }

  if (els.metricGrid) {
    els.metricGrid.addEventListener("click", function (ev) {
      const th = ev.target.closest("th.adash-sortable");
      if (th && els.metricGrid.contains(th)) {
        onMetricSortHeader(th.dataset.sortKey);
      }
    });
    els.metricGrid.addEventListener("keydown", function (ev) {
      if (ev.key !== "Enter" && ev.key !== " ") return;
      const th = ev.target.closest("th.adash-sortable");
      if (!th || !els.metricGrid.contains(th)) return;
      ev.preventDefault();
      onMetricSortHeader(th.dataset.sortKey);
    });
    els.metricGrid.addEventListener("input", function (ev) {
      if (ev.target.classList.contains("adash-col-filter")) {
        refreshMetricGrid();
      }
    });
  }

  function statusBadge(status) {
    const s = String(status || "").toUpperCase();
    if (s === "SUCCESS") return '<span class="badge text-bg-success">SUCCESS</span>';
    if (s === "FIRST_SET") return '<span class="badge text-bg-success">FIRST_SET</span>';
    if (s === "RESET") return '<span class="badge text-bg-warning">RESET</span>';
    return '<span class="badge text-bg-danger">' + escapeHtml(s || "FAILED") + "</span>";
  }

  async function refreshActivityCard(card) {
    if (!card) return;
    const kind = card.getAttribute("data-adash-activity");
    const api = card.getAttribute("data-api-url");
    const body = card.querySelector("[data-adash-activity-body]");
    if (!api || !body) return;
    const periodEl = card.querySelector(".adash-activity-period");
    const searchEl = card.querySelector(".adash-activity-search");
    const period = periodEl ? periodEl.value : "all";
    const q = searchEl ? searchEl.value.trim() : "";
    const url = new URL(api, window.location.origin);
    url.searchParams.set("limit", "10");
    url.searchParams.set("period", period);
    if (q) url.searchParams.set("q", q);
    try {
      const res = await fetch(url.toString(), {
        credentials: "same-origin",
        headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await parseJsonResponse(res);
      const rows = data.rows || [];
      if (!rows.length) {
        const cols = kind === "password-events" ? 3 : 4;
        body.innerHTML =
          '<tr class="adash-activity-empty"><td colspan="' +
          cols +
          '" class="text-muted small">No records for this filter.</td></tr>';
        return;
      }
      if (kind === "password-events") {
        body.innerHTML = rows
          .map(function (r) {
            return (
              "<tr><td>" +
              escapeHtml(r.user_id) +
              "</td><td>" +
              statusBadge(r.event_type) +
              "</td><td>" +
              escapeHtml(r.event_time) +
              "</td></tr>"
            );
          })
          .join("");
      } else {
        body.innerHTML = rows
          .map(function (r) {
            return (
              "<tr><td>" +
              escapeHtml(r.user_id) +
              "</td><td>" +
              escapeHtml(r.login_time) +
              "</td><td>" +
              escapeHtml(r.ip_address) +
              "</td><td>" +
              statusBadge(r.status) +
              "</td></tr>"
            );
          })
          .join("");
      }
      const exportBtn = card.querySelector("[data-adash-export]");
      if (exportBtn && cfg.loginsExportUrl) {
        const exp = new URL(cfg.loginsExportUrl, window.location.origin);
        exp.searchParams.set("period", period);
        if (q) exp.searchParams.set("q", q);
        exportBtn.setAttribute("href", exp.pathname + exp.search);
      }
    } catch (err) {
      body.innerHTML =
        '<tr><td colspan="4" class="text-danger small">' +
        escapeHtml(err.message || "Unable to refresh") +
        "</td></tr>";
    }
  }

  function initActivityCards() {
    const cards = document.querySelectorAll("[data-adash-activity]");
    if (!cards.length) return;
    function refreshAll() {
      cards.forEach(refreshActivityCard);
    }
    cards.forEach(function (card) {
      const periodEl = card.querySelector(".adash-activity-period");
      const searchEl = card.querySelector(".adash-activity-search");
      if (periodEl) periodEl.addEventListener("change", function () { refreshActivityCard(card); });
      if (searchEl) {
        let t = null;
        searchEl.addEventListener("input", function () {
          window.clearTimeout(t);
          t = window.setTimeout(function () { refreshActivityCard(card); }, 300);
        });
      }
    });
    window.setInterval(refreshAll, 30000);
  }

  initActivityCards();
})();
