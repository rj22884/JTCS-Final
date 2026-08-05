(function () {
  "use strict";

  const api = window.FS_API;
  if (!api) return;

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
    drillModalEl: document.getElementById("fsDrillModal"),
    drillTitle: document.getElementById("fsDrillTitle"),
    drillBody: document.getElementById("fsDrillBody"),
  };

  let activeReport = window.FS_ACTIVE_REPORT || "balance-sheet";
  let searchTimer = null;
  const drillModal =
    els.drillModalEl && window.bootstrap ? new bootstrap.Modal(els.drillModalEl) : null;

  function reportUrl(template, key) {
    return String(template || "").replace("__KEY__", encodeURIComponent(key));
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function money(value) {
    const n = Number(String(value == null ? 0 : value).replace(/,/g, ""));
    if (Number.isNaN(n)) return "0.00";
    return n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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
    return params;
  }

  function renderTreeNodes(nodes, depth) {
    depth = depth || 0;
    let html = "";
    (nodes || []).forEach(function (node, idx) {
      const id = "fsn-" + depth + "-" + idx + "-" + (node.group_id || "x");
      const hasKids = (node.children && node.children.length) || (node.ledgers && node.ledgers.length);
      html +=
        '<div class="fs-node' +
        (hasKids ? " fs-toggle" : "") +
        " fs-indent-" +
        Math.min(depth, 4) +
        '" data-target="' +
        id +
        '">' +
        "<span>" +
        (hasKids ? "▾ " : "") +
        escapeHtml(node.group_name) +
        "</span>" +
        "<span>" +
        money(node.display_closing || node.closing) +
        "</span></div>";
      if (hasKids) {
        html += '<div class="fs-children" id="' + id + '">';
        (node.ledgers || []).forEach(function (led) {
          html +=
            '<div class="fs-ledger fs-indent-' +
            Math.min(depth + 1, 4) +
            '" data-ledger="' +
            escapeHtml(led.ledger_key) +
            '" data-name="' +
            escapeHtml(led.ledger_name) +
            '"><span>' +
            escapeHtml(led.ledger_name) +
            "</span><span>" +
            money(led.display_closing || led.closing) +
            "</span></div>";
        });
        html += renderTreeNodes(node.children || [], depth + 1);
        html += "</div>";
      }
    });
    return html;
  }

  function renderBalanceSheet(report) {
    const left = report.left || {};
    const right = report.right || {};
    return (
      '<div class="fs-bs-grid">' +
      '<div class="fs-bs-col"><div class="fs-bs-head"><span>' +
      escapeHtml(left.title || "Liabilities") +
      "</span><span>Amount</span></div><div class=\"fs-tree\">" +
      renderTreeNodes(left.nodes || []) +
      '</div><div class="fs-total-row"><span>Total</span><span>' +
      money(left.total) +
      "</span></div></div>" +
      '<div class="fs-bs-col"><div class="fs-bs-head"><span>' +
      escapeHtml(right.title || "Assets") +
      "</span><span>Amount</span></div><div class=\"fs-tree\">" +
      renderTreeNodes(right.nodes || []) +
      '</div><div class="fs-total-row"><span>Total</span><span>' +
      money(right.total) +
      "</span></div></div></div>" +
      '<div class="mt-2 small">' +
      (report.balanced
        ? '<span class="fs-badge-ok">Balanced</span>'
        : '<span class="fs-badge-warn">Difference: ' + money(report.difference) + "</span>") +
      "</div>"
    );
  }

  function renderSections(report) {
    let html = "";
    (report.sections || []).forEach(function (sec) {
      if (sec.emphasis) {
        html +=
          '<div class="fs-emphasis"><span>' +
          escapeHtml(sec.title) +
          "</span><span>" +
          money(sec.total != null ? sec.total : sec.amount) +
          "</span></div>";
        return;
      }
      html += '<div class="fs-section-title">' + escapeHtml(sec.title) + "</div>";
      if (sec.nodes && sec.nodes.length) {
        html += '<div class="fs-tree">' + renderTreeNodes(sec.nodes) + "</div>";
      }
      if (sec.total != null || sec.amount != null) {
        html +=
          '<div class="fs-total-row"><span>Total — ' +
          escapeHtml(sec.title) +
          "</span><span>" +
          money(sec.total != null ? sec.total : sec.amount) +
          "</span></div>";
      }
    });
    return html;
  }

  function renderTrialBalance(report) {
    let html =
      '<table class="fs-table"><thead><tr><th>Particulars</th><th>Group</th><th class="num">Debit</th><th class="num">Credit</th></tr></thead><tbody>';
    (report.rows || []).forEach(function (row) {
      html +=
        '<tr class="fs-clickable" data-ledger="' +
        escapeHtml(row.ledger_key || "") +
        '" data-name="' +
        escapeHtml(row.ledger_name || "") +
        '"><td>' +
        escapeHtml(row.ledger_name) +
        "</td><td>" +
        escapeHtml(row.group_name) +
        '</td><td class="num">' +
        money(row.debit) +
        '</td><td class="num">' +
        money(row.credit) +
        "</td></tr>";
    });
    html +=
      '</tbody><tfoot><tr><td colspan="2">Total</td><td class="num">' +
      money(report.total_debit) +
      '</td><td class="num">' +
      money(report.total_credit) +
      "</td></tr></tfoot></table>";
    html +=
      '<div class="mt-2 small">' +
      (report.balanced
        ? '<span class="fs-badge-ok">Trial Balance tallies</span>'
        : '<span class="fs-badge-warn">Out of balance</span>') +
      "</div>";
    return html;
  }

  function renderDepreciation(report) {
    let html =
      '<table class="fs-table"><thead><tr>' +
      "<th>Asset</th><th>Purchase Date</th><th class=\"num\">Purchase Value</th><th class=\"num\">Rate %</th>" +
      "<th class=\"num\">CY Depreciation</th><th class=\"num\">Accumulated</th><th class=\"num\">WDV</th>" +
      "</tr></thead><tbody>";
    (report.rows || []).forEach(function (row) {
      html +=
        "<tr><td>" +
        escapeHtml(row.asset_name) +
        "</td><td>" +
        escapeHtml(row.purchase_date) +
        '</td><td class="num">' +
        money(row.purchase_value) +
        '</td><td class="num">' +
        money(row.depreciation_rate) +
        '</td><td class="num">' +
        money(row.current_year_depreciation) +
        '</td><td class="num">' +
        money(row.accumulated_depreciation) +
        '</td><td class="num">' +
        money(row.wdv) +
        "</td></tr>";
    });
    const t = report.totals || {};
    html +=
      '</tbody><tfoot><tr><td colspan="2">Total</td><td class="num">' +
      money(t.purchase_value) +
      '</td><td></td><td class="num">' +
      money(t.current_year_depreciation) +
      '</td><td class="num">' +
      money(t.accumulated_depreciation) +
      '</td><td class="num">' +
      money(t.wdv) +
      "</td></tr></tfoot></table>";
    if (!(report.rows || []).length) {
      html +=
        '<p class="small text-muted mt-2">No fixed assets yet. Add rows in <code>FixedAssetMaster</code> (Purchase Date, Value, Rate) to populate Depreciation Chart / Schedule.</p>';
    }
    return html;
  }

  function renderFundFlow(report) {
    let html = '<div class="row g-3"><div class="col-md-6"><div class="fs-section-title">Sources</div><table class="fs-table"><tbody>';
    (report.sources || []).forEach(function (r) {
      html += "<tr><td>" + escapeHtml(r.name) + '</td><td class="num">' + money(r.amount) + "</td></tr>";
    });
    html +=
      '<tr><td><strong>Total Sources</strong></td><td class="num"><strong>' +
      money(report.sources_total) +
      "</strong></td></tr></tbody></table></div>";
    html += '<div class="col-md-6"><div class="fs-section-title">Applications</div><table class="fs-table"><tbody>';
    (report.applications || []).forEach(function (r) {
      html += "<tr><td>" + escapeHtml(r.name) + '</td><td class="num">' + money(r.amount) + "</td></tr>";
    });
    html +=
      '<tr><td><strong>Total Applications</strong></td><td class="num"><strong>' +
      money(report.applications_total) +
      "</strong></td></tr></tbody></table></div></div>";
    return html;
  }

  function renderRatios(report) {
    let html =
      '<table class="fs-table"><thead><tr><th>Ratio</th><th class="num">Value</th><th>Formula</th></tr></thead><tbody>';
    (report.ratios || []).forEach(function (r) {
      html +=
        "<tr><td>" +
        escapeHtml(r.name) +
        '</td><td class="num">' +
        (r.value == null ? "—" : money(r.value)) +
        "</td><td>" +
        escapeHtml(r.formula) +
        "</td></tr>";
    });
    html += "</tbody></table>";
    return html;
  }

  function renderReport(report) {
    const layout = report.layout;
    if (layout === "tally-bs") return renderBalanceSheet(report);
    if (layout === "trial-balance") return renderTrialBalance(report);
    if (layout === "depreciation" || layout === "fixed-assets") return renderDepreciation(report);
    if (layout === "fund-flow") return renderFundFlow(report);
    if (layout === "ratios") return renderRatios(report);
    return renderSections(report);
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
      const meta = report.meta || {};
      if (els.title) els.title.textContent = meta.report_title || "Financial Statements";
      if (els.meta) {
        els.meta.textContent =
          (meta.fy_label || "") +
          "  ·  " +
          (meta.date_from || "") +
          " to " +
          (meta.date_to || "");
      }
      els.body.innerHTML = renderReport(report);
      bindTreeToggles();
    } catch (err) {
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
    const kind = data.ledger_kind || "generic";
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
        escapeHtml(m.value || "—") +
        "</div>";
    });
    html += "</div>";
    html +=
      '<div class="fs-ledger-closing">Closing Balance<br><strong>Rs. ' +
      money(data.closing) +
      "</strong></div>";
    html += "</div>";

    if (!lines.length) {
      html += '<div class="text-muted small">No ledger rows for this period.</div></div>';
      return html;
    }

    html += '<div class="table-responsive"><table class="fs-table fs-ledger-table"><thead><tr>';
    headers.forEach(function (h) {
      const isNum =
        h === "Debit" ||
        h === "Credit" ||
        h === "Running Balance" ||
        h === "Debit (Bill)" ||
        h === "Credit (Receipt)";
      html += '<th class="' + (isNum ? "num" : "") + '">' + escapeHtml(h) + "</th>";
    });
    html += "</tr></thead><tbody>";

    lines.forEach(function (row) {
      const rowKind = row.kind || "txn";
      const clickable = row.clickable && (row.SourceRecordID || row.voucher_id);
      const cls =
        "fs-ledger-row fs-ledger-row-" +
        rowKind +
        (clickable ? " fs-clickable fs-voucher-row" : "");
      html +=
        '<tr class="' +
        cls +
        '" data-table="' +
        escapeHtml(row.SourceTable || "") +
        '" data-id="' +
        escapeHtml(row.SourceRecordID || row.voucher_id || "") +
        '">';

      if (kind === "customer") {
        html +=
          "<td>" +
          escapeHtml(row.voucher_date || "—") +
          "</td><td>" +
          escapeHtml(row.bill || row.reference || "") +
          "</td><td>" +
          escapeHtml(row.work || row.source || "") +
          "</td><td>" +
          escapeHtml(row.narration || "—") +
          '</td><td class="num">' +
          moneyOrDash(row.debit) +
          '</td><td class="num">' +
          moneyOrDash(row.credit) +
          '</td><td class="num">' +
          moneyOrDash(row.running_balance) +
          "</td>";
      } else {
        html +=
          "<td>" +
          escapeHtml(row.voucher_date || "—") +
          "</td><td>" +
          escapeHtml(row.narration || "—") +
          "</td><td>" +
          escapeHtml(row.reference || "") +
          "</td><td>" +
          escapeHtml(row.source || "") +
          "</td><td>" +
          escapeHtml(row.voucher_type || "") +
          '</td><td class="num">' +
          moneyOrDash(row.debit) +
          '</td><td class="num">' +
          moneyOrDash(row.credit) +
          '</td><td class="num">' +
          moneyOrDash(row.running_balance) +
          "</td>";
      }
      html += "</tr>";
    });
    html += "</tbody></table></div></div>";
    return html;
  }

  async function openVouchers(ledgerKey, name) {
    if (!els.drillBody) return;
    if (els.drillTitle) els.drillTitle.textContent = "Ledger — " + name;
    els.drillBody.innerHTML = '<div class="text-muted small">Loading ledger…</div>';
    drillModal?.show();
    const params = queryParams();
    params.set("ledger_key", ledgerKey);
    try {
      const res = await fetch(api.vouchers + "?" + params.toString(), {
        headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load ledger.");
      els.drillBody.innerHTML = renderLedgerStatement(data, name);
      els.drillBody.querySelectorAll(".fs-voucher-row").forEach(function (tr) {
        tr.addEventListener("click", function () {
          openVoucherDetail(tr.getAttribute("data-table"), tr.getAttribute("data-id"));
        });
      });
    } catch (err) {
      els.drillBody.innerHTML =
        '<div class="text-danger small">' + escapeHtml(err.message || String(err)) + "</div>";
    }
  }

  async function openVoucherDetail(sourceTable, sourceId) {
    if (!sourceId) return;
    const params = new URLSearchParams();
    params.set("source_table", sourceTable || "");
    params.set("source_id", sourceId);
    try {
      const res = await fetch(api.voucherDetail + "?" + params.toString(), {
        headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load voucher.");
      const rec = data.record || {};
      let html = '<div class="small mb-2 text-muted">Voucher details</div><table class="fs-table"><tbody>';
      Object.keys(rec).forEach(function (key) {
        html +=
          "<tr><td>" +
          escapeHtml(key) +
          "</td><td>" +
          escapeHtml(rec[key]) +
          "</td></tr>";
      });
      html += "</tbody></table>";
      if (els.drillTitle) els.drillTitle.textContent = "Voucher #" + sourceId;
      els.drillBody.innerHTML = html;
    } catch (err) {
      alert(err.message || String(err));
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

  document.querySelectorAll(".fs-nav-item").forEach(function (link) {
    link.addEventListener("click", function (event) {
      // Allow normal navigation; also soft-switch if same page SPA-style
      const key = link.getAttribute("data-report");
      if (!key || key === activeReport) return;
      // Let browser navigate for URL/bookmark fidelity
    });
  });

  loadReport();
})();
