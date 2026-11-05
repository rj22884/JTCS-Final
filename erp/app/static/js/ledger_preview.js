/**
 * Shared ledger preview grid: From/To dates, filter, sort, and edit.
 * Used by Dashboard "Search Ledger Here" and Reports → Ledger Report.
 */
(function () {
  "use strict";

  const modal = document.getElementById("ledgerPreviewModal");
  if (!modal) return;

  const cfg = window.LEDGER_REPORT || {};
  const dashCfg = window.DASHBOARD || {};

  let sortKey = "date";
  let sortDir = -1;
  let reloadPreview = null;
  let groupBy = null;
  let mutationActive = false;
  let returnToPreviewAfterMutation = false;
  let ecourtEntryOpenTimer = null;
  let previewPage = 1;
  let previewPageSize = 20;

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
      pageSize: document.getElementById("ledgerPreviewPageSize"),
      pageInfo: document.getElementById("ledgerPreviewPageInfo"),
      prev: document.getElementById("ledgerPreviewPrev"),
      next: document.getElementById("ledgerPreviewNext"),
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
    return !!(tr && tr.querySelector("td") && !isChromeRow(tr) && !tr.classList.contains("ledger-preview-empty-row"));
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
    if (!groupBy) {
      applyPreviewPagination();
      return;
    }

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
    applyPreviewPagination();
  }

  function applyPreviewPagination() {
    const els = toolbar();
    if (!els.grid || !els.grid.tBodies[0]) return;
    if (els.pageSize) {
      const requestedSize = Number(els.pageSize.value);
      previewPageSize = [20, 25, 50, 100, 500].includes(requestedSize) ? requestedSize : 20;
      els.pageSize.value = String(previewPageSize);
    }
    const tbody = els.grid.tBodies[0];
    const eligible = Array.prototype.filter.call(tbody.rows, function (tr) {
      return isDataRow(tr) && !tr.hidden;
    });
    const total = eligible.length;
    const pages = Math.max(1, Math.ceil(total / previewPageSize));
    previewPage = Math.min(Math.max(1, previewPage), pages);
    const startIndex = (previewPage - 1) * previewPageSize;
    const pageRows = new Set(eligible.slice(startIndex, startIndex + previewPageSize));
    let groupHeader = null;
    let groupHasVisibleRow = false;
    Array.prototype.forEach.call(tbody.rows, function (tr) {
      if (tr.classList.contains("ledger-group-header")) {
        groupHeader = tr;
        groupHasVisibleRow = false;
        tr.style.display = "none";
        return;
      }
      if (tr.classList.contains("ledger-group-total")) {
        tr.style.display = groupHasVisibleRow ? "" : "none";
        if (groupHeader) groupHeader.style.display = groupHasVisibleRow ? "" : "none";
        groupHeader = null;
        groupHasVisibleRow = false;
        return;
      }
      if (!isDataRow(tr)) return;
      const show = !tr.hidden && pageRows.has(tr);
      tr.style.display = show ? "" : "none";
      if (show && groupHeader) groupHasVisibleRow = true;
    });
    if (groupHeader) groupHeader.style.display = groupHasVisibleRow ? "" : "none";
    const first = total ? startIndex + 1 : 0;
    const last = Math.min(startIndex + previewPageSize, total);
    if (els.pageInfo) {
      els.pageInfo.textContent = "Showing " + first + "–" + last + " of " + total + " records · Page " + previewPage + " of " + pages;
    }
    if (els.prev) els.prev.disabled = previewPage <= 1;
    if (els.next) els.next.disabled = previewPage >= pages;
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
    previewPage = 1;
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
      source_reference: tr.getAttribute("data-source-reference") || "",
      source_group: tr.getAttribute("data-source-group") || "",
      work_type: tr.getAttribute("data-work-type") || "",
      can_edit: tr.getAttribute("data-can-edit") === "1",
      source_lock_message: tr.getAttribute("data-source-lock") || "",
      description: (tr.querySelector('[data-col="description"]')?.textContent || "").trim(),
    };
  }

  function onSourceEntryModalHidden() {
    window.dispatchEvent(new CustomEvent("jtcs:ledger-mutated"));
    if (returnToPreviewAfterMutation && typeof reloadPreview === "function") {
      returnToPreviewAfterMutation = false;
      Promise.resolve(reloadPreview()).finally(function () {
        mutationActive = false;
      });
    } else {
      mutationActive = false;
    }
  }

  function bindSourceEntryModal(modalEl) {
    if (!modalEl || modalEl.dataset.ledgerPreviewBound === "1") return;
    modalEl.dataset.ledgerPreviewBound = "1";
    modalEl.addEventListener("hidden.bs.modal", onSourceEntryModalHidden);
  }

  function ensureSourceEntryModal() {
    let modalEl = document.getElementById("dashSourceEntryModal");
    let frame = document.getElementById("dashSourceEntryFrame");
    if (!modalEl || !frame) {
      modalEl = document.createElement("div");
      modalEl.className = "modal fade";
      modalEl.id = "dashSourceEntryModal";
      modalEl.tabIndex = -1;
      modalEl.setAttribute("aria-hidden", "true");
      modalEl.innerHTML =
        '<div class="modal-dialog modal-xl modal-dialog-scrollable">' +
          '<div class="modal-content">' +
            '<div class="modal-header py-2">' +
              '<h5 class="modal-title" id="dashSourceEntryModalTitle">Edit Entry</h5>' +
              '<button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>' +
            '</div>' +
            '<div class="modal-body p-0" style="min-height:70vh">' +
              '<iframe id="dashSourceEntryFrame" title="Source entry" style="width:100%;height:70vh;border:0"></iframe>' +
            '</div>' +
          '</div>' +
        '</div>';
      document.body.appendChild(modalEl);
      frame = modalEl.querySelector("#dashSourceEntryFrame");
    }
    bindSourceEntryModal(modalEl);
    return { modalEl: modalEl, frame: frame };
  }

  function openEcourtEntryInFrame(frame, receiptNo, stationeryNo) {
    if (ecourtEntryOpenTimer) clearInterval(ecourtEntryOpenTimer);
    const startedAt = Date.now();
    const receiptKey = String(receiptNo || "").trim().toUpperCase();
    const stationeryKey = String(stationeryNo || "").trim();
    ecourtEntryOpenTimer = setInterval(function () {
      let doc;
      try {
        doc = frame.contentDocument;
      } catch (err) {
        return;
      }
      const body = doc && doc.querySelector("#ecourtGridBody");
      if (body) {
        let parent = null;
        body.querySelectorAll("tr.ecourt-tree-parent").forEach(function (tr) {
          if (!parent && tr.dataset.stationery === stationeryKey) parent = tr;
        });
        if (parent) {
          const rows = body.querySelectorAll("tr.ecourt-tree-child");
          let editButton = null;
          rows.forEach(function (tr) {
            if (!editButton && String(tr.dataset.receiptNo || "").trim().toUpperCase() === receiptKey) {
              editButton = tr.querySelector(".ecourt-edit-btn");
            }
          });
          if (!editButton) {
            const toggle = parent.querySelector(".ecourt-tree-toggle");
            if (toggle && toggle.textContent.trim() === "+") toggle.click();
            body.querySelectorAll("tr.ecourt-tree-child").forEach(function (tr) {
              if (!editButton && String(tr.dataset.receiptNo || "").trim().toUpperCase() === receiptKey) {
                editButton = tr.querySelector(".ecourt-edit-btn");
              }
            });
          }
          if (editButton) {
            clearInterval(ecourtEntryOpenTimer);
            ecourtEntryOpenTimer = null;
            editButton.click();
            return;
          }
        }
      }
      if (Date.now() - startedAt >= 15000) {
        clearInterval(ecourtEntryOpenTimer);
        ecourtEntryOpenTimer = null;
        alert("The e-Court page opened, but the selected entry could not be opened automatically.");
      }
    }, 250);
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
    let sourceUrl;
    try {
      sourceUrl = new URL(row.source_url, window.location.origin);
    } catch (err) {
      alert("The source entry link is invalid.");
      return;
    }
    if (row.source_module === "stamp") {
      sourceUrl.searchParams.set("ledger_edit", "1");
    }
    if (sourceUrl.origin !== window.location.origin) {
      alert("The source entry link is not on this site.");
      return;
    }
    const source = ensureSourceEntryModal();
    if (!source.frame || !window.bootstrap) {
      window.location.assign(sourceUrl.href);
      return;
    }
    const sourceModal = bootstrap.Modal.getOrCreateInstance(source.modalEl);
    mutationActive = true;
    returnToPreviewAfterMutation = true;
    const title = document.getElementById("dashSourceEntryModalTitle");
    if (title) title.textContent = "Edit Entry";
    source.frame.onload = null;
    if (row.source_module === "ecourt" && row.source_reference) {
      source.frame.onload = function () {
        source.frame.onload = null;
        openEcourtEntryInFrame(source.frame, row.source_reference, row.source_group);
      };
    }
    source.frame.src = sourceUrl.href;
    source.modalEl.style.zIndex = "1065";
    sourceModal.show();
  }
  modal.addEventListener("click", function (event) {
    if (event.target.closest("#ledgerPreviewPrev")) {
      event.preventDefault();
      previewPage = Math.max(1, previewPage - 1);
      applyPreviewPagination();
      return;
    }
    if (event.target.closest("#ledgerPreviewNext")) {
      event.preventDefault();
      previewPage += 1;
      applyPreviewPagination();
      return;
    }
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
      previewPage = 1;
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
  });

  modal.addEventListener("input", function (event) {
    if (event.target && event.target.id === "ledgerPreviewFilter") applyFilter();
  });
  modal.addEventListener("change", function (event) {
    if (!event.target || event.target.id !== "ledgerPreviewPageSize") return;
    previewPage = 1;
    applyFilter();
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

  bindSourceEntryModal(document.getElementById("dashSourceEntryModal"));
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
