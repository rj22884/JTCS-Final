(function () {
  "use strict";

  const api = window.FS_API;
  const ViewManager = window.FinancialViewManager;
  if (!api || !ViewManager) return;

  const els = {
    title: document.getElementById("fsReportTitle"),
    body: document.getElementById("fsReportBody"),
    meta: document.getElementById("fsMeta"),
    status: document.getElementById("fsStatus"),
    dateFrom: document.getElementById("fsDateFrom"),
    dateTo: document.getElementById("fsDateTo"),
    search: document.getElementById("fsSearch"),
    refreshBtn: document.getElementById("fsRefreshBtn"),
    printBtn: document.getElementById("fsPrintBtn"),
    pdfBtn: document.getElementById("fsPdfBtn"),
    excelBtn: document.getElementById("fsExcelBtn"),
    viewHorizontalBtn: document.getElementById("fsViewHorizontalBtn"),
    viewVerticalBtn: document.getElementById("fsViewVerticalBtn"),
    drillModalEl: document.getElementById("fsDrillModal"),
    drillTitle: document.getElementById("fsDrillTitle"),
    drillBody: document.getElementById("fsDrillBody"),
  };

  let activeReport = window.FS_ACTIVE_REPORT || "balance-sheet";
  let searchTimer = null;
  let lastReport = null;
  const drillModal =
    els.drillModalEl && window.bootstrap ? new bootstrap.Modal(els.drillModalEl) : null;

  function updateMetaViewLabel() {
    if (!els.meta || !lastReport) return;
    const meta = lastReport.meta || {};
    const base =
      (meta.fy_label || "") +
      "  ·  " +
      (meta.date_from || "") +
      " to " +
      (meta.date_to || "");
    els.meta.textContent =
      base +
      "  ·  " +
      (ViewManager.getMode() === ViewManager.VERTICAL ? "Vertical" : "Horizontal") +
      " view";
  }

  ViewManager.bindToggle({
    horizontalBtn: els.viewHorizontalBtn,
    verticalBtn: els.viewVerticalBtn,
    onChange: function () {
      if (lastReport) {
        paintReport(lastReport, { preserveState: true });
        updateMetaViewLabel();
      }
    },
  });

  function reportUrl(template, key) {
    return String(template || "").replace("__KEY__", encodeURIComponent(key));
  }

  function escapeHtml(value) {
    return ViewManager.escapeHtml(value);
  }

  function money(value) {
    return ViewManager.money(value);
  }

  function showStatus(message, type) {
    if (!els.status) return;
    if (!message) {
      els.status.classList.add("d-none");
      els.status.textContent = "";
      return;
    }
    els.status.textContent = message;
    els.status.className = "alert py-2 small mb-2 alert-" + (type || "info");
    els.status.classList.remove("d-none");
  }

  function queryParams() {
    const params = new URLSearchParams();
    if (els.dateFrom?.value) params.set("date_from", els.dateFrom.value);
    if (els.dateTo?.value) params.set("date_to", els.dateTo.value);
    const q = (els.search?.value || "").trim();
    if (q) params.set("search", q);
    params.set("view", ViewManager.getMode());
    return params;
  }

  function captureUiState() {
    const collapsed = [];
    els.body?.querySelectorAll(".fs-children.collapsed").forEach(function (el) {
      if (el.id) collapsed.push(el.id);
    });
    return {
      collapsed: collapsed,
      scrollTop: els.body ? els.body.scrollTop : 0,
    };
  }

  function restoreUiState(state) {
    if (!state || !els.body) return;
    (state.collapsed || []).forEach(function (id) {
      const target = document.getElementById(id);
      if (!target) return;
      target.classList.add("collapsed");
      const toggle = els.body.querySelector('.fs-node.fs-toggle[data-target="' + id + '"]');
      const label = toggle && toggle.querySelector("span");
      if (label) {
        label.textContent = (label.textContent || "").replace(/^▾ /, "▸ ");
      }
    });
    els.body.scrollTop = state.scrollTop || 0;
  }

  function paintReport(report, opts) {
    opts = opts || {};
    const state = opts.preserveState ? captureUiState() : null;
    els.body.innerHTML = ViewManager.render(report, ViewManager.getMode());
    bindTreeToggles();
    if (state) restoreUiState(state);
  }

  async function loadReport() {
    if (!els.body) return;
    showStatus("");
    els.body.innerHTML = '<div class="text-muted small py-4">Loading report…</div>';
    const url = reportUrl(api.report, activeReport) + "?" + queryParams().toString();
    try {
      const res = await fetch(url, {
        headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load report.");
      const report = data.report || {};
      lastReport = report;
      const meta = report.meta || {};
      if (els.title) els.title.textContent = meta.report_title || "Financial Statements";
      if (els.meta) {
        els.meta.textContent =
          (meta.fy_label || "") +
          "  ·  " +
          (meta.date_from || "") +
          " to " +
          (meta.date_to || "") +
          "  ·  " +
          (ViewManager.getMode() === ViewManager.VERTICAL ? "Vertical" : "Horizontal") +
          " view";
      }
      paintReport(report, { preserveState: false });
    } catch (err) {
      lastReport = null;
      els.body.innerHTML = "";
      showStatus(err.message || String(err), "danger");
    }
  }

  function bindTreeToggles() {
    els.body?.querySelectorAll(".fs-node.fs-toggle").forEach(function (el) {
      el.addEventListener("click", function () {
        const target = document.getElementById(el.getAttribute("data-target"));
        if (!target) return;
        target.classList.toggle("collapsed");
        const label = el.querySelector("span");
        if (label) {
          const text = label.textContent || "";
          if (target.classList.contains("collapsed")) {
            label.textContent = text.replace(/^▾ /, "▸ ");
          } else {
            label.textContent = text.replace(/^▸ /, "▾ ");
          }
        }
      });
    });
    els.body?.querySelectorAll(".fs-ledger, tr.fs-clickable").forEach(function (el) {
      el.addEventListener("click", function () {
        const key = el.getAttribute("data-ledger");
        const name = el.getAttribute("data-name") || "Ledger";
        if (!key || key.indexOf("suspense") === 0) return;
        openVouchers(key, name);
      });
    });
  }

  function moneyOrDash(value) {
    if (value === null || value === undefined || value === "") return "—";
    return money(value);
  }

  function renderLedgerStatement(data, fallbackName) {
    const title = data.title || "Ledger Statement";
    const entity = data.entity_name || fallbackName || "";
    const headers = data.headers || [];
    const lines = data.lines || data.rows || [];
    if (els.drillTitle) {
      els.drillTitle.textContent = title + (entity ? " — " + entity : "");
    }

    let html = '<div class="fs-ledger-preview">';
    html += '<div class="fs-ledger-top">';
    html += '<div><div class="fs-ledger-entity">' + escapeHtml(entity) + "</div>";
    (data.meta || []).forEach(function (m) {
      html +=
        '<div class="fs-ledger-meta"><strong>' +
        escapeHtml(m.label) +
        ":</strong> " +
        escapeHtml(m.value) +
        "</div>";
    });
    html += "</div>";
    html +=
      '<div class="fs-ledger-closing">Closing<br><strong>' +
      money(data.closing) +
      "</strong></div></div>";

    html += '<div class="table-responsive"><table class="fs-table fs-ledger-table"><thead><tr>';
    headers.forEach(function (h) {
      html +=
        "<th" +
        (h.align === "right" ? ' class="num"' : "") +
        ">" +
        escapeHtml(h.label || h.key) +
        "</th>";
    });
    html += "</tr></thead><tbody>";
    lines.forEach(function (line) {
      const rowType = line.row_type || "txn";
      html += '<tr class="fs-ledger-row-' + escapeHtml(rowType) + '">';
      headers.forEach(function (h) {
        const key = h.key;
        let val = line[key];
        if (h.align === "right" || key === "debit" || key === "credit" || key === "balance") {
          html += '<td class="num">' + moneyOrDash(val) + "</td>";
        } else {
          html += "<td>" + escapeHtml(val == null ? "" : val) + "</td>";
        }
      });
      html += "</tr>";
    });
    html += "</tbody></table></div></div>";
    return html;
  }

  async function openVouchers(ledgerKey, name) {
    if (!drillModal || !els.drillBody) return;
    els.drillBody.innerHTML = '<div class="text-muted small">Loading…</div>';
    drillModal.show();
    const params = queryParams();
    params.set("ledger_key", ledgerKey);
    try {
      const res = await fetch(api.vouchers + "?" + params.toString(), {
        headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load ledger.");
      if (data.format === "ledger" || data.headers) {
        els.drillBody.innerHTML = renderLedgerStatement(data, name);
        return;
      }
      let html =
        '<table class="fs-table"><thead><tr><th>Date</th><th>Voucher</th><th>Narration</th><th class="num">Debit</th><th class="num">Credit</th></tr></thead><tbody>';
      (data.rows || data.vouchers || []).forEach(function (row) {
        html +=
          "<tr><td>" +
          escapeHtml(row.date || row.voucher_date || "") +
          "</td><td>" +
          escapeHtml(row.voucher_no || row.source || "") +
          "</td><td>" +
          escapeHtml(row.narration || "") +
          '</td><td class="num">' +
          money(row.debit) +
          '</td><td class="num">' +
          money(row.credit) +
          "</td></tr>";
      });
      html += "</tbody></table>";
      if (els.drillTitle) els.drillTitle.textContent = name;
      els.drillBody.innerHTML = html;
    } catch (err) {
      els.drillBody.innerHTML =
        '<div class="alert alert-danger py-2 small mb-0">' +
        escapeHtml(err.message || String(err)) +
        "</div>";
    }
  }

  function exportReport(fmt) {
    const url =
      reportUrl(api.export, activeReport) +
      "?" +
      queryParams().toString() +
      "&format=" +
      encodeURIComponent(fmt);
    window.location.href = url;
  }

  els.refreshBtn?.addEventListener("click", loadReport);
  els.printBtn?.addEventListener("click", function () {
    window.print();
  });
  els.pdfBtn?.addEventListener("click", function () {
    exportReport("pdf");
  });
  els.excelBtn?.addEventListener("click", function () {
    exportReport("xlsx");
  });
  els.dateFrom?.addEventListener("change", loadReport);
  els.dateTo?.addEventListener("change", loadReport);
  els.search?.addEventListener("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadReport, 300);
  });

  loadReport();
})();
