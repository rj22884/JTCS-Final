/**
 * Shared ledger preview grid: From/To dates, filter, sort, edit/delete.
 * Used by Dashboard "Search Ledger Here" and Reports → Ledger Report.
 */
(function () {
  "use strict";

  const modal = document.getElementById("ledgerPreviewModal");
  if (!modal) return;

  const cfg = window.LEDGER_REPORT || {};
  const dashCfg = window.DASHBOARD || {};

  let sortKey = "date";
  let sortDir = 1;
  let reloadPreview = null;
  let groupBy = null;
  let mutationActive = false;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function toolbar() {
    return {
      from: document.getElementById("ledgerPreviewDateFrom"),
      to: document.getElementById("ledgerPreviewDateTo"),
      filter: document.getElementById("ledgerPreviewFilter"),
      apply: document.getElementById("ledgerPreviewApplyDates"),
      groupBtn: document.getElementById("ledgerPreviewGroupByBtn"),
      removeGroup: document.getElementById("ledgerPreviewRemoveGroup"),
      grid: document.getElementById("ledgerPreviewGrid"),
    };
  }

  function readDateValue(el) {
    return el ? String(el.value || "").trim() : "";
  }

  function resolvePreviewDates() {
    const els = toolbar();
    const pageFrom = document.getElementById("ledgerDateFrom");
    const pageTo = document.getElementById("ledgerDateTo");
    const fsFrom = document.getElementById("fsDateFrom");
    const fsTo = document.getElementById("fsDateTo");
    const dashFrom = document.getElementById("dashDateFrom");
    const dashTo = document.getElementById("dashDateTo");
    const onLedgerReport = !!pageFrom;
    const from =
      readDateValue(els.from) ||
      readDateValue(pageFrom) ||
      readDateValue(fsFrom) ||
      readDateValue(dashFrom) ||
      (onLedgerReport ? "" : String(cfg.fyStart || "").trim()) ||
      "";
    const to =
      readDateValue(els.to) ||
      readDateValue(pageTo) ||
      readDateValue(fsTo) ||
      readDateValue(dashTo) ||
      (onLedgerReport ? "" : String(cfg.today || "").trim()) ||
      "";
    return { from: from, to: to };
  }

  function dateQuery() {
    const dates = resolvePreviewDates();
    const params = new URLSearchParams();
    if (dates.from) params.set("date_from", dates.from);
    if (dates.to) params.set("date_to", dates.to);
    const q = params.toString();
    return q ? "?" + q : "";
  }

  function ensurePreviewDatesFilled() {
    const els = toolbar();
    if (!els.from || !els.to) return;
    const pageFrom = document.getElementById("ledgerDateFrom");
    const pageTo = document.getElementById("ledgerDateTo");
    if (!readDateValue(els.from)) {
      els.from.value =
        readDateValue(pageFrom) || String(cfg.fyStart || "").trim() || "";
    }
    if (!readDateValue(els.to)) {
      els.to.value = readDateValue(pageTo) || String(cfg.today || "").trim() || "";
    }
  }

  function applyPreviewDates() {
    ensurePreviewDatesFilled();
    const dates = resolvePreviewDates();
    if (!dates.from || !dates.to) {
      alert("Enter both From Date and To Date, then click Apply.");
      return false;
    }
    const pageFrom = document.getElementById("ledgerDateFrom");
    const pageTo = document.getElementById("ledgerDateTo");
    if (pageFrom && !readDateValue(pageFrom)) pageFrom.value = dates.from;
    if (pageTo && !readDateValue(pageTo)) pageTo.value = dates.to;
    if (typeof reloadPreview === "function") {
      reloadPreview();
      return true;
    }
    alert("Preview reload is not ready. Close the preview and open it again.");
    return false;
  }

  function parseMoney(text) {
    const n = parseFloat(String(text == null ? "" : text).replace(/,/g, ""));
    return Number.isFinite(n) ? n : 0;
  }

  function formatMoney(value) {
    return Number(value || 0).toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function isChromeRow(tr) {
    return !!(
      tr &&
      (tr.classList.contains("ledger-group-header") || tr.classList.contains("ledger-group-total"))
    );
  }

  function isDataRow(tr) {
    return !!(tr && tr.querySelector("td") && !isChromeRow(tr));
  }

  function markOriginalOrder(tbody) {
    Array.prototype.forEach.call(tbody.rows, function (tr, index) {
      if (!tr.hasAttribute("data-orig-idx")) {
        tr.setAttribute("data-orig-idx", String(index));
      }
    });
  }

  function clearGroupRows(tbody) {
    tbody.querySelectorAll("tr.ledger-group-header, tr.ledger-group-total").forEach(function (tr) {
      tr.remove();
    });
  }

  function restoreOriginalOrder(tbody) {
    const rows = Array.prototype.slice.call(tbody.rows);
    rows.sort(function (a, b) {
      return Number(a.getAttribute("data-orig-idx") || 0) - Number(b.getAttribute("data-orig-idx") || 0);
    });
    rows.forEach(function (tr) {
      tbody.appendChild(tr);
    });
  }

  function rowMoney(tr, col) {
    const td = tr.querySelector('[data-col="' + col + '"]');
    if (!td) return 0;
    const raw = td.getAttribute("data-sort-value");
    return parseMoney(raw != null && raw !== "" ? raw : td.textContent);
  }

  const MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];
  const PERIOD_MODES = { day: 1, week: 1, month: 1, quarter: 1, year: 1 };
  const GROUP_LABELS = {
    day: "Day",
    week: "Week",
    month: "Month",
    quarter: "Quarter",
    year: "Year",
    debit: "Debit",
    credit: "Credit",
  };

  function pad2(value) {
    return String(value).padStart(2, "0");
  }

  function formatDmY(d) {
    return pad2(d.getDate()) + "/" + pad2(d.getMonth() + 1) + "/" + d.getFullYear();
  }

  function isoDay(d) {
    return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate());
  }

  function fyLabel(startYear) {
    return "FY " + startYear + "-" + String(startYear + 1).slice(-2);
  }

  function rowDate(tr) {
    const td = tr.querySelector('[data-col="date"]');
    if (!td) return null;
    const iso = String(td.getAttribute("data-sort-value") || "").trim();
    const isoMatch = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (isoMatch) {
      return new Date(Number(isoMatch[1]), Number(isoMatch[2]) - 1, Number(isoMatch[3]));
    }
    const text = String(td.textContent || "").trim();
    const shown = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (!shown) return null;
    return new Date(Number(shown[3]), Number(shown[2]) - 1, Number(shown[1]));
  }

  function fyParts(d) {
    const month = d.getMonth();
    if (month >= 3) {
      return { quarter: Math.floor((month - 3) / 3) + 1, year: d.getFullYear() };
    }
    return { quarter: 4, year: d.getFullYear() - 1 };
  }

  function periodGroup(tr, mode) {
    const d = rowDate(tr);
    if (!d) return { key: "9999-99-99", label: "—" };
    if (mode === "day") {
      return { key: isoDay(d), label: "Date: " + formatDmY(d) };
    }
    if (mode === "week") {
      const weekday = d.getDay();
      const mondayOffset = weekday === 0 ? -6 : 1 - weekday;
      const start = new Date(d.getFullYear(), d.getMonth(), d.getDate() + mondayOffset);
      const end = new Date(start.getFullYear(), start.getMonth(), start.getDate() + 6);
      return {
        key: isoDay(start),
        label: "Week: " + formatDmY(start) + " – " + formatDmY(end),
      };
    }
    if (mode === "month") {
      return {
        key: d.getFullYear() + "-" + pad2(d.getMonth() + 1),
        label: "Month: " + MONTH_NAMES[d.getMonth()] + " " + d.getFullYear(),
      };
    }
    const fy = fyParts(d);
    if (mode === "quarter") {
      return {
        key: fy.year + "-Q" + fy.quarter,
        label: "Quarter: Q" + fy.quarter + " " + fyLabel(fy.year),
      };
    }
    return { key: String(fy.year), label: "Year: " + fyLabel(fy.year) };
  }

  function groupKey(tr, mode) {
    if (PERIOD_MODES[mode]) return periodGroup(tr, mode).key;
    return rowMoney(tr, mode === "debit" ? "debit" : "credit").toFixed(2);
  }

  function groupLabel(mode, key, tr) {
    if (PERIOD_MODES[mode]) return periodGroup(tr, mode).label;
    if (mode === "debit") return "Debit: " + formatMoney(parseFloat(key));
    return "Credit: " + formatMoney(parseFloat(key));
  }

  function updateGroupButtons() {
    const els = toolbar();
    if (els.groupBtn) {
      els.groupBtn.innerHTML = groupBy
        ? '<i class="bi bi-collection"></i> Group By: ' + (GROUP_LABELS[groupBy] || groupBy)
        : '<i class="bi bi-collection"></i> Group By';
      els.groupBtn.classList.toggle("active", !!groupBy);
    }
    if (els.removeGroup) {
      els.removeGroup.disabled = !groupBy;
    }
    document.querySelectorAll(".ledger-group-by-opt").forEach(function (opt) {
      opt.classList.toggle("active", opt.getAttribute("data-group-by") === groupBy);
    });
  }

  function applyGroup() {
    const els = toolbar();
    if (!els.grid) return;
    const tbody = els.grid.tBodies[0];
    if (!tbody) return;
    clearGroupRows(tbody);
    updateGroupButtons();
    if (!groupBy) return;

    const opening = [];
    const rest = [];
    Array.prototype.forEach.call(tbody.rows, function (tr) {
      if (!isDataRow(tr)) return;
      if ((tr.getAttribute("data-kind") || "") === "opening") opening.push(tr);
      else rest.push(tr);
    });

    const visible = rest.filter(function (tr) {
      return !tr.hidden;
    });
    const hidden = rest.filter(function (tr) {
      return tr.hidden;
    });

    const groups = [];
    const index = {};
    visible.forEach(function (tr) {
      const key = groupKey(tr, groupBy);
      if (!Object.prototype.hasOwnProperty.call(index, key)) {
        index[key] = groups.length;
        groups.push({ key: key, rows: [], label: groupLabel(groupBy, key, tr) });
      }
      groups[index[key]].rows.push(tr);
    });
    if (PERIOD_MODES[groupBy]) {
      groups.sort(function (a, b) {
        if (a.key < b.key) return -1;
        if (a.key > b.key) return 1;
        return 0;
      });
    }

    opening.forEach(function (tr) {
      tbody.appendChild(tr);
    });
    groups.forEach(function (group) {
      let debit = 0;
      let credit = 0;
      group.rows.forEach(function (tr) {
        debit += rowMoney(tr, "debit");
        credit += rowMoney(tr, "credit");
      });
      const countLabel =
        group.rows.length + " record" + (group.rows.length === 1 ? "" : "s");
      const header = document.createElement("tr");
      header.className = "ledger-group-header";
      header.innerHTML =
        '<td colspan="2"><strong>' +
        escapeHtml(group.label) +
        "</strong> <span class=\"text-muted\">(" +
        countLabel +
        ")</span></td>" +
        '<td class="text-end"><strong>' +
        formatMoney(debit) +
        "</strong></td>" +
        '<td class="text-end"><strong>' +
        formatMoney(credit) +
        "</strong></td>" +
        "<td></td><td></td>";
      tbody.appendChild(header);
      group.rows.forEach(function (tr) {
        tbody.appendChild(tr);
      });
      const total = document.createElement("tr");
      total.className = "ledger-group-total";
      total.innerHTML =
        '<td colspan="2"><strong>' +
        escapeHtml(PERIOD_MODES[groupBy] ? GROUP_LABELS[groupBy] + " Total" : "Total Debit / Credit") +
        "</strong></td>" +
        '<td class="text-end"><strong>' +
        formatMoney(debit) +
        "</strong></td>" +
        '<td class="text-end"><strong>' +
        formatMoney(credit) +
        "</strong></td>" +
        "<td colspan=\"2\"></td>";
      tbody.appendChild(total);
    });
    hidden.forEach(function (tr) {
      tbody.appendChild(tr);
    });
  }

  function setGroupBy(mode) {
    groupBy = mode || null;
    applyGroup();
  }

  function removeGroup() {
    groupBy = null;
    const els = toolbar();
    const tbody = els.grid && els.grid.tBodies[0];
    if (tbody) {
      clearGroupRows(tbody);
      restoreOriginalOrder(tbody);
    }
    updateGroupButtons();
    applySort();
    applyFilter();
  }

  function applyFilter() {
    const els = toolbar();
    if (!els.grid) return;
    const needle = String(els.filter?.value || "")
      .trim()
      .toLowerCase();
    els.grid.querySelectorAll("tbody tr").forEach(function (tr) {
      if (!tr.querySelector("td") || isChromeRow(tr)) return;
      if (!needle) {
        tr.hidden = false;
        return;
      }
      tr.hidden = (tr.textContent || "").toLowerCase().indexOf(needle) === -1;
    });
    applyGroup();
  }

  function cellSortValue(tr, key, type) {
    const td = tr.querySelector('[data-col="' + key + '"]');
    if (!td) return "";
    const raw = td.getAttribute("data-sort-value");
    const text = raw != null && raw !== "" ? raw : (td.textContent || "").trim();
    if (type === "num") {
      const n = parseFloat(String(text).replace(/,/g, ""));
      return Number.isFinite(n) ? n : 0;
    }
    return String(text).toLowerCase();
  }

  function applySort() {
    const els = toolbar();
    if (!els.grid) return;
    const th = els.grid.querySelector('th[data-sort="' + sortKey + '"]');
    const type = th ? th.getAttribute("data-sort-type") || "text" : "text";
    const tbody = els.grid.tBodies[0];
    if (!tbody) return;
    clearGroupRows(tbody);
    const rows = Array.prototype.slice.call(tbody.rows);
    const opening = [];
    const rest = [];
    rows.forEach(function (tr) {
      if (!isDataRow(tr)) return;
      if ((tr.getAttribute("data-kind") || "") === "opening") opening.push(tr);
      else rest.push(tr);
    });
    rest.sort(function (a, b) {
      const av = cellSortValue(a, sortKey, type);
      const bv = cellSortValue(b, sortKey, type);
      if (av < bv) return -1 * sortDir;
      if (av > bv) return 1 * sortDir;
      return 0;
    });
    opening.concat(rest).forEach(function (tr) {
      tbody.appendChild(tr);
    });
    els.grid.querySelectorAll("th.ledger-sort").forEach(function (header) {
      header.classList.toggle("is-sorted", header.getAttribute("data-sort") === sortKey);
    });
  }

  function rowFromTr(tr) {
    if (!tr) return null;
    return {
      source_url: tr.getAttribute("data-source-url") || "",
      source_module: tr.getAttribute("data-source-module") || "",
      source_module_id: tr.getAttribute("data-source-module-id") || "",
      work_type: tr.getAttribute("data-work-type") || "",
      can_edit: tr.getAttribute("data-can-edit") === "1",
      can_delete: tr.getAttribute("data-can-delete") === "1",
      source_lock_message: tr.getAttribute("data-source-lock") || "",
      description: (tr.querySelector('[data-col="description"]')?.textContent || "").trim(),
    };
  }

  function apiUrl(template, id) {
    if (!template) return "";
    return String(template).replace(/\/0(?=\/|$)/, "/" + encodeURIComponent(id));
  }

  function resolveDeleteUrl(row) {
    if (!row || !row.can_delete) return null;
    const id = row.source_module_id;
    const mod = String(row.source_module || "");
    const urls = Object.assign({}, dashCfg.deleteUrls || {}, cfg.deleteUrls || {});
    if (!id || !mod) return null;
    if (mod === "stamp" && urls.stamp) return apiUrl(urls.stamp, id);
    if (mod === "ecourt" && urls.ecourt) return apiUrl(urls.ecourt, id);
    if (mod === "income_expense" && urls.income_expense) {
      return apiUrl(urls.income_expense, id);
    }
    if (mod === "bank_cash" && urls.bank_cash) return apiUrl(urls.bank_cash, id);
    if ((mod === "invoice" || mod === "gst_invoice") && urls.invoice) {
      return apiUrl(urls.invoice, id);
    }
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

  function csrfToken() {
    return cfg.csrfToken || dashCfg.csrfToken || "";
  }

  function openEdit(row) {
    if (row && row.source_lock_message) {
      alert(row.source_lock_message);
      return;
    }
    if (!row || !row.can_edit || !row.source_url) {
      alert("Edit is not available for this row. Source entry could not be resolved.");
      return;
    }
    const frame = document.getElementById("dashSourceEntryFrame");
    const modalEl = document.getElementById("dashSourceEntryModal");
    if (frame && modalEl && window.bootstrap) {
      const sourceModal = bootstrap.Modal.getOrCreateInstance(modalEl);
      mutationActive = true;
      const title = document.getElementById("dashSourceEntryModalTitle");
      if (title) title.textContent = "Edit Entry";
      frame.src = row.source_url;
      // Stack above ledger preview modal when both are open.
      modalEl.style.zIndex = "1065";
      sourceModal.show();
      return;
    }
    window.open(row.source_url, "_blank");
  }

  async function deleteRow(row) {
    if (row && row.source_lock_message) {
      alert(row.source_lock_message);
      return;
    }
    const url = resolveDeleteUrl(row);
    if (!url) {
      alert("Delete is not available for this row.");
      return;
    }
    const label = row.description || "this entry";
    let creds = null;
    mutationActive = true;
    try {
      if (!window.JTCSDeleteConfirm?.ask) {
        if (!(await JTCSDialog.confirm("This will permanently delete from your database.\n\nClick OK for Yes, or Cancel for No."))) {
          return;
        }
      } else {
        creds = await window.JTCSDeleteConfirm.ask({
          title: "Confirm Delete",
          message: "This will permanently delete from your database.\n\nEnter your User ID and password.",
          confirmLabel: "Yes",
          cancelLabel: "No",
        });
        if (!creds) return;
      }
      const res = await fetch(url, {
        method: "POST",
        headers: Object.assign(
          { Accept: "application/json", "X-CSRFToken": csrfToken() },
          creds ? { "Content-Type": "application/json" } : {}
        ),
        ...(creds
          ? { body: JSON.stringify({ user_id: creds.user_id, password: creds.password }) }
          : {}),
      });
      const data = await res.json().catch(function () {
        return {};
      });
      if (!res.ok || data.ok === false) {
        throw new Error(data.error || data.message || "Delete failed.");
      }
      if (typeof reloadPreview === "function") await reloadPreview();
    } catch (err) {
      alert(err.message || "Delete failed.");
    } finally {
      if (!modal.classList.contains("show") && typeof reloadPreview === "function") {
        await reloadPreview();
      }
      mutationActive = false;
    }
  }

  modal.addEventListener("click", function (event) {
    if (event.target.closest("#ledgerPreviewApplyDates")) {
      event.preventDefault();
      applyPreviewDates();
      return;
    }
    const groupOpt = event.target.closest(".ledger-group-by-opt");
    if (groupOpt && modal.contains(groupOpt)) {
      event.preventDefault();
      setGroupBy(groupOpt.getAttribute("data-group-by") || "");
      return;
    }
    if (event.target.closest("#ledgerPreviewRemoveGroup")) {
      event.preventDefault();
      removeGroup();
      return;
    }
    const sortTh = event.target.closest("th.ledger-sort");
    if (sortTh && modal.contains(sortTh)) {
      const key = sortTh.getAttribute("data-sort") || "date";
      if (sortKey === key) sortDir *= -1;
      else {
        sortKey = key;
        sortDir = 1;
      }
      applySort();
      applyFilter();
      return;
    }
    const editBtn = event.target.closest(".ledger-row-edit");
    if (editBtn && !editBtn.disabled) {
      event.preventDefault();
      openEdit(rowFromTr(editBtn.closest("tr")));
      return;
    }
    const delBtn = event.target.closest(".ledger-row-delete");
    if (delBtn && !delBtn.disabled) {
      event.preventDefault();
      deleteRow(rowFromTr(delBtn.closest("tr")));
    }
  });

  modal.addEventListener("input", function (event) {
    if (event.target && event.target.id === "ledgerPreviewFilter") applyFilter();
  });
  modal.addEventListener("keydown", function (event) {
    if (event.key !== "Enter") return;
    if (
      event.target &&
      (event.target.id === "ledgerPreviewDateFrom" ||
        event.target.id === "ledgerPreviewDateTo")
    ) {
      event.preventDefault();
      applyPreviewDates();
    }
  });

  modal.addEventListener("hidden.bs.modal", function () {
    if (!mutationActive) groupBy = null;
  });

  document.getElementById("dashSourceEntryModal")?.addEventListener(
    "hidden.bs.modal",
    function () {
      if (
        (modal.classList.contains("show") || mutationActive) &&
        typeof reloadPreview === "function"
      ) {
        Promise.resolve(reloadPreview()).finally(function () {
          mutationActive = false;
        });
      }
    }
  );

  window.JTCSLedgerPreview = {
    dateQuery: dateQuery,
    viewQuery: function () {
      const params = new URLSearchParams();
      if (groupBy) params.set("group_by", groupBy);
      const box = document.getElementById("ledgerPreviewFilter");
      const q = box ? String(box.value || "").trim() : "";
      if (q) params.set("grid_q", q);
      if (groupBy || q) {
        params.set("sort_key", sortKey || "date");
        params.set("sort_dir", sortDir < 0 ? "desc" : "asc");
      }
      return params.toString();
    },
    appendView: function (url) {
      const extra =
        window.JTCSLedgerPreview && typeof window.JTCSLedgerPreview.viewQuery === "function"
          ? window.JTCSLedgerPreview.viewQuery()
          : "";
      if (!extra) return url;
      return url + (String(url).indexOf("?") >= 0 ? "&" : "?") + extra;
    },
    setReloader: function (fn) {
      reloadPreview = fn;
    },
    isMutationActive: function () {
      return mutationActive;
    },
    afterRender: function () {
      ensurePreviewDatesFilled();
      const els = toolbar();
      if (els.grid && els.grid.tBodies[0]) {
        markOriginalOrder(els.grid.tBodies[0]);
      }
      updateGroupButtons();
      applySort();
      applyFilter();
    },
  };
})();
