/**
 * FinancialViewManager — reusable Horizontal / Vertical layout for FS reports.
 * Default: Horizontal (Tally-style). Persists choice in localStorage.
 */
(function (global) {
  "use strict";

  var STORAGE_KEY = "jtcs.fs.viewMode";
  var HORIZONTAL = "horizontal";
  var VERTICAL = "vertical";

  function normalizeMode(mode) {
    return mode === VERTICAL ? VERTICAL : HORIZONTAL;
  }

  function getMode() {
    try {
      return normalizeMode(localStorage.getItem(STORAGE_KEY));
    } catch (e) {
      return HORIZONTAL;
    }
  }

  function setMode(mode) {
    mode = normalizeMode(mode);
    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch (e) {
      /* ignore quota / private mode */
    }
    return mode;
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function money(value) {
    var n = Number(String(value == null ? 0 : value).replace(/,/g, ""));
    if (Number.isNaN(n)) return "0.00";
    return n.toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function moneyNum(value) {
    var n = Number(String(value == null ? 0 : value).replace(/,/g, ""));
    return Number.isNaN(n) ? 0 : n;
  }

  /** Sync Bootstrap toggle button classes — only one active (btn-primary). */
  function applyToggleClasses(horizontalBtn, verticalBtn, mode) {
    mode = normalizeMode(mode);
    if (horizontalBtn) {
      horizontalBtn.classList.toggle("btn-primary", mode === HORIZONTAL);
      horizontalBtn.classList.toggle("btn-outline-primary", mode !== HORIZONTAL);
      horizontalBtn.setAttribute("aria-pressed", mode === HORIZONTAL ? "true" : "false");
    }
    if (verticalBtn) {
      verticalBtn.classList.toggle("btn-primary", mode === VERTICAL);
      verticalBtn.classList.toggle("btn-outline-primary", mode !== VERTICAL);
      verticalBtn.setAttribute("aria-pressed", mode === VERTICAL ? "true" : "false");
    }
  }

  /**
   * Bind Horizontal / Vertical toggle buttons.
   * @param {{horizontalBtn: HTMLElement, verticalBtn: HTMLElement, onChange?: Function}} opts
   */
  function bindToggle(opts) {
    opts = opts || {};
    var hBtn = opts.horizontalBtn;
    var vBtn = opts.verticalBtn;
    var onChange = typeof opts.onChange === "function" ? opts.onChange : null;

    function syncUi() {
      applyToggleClasses(hBtn, vBtn, getMode());
    }

    if (hBtn) {
      hBtn.addEventListener("click", function () {
        if (getMode() === HORIZONTAL) return;
        setMode(HORIZONTAL);
        syncUi();
        if (onChange) onChange(HORIZONTAL);
      });
    }
    if (vBtn) {
      vBtn.addEventListener("click", function () {
        if (getMode() === VERTICAL) return;
        setMode(VERTICAL);
        syncUi();
        if (onChange) onChange(VERTICAL);
      });
    }
    syncUi();
    return { getMode: getMode, setMode: setMode, sync: syncUi };
  }

  function ledgerClickAttrs(led) {
    var key = (led && (led.ledger_key || led.ledgerKey)) || "";
    var name = (led && (led.ledger_name || led.name)) || "";
    var kind = (led && led.preview_kind) || "";
    var id = led && led.preview_id != null && led.preview_id !== "" ? String(led.preview_id) : "";
    if (!kind && String(key).indexOf("bank-") === 0) {
      kind = "bank";
      id = String(key).split("-")[1] || "";
    }
    return (
      ' data-ledger="' +
      escapeHtml(key) +
      '" data-name="' +
      escapeHtml(name) +
      '" data-preview-kind="' +
      escapeHtml(kind) +
      '" data-preview-id="' +
      escapeHtml(id) +
      '"'
    );
  }

  function renderTreeNodes(nodes, depth, idPrefix) {
    depth = depth || 0;
    idPrefix = idPrefix || "fsn";
    var html = "";
    (nodes || []).forEach(function (node, idx) {
      var id = idPrefix + "-" + depth + "-" + idx + "-" + (node.group_id || "x");
      var hasKids =
        (node.children && node.children.length) || (node.ledgers && node.ledgers.length);
      html +=
        '<div class="fs-node' +
        (hasKids ? " fs-toggle" : "") +
        " fs-indent-" +
        Math.min(depth, 4) +
        '" data-target="' +
        id +
        '"><span>' +
        (hasKids ? "▾ " : "") +
        escapeHtml(node.group_name) +
        "</span><span>" +
        money(node.display_closing != null ? node.display_closing : node.closing) +
        "</span></div>";
      if (hasKids) {
        html += '<div class="fs-children" id="' + id + '">';
        (node.ledgers || []).forEach(function (led) {
          html +=
            '<div class="fs-ledger fs-indent-' +
            Math.min(depth + 1, 4) +
            '"' +
            ledgerClickAttrs(led) +
            "><span>" +
            escapeHtml(led.ledger_name) +
            "</span><span>" +
            money(led.display_closing != null ? led.display_closing : led.closing) +
            "</span></div>";
        });
        html += renderTreeNodes(node.children || [], depth + 1, id);
        html += "</div>";
      }
    });
    return html;
  }

  function renderTwoColumn(leftTitle, leftNodes, leftTotal, rightTitle, rightNodes, rightTotal, footerHtml) {
    return (
      '<div class="fs-bs-grid fs-view-horizontal" data-fs-view="horizontal">' +
      '<div class="fs-bs-col"><div class="fs-bs-head"><span>' +
      escapeHtml(leftTitle) +
      "</span><span>Amount</span></div><div class=\"fs-tree\">" +
      renderTreeNodes(leftNodes || [], 0, "fsl") +
      '</div><div class="fs-total-row"><span>Total</span><span>' +
      money(leftTotal) +
      "</span></div></div>" +
      '<div class="fs-bs-col"><div class="fs-bs-head"><span>' +
      escapeHtml(rightTitle) +
      "</span><span>Amount</span></div><div class=\"fs-tree\">" +
      renderTreeNodes(rightNodes || [], 0, "fsr") +
      '</div><div class="fs-total-row"><span>Total</span><span>' +
      money(rightTotal) +
      "</span></div></div></div>" +
      (footerHtml || "")
    );
  }

  function renderStackedBlock(title, nodes, total, totalLabel) {
    var html = '<div class="fs-v-block">';
    html += '<div class="fs-section-title">' + escapeHtml(title) + "</div>";
    html += '<div class="fs-tree">' + renderTreeNodes(nodes || [], 0, "fsv") + "</div>";
    if (total != null) {
      html +=
        '<div class="fs-total-row"><span>' +
        escapeHtml(totalLabel || "Total — " + title) +
        "</span><span>" +
        money(total) +
        "</span></div>";
    }
    html += "</div>";
    return html;
  }

  function balanceFooter(report) {
    return (
      '<div class="mt-2 small">' +
      (report.balanced
        ? '<span class="fs-badge-ok">Balanced</span>'
        : '<span class="fs-badge-warn">Difference: ' + money(report.difference) + "</span>") +
      "</div>"
    );
  }

  /* ---------- Balance Sheet ---------- */
  function renderBalanceSheetHorizontal(report) {
    var left = report.left || {};
    var right = report.right || {};
    return renderTwoColumn(
      left.title || "Liabilities",
      left.nodes,
      left.total,
      right.title || "Assets",
      right.nodes,
      right.total,
      balanceFooter(report)
    );
  }

  function renderBalanceSheetVertical(report) {
    var left = report.left || {};
    var right = report.right || {};
    var html = '<div class="fs-view-vertical" data-fs-view="vertical">';
    html += '<div class="fs-v-report-title">BALANCE SHEET</div>';
    html += renderStackedBlock(left.title || "Liabilities", left.nodes, left.total, "Total Liabilities");
    html += '<hr class="fs-v-divider">';
    html += renderStackedBlock(right.title || "Assets", right.nodes, right.total, "Total Assets");
    html += balanceFooter(report);
    html += "</div>";
    return html;
  }

  /* ---------- P&L / Trading (section-based) ---------- */
  function splitPnLSides(sections) {
    var leftSecs = [];
    var rightSecs = [];
    var leftTotal = 0;
    var rightTotal = 0;
    (sections || []).forEach(function (sec) {
      var title = String(sec.title || "");
      var t = title.toLowerCase();
      var amt = moneyNum(sec.total != null ? sec.total : sec.amount);
      if (sec.emphasis) {
        if (amt >= 0) {
          rightSecs.push(sec);
          rightTotal += amt;
        } else {
          leftSecs.push({
            title: title.replace(/Profit/gi, "Loss"),
            nodes: sec.nodes || [],
            total: Math.abs(amt),
            emphasis: true,
          });
          leftTotal += Math.abs(amt);
        }
        return;
      }
      if (t.indexOf("expense") >= 0) {
        leftSecs.push(sec);
        leftTotal += amt;
      } else {
        rightSecs.push(sec);
        rightTotal += amt;
      }
    });
    return { leftSecs: leftSecs, rightSecs: rightSecs, leftTotal: leftTotal, rightTotal: rightTotal };
  }

  function renderSectionColumn(secs, idPrefix) {
    var html = '<div class="fs-tree">';
    (secs || []).forEach(function (sec, i) {
      if (sec.emphasis) {
        html +=
          '<div class="fs-emphasis"><span>' +
          escapeHtml(sec.title) +
          "</span><span>" +
          money(sec.total != null ? sec.total : sec.amount) +
          "</span></div>";
        return;
      }
      html +=
        '<div class="fs-col-section-title">' + escapeHtml(sec.title) + "</div>";
      html += renderTreeNodes(sec.nodes || [], 0, idPrefix + i);
      if (sec.total != null || sec.amount != null) {
        html +=
          '<div class="fs-subtotal-row"><span>Total — ' +
          escapeHtml(sec.title) +
          "</span><span>" +
          money(sec.total != null ? sec.total : sec.amount) +
          "</span></div>";
      }
    });
    html += "</div>";
    return html;
  }

  function renderSectionsHorizontal(report, leftLabel, rightLabel) {
    var split = splitPnLSides(report.sections || []);
    return (
      '<div class="fs-bs-grid fs-view-horizontal" data-fs-view="horizontal">' +
      '<div class="fs-bs-col"><div class="fs-bs-head"><span>' +
      escapeHtml(leftLabel || "Expenses") +
      "</span><span>Amount</span></div>" +
      renderSectionColumn(split.leftSecs, "fse") +
      '<div class="fs-total-row"><span>Total</span><span>' +
      money(split.leftTotal) +
      "</span></div></div>" +
      '<div class="fs-bs-col"><div class="fs-bs-head"><span>' +
      escapeHtml(rightLabel || "Income") +
      "</span><span>Amount</span></div>" +
      renderSectionColumn(split.rightSecs, "fsi") +
      '<div class="fs-total-row"><span>Total</span><span>' +
      money(split.rightTotal) +
      "</span></div></div></div>"
    );
  }

  function renderSectionsVertical(report) {
    var html = '<div class="fs-view-vertical" data-fs-view="vertical">';
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
        html += '<div class="fs-tree">' + renderTreeNodes(sec.nodes, 0, "fsv") + "</div>";
      }
      if (sec.total != null || sec.amount != null) {
        html +=
          '<div class="fs-total-row"><span>Total — ' +
          escapeHtml(sec.title) +
          "</span><span>" +
          money(sec.total != null ? sec.total : sec.amount) +
          "</span></div>";
      }
      html += '<hr class="fs-v-divider">';
    });
    html += "</div>";
    return html;
  }

  /* ---------- Trial Balance ---------- */
  function renderTrialHorizontal(report) {
    var drRows = [];
    var crRows = [];
    (report.rows || []).forEach(function (row) {
      var dr = moneyNum(row.debit);
      var cr = moneyNum(row.credit);
      if (dr > 0) {
        drRows.push({
          name: row.ledger_name,
          amount: dr,
          ledger_key: row.ledger_key,
          preview_kind: row.preview_kind,
          preview_id: row.preview_id,
        });
      }
      if (cr > 0) {
        crRows.push({
          name: row.ledger_name,
          amount: cr,
          ledger_key: row.ledger_key,
          preview_kind: row.preview_kind,
          preview_id: row.preview_id,
        });
      }
    });
    function sideList(rows, prefix) {
      var html = '<div class="fs-tree">';
      rows.forEach(function (r) {
        html +=
          '<div class="fs-ledger"' +
          ledgerClickAttrs(r) +
          "><span>" +
          escapeHtml(r.name) +
          "</span><span>" +
          money(r.amount) +
          "</span></div>";
      });
      html += "</div>";
      return html;
    }
    return (
      '<div class="fs-bs-grid fs-view-horizontal" data-fs-view="horizontal">' +
      '<div class="fs-bs-col"><div class="fs-bs-head"><span>Debit</span><span>Amount</span></div>' +
      sideList(drRows, "dr") +
      '<div class="fs-total-row"><span>Total</span><span>' +
      money(report.total_debit) +
      "</span></div></div>" +
      '<div class="fs-bs-col"><div class="fs-bs-head"><span>Credit</span><span>Amount</span></div>' +
      sideList(crRows, "cr") +
      '<div class="fs-total-row"><span>Total</span><span>' +
      money(report.total_credit) +
      "</span></div></div></div>" +
      '<div class="mt-2 small">' +
      (report.balanced
        ? '<span class="fs-badge-ok">Trial Balance tallies</span>'
        : '<span class="fs-badge-warn">Out of balance</span>') +
      "</div>"
    );
  }

  function renderTrialVertical(report) {
    var html =
      '<div class="fs-view-vertical" data-fs-view="vertical">' +
      '<table class="fs-table"><thead><tr><th>Ledger Name</th><th>Group</th><th class="num">Debit</th><th class="num">Credit</th></tr></thead><tbody>';
    (report.rows || []).forEach(function (row) {
      html +=
        '<tr class="fs-clickable"' +
        ledgerClickAttrs(row) +
        "><td>" +
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
      "</div></div>";
    return html;
  }

  /* ---------- Fund Flow ---------- */
  function renderFundHorizontal(report) {
    var html =
      '<div class="fs-bs-grid fs-view-horizontal" data-fs-view="horizontal">' +
      '<div class="fs-bs-col"><div class="fs-bs-head"><span>Sources</span><span>Amount</span></div><div class="fs-tree">';
    (report.sources || []).forEach(function (r) {
      html +=
        '<div class="fs-ledger"><span>' +
        escapeHtml(r.name) +
        "</span><span>" +
        money(r.amount) +
        "</span></div>";
    });
    html +=
      '</div><div class="fs-total-row"><span>Total Sources</span><span>' +
      money(report.sources_total) +
      "</span></div></div>";
    html +=
      '<div class="fs-bs-col"><div class="fs-bs-head"><span>Applications</span><span>Amount</span></div><div class="fs-tree">';
    (report.applications || []).forEach(function (r) {
      html +=
        '<div class="fs-ledger"><span>' +
        escapeHtml(r.name) +
        "</span><span>" +
        money(r.amount) +
        "</span></div>";
    });
    html +=
      '</div><div class="fs-total-row"><span>Total Applications</span><span>' +
      money(report.applications_total) +
      "</span></div></div></div>";
    return html;
  }

  function renderFundVertical(report) {
    var html = '<div class="fs-view-vertical" data-fs-view="vertical">';
    html += '<div class="fs-section-title">Sources</div><div class="fs-tree">';
    (report.sources || []).forEach(function (r) {
      html +=
        '<div class="fs-ledger"><span>' +
        escapeHtml(r.name) +
        "</span><span>" +
        money(r.amount) +
        "</span></div>";
    });
    html +=
      '</div><div class="fs-total-row"><span>Total Sources</span><span>' +
      money(report.sources_total) +
      "</span></div><hr class=\"fs-v-divider\">";
    html += '<div class="fs-section-title">Applications</div><div class="fs-tree">';
    (report.applications || []).forEach(function (r) {
      html +=
        '<div class="fs-ledger"><span>' +
        escapeHtml(r.name) +
        "</span><span>" +
        money(r.amount) +
        "</span></div>";
    });
    html +=
      '</div><div class="fs-total-row"><span>Total Applications</span><span>' +
      money(report.applications_total) +
      "</span></div></div>";
    return html;
  }

  /* ---------- Tabular fallbacks (depreciation / ratios) ---------- */
  function renderDepreciation(report) {
    var html =
      '<table class="fs-table"><thead><tr>' +
      "<th>Asset</th><th>Purchase Date</th><th class=\"num\">Purchase Value</th><th class=\"num\">Rate %</th>" +
      "<th class=\"num\">CY Depreciation</th><th class=\"num\">Accumulated</th><th class=\"num\">WDV</th>" +
      "</tr></thead><tbody>";
    (report.rows || []).forEach(function (row) {
      html +=
        "<tr><td>" +
        escapeHtml(row.asset_name) +
        "</td><td>" +
        escapeHtml((window.formatDisplaySmart || window.formatDisplayDate || String)(row.purchase_date)) +
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
    var t = report.totals || {};
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
        '<p class="small text-muted mt-2">No fixed assets yet. Add rows in <code>FixedAssetMaster</code> to populate this report.</p>';
    }
    return html;
  }

  function renderRatios(report) {
    var html =
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

  function renderCashFlowHorizontal(report) {
    /* Pair inflow/outflow style two-column from flat sections */
    var secs = report.sections || [];
    var left = [];
    var right = [];
    secs.forEach(function (sec, i) {
      if (sec.emphasis) return;
      var t = String(sec.title || "").toLowerCase();
      if (t.indexOf("outflow") >= 0 || i % 2 === 1) left.push(sec);
      else right.push(sec);
    });
    if (!left.length && !right.length) {
      return renderSectionsVertical(report);
    }
    function amtCol(list, prefix) {
      var html = '<div class="fs-tree">';
      list.forEach(function (sec) {
        html +=
          '<div class="fs-ledger"><span>' +
          escapeHtml(sec.title) +
          "</span><span>" +
          money(sec.amount != null ? sec.amount : sec.total) +
          "</span></div>";
      });
      html += "</div>";
      return html;
    }
    var emphasis = secs.filter(function (s) {
      return s.emphasis;
    });
    var html =
      '<div class="fs-bs-grid fs-view-horizontal" data-fs-view="horizontal">' +
      '<div class="fs-bs-col"><div class="fs-bs-head"><span>Outflows / Applications</span><span>Amount</span></div>' +
      amtCol(left, "cfl") +
      "</div>" +
      '<div class="fs-bs-col"><div class="fs-bs-head"><span>Inflows / Sources</span><span>Amount</span></div>' +
      amtCol(right, "cfr") +
      "</div></div>";
    emphasis.forEach(function (sec) {
      html +=
        '<div class="fs-emphasis mt-2"><span>' +
        escapeHtml(sec.title) +
        "</span><span>" +
        money(sec.amount != null ? sec.amount : sec.total) +
        "</span></div>";
    });
    return html;
  }

  /** Generic horizontal renderer — routes by report.layout */
  function renderHorizontal(report) {
    report = report || {};
    var layout = report.layout;
    if (layout === "tally-bs") return renderBalanceSheetHorizontal(report);
    if (layout === "trial-balance") return renderTrialHorizontal(report);
    if (layout === "fund-flow") return renderFundHorizontal(report);
    if (layout === "cash-flow") return renderCashFlowHorizontal(report);
    if (layout === "pnl" || layout === "trading") {
      return renderSectionsHorizontal(
        report,
        layout === "trading" ? "Debit" : "Expenses",
        layout === "trading" ? "Credit" : "Income"
      );
    }
    if (layout === "depreciation" || layout === "fixed-assets") return renderDepreciation(report);
    if (layout === "ratios") return renderRatios(report);
    if (report.left && report.right) return renderBalanceSheetHorizontal(report);
    if (report.sections) return renderSectionsHorizontal(report, "Particulars (Dr)", "Particulars (Cr)");
    return '<div class="text-muted small">No data for horizontal view.</div>';
  }

  /** Generic vertical renderer — routes by report.layout */
  function renderVertical(report) {
    report = report || {};
    var layout = report.layout;
    if (layout === "tally-bs") return renderBalanceSheetVertical(report);
    if (layout === "trial-balance") return renderTrialVertical(report);
    if (layout === "fund-flow") return renderFundVertical(report);
    if (layout === "depreciation" || layout === "fixed-assets") return renderDepreciation(report);
    if (layout === "ratios") return renderRatios(report);
    if (report.left && report.right) return renderBalanceSheetVertical(report);
    if (report.sections) return renderSectionsVertical(report);
    return '<div class="text-muted small">No data for vertical view.</div>';
  }

  function render(report, mode) {
    mode = normalizeMode(mode != null ? mode : getMode());
    return mode === VERTICAL ? renderVertical(report) : renderHorizontal(report);
  }

  global.FinancialViewManager = {
    STORAGE_KEY: STORAGE_KEY,
    HORIZONTAL: HORIZONTAL,
    VERTICAL: VERTICAL,
    getMode: getMode,
    setMode: setMode,
    bindToggle: bindToggle,
    applyToggleClasses: applyToggleClasses,
    render: render,
    renderHorizontal: renderHorizontal,
    renderVertical: renderVertical,
    escapeHtml: escapeHtml,
    money: money,
  };
})(window);
