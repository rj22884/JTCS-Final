/**
 * Open the shared Ledger Report preview modal from other pages
 * (e.g. Master delete-in-use → "Do you want to see transaction?").
 */
(function () {
  "use strict";

  const cfg = window.LEDGER_REPORT;
  const modalEl = document.getElementById("ledgerPreviewModal");
  if (!cfg || !modalEl) return;

  const els = {
    previewModalEl: modalEl,
    previewDialog: document.getElementById("ledgerPreviewDialog"),
    previewTitle: document.getElementById("ledgerPreviewModalTitle"),
    previewBody: document.getElementById("ledgerPreviewBody"),
    maximizeBtn: document.getElementById("ledgerMaximizeBtn"),
    maximizeIcon: document.getElementById("ledgerMaximizeIcon"),
    exportBtn: document.getElementById("ledgerExportBtn"),
  };

  const previewModal = window.bootstrap
    ? bootstrap.Modal.getOrCreateInstance(els.previewModalEl)
    : null;

  let currentKind = "";
  let currentId = "";
  let currentAllDates = false;
  let isMaximized = false;

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

  function allDatesQuery() {
    const params = new URLSearchParams();
    params.set("date_from", "2000-01-01");
    params.set("date_to", cfg.today || new Date().toISOString().slice(0, 10));
    return "?" + params.toString();
  }

  function dateQuery(allDates) {
    if (allDates) return allDatesQuery();
    if (window.JTCSLedgerPreview && typeof window.JTCSLedgerPreview.dateQuery === "function") {
      const q = window.JTCSLedgerPreview.dateQuery();
      if (q) return q;
    }
    const params = new URLSearchParams();
    if (cfg.fyStart) params.set("date_from", cfg.fyStart);
    if (cfg.today) params.set("date_to", cfg.today);
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

  function previewHasTxnRows() {
    const grid = document.getElementById("ledgerPreviewGrid");
    if (!grid) return false;
    return !!grid.querySelector('tbody tr[data-kind="txn"]');
  }

  async function fetchPreview(kind, id, allDates) {
    const url = previewUrl(kind, id);
    const res = await fetch(url + dateQuery(allDates), {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load preview.");
    return data;
  }

  function renderPreview(data) {
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
  }

  async function openPreview(kind, id, options) {
    if (!previewModal || !els.previewBody) {
      alert("Preview is not available.");
      return;
    }
    const url = previewUrl(kind, id);
    if (!url) {
      alert("Preview URL is not configured.");
      return;
    }
    const opts = options || {};
    currentKind = kind;
    currentId = String(id);
    currentAllDates = !!opts.allDates;
    setExportEnabled(false);
    setMaximized(false);
    if (els.previewTitle) els.previewTitle.textContent = "Ledger Preview";
    els.previewBody.innerHTML =
      '<div class="text-muted small py-4 text-center">Loading preview…</div>';
    previewModal.show();
    try {
      let data = await fetchPreview(kind, id, currentAllDates);
      renderPreview(data);
      if (!currentAllDates && !previewHasTxnRows()) {
        currentAllDates = true;
        data = await fetchPreview(kind, id, true);
        renderPreview(data);
      }
    } catch (err) {
      currentKind = "";
      currentId = "";
      currentAllDates = false;
      setExportEnabled(false);
      els.previewBody.innerHTML =
        '<div class="alert alert-danger mb-0">' +
        escapeHtml(err.message || "Unable to load preview.") +
        "</div>";
    }
  }

  async function offerSeeTransaction(kind, id, errorMessage) {
    const message =
      (errorMessage || "This record is linked to other records and cannot be deleted.") +
      "\n\nDo you want to see transaction?";
    let see = false;
    if (window.JTCSDialog && typeof JTCSDialog.confirm === "function") {
      see = await JTCSDialog.confirm(message, {
        title: "Error",
        type: "error",
        okLabel: "Yes",
        cancelLabel: "No",
        okClass: "btn-primary",
      });
    } else {
      see = window.confirm(message);
    }
    if (!see) return;
    setTimeout(function () {
      openPreview(kind, id, { allDates: true });
    }, 80);
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
    window.location.href = url + dateQuery(currentAllDates);
  }

  function onExportClick(event) {
    const opt = event.target.closest(".ledger-export-opt");
    if (!opt) return;
    event.preventDefault();
    const fmt = (opt.getAttribute("data-fmt") || "").toLowerCase();
    if (!fmt) return;
    downloadExport(fmt);
  }

  els.maximizeBtn?.addEventListener("click", function () {
    setMaximized(!isMaximized);
  });
  els.previewModalEl.addEventListener("click", onExportClick);
  els.previewModalEl.addEventListener("hidden.bs.modal", function () {
    setMaximized(false);
    setExportEnabled(false);
    currentKind = "";
    currentId = "";
    currentAllDates = false;
  });

  if (window.JTCSLedgerPreview && typeof window.JTCSLedgerPreview.setReloader === "function") {
    window.JTCSLedgerPreview.setReloader(function () {
      if (currentKind && currentId) {
        openPreview(currentKind, currentId, { allDates: currentAllDates });
      }
    });
  }

  window.JTCSLedgerPreviewHost = {
    open: openPreview,
    offerSeeTransaction: offerSeeTransaction,
  };
  if (window.JTCSLedgerPreview) {
    window.JTCSLedgerPreview.open = openPreview;
  }
})();
