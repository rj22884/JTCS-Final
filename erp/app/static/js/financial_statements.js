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
    previewModalEl: document.getElementById("ledgerPreviewModal"),
    previewDialog: document.getElementById("ledgerPreviewDialog"),
    previewTitle: document.getElementById("ledgerPreviewModalTitle"),
    previewBody: document.getElementById("ledgerPreviewBody"),
    maximizeBtn: document.getElementById("ledgerMaximizeBtn"),
    maximizeIcon: document.getElementById("ledgerMaximizeIcon"),
    exportBtn: document.getElementById("ledgerExportBtn"),
  };

  const ledgerCfg = window.LEDGER_REPORT || {};
  let activeReport = window.FS_ACTIVE_REPORT || "balance-sheet";
  let searchTimer = null;
  let lastReport = null;
  let previewKind = "";
  let previewId = "";
  let isMaximized = false;
  const drillModal =
    els.drillModalEl && window.bootstrap ? new bootstrap.Modal(els.drillModalEl) : null;
  const previewModal =
    els.previewModalEl && window.bootstrap
      ? bootstrap.Modal.getOrCreateInstance(els.previewModalEl)
      : null;

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
        const kind = (el.getAttribute("data-preview-kind") || "").trim();
        const id = (el.getAttribute("data-preview-id") || "").trim();
        if (!key || key.indexOf("suspense") === 0) return;
        if (kind && id && previewModal) {
          openLedgerPreview(kind, id);
          return;
        }
        openVouchers(key, name);
      });
    });
  }

  function moneyOrDash(value) {
    if (value === null || value === undefined || value === "") return "—";
    return money(value);
  }

  function previewUrl(kind, id) {
    return String(ledgerCfg.previewUrl || "").replace(
      /\/preview\/[^/]+\/0(?=$|[/?#])/,
      "/preview/" + encodeURIComponent(kind) + "/" + String(id)
    );
  }

  function exportUrl(kind, id, fmt) {
    return String(ledgerCfg.exportUrl || "")
      .replace(
        /\/export\/[^/]+\/0\/pdf(?=$|[/?#])/,
        "/export/" + encodeURIComponent(kind) + "/" + String(id) + "/" + encodeURIComponent(fmt)
      )
      .replace(
        /\/export\/[^/]+\/0\/[^/?#]+(?=$|[/?#])/,
        "/export/" + encodeURIComponent(kind) + "/" + String(id) + "/" + encodeURIComponent(fmt)
      );
  }

  function previewDateQuery() {
    if (window.JTCSLedgerPreview && typeof window.JTCSLedgerPreview.dateQuery === "function") {
      return window.JTCSLedgerPreview.dateQuery();
    }
    return fsPageDateQuery();
  }

  function fsPageDateQuery() {
    const params = new URLSearchParams();
    if (els.dateFrom?.value) params.set("date_from", els.dateFrom.value);
    if (els.dateTo?.value) params.set("date_to", els.dateTo.value);
    const q = params.toString();
    return q ? "?" + q : "";
  }

  function setExportEnabled(on) {
    if (els.exportBtn) els.exportBtn.disabled = !on;
  }

  function setMaximized(on) {
    isMaximized = !!on;
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

  async function openLedgerPreview(kind, id) {
    if (!previewModal || !els.previewBody) {
      return;
    }
    const url = previewUrl(kind, id);
    if (!url) return;
    const isReload =
      previewKind === kind &&
      previewId === String(id) &&
      !!(els.previewModalEl && els.previewModalEl.classList.contains("show"));
    previewKind = kind;
    previewId = String(id);
    setExportEnabled(false);
    setMaximized(isMaximized && isReload);
    if (els.previewTitle) els.previewTitle.textContent = "Ledger Preview";
    const qs = isReload ? previewDateQuery() : fsPageDateQuery();
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
      previewKind = "";
      previewId = "";
      setExportEnabled(false);
      els.previewBody.innerHTML =
        '<div class="alert alert-danger mb-0">' +
        escapeHtml(err.message || "Unable to load preview.") +
        "</div>";
    }
  }

  function downloadExport(fmt) {
    if (!previewKind || !previewId) return;
    const url = exportUrl(previewKind, previewId, fmt);
    if (!url) return;
    window.location.href = url + previewDateQuery();
  }

  function normalizeHeader(h) {
    if (h && typeof h === "object") {
      return {
        key: h.key || "",
        label: h.label || h.key || "",
        align: h.align || "",
      };
    }
    const label = String(h || "");
    const map = {
      Date: "voucher_date",
      Description: "narration",
      Reference: "reference",
      Source: "source",
      "Ledger Kind": "voucher_type",
      Debit: "debit",
      Credit: "credit",
      "Running Balance": "running_balance",
      "Bill / Ref No.": "bill",
      "Work Type": "work",
      "Debit (Bill)": "debit",
      "Credit (Receipt)": "credit",
    };
    const key = map[label] || label.toLowerCase().replace(/\s+/g, "_");
    const align =
      key === "debit" || key === "credit" || key === "running_balance" || key === "balance"
        ? "right"
        : "";
    return { key: key, label: label, align: align };
  }

  function lineValue(line, key) {
    if (line[key] != null && line[key] !== "") return line[key];
    if (key === "voucher_date") return line.date || "";
    if (key === "narration") return line.description || "";
    if (key === "running_balance") return line.balance;
    return line[key];
  }

  function renderLedgerStatement(data, fallbackName, ledgerKey) {
    const title = data.title || "Ledger Statement";
    const entity = data.entity_name || fallbackName || "";
    const headers = (data.headers || []).map(normalizeHeader);
    const lines = data.lines || data.rows || [];
    if (els.drillTitle) {
      els.drillTitle.textContent = title + (entity ? " — " + entity : "");
    }

    const fromVal = data.date_from || (els.dateFrom && els.dateFrom.value) || "";
    const toVal = data.date_to || (els.dateTo && els.dateTo.value) || "";

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

    html +=
      '<div class="ledger-preview-toolbar">' +
      '<div class="ledger-preview-dates">' +
      "<label><span>From Date</span>" +
      '<input type="date" class="form-control form-control-sm" id="fsDrillDateFrom" value="' +
      escapeHtml(fromVal) +
      '" aria-label="From Date"></label>' +
      "<label><span>To Date</span>" +
      '<input type="date" class="form-control form-control-sm" id="fsDrillDateTo" value="' +
      escapeHtml(toVal) +
      '" aria-label="To Date"></label>' +
      '<button type="button" class="btn btn-sm btn-primary" id="fsDrillApplyDates" data-ledger="' +
      escapeHtml(ledgerKey || "") +
      '" data-name="' +
      escapeHtml(fallbackName || "") +
      '"><i class="bi bi-funnel"></i> Apply</button>' +
      "</div></div>";

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
      const rowType = line.kind || line.row_type || "txn";
      html += '<tr class="fs-ledger-row-' + escapeHtml(rowType) + '">';
      headers.forEach(function (h) {
        const key = h.key;
        const val = lineValue(line, key);
        if (h.align === "right" || key === "debit" || key === "credit" || key === "balance" || key === "running_balance") {
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

  function bindDrillDateApply() {
    const btn = els.drillBody && els.drillBody.querySelector("#fsDrillApplyDates");
    if (!btn) return;
    btn.addEventListener("click", function () {
      const fromEl = document.getElementById("fsDrillDateFrom");
      const toEl = document.getElementById("fsDrillDateTo");
      openVouchers(
        btn.getAttribute("data-ledger") || "",
        btn.getAttribute("data-name") || "Ledger",
        fromEl && fromEl.value,
        toEl && toEl.value
      );
    });
  }

  async function openVouchers(ledgerKey, name, dateFrom, dateTo) {
    if (!drillModal || !els.drillBody || !ledgerKey) return;
    els.drillBody.innerHTML = '<div class="text-muted small">Loading…</div>';
    drillModal.show();
    const params = queryParams();
    params.set("ledger_key", ledgerKey);
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    try {
      const res = await fetch(api.vouchers + "?" + params.toString(), {
        headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load ledger.");
      if (data.format === "ledger" || data.headers) {
        els.drillBody.innerHTML = renderLedgerStatement(data, name, ledgerKey);
        bindDrillDateApply();
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

  els.maximizeBtn?.addEventListener("click", function () {
    setMaximized(!isMaximized);
  });
  els.previewModalEl?.addEventListener("click", function (event) {
    const opt = event.target.closest(".ledger-export-opt");
    if (!opt) return;
    event.preventDefault();
    downloadExport((opt.getAttribute("data-fmt") || "").toLowerCase());
  });
  els.previewModalEl?.addEventListener("hidden.bs.modal", function () {
    setMaximized(false);
    setExportEnabled(false);
    previewKind = "";
    previewId = "";
  });

  if (window.JTCSLedgerPreview && typeof window.JTCSLedgerPreview.setReloader === "function") {
    window.JTCSLedgerPreview.setReloader(function () {
      if (previewKind && previewId) openLedgerPreview(previewKind, previewId);
    });
  }

  loadReport();
})();
