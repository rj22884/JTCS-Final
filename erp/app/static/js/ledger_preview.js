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
      grid: document.getElementById("ledgerPreviewGrid"),
    };
  }

  function dateQuery() {
    const els = toolbar();
    const pageFrom = document.getElementById("ledgerDateFrom");
    const pageTo = document.getElementById("ledgerDateTo");
    const fsFrom = document.getElementById("fsDateFrom");
    const fsTo = document.getElementById("fsDateTo");
    const dashFrom = document.getElementById("dashDateFrom");
    const dashTo = document.getElementById("dashDateTo");
    const from =
      (els.from && els.from.value) ||
      (pageFrom && pageFrom.value) ||
      (fsFrom && fsFrom.value) ||
      (dashFrom && dashFrom.value) ||
      cfg.fyStart ||
      "";
    const to =
      (els.to && els.to.value) ||
      (pageTo && pageTo.value) ||
      (fsTo && fsTo.value) ||
      (dashTo && dashTo.value) ||
      cfg.today ||
      "";
    const params = new URLSearchParams();
    if (from) params.set("date_from", from);
    if (to) params.set("date_to", to);
    const q = params.toString();
    return q ? "?" + q : "";
  }

  function applyFilter() {
    const els = toolbar();
    if (!els.grid) return;
    const needle = String(els.filter?.value || "")
      .trim()
      .toLowerCase();
    els.grid.querySelectorAll("tbody tr").forEach(function (tr) {
      if (!tr.querySelector("td")) return;
      if (!needle) {
        tr.hidden = false;
        return;
      }
      tr.hidden = (tr.textContent || "").toLowerCase().indexOf(needle) === -1;
    });
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
    const rows = Array.prototype.slice.call(tbody.rows);
    const opening = [];
    const rest = [];
    rows.forEach(function (tr) {
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
    if (mod === "invoice" && urls.invoice) return apiUrl(urls.invoice, id);
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
    if (!row || !row.can_edit || !row.source_url) {
      alert("Edit is not available for this row.");
      return;
    }
    const frame = document.getElementById("dashSourceEntryFrame");
    const modalEl = document.getElementById("dashSourceEntryModal");
    if (frame && modalEl && window.bootstrap) {
      const sourceModal = bootstrap.Modal.getOrCreateInstance(modalEl);
      const title = document.getElementById("dashSourceEntryModalTitle");
      if (title) title.textContent = "Edit Entry";
      frame.src = row.source_url;
      sourceModal.show();
      return;
    }
    window.open(row.source_url, "_blank");
  }

  async function deleteRow(row) {
    const url = resolveDeleteUrl(row);
    if (!url) {
      alert("Delete is not available for this row.");
      return;
    }
    const label = row.description || "this entry";
    let creds = null;
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
    try {
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
      if (typeof reloadPreview === "function") reloadPreview();
    } catch (err) {
      alert(err.message || "Delete failed.");
    }
  }

  modal.addEventListener("click", function (event) {
    if (event.target.closest("#ledgerPreviewApplyDates")) {
      event.preventDefault();
      if (typeof reloadPreview === "function") reloadPreview();
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
    if (event.target && event.target.id === "ledgerPreviewDateFrom") {
      event.preventDefault();
      if (typeof reloadPreview === "function") reloadPreview();
    }
    if (event.target && event.target.id === "ledgerPreviewDateTo") {
      event.preventDefault();
      if (typeof reloadPreview === "function") reloadPreview();
    }
  });

  document.getElementById("dashSourceEntryModal")?.addEventListener(
    "hidden.bs.modal",
    function () {
      if (modal.classList.contains("show") && typeof reloadPreview === "function") {
        reloadPreview();
      }
    }
  );

  window.JTCSLedgerPreview = {
    dateQuery: dateQuery,
    setReloader: function (fn) {
      reloadPreview = fn;
    },
    afterRender: function () {
      applySort();
      applyFilter();
    },
  };
})();
