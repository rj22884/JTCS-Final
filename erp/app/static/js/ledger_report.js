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
  };

  const previewModal =
    els.previewModalEl && window.bootstrap
      ? bootstrap.Modal.getOrCreateInstance(els.previewModalEl)
      : null;

  let searchTimer = null;
  let currentKind = "";
  let currentId = "";
  let isMaximized = false;

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
    if (kind === "customer" && search.length < 2) {
      return "Type at least 2 characters to search customers.";
    }
    if (!search && kind === "all") {
      return "Select a ledger type or type a search term.";
    }
    return "No ledgers found.";
  }

  function renderRows(rows, kind, search) {
    if (!els.body) return;
    if (!rows.length) {
      els.body.innerHTML =
        '<tr><td colspan="5" class="text-center text-muted py-4">' +
        escapeHtml(emptyMessage(kind, search)) +
        "</td></tr>";
      if (els.count) els.count.textContent = "0 ledgers";
      return;
    }
    if (els.count) {
      els.count.textContent = rows.length + " ledger" + (rows.length === 1 ? "" : "s");
    }
    els.body.innerHTML = rows
      .map(function (row) {
        const typeLabel = KIND_LABELS[row.kind] || row.kind || "—";
        return (
          "<tr>" +
          "<td><span class=\"badge text-bg-light border ledger-kind-badge\">" +
          escapeHtml(typeLabel) +
          "</span></td>" +
          "<td><strong>" +
          escapeHtml(row.label || "—") +
          "</strong>" +
          (row.active === false
            ? ' <span class="badge text-bg-secondary ms-1">Inactive</span>'
            : "") +
          "</td>" +
          "<td>" +
          escapeHtml(row.subtitle || "—") +
          "</td>" +
          '<td class="text-end">' +
          escapeHtml(row.txn_count == null ? "—" : row.txn_count) +
          "</td>" +
          '<td class="text-end">' +
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
  }

  function loadLedgers() {
    const kind = (els.kind?.value || "all").trim().toLowerCase();
    const search = (els.search?.value || "").trim();

    if (kind === "customer" && search.length < 2) {
      renderRows([], kind, search);
      return Promise.resolve();
    }
    if (kind === "all" && search.length < 2) {
      if (els.body) {
        els.body.innerHTML =
          '<tr><td colspan="5" class="text-center text-muted py-4">' +
          "Select a ledger type, or type at least 2 characters to search all.</td></tr>";
      }
      if (els.count) els.count.textContent = "Search to list ledgers";
      return Promise.resolve();
    }

    const params = new URLSearchParams();
    params.set("kind", kind);
    if (search) params.set("search", search);
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
        if (els.body) {
          els.body.innerHTML =
            '<tr><td colspan="5" class="text-center text-danger py-4">' +
            escapeHtml(err.message || "Unable to search ledgers.") +
            "</td></tr>";
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
  els.refreshBtn?.addEventListener("click", loadLedgers);
  els.kind?.addEventListener("change", function () {
    clearTimeout(searchTimer);
    loadLedgers();
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

  if (window.JTCSLedgerPreview && typeof window.JTCSLedgerPreview.setReloader === "function") {
    window.JTCSLedgerPreview.setReloader(function () {
      if (currentKind && currentId) openPreview(currentKind, currentId);
    });
  }
})();
