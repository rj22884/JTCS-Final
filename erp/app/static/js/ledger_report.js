(function () {
  "use strict";

  const cfg = window.LEDGER_REPORT;
  if (!cfg) return;

  const els = {
    dateFrom: document.getElementById("ledgerDateFrom"),
    dateTo: document.getElementById("ledgerDateTo"),
    kind: document.getElementById("ledgerKind"),
    search: document.getElementById("ledgerSearch"),
    searchBtn: document.getElementById("ledgerSearchBtn"),
    refreshBtn: document.getElementById("ledgerRefreshBtn"),
    body: document.getElementById("ledgerGridBody"),
    count: document.getElementById("ledgerCount"),
    previewModalEl: document.getElementById("ledgerPreviewModal"),
    previewDialog: document.getElementById("ledgerPreviewDialog"),
    previewTitle: document.getElementById("ledgerPreviewModalTitle"),
    previewBody: document.getElementById("ledgerPreviewBody"),
    maximizeBtn: document.getElementById("ledgerMaximizeBtn"),
    maximizeIcon: document.getElementById("ledgerMaximizeIcon"),
    exportBtn: document.getElementById("ledgerExportBtn"),
    summaryBsBody: document.getElementById("ledgerSummaryBsBody"),
    summaryPlBody: document.getElementById("ledgerSummaryPlBody"),
    summaryBsPeriod: document.getElementById("ledgerSummaryBsPeriod"),
    summaryPlPeriod: document.getElementById("ledgerSummaryPlPeriod"),
  };

  const previewModal =
    els.previewModalEl && window.bootstrap
      ? bootstrap.Modal.getOrCreateInstance(els.previewModalEl)
      : null;

  let searchTimer = null;
  let currentKind = "";
  let currentId = "";
  let isMaximized = false;
  let currentRows = [];
  let lastKind = "all";
  let lastSearch = "";
  let sortState = { key: "closing", dir: "desc" };
  const GRID_COLSPAN = 6;

  const KIND_LABELS = {
    bank: "Bank",
    customer: "Customer",
    work: "Work / Category",
    item: "Item",
  };

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function previewUrl(kind, id) {
    return String(cfg.previewUrl || "").replace(
      /\/preview\/[^/]+\/0(?=$|[/?#])/,
      "/preview/" + encodeURIComponent(kind) + "/" + String(id)
    );
  }

  function exportUrl(kind, id, fmt) {
    return String(cfg.exportUrl || "")
      .replace(
        /\/export\/[^/]+\/0\/pdf(?=$|[/?#])/,
        "/export/" + encodeURIComponent(kind) + "/" + String(id) + "/" + encodeURIComponent(fmt)
      )
      .replace(
        /\/export\/[^/]+\/0\/[^/?#]+(?=$|[/?#])/,
        "/export/" + encodeURIComponent(kind) + "/" + String(id) + "/" + encodeURIComponent(fmt)
      );
  }

  function dateQuery() {
    if (window.JTCSLedgerPreview && typeof window.JTCSLedgerPreview.dateQuery === "function") {
      return window.JTCSLedgerPreview.dateQuery();
    }
    const params = new URLSearchParams();
    const from = (els.dateFrom?.value || "").trim();
    const to = (els.dateTo?.value || "").trim();
    if (from) params.set("date_from", from);
    if (to) params.set("date_to", to);
    const q = params.toString();
    return q ? "?" + q : "";
  }

  function setExportEnabled(enabled) {
    if (els.exportBtn) els.exportBtn.disabled = !enabled;
  }

  function setMaximized(next) {
    isMaximized = !!next;
    if (els.previewDialog) {
      els.previewDialog.classList.toggle("ledger-modal-maximized", isMaximized);
    }
    if (els.previewModalEl) {
      els.previewModalEl.classList.toggle("ledger-modal-is-max", isMaximized);
    }
    if (els.maximizeBtn) {
      els.maximizeBtn.title = isMaximized ? "Restore" : "Maximize";
      els.maximizeBtn.setAttribute("aria-label", isMaximized ? "Restore" : "Maximize");
    }
    if (els.maximizeIcon) {
      els.maximizeIcon.className = isMaximized
        ? "bi bi-fullscreen-exit"
        : "bi bi-arrows-fullscreen";
    }
  }

  function emptyMessage(kind, search) {
    return "No ledgers found.";
  }

  function emptyRow(message, danger) {
    return (
      '<tr><td colspan="' +
      GRID_COLSPAN +
      '" class="text-center ' +
      (danger ? "text-danger" : "text-muted") +
      ' py-4">' +
      message +
      "</td></tr>"
    );
  }

  function formatMoney(value) {
    const num = parseFloat(value);
    if (Number.isNaN(num)) return "₹ 0.00";
    const abs = Math.abs(num).toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    return (num < 0 ? "-₹ " : "₹ ") + abs;
  }

  function formatClosing(row) {
    const value = row && typeof row === "object" ? row.closing : row;
    if (value == null || value === "") {
      return '<span class="text-muted">—</span>';
    }
    const num = parseFloat(value);
    if (Number.isNaN(num) || Math.abs(num) < 0.005) {
      return '<span class="lr-no-overdue">No overdue</span>';
    }
    const side = String((row && row.closing_dr_cr) || "").trim().toUpperCase();
    const cls = side === "DR" ? "lr-dr-balance" : side === "CR" ? "lr-cr-balance" : "";
    const suffix = side === "DR" ? " Dr" : side === "CR" ? " Cr" : "";
    return (
      '<span class="' +
      cls +
      '">' +
      escapeHtml(formatMoney(Math.abs(num)) + suffix) +
      "</span>"
    );
  }

  function formatDisplayDate(value) {
    if (!value) return "";
    if (window.formatDisplaySmart) return window.formatDisplaySmart(value);
    if (window.formatDisplayDate) return window.formatDisplayDate(value);
    return String(value);
  }

  function summaryRow(label, amount, extraClass) {
    const num = parseFloat(amount);
    const cls = extraClass ? " lr-summary-row " + extraClass : " lr-summary-row";
    const valueHtml =
      amount === "" || amount == null
        ? ""
        : escapeHtml(formatMoney(Number.isNaN(num) ? 0 : num));
    return (
      '<div class="' +
      cls.trim() +
      '"><span>' +
      escapeHtml(label) +
      "</span><span>" +
      valueHtml +
      "</span></div>"
    );
  }

  function renderSummaries(data) {
    const bs = (data && data.balance_sheet) || {};
    const pl = (data && data.profit_loss) || {};
    const period =
      formatDisplayDate(data && data.date_from) +
      " to " +
      formatDisplayDate(data && data.date_to);
    if (els.summaryBsPeriod) els.summaryBsPeriod.textContent = "As of " + formatDisplayDate(data && data.date_to);
    if (els.summaryPlPeriod) els.summaryPlPeriod.textContent = period;

    let bsHtml = summaryRow("Liabilities", "", "is-section");
    (bs.liabilities || []).forEach(function (line) {
      bsHtml += summaryRow(line.name || "—", line.amount);
    });
    bsHtml += summaryRow("Total Liabilities", bs.liabilities_total, "is-total");
    bsHtml += summaryRow("Assets", "", "is-section");
    (bs.assets || []).forEach(function (line) {
      bsHtml += summaryRow(line.name || "—", line.amount);
    });
    bsHtml += summaryRow("Total Assets", bs.assets_total, "is-total");
    const diff = parseFloat(bs.difference);
    bsHtml += summaryRow(
      "Difference",
      bs.difference,
      bs.balanced || Math.abs(diff) < 0.005 ? "is-total" : "is-total is-unbalanced"
    );
    if (els.summaryBsBody) els.summaryBsBody.innerHTML = bsHtml;

    const gross = parseFloat(pl.gross_profit);
    const net = parseFloat(pl.net_profit);
    let plHtml = "";
    plHtml += summaryRow("Direct Income", pl.direct_income);
    plHtml += summaryRow("Direct Expenses", pl.direct_expenses);
    plHtml += summaryRow(
      gross < 0 ? "Gross Loss" : "Gross Profit",
      Number.isNaN(gross) ? 0 : Math.abs(gross),
      gross < 0 ? "is-total is-loss" : "is-total is-profit"
    );
    plHtml += summaryRow("Indirect Income", pl.indirect_income);
    plHtml += summaryRow("Indirect Expenses", pl.indirect_expenses);
    plHtml += summaryRow(
      net < 0 ? "Net Loss" : "Net Profit",
      Number.isNaN(net) ? 0 : Math.abs(net),
      net < 0 ? "is-total is-loss" : "is-total is-profit"
    );
    if (els.summaryPlBody) els.summaryPlBody.innerHTML = plHtml;
  }

  function loadSummaries() {
    if (!cfg.summaryUrl || !els.summaryBsBody) return;
    const params = new URLSearchParams();
    const from = (els.dateFrom?.value || "").trim();
    const to = (els.dateTo?.value || "").trim();
    if (from) params.set("date_from", from);
    if (to) params.set("date_to", to);
    const empty = '<div class="lr-summary-empty text-muted">Unable to load summary.</div>';
    return fetch(cfg.summaryUrl + "?" + params.toString(), {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load summaries.");
          renderSummaries(data.summaries || {});
        });
      })
      .catch(function () {
        if (els.summaryBsBody) els.summaryBsBody.innerHTML = empty;
        if (els.summaryPlBody) els.summaryPlBody.innerHTML = empty;
      });
  }

  function sortRows(rows) {
    if (!sortState.key) return rows.slice();
    const key = sortState.key;
    const dir = sortState.dir === "asc" ? 1 : -1;
    const numeric = key === "txn_count" || key === "closing";
    return rows.slice().sort(function (a, b) {
      let av = a[key];
      let bv = b[key];
      if (numeric) {
        av = parseFloat(av);
        bv = parseFloat(bv);
        if (Number.isNaN(av)) av = 0;
        if (Number.isNaN(bv)) bv = 0;
        if (av === bv) return String(a.label || "").localeCompare(String(b.label || ""));
        return (av - bv) * dir;
      }
      av = String(av == null ? "" : av).toLowerCase();
      bv = String(bv == null ? "" : bv).toLowerCase();
      if (av === bv) return String(a.label || "").localeCompare(String(b.label || ""));
      return av < bv ? -1 * dir : 1 * dir;
    });
  }

  function syncSortHeaders() {
    document.querySelectorAll("#ledgerReportGrid th.lr-sortable").forEach(function (th) {
      const key = th.getAttribute("data-sort-key") || "";
      const active = key === sortState.key;
      th.classList.toggle("is-sorted", active);
      const icon = th.querySelector(".lr-sort-icon");
      if (!icon) return;
      icon.className =
        "bi lr-sort-icon " +
        (active ? (sortState.dir === "asc" ? "bi-sort-up" : "bi-sort-down") : "bi-arrow-down-up");
    });
  }

  function renderRows(rows, kind, search) {
    if (!els.body) return;
    lastKind = kind;
    lastSearch = search;
    currentRows = rows || [];
    if (!currentRows.length) {
      els.body.innerHTML = emptyRow(escapeHtml(emptyMessage(kind, search)));
      if (els.count) els.count.textContent = "0 ledgers";
      syncSortHeaders();
      return;
    }
    if (els.count) {
      els.count.textContent = currentRows.length + " ledger" + (currentRows.length === 1 ? "" : "s");
    }
    els.body.innerHTML = sortRows(currentRows)
      .map(function (row) {
        const typeLabel = KIND_LABELS[row.kind] || row.kind || "—";
        return (
          "<tr>" +
          '<td class="lr-col-fit"><span class="badge text-bg-light border ledger-kind-badge">' +
          escapeHtml(typeLabel) +
          "</span></td>" +
          '<td class="lr-col-ledger"><strong>' +
          escapeHtml(row.label || "—") +
          "</strong>" +
          (row.active === false
            ? ' <span class="badge text-bg-secondary ms-1">Inactive</span>'
            : "") +
          "</td>" +
          '<td class="lr-col-fit">' +
          escapeHtml(row.subtitle || "—") +
          "</td>" +
          '<td class="lr-col-fit text-end">' +
          escapeHtml(row.txn_count == null ? "—" : row.txn_count) +
          "</td>" +
          '<td class="lr-col-fit text-end">' +
          formatClosing(row) +
          "</td>" +
          '<td class="lr-col-fit text-end">' +
          '<button type="button" class="btn btn-outline-info btn-sm ledger-preview-btn" data-kind="' +
          escapeHtml(row.kind) +
          '" data-id="' +
          escapeHtml(row.id) +
          '"><i class="bi bi-eye"></i> Preview</button>' +
          "</td>" +
          "</tr>"
        );
      })
      .join("");
    syncSortHeaders();
  }

  function loadLedgers() {
    const kind = (els.kind?.value || "all").trim().toLowerCase();
    const search = (els.search?.value || "").trim();

    const params = new URLSearchParams();
    params.set("kind", kind);
    if (search) params.set("search", search);
    const from = (els.dateFrom?.value || "").trim();
    const to = (els.dateTo?.value || "").trim();
    if (from) params.set("date_from", from);
    if (to) params.set("date_to", to);
    const url = cfg.searchUrl + "?" + params.toString();

    if (els.count) els.count.textContent = "Searching…";
    return fetch(url, {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Unable to search ledgers.");
          renderRows(data.rows || [], kind, search);
        });
      })
      .catch(function (err) {
        currentRows = [];
        if (els.body) {
          els.body.innerHTML = emptyRow(
            escapeHtml(err.message || "Unable to search ledgers."),
            true
          );
        }
        if (els.count) els.count.textContent = "Error";
      });
  }

  async function openPreview(kind, id) {
    if (!previewModal || !els.previewBody) {
      alert("Preview is not available.");
      return;
    }
    const url = previewUrl(kind, id);
    if (!url) {
      alert("Preview URL is not configured.");
      return;
    }
    currentKind = kind;
    currentId = String(id);
    setExportEnabled(false);
    setMaximized(false);
    if (els.previewTitle) els.previewTitle.textContent = "Ledger Preview";
    const qs = dateQuery();
    els.previewBody.innerHTML =
      '<div class="text-muted small py-4 text-center">Loading preview…</div>';
    previewModal.show();
    try {
      const res = await fetch(url + qs, {
        headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load preview.");
      els.previewBody.innerHTML = data.html || "";
      if (els.previewTitle) {
        const bits = [data.title || "Ledger Preview"];
        if (data.entity_name) bits.push(data.entity_name);
        els.previewTitle.textContent = bits.join(" — ");
      }
      setExportEnabled(true);
      if (window.JTCSLedgerPreview && typeof window.JTCSLedgerPreview.afterRender === "function") {
        window.JTCSLedgerPreview.afterRender();
      }
    } catch (err) {
      currentKind = "";
      currentId = "";
      setExportEnabled(false);
      els.previewBody.innerHTML =
        '<div class="alert alert-danger mb-0">' +
        escapeHtml(err.message || "Unable to load preview.") +
        "</div>";
    }
  }

  function downloadExport(fmt) {
    if (!currentKind || !currentId) {
      alert("Open a ledger preview before exporting.");
      return;
    }
    const url = exportUrl(currentKind, currentId, fmt);
    if (!url) {
      alert("Export URL is not configured.");
      return;
    }
    window.location.href = url + dateQuery();
  }

  function onSortHeader(event) {
    const th = event.target.closest("th.lr-sortable");
    if (!th) return;
    event.preventDefault();
    const key = th.getAttribute("data-sort-key") || "";
    if (!key) return;
    if (sortState.key === key) {
      sortState.dir = sortState.dir === "asc" ? "desc" : "asc";
    } else {
      sortState.key = key;
      sortState.dir = key === "txn_count" || key === "closing" ? "desc" : "asc";
    }
    renderRows(currentRows, lastKind, lastSearch);
  }

  function onGridClick(event) {
    const btn = event.target.closest(".ledger-preview-btn");
    if (!btn) return;
    event.preventDefault();
    const kind = btn.getAttribute("data-kind") || "";
    const id = btn.getAttribute("data-id");
    if (!kind || !id) return;
    openPreview(kind, id);
  }

  function onExportClick(event) {
    const opt = event.target.closest(".ledger-export-opt");
    if (!opt) return;
    event.preventDefault();
    const fmt = (opt.getAttribute("data-fmt") || "").toLowerCase();
    if (!fmt) return;
    downloadExport(fmt);
  }

  function scheduleSearch() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadLedgers, 280);
  }

  els.search?.addEventListener("input", scheduleSearch);
  els.search?.addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
      event.preventDefault();
      clearTimeout(searchTimer);
      loadLedgers();
    }
  });
  els.searchBtn?.addEventListener("click", function () {
    clearTimeout(searchTimer);
    loadLedgers();
  });
  els.refreshBtn?.addEventListener("click", function () {
    loadLedgers();
    loadSummaries();
  });
  els.kind?.addEventListener("change", function () {
    clearTimeout(searchTimer);
    loadLedgers();
  });
  els.dateFrom?.addEventListener("change", function () {
    clearTimeout(searchTimer);
    loadLedgers();
    loadSummaries();
  });
  els.dateTo?.addEventListener("change", function () {
    clearTimeout(searchTimer);
    loadLedgers();
    loadSummaries();
  });
  document.getElementById("ledgerReportGrid")?.addEventListener("click", onSortHeader);
  document.getElementById("ledgerReportGrid")?.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    const th = event.target.closest("th.lr-sortable");
    if (!th) return;
    event.preventDefault();
    onSortHeader(event);
  });
  els.body?.addEventListener("click", onGridClick);
  els.maximizeBtn?.addEventListener("click", function () {
    setMaximized(!isMaximized);
  });
  els.previewModalEl?.addEventListener("click", onExportClick);
  els.previewModalEl?.addEventListener("hidden.bs.modal", function () {
    setMaximized(false);
    setExportEnabled(false);
    currentKind = "";
    currentId = "";
  });

  loadLedgers();
  loadSummaries();

  if (window.JTCSLedgerPreview && typeof window.JTCSLedgerPreview.setReloader === "function") {
    window.JTCSLedgerPreview.setReloader(function () {
      if (currentKind && currentId) openPreview(currentKind, currentId);
    });
  }
})();
