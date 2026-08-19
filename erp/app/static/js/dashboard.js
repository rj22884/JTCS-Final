(function () {
  "use strict";

  const cfg = window.DASHBOARD || {};
  const metricModalEl = document.getElementById("dashMetricModal");
  const entryModalEl = document.getElementById("dashEntryModal");
  const sourceModalEl = document.getElementById("dashSourceEntryModal");
  const activityPickModalEl = document.getElementById("dashActivityPickModal");
  if (!metricModalEl) return;

  const metricModal = new bootstrap.Modal(metricModalEl);
  const entryModal = entryModalEl ? new bootstrap.Modal(entryModalEl) : null;
  const sourceModal = sourceModalEl ? new bootstrap.Modal(sourceModalEl) : null;
  const activityPickModal = activityPickModalEl
    ? new bootstrap.Modal(activityPickModalEl)
    : null;

  const els = {
    title: document.getElementById("dashMetricModalTitle"),
    sub: document.getElementById("dashMetricModalSub"),
    totalLabel: document.getElementById("dashMetricTotalLabel"),
    actions: document.getElementById("dashMetricActions"),
    body: document.getElementById("dashMetricGridBody"),
    empty: document.getElementById("dashMetricEmpty"),
    addBtn: document.getElementById("dashAddEntryBtn"),
    editBtn: document.getElementById("dashEditEntryBtn"),
    deleteBtn: document.getElementById("dashDeleteEntryBtn"),
    maximizeBtn: document.getElementById("dashMetricMaximizeBtn"),
    maximizeIcon: document.getElementById("dashMetricMaximizeIcon"),
    periodForm: document.getElementById("dashPeriodForm"),
    customDatesBtn: document.getElementById("dashCustomDatesBtn"),
    entryTitle: document.getElementById("dashEntryModalTitle"),
    entryId: document.getElementById("dashEntryId"),
    entryDate: document.getElementById("dashEntryDate"),
    entryAmount: document.getElementById("dashEntryAmount"),
    entryDescription: document.getElementById("dashEntryDescription"),
    entryError: document.getElementById("dashEntryError"),
    entrySaveBtn: document.getElementById("dashEntrySaveBtn"),
    dateFrom: document.getElementById("dashDateFrom"),
    dateTo: document.getElementById("dashDateTo"),
    grid: document.getElementById("dashMetricGrid"),
    sourceTitle: document.getElementById("dashSourceEntryModalTitle"),
    sourceSub: document.getElementById("dashSourceEntryModalSub"),
    sourceFrame: document.getElementById("dashSourceEntryFrame"),
    sourceMaximizeBtn: document.getElementById("dashSourceMaximizeBtn"),
    sourceMaximizeIcon: document.getElementById("dashSourceMaximizeIcon"),
    activityList: document.getElementById("dashActivityList"),
  };

  let reloadAfterSourceClose = false;

  let currentMetric = "";
  let currentLabel = "";
  let currentAccountId = "";
  let todayActivityMode = false;
  let sourceRows = [];
  let currentRows = [];
  let selectedRowKey = null;
  let sortState = { key: "entry_date", dir: "asc" };
  let modalMaximized = false;
  let sourceModalMaximized = false;
  let sourceHighlightTimer = null;
  let pendingSourceRow = null;
  let filters = {
    entry_date: "",
    source: "",
    reference: "",
    work: "",
    customer: "",
    description: "",
    amount: "",
    running_balance: "",
  };

  function setModalMaximized(on) {
    modalMaximized = !!on;
    metricModalEl.classList.toggle("dash-modal-maximized", modalMaximized);
    if (els.maximizeBtn) {
      els.maximizeBtn.title = modalMaximized ? "Minimize" : "Maximize";
      els.maximizeBtn.setAttribute("aria-label", modalMaximized ? "Minimize" : "Maximize");
    }
    if (els.maximizeIcon) {
      els.maximizeIcon.className = modalMaximized ? "bi bi-fullscreen-exit" : "bi bi-fullscreen";
    }
  }

  function setSourceModalMaximized(on) {
    if (!sourceModalEl) return;
    sourceModalMaximized = !!on;
    sourceModalEl.classList.toggle("dash-modal-maximized", sourceModalMaximized);
    if (els.sourceMaximizeBtn) {
      els.sourceMaximizeBtn.title = sourceModalMaximized ? "Minimize" : "Maximize";
      els.sourceMaximizeBtn.setAttribute(
        "aria-label",
        sourceModalMaximized ? "Minimize" : "Maximize"
      );
    }
    if (els.sourceMaximizeIcon) {
      els.sourceMaximizeIcon.className = sourceModalMaximized
        ? "bi bi-fullscreen-exit"
        : "bi bi-fullscreen";
    }
  }

  function selectMetricRow(key) {
    selectedRowKey = key || null;
    if (!els.body) return;
    els.body.querySelectorAll("tr[data-row-key]").forEach(function (tr) {
      const match = tr.getAttribute("data-row-key") === selectedRowKey;
      tr.classList.toggle("dash-row-selected", match);
      const radio = tr.querySelector(".dash-row-select");
      if (radio && !radio.disabled) radio.checked = match;
    });
    syncActionButtons();
  }

  function clearSourceHighlightTimer() {
    if (sourceHighlightTimer) {
      clearInterval(sourceHighlightTimer);
      sourceHighlightTimer = null;
    }
  }

  function injectSourceHighlightStyle(doc) {
    if (!doc || doc.getElementById("dashSourceHighlightStyle")) return;
    const style = doc.createElement("style");
    style.id = "dashSourceHighlightStyle";
    style.textContent =
      ".dash-source-row-selected," +
      ".dash-source-row-selected > *," +
      "tr.dash-source-row-selected," +
      "tr.dash-source-row-selected > td," +
      "tr.table-active.dash-source-row-selected," +
      "tr.table-active.dash-source-row-selected > td {" +
      "background-color:#bfdbfe !important;" +
      "--bs-table-bg:#bfdbfe !important;" +
      "--bs-table-accent-bg:#bfdbfe !important;" +
      "box-shadow:inset 0 0 0 9999px #bfdbfe !important;" +
      "}";
    (doc.head || doc.documentElement).appendChild(style);
  }

  function findSourceRecordRow(doc, row) {
    if (!doc || !row) return null;
    const id = row.source_module_id != null ? String(row.source_module_id) : "";
    const module = String(row.source_module || "");
    if (!id) return null;

    const selectors = [];
    if (module === "stamp") {
      selectors.push('tr[data-stamp-id="' + id + '"]');
    } else if (module === "income_expense" || module === "bank_cash") {
      selectors.push('tr[data-entry-id="' + id + '"]', 'button[data-id="' + id + '"]');
    } else if (module === "printing_scanning") {
      selectors.push(
        'tr[data-printing-scan-id="' + id + '"]',
        'tr[data-entry-id="' + id + '"]',
        'button[data-id="' + id + '"]'
      );
    } else if (module === "followup" || module.indexOf("followup") === 0) {
      selectors.push('tr[data-entry-id="' + id + '"]', 'button[data-id="' + id + '"]');
    } else {
      selectors.push(
        'tr[data-stamp-id="' + id + '"]',
        'tr[data-entry-id="' + id + '"]',
        'tr[data-id="' + id + '"]',
        'button[data-id="' + id + '"]'
      );
    }

    for (let i = 0; i < selectors.length; i++) {
      const el = doc.querySelector(selectors[i]);
      if (!el) continue;
      return el.closest("tr") || el;
    }
    return null;
  }

  function applySourceRecordHighlight(row) {
    if (!els.sourceFrame || !row) return false;
    let doc;
    try {
      doc = els.sourceFrame.contentDocument;
    } catch (err) {
      return false;
    }
    if (!doc || !doc.body) return false;

    injectSourceHighlightStyle(doc);
    const target = findSourceRecordRow(doc, row);
    if (!target) return false;

    doc.querySelectorAll(".dash-source-row-selected").forEach(function (el) {
      el.classList.remove("dash-source-row-selected");
    });

    const tr = target.tagName === "TR" ? target : target.closest("tr");
    if (!tr) return false;

    tr.classList.add("table-active", "dash-source-row-selected");
    try {
      // Prefer activating the matched control (edit button) when present.
      if (target !== tr && typeof target.click === "function") {
        target.click();
      } else {
        tr.click();
      }
    } catch (err) {
      /* ignore */
    }
    // Re-apply after module click handlers that may reset selection styles.
    tr.classList.add("table-active", "dash-source-row-selected");
    try {
      tr.scrollIntoView({ block: "center", behavior: "smooth" });
    } catch (err) {
      try {
        tr.scrollIntoView(true);
      } catch (err2) {
        /* ignore */
      }
    }
    return true;
  }

  function startSourceRecordHighlight(row) {
    clearSourceHighlightTimer();
    pendingSourceRow = row || null;
    if (!pendingSourceRow) return;
    let attempts = 0;
    sourceHighlightTimer = setInterval(function () {
      attempts += 1;
      if (applySourceRecordHighlight(pendingSourceRow) || attempts >= 40) {
        clearSourceHighlightTimer();
      }
    }, 250);
  }

  function ensureSourceBackdropStack() {
    const backdrops = document.querySelectorAll(".modal-backdrop");
    if (!backdrops.length) return;
    const last = backdrops[backdrops.length - 1];
    last.classList.add("dash-source-backdrop");
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatMoney(value) {
    const num = parseFloat(value || "0");
    if (Number.isNaN(num)) return "₹ 0.00";
    if (num < 0) return "-₹ " + Math.abs(num).toFixed(2);
    return "₹ " + num.toFixed(2);
  }

  function isExpenseMetric() {
    return currentMetric === "total_expenses" || currentMetric === "expense";
  }

  function formatDisplayDate(value) {
    if (window.JtcsFormatDisplayDate) return window.JtcsFormatDisplayDate(value);
    return value || "";
  }

  function apiUrl(template, id) {
    return String(template || "").replace("/0", "/" + String(id));
  }

  function periodParams() {
    const from = (els.dateFrom && els.dateFrom.value) || cfg.dateFrom || "";
    const to = (els.dateTo && els.dateTo.value) || cfg.dateTo || "";
    return { from: from, to: to };
  }

  function isClosingMetric() {
    return (
      currentMetric === "cash_closing_balance" ||
      currentMetric === "bank_closing_balance"
    );
  }

  function sourceLabel(source) {
    if (source === "opening") return "Opening";
    if (source === "manual") return "Manual";
    return "System";
  }

  function selectedRow() {
    return currentRows.find(function (row) {
      return row.row_key === selectedRowKey;
    });
  }

  function rowHasSourceLink(row) {
    if (!row || row.source === "opening") return false;
    if (row.can_open === true || row.can_open === 1 || row.can_open === "1") return true;
    if (row.source_url) return true;
    if (row.source_module && row.source_module_id) return true;
    return false;
  }

  function rowCanEdit(row) {
    if (!row || todayActivityMode) return false;
    if (row.source === "opening") return false;
    return !!(rowHasSourceLink(row) || (row.source === "manual" && row.can_edit));
  }

  function resolveDeleteUrl(row) {
    if (!row || todayActivityMode || row.source === "opening") return null;
    if (row.source === "manual" && row.entry_id) {
      return apiUrl(cfg.deleteUrlTemplate, row.entry_id);
    }
    const id = row.source_module_id;
    const mod = String(row.source_module || "");
    const urls = cfg.deleteUrls || {};
    if (!id || !mod) return null;
    if (mod === "stamp" && urls.stamp) return apiUrl(urls.stamp, id);
    if (mod === "ecourt" && urls.ecourt) return apiUrl(urls.ecourt, id);
    if (mod === "income_expense" && urls.income_expense) {
      return apiUrl(urls.income_expense, id);
    }
    if (mod === "bank_cash" && urls.bank_cash) return apiUrl(urls.bank_cash, id);
    if (mod === "printing_scanning") {
      const src = String(row.source_url || "");
      const tpl =
        src.indexOf("/others/expense/") >= 0
          ? urls.printing_expense
          : urls.printing_income;
      return tpl ? apiUrl(tpl, id) : null;
    }
    if (mod === "followup") {
      const wt = String(row.work_type || "").toUpperCase();
      const map = { ITR: "itr", DSC: "dsc", TDS: "tds", GST: "gst" };
      const key = map[wt];
      if (key && urls[key]) return apiUrl(urls[key], id);
    }
    return null;
  }

  function rowCanDelete(row) {
    return !!resolveDeleteUrl(row);
  }

  function syncActionButtons() {
    const row = selectedRow();
    if (els.editBtn) els.editBtn.disabled = !rowCanEdit(row);
    if (els.deleteBtn) els.deleteBtn.disabled = !rowCanDelete(row);
  }

  function setTodayActivityMode(on) {
    todayActivityMode = !!on;
    if (els.addBtn) els.addBtn.classList.toggle("d-none", todayActivityMode);
    if (els.editBtn) els.editBtn.classList.toggle("d-none", todayActivityMode);
    if (els.deleteBtn) els.deleteBtn.classList.toggle("d-none", todayActivityMode);
    syncActionButtons();
  }

  function toggleRunningColumn(show) {
    if (!els.grid) return;
    els.grid.querySelectorAll(".dash-running-col").forEach(function (el) {
      el.classList.toggle("d-none", !show);
    });
  }

  function prepareRows(rows) {
    var list = (rows || []).map(function (row, index) {
      var amountNum = Number(row.amount || 0);
      // Expenses are outflows — show as negative (red) in Cash / Expense popups.
      if ((isExpenseMetric() || row.is_expense) && amountNum > 0) {
        amountNum = -amountNum;
      }
      var prepared = Object.assign({}, row, {
        _idx: index,
        amount_num: amountNum,
        source_label: sourceLabel(row.source),
        running_balance: null,
        running_balance_num: null,
      });
      // Keep "click here for more" when module link is present (e.g. Cash Deposit / OBC).
      if (rowHasSourceLink(prepared)) prepared.can_open = true;
      return prepared;
    });

    if (!isClosingMetric()) return list;

    var opening = [];
    var rest = [];
    list.forEach(function (row) {
      if (row.source === "opening") opening.push(row);
      else rest.push(row);
    });
    rest.sort(function (a, b) {
      var da = String(a.entry_date || "");
      var db = String(b.entry_date || "");
      if (da !== db) return da < db ? -1 : 1;
      var ra = String(a.reference || "");
      var rb = String(b.reference || "");
      if (ra !== rb) return ra < rb ? -1 : 1;
      return a._idx - b._idx;
    });
    var ordered = opening.concat(rest);
    var running = 0;
    ordered.forEach(function (row) {
      running += Number(row.amount_num || 0);
      row.running_balance_num = running;
      row.running_balance = running.toFixed(2);
    });
    return ordered;
  }

  function rowMatchesFilters(row) {
    function match(filterKey, value) {
      var needle = String(filters[filterKey] || "").trim().toLowerCase();
      if (!needle) return true;
      return String(value == null ? "" : value).toLowerCase().indexOf(needle) !== -1;
    }
    return (
      match("entry_date", row.entry_date) &&
      match("source", row.source_label) &&
      match("reference", row.reference) &&
      match("work", row.work) &&
      match("customer", row.customer) &&
      match("description", row.description) &&
      match("amount", row.amount) &&
      match("running_balance", row.running_balance)
    );
  }

  function compareRows(a, b) {
    var key = sortState.key || "entry_date";
    var dir = sortState.dir === "desc" ? -1 : 1;
    var av;
    var bv;
    if (key === "amount") {
      av = Number(a.amount_num || 0);
      bv = Number(b.amount_num || 0);
    } else if (key === "running_balance") {
      av = Number(a.running_balance_num || 0);
      bv = Number(b.running_balance_num || 0);
    } else if (key === "source") {
      av = String(a.source_label || "");
      bv = String(b.source_label || "");
    } else {
      av = String(a[key] == null ? "" : a[key]);
      bv = String(b[key] == null ? "" : b[key]);
    }
    if (av < bv) return -1 * dir;
    if (av > bv) return 1 * dir;
    return (a._idx - b._idx) * dir;
  }

  function updateSortIcons() {
    if (!els.grid) return;
    els.grid.querySelectorAll(".dash-th-label").forEach(function (label) {
      var key = label.getAttribute("data-sort");
      var icon = label.querySelector(".dash-sort-icon");
      if (!icon) return;
      if (key === sortState.key) {
        icon.className =
          "bi dash-sort-icon " +
          (sortState.dir === "desc" ? "bi-sort-down" : "bi-sort-up");
      } else {
        icon.className = "bi bi-arrow-down-up dash-sort-icon";
      }
    });
  }

  function closeSourceEntryModal() {
    clearSourceHighlightTimer();
    pendingSourceRow = null;
    setSourceModalMaximized(false);
    if (els.sourceFrame) {
      els.sourceFrame.onload = null;
      els.sourceFrame.src = "about:blank";
    }
    if (els.sourceSub) els.sourceSub.textContent = "";
  }

  function openSourceUrl(url, title, subText, highlightRow) {
    if (!url || !sourceModal || !els.sourceFrame) {
      alert("Source entry is not available.");
      return;
    }
    if (els.sourceTitle) els.sourceTitle.textContent = title || "Entry";
    if (els.sourceSub) els.sourceSub.textContent = subText || "";
    clearSourceHighlightTimer();
    pendingSourceRow = highlightRow || null;
    reloadAfterSourceClose = true;
    setSourceModalMaximized(true);
    els.sourceFrame.onload = function () {
      if (highlightRow) startSourceRecordHighlight(highlightRow);
    };
    els.sourceFrame.src = url;
    sourceModal.show();
  }

  function openSourceEntry(row) {
    if (!row || !rowHasSourceLink(row)) {
      alert("Source entry is not available for this row.");
      return;
    }
    if (row.source_module === "dashboard_manual") {
      selectMetricRow(row.row_key);
      openEntryForm("edit", row);
      return;
    }
    if (!row.source_url) {
      alert("Source entry is not available for this row.");
      return;
    }

    if (row.row_key && String(row.row_key).indexOf("recent-") !== 0) {
      selectMetricRow(row.row_key);
    }

    const bits = [];
    if (row.reference) bits.push(row.reference);
    if (row.customer && row.customer !== "—") bits.push(row.customer);
    if (row.amount_num != null && !Number.isNaN(Number(row.amount_num))) {
      bits.push(formatMoney(row.amount_num));
    } else if (row.amount != null && row.amount !== "") {
      bits.push(formatMoney(row.amount));
    }
    openSourceUrl(row.source_url, row.work || row.metric_label || "Entry", bits.join(" • "), row);
  }

  function openActivityPicker() {
    if (todayActivityMode) return;
    const activities = Array.isArray(cfg.activities) ? cfg.activities : [];
    if (!activities.length) {
      openEntryForm("add");
      return;
    }
    if (!activityPickModal || !els.activityList) {
      openEntryForm("add");
      return;
    }
    els.activityList.innerHTML = activities
      .map(function (act) {
        return (
          '<button type="button" class="list-group-item list-group-item-action dash-activity-option" data-activity-key="' +
          escapeHtml(act.key || "") +
          '">' +
          '<i class="bi bi-box-arrow-up-right me-2"></i>' +
          escapeHtml(act.label || act.key || "Activity") +
          "</button>"
        );
      })
      .join("");
    activityPickModal.show();
  }

  function startActivity(key) {
    const activities = Array.isArray(cfg.activities) ? cfg.activities : [];
    const act = activities.find(function (item) {
      return item.key === key;
    });
    if (!act) return;
    activityPickModal?.hide();
    if (!act.url || act.module === "dashboard_manual") {
      openEntryForm("add");
      return;
    }
    openSourceUrl(act.url, act.label || "Add Entry", "New entry", null);
  }

  function renderRows() {
    selectedRowKey = null;
    syncActionButtons();
    if (!els.body) return;

    toggleRunningColumn(isClosingMetric());
    updateSortIcons();

    var filtered = sourceRows.filter(rowMatchesFilters).sort(compareRows);
    currentRows = filtered;

    if (!filtered.length) {
      els.body.innerHTML = "";
      els.empty?.classList.remove("d-none");
      return;
    }
    els.empty?.classList.add("d-none");

    els.body.innerHTML = filtered
      .map(function (row) {
        const isManual = row.source === "manual";
        const isOpening = row.source === "opening";
        const amountNum = Number(row.amount_num || 0);
        const amountClass =
          isOpening
            ? ""
            : amountNum < 0
              ? " dash-row-amt-neg"
              : amountNum > 0
                ? " dash-row-amt-pos"
                : "";
        const rowClass =
          (isOpening
            ? "dash-row-opening"
            : isManual
              ? "dash-row-manual"
              : "dash-row-system") + amountClass;
        const badgeClass = isOpening
          ? "dash-source-opening"
          : isManual
            ? "dash-source-manual"
            : "dash-source-system";
        const disabledAttr = rowCanEdit(row) || rowCanDelete(row) ? "" : " disabled";
        const runningCell = isClosingMetric()
          ? '<td class="text-end dash-running-cell">' +
            escapeHtml(formatMoney(row.running_balance)) +
            "</td>"
          : "";
        const moreCell = rowHasSourceLink(row)
          ? '<td><button type="button" class="btn btn-link btn-sm p-0 dash-open-source">click here for more</button></td>'
          : '<td class="text-muted small">—</td>';
        const canDel = rowCanDelete(row);
        const actionsCell = canDel
          ? '<td class="text-nowrap">' +
            '<button type="button" class="btn btn-sm btn-outline-danger dash-row-delete" title="Delete">' +
            '<i class="bi bi-trash"></i> Delete' +
            "</button></td>"
          : '<td class="text-muted small">—</td>';
        return (
          '<tr class="' +
          rowClass +
          '" data-row-key="' +
          escapeHtml(row.row_key) +
          '" data-source="' +
          escapeHtml(row.source) +
          '">' +
          "<td>" +
          '<input type="radio" name="dashMetricSelect" class="form-check-input dash-row-select"' +
          disabledAttr +
          ' value="' +
          escapeHtml(row.row_key) +
          '">' +
          "</td>" +
          "<td>" +
          escapeHtml(formatDisplayDate(row.entry_date)) +
          "</td>" +
          "<td><span class=\"dash-source-badge " +
          badgeClass +
          '">' +
          escapeHtml(row.source_label) +
          "</span></td>" +
          "<td>" +
          escapeHtml(row.reference || "—") +
          "</td>" +
          "<td>" +
          escapeHtml(row.work || "—") +
          "</td>" +
          "<td>" +
          escapeHtml(row.customer || "—") +
          "</td>" +
          "<td>" +
          escapeHtml(row.description || "—") +
          "</td>" +
          '<td class="text-end dash-amt-cell">' +
          escapeHtml(formatMoney(row.amount_num)) +
          "</td>" +
          runningCell +
          moreCell +
          actionsCell +
          "</tr>"
        );
      })
      .join("");

    if (els.sub && els.sub.dataset.baseText) {
      els.sub.textContent =
        els.sub.dataset.baseText + " · showing " + filtered.length + " of " + sourceRows.length;
    }
  }

  function setSourceRows(rows) {
    sourceRows = prepareRows(rows || []);
    if (isClosingMetric()) {
      sortState = { key: "entry_date", dir: "asc" };
    }
    renderRows();
  }

  function updateCardTotal(metricKey, total) {
    const el = document.querySelector('[data-metric-value="' + metricKey + '"]');
    if (!el) return;
    el.textContent = formatMoney(total);
    const num = parseFloat(total || "0");
    if (!Number.isNaN(num) && num < 0) {
      el.classList.add("is-negative");
    } else {
      el.classList.remove("is-negative");
    }
  }

  function resetFilters() {
    Object.keys(filters).forEach(function (key) {
      filters[key] = "";
    });
    if (!els.grid) return;
    els.grid.querySelectorAll(".dash-col-filter").forEach(function (input) {
      input.value = "";
    });
  }

  function loadDetails() {
    if (!currentMetric) return Promise.resolve();
    var url;
    if (todayActivityMode) {
      if (!cfg.todayDetailsUrl) return Promise.resolve();
      url =
        cfg.todayDetailsUrl +
        "?metric=" +
        encodeURIComponent(currentMetric);
      if (currentAccountId) {
        url += "&account_id=" + encodeURIComponent(currentAccountId);
      }
    } else {
      if (!cfg.detailsUrl) return Promise.resolve();
      const period = periodParams();
      url =
        cfg.detailsUrl +
        "?metric=" +
        encodeURIComponent(currentMetric) +
        "&from=" +
        encodeURIComponent(period.from) +
        "&to=" +
        encodeURIComponent(period.to);
    }

    if (els.body) {
      els.body.innerHTML =
        '<tr><td colspan="11" class="text-muted">Loading...</td></tr>';
    }

    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) {
            throw new Error(data.error || "Unable to load details.");
          }
          return data;
        });
      })
      .then(function (data) {
        if (els.title) els.title.textContent = data.metric_label || currentLabel;
        var scopeLabel = todayActivityMode
          ? "Today's Activity · " + formatDisplayDate(data.date_from || cfg.systemDate)
          : "Period " +
            formatDisplayDate(data.date_from) +
            " — " +
            formatDisplayDate(data.date_to);
        var baseText = scopeLabel + " · " + (data.row_count || 0) + " record(s)";
        if (els.sub) {
          els.sub.dataset.baseText = baseText;
          els.sub.textContent = baseText;
        }
        if (els.totalLabel) {
          var totalNum = Number(data.total || 0);
          if (isExpenseMetric() && totalNum > 0) totalNum = -totalNum;
          els.totalLabel.textContent =
            (isClosingMetric() ? "Closing: " : "Total: ") + formatMoney(totalNum);
          els.totalLabel.classList.toggle("dash-total-expense", isExpenseMetric());
        }
        if (!todayActivityMode) {
          updateCardTotal(currentMetric, data.total);
        }
        resetFilters();
        setSourceRows(data.rows || []);
      })
      .catch(function (err) {
        if (els.body) {
          els.body.innerHTML =
            '<tr><td colspan="11" class="text-danger">' +
            escapeHtml(err.message || "Load failed.") +
            "</td></tr>";
        }
      });
  }

  function openMetric(metric, label) {
    currentMetric = metric;
    currentLabel = label || metric;
    currentAccountId = "";
    setTodayActivityMode(false);
    if (els.title) els.title.textContent = currentLabel;
    if (els.sub) els.sub.textContent = "Loading...";
    setModalMaximized(false);
    metricModal.show();
    loadDetails();
  }

  function openTodayActivity(metric, label, accountId) {
    currentMetric = metric;
    currentLabel = label || metric;
    currentAccountId = accountId || "";
    setTodayActivityMode(true);
    if (els.title) els.title.textContent = currentLabel;
    if (els.sub) els.sub.textContent = "Loading...";
    setModalMaximized(true);
    metricModal.show();
    loadDetails();
  }

  function openEntryForm(mode, row) {
    if (!entryModal || todayActivityMode) return;
    if (els.entryError) {
      els.entryError.classList.add("d-none");
      els.entryError.textContent = "";
    }
    if (mode === "edit" && row) {
      if (els.entryTitle) els.entryTitle.textContent = "Edit Entry";
      if (els.entryId) els.entryId.value = String(row.entry_id || "");
      if (els.entryDate) els.entryDate.value = row.entry_date || "";
      if (els.entryAmount) els.entryAmount.value = row.amount || "";
      if (els.entryDescription) els.entryDescription.value = row.description || "";
    } else {
      if (els.entryTitle) els.entryTitle.textContent = "Add Entry";
      if (els.entryId) els.entryId.value = "";
      if (els.entryDate) {
        els.entryDate.value =
          (els.dateTo && els.dateTo.value) || cfg.dateTo || new Date().toISOString().slice(0, 10);
      }
      if (els.entryAmount) els.entryAmount.value = "";
      if (els.entryDescription) els.entryDescription.value = "";
    }
    entryModal.show();
  }

  function saveEntry() {
    const entryId = (els.entryId && els.entryId.value) || "";
    const payload = {
      metric_key: currentMetric,
      entry_date: els.entryDate ? els.entryDate.value : "",
      amount: els.entryAmount ? els.entryAmount.value : "",
      description: els.entryDescription ? els.entryDescription.value : "",
    };
    if (!payload.entry_date) {
      if (els.entryError) {
        els.entryError.textContent = "Date is required.";
        els.entryError.classList.remove("d-none");
      }
      return;
    }
    if (!payload.amount || Number(payload.amount) === 0) {
      if (els.entryError) {
        els.entryError.textContent = "Amount is required and cannot be zero.";
        els.entryError.classList.remove("d-none");
      }
      return;
    }

    const url = entryId ? apiUrl(cfg.updateUrlTemplate, entryId) : cfg.createUrl;
    if (els.entrySaveBtn) els.entrySaveBtn.disabled = true;

    fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": cfg.csrfToken || "",
      },
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) {
            throw new Error(data.error || "Save failed.");
          }
          return data;
        });
      })
      .then(function () {
        entryModal?.hide();
        return loadDetails();
      })
      .catch(function (err) {
        if (els.entryError) {
          els.entryError.textContent = err.message || "Save failed.";
          els.entryError.classList.remove("d-none");
        } else {
          alert(err.message || "Save failed.");
        }
      })
      .finally(function () {
        if (els.entrySaveBtn) els.entrySaveBtn.disabled = false;
      });
  }

  async function deleteRow(row) {
    const url = resolveDeleteUrl(row);
    if (!url) {
      alert("Delete is not available for this row.");
      return;
    }
    const label = row.reference || row.work || "this entry";
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!(await JTCSDialog.confirm("Confirm delete: " + label + " ?"))) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: "Confirm delete: " + label + " ?" });
      if (!creds) return;
    }

    fetch(url, {
      method: "POST",
      headers: Object.assign(
        { Accept: "application/json", "X-CSRFToken": cfg.csrfToken || "" },
        creds ? { "Content-Type": "application/json" } : {}
      ),
      ...(creds
        ? { body: JSON.stringify({ user_id: creds.user_id, password: creds.password }) }
        : {}),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) {
            throw new Error(data.error || data.message || "Delete failed.");
          }
          return data;
        });
      })
      .then(function () {
        return loadDetails();
      })
      .catch(function (err) {
        alert(err.message || "Delete failed.");
      });
  }

  function deleteSelected() {
    const row = selectedRow();
    if (!row) {
      alert("Select a row to delete.");
      return;
    }
    deleteRow(row);
  }

  function recentRowFromEl(tr) {
    if (!tr) return null;
    return {
      row_key: tr.getAttribute("data-row-key") || "",
      can_open: tr.getAttribute("data-can-open") === "1",
      source_url: tr.getAttribute("data-source-url") || "",
      source_module: tr.getAttribute("data-source-module") || "",
      source_module_id: tr.getAttribute("data-source-module-id") || "",
      work: tr.getAttribute("data-work") || "",
      reference: tr.getAttribute("data-reference") || "",
      customer: tr.getAttribute("data-customer") || "",
      bank_account: tr.getAttribute("data-bank-account") || "",
      amount: tr.getAttribute("data-amount") || "",
      is_expense: tr.getAttribute("data-is-expense") === "1",
    };
  }

  function openRecentSource(tr) {
    const row = recentRowFromEl(tr);
    if (!row) return;
    if (!row.can_open || !row.source_url) {
      alert("Source entry form is not available for this transaction.");
      return;
    }
    openSourceEntry(row);
  }

  const recentBody = document.getElementById("dashRecentBody");
  if (recentBody) {
    recentBody.addEventListener("click", function (event) {
      const tr = event.target.closest("tr.dash-recent-row");
      if (!tr || !recentBody.contains(tr)) return;
      openRecentSource(tr);
    });
    recentBody.addEventListener("keydown", function (event) {
      if (event.key !== "Enter" && event.key !== " ") return;
      const tr = event.target.closest("tr.dash-recent-row");
      if (!tr || !recentBody.contains(tr)) return;
      event.preventDefault();
      openRecentSource(tr);
    });
  }

  document.querySelectorAll(".dash-metric-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      openMetric(btn.getAttribute("data-metric"), btn.getAttribute("data-label"));
    });
  });

  document.querySelectorAll(".dash-today-metric-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      openTodayActivity(
        btn.getAttribute("data-today-metric"),
        btn.getAttribute("data-label"),
        btn.getAttribute("data-account-id")
      );
    });
  });

  els.grid?.addEventListener("click", function (event) {
    const sortLabel = event.target.closest(".dash-th-label");
    if (sortLabel) {
      const key = sortLabel.getAttribute("data-sort");
      if (!key) return;
      if (sortState.key === key) {
        sortState.dir = sortState.dir === "asc" ? "desc" : "asc";
      } else {
        sortState.key = key;
        sortState.dir = key === "entry_date" ? "asc" : "asc";
      }
      renderRows();
      return;
    }
  });

  els.grid?.addEventListener("input", function (event) {
    const input = event.target.closest(".dash-col-filter");
    if (!input) return;
    const key = input.getAttribute("data-filter");
    if (!key) return;
    filters[key] = input.value || "";
    renderRows();
  });

  els.body?.addEventListener("change", function (event) {
    const input = event.target.closest(".dash-row-select");
    if (!input) return;
    selectMetricRow(input.value);
  });

  els.body?.addEventListener("click", function (event) {
    const openBtn = event.target.closest(".dash-open-source");
    if (openBtn) {
      event.preventDefault();
      event.stopPropagation();
      const tr = openBtn.closest("tr[data-row-key]");
      if (!tr) return;
      const key = tr.getAttribute("data-row-key");
      const row = currentRows.find(function (item) {
        return item.row_key === key;
      });
      openSourceEntry(row);
      return;
    }
    const delBtn = event.target.closest(".dash-row-delete");
    if (delBtn) {
      event.preventDefault();
      event.stopPropagation();
      const tr = delBtn.closest("tr[data-row-key]");
      if (!tr) return;
      const key = tr.getAttribute("data-row-key");
      const row = currentRows.find(function (item) {
        return item.row_key === key;
      });
      if (row) {
        selectMetricRow(row.row_key);
        deleteRow(row);
      }
      return;
    }
    const tr = event.target.closest("tr[data-row-key]");
    if (!tr) return;
    const radio = tr.querySelector(".dash-row-select");
    if (radio && !radio.disabled) {
      selectMetricRow(radio.value);
    }
  });

  metricModalEl.addEventListener("hidden.bs.modal", function () {
    setModalMaximized(false);
    setTodayActivityMode(false);
    currentAccountId = "";
    if (sourceModalEl && sourceModalEl.classList.contains("show")) {
      sourceModal?.hide();
    }
    closeSourceEntryModal();
  });

  sourceModalEl?.addEventListener("shown.bs.modal", function () {
    ensureSourceBackdropStack();
  });

  sourceModalEl?.addEventListener("hidden.bs.modal", function () {
    closeSourceEntryModal();
    if (reloadAfterSourceClose) {
      reloadAfterSourceClose = false;
      loadDetails();
    }
  });

  els.activityList?.addEventListener("click", function (event) {
    const btn = event.target.closest(".dash-activity-option");
    if (!btn) return;
    startActivity(btn.getAttribute("data-activity-key") || "");
  });

  els.maximizeBtn?.addEventListener("click", function () {
    setModalMaximized(!modalMaximized);
  });

  els.sourceMaximizeBtn?.addEventListener("click", function () {
    setSourceModalMaximized(!sourceModalMaximized);
  });

  els.customDatesBtn?.addEventListener("click", function () {
    els.customDatesBtn.classList.add("active");
    document.querySelectorAll(".dash-period-row-presets a.btn").forEach(function (btn) {
      btn.classList.remove("active");
    });
    els.dateFrom?.focus();
  });

  els.periodForm?.addEventListener("submit", function (event) {
    const from = (els.dateFrom?.value || "").trim();
    const to = (els.dateTo?.value || "").trim();
    if (!from || !to) {
      event.preventDefault();
      alert("Custom Dates ke liye From aur To dono select karein.");
      (from ? els.dateTo : els.dateFrom)?.focus();
      return;
    }
    // Ensure custom apply does not keep a preset query param.
    const periodInput = els.periodForm.querySelector('input[name="period"]');
    if (periodInput) periodInput.remove();
  });

  els.addBtn?.addEventListener("click", function () {
    openActivityPicker();
  });
  els.editBtn?.addEventListener("click", function () {
    const row = selectedRow();
    if (!rowCanEdit(row)) {
      alert("Select a row that can be opened for edit.");
      return;
    }
    openSourceEntry(row);
  });
  els.deleteBtn?.addEventListener("click", deleteSelected);
  els.entrySaveBtn?.addEventListener("click", saveEntry);
})();
