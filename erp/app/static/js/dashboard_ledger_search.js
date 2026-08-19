(function () {
  "use strict";

  const cfg = window.LEDGER_REPORT;
  const box = document.getElementById("dashLedgerSearchBox");
  if (!cfg || !box) return;

  const els = {
    search: document.getElementById("dashLedgerSearch"),
    searchBtn: document.getElementById("dashLedgerSearchBtn"),
    results: document.getElementById("dashLedgerResults"),
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

  const KIND_LABELS = {
    bank: "Bank",
    customer: "Customer",
    work: "Work / Category",
    item: "Item",
  };

  let searchTimer = null;
  let currentKind = "";
  let currentId = "";
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

  function dateQuery() {
    if (window.JTCSLedgerPreview && typeof window.JTCSLedgerPreview.dateQuery === "function") {
      return window.JTCSLedgerPreview.dateQuery();
    }
    const params = new URLSearchParams();
    if (cfg.fyStart) params.set("date_from", cfg.fyStart);
    if (cfg.today) params.set("date_to", cfg.today);
    const q = params.toString();
    return q ? "?" + q : "";
  }

  function hideResults() {
    if (!els.results) return;
    els.results.classList.add("d-none");
    els.results.innerHTML = "";
  }

  function showMessage(text) {
    if (!els.results) return;
    els.results.innerHTML =
      '<div class="dash-ledger-search-empty">' + escapeHtml(text) + "</div>";
    els.results.classList.remove("d-none");
  }

  function renderResults(rows) {
    if (!els.results) return;
    if (!rows.length) {
      showMessage("No ledgers found.");
      return;
    }
    els.results.innerHTML = rows
      .map(function (row) {
        const typeLabel = KIND_LABELS[row.kind] || row.kind || "Ledger";
        const detail = row.subtitle || row.meta || "";
        return (
          '<button type="button" class="dash-ledger-search-item" data-kind="' +
          escapeHtml(row.kind) +
          '" data-id="' +
          escapeHtml(row.id) +
          '"><strong>' +
          escapeHtml(row.label || "—") +
          "</strong><span>" +
          escapeHtml(typeLabel) +
          (detail ? " · " + detail : "") +
          "</span></button>"
        );
      })
      .join("");
    els.results.classList.remove("d-none");
  }

  function searchLedgers() {
    const search = (els.search?.value || "").trim();
    if (search.length < 2) {
      showMessage("Type at least 2 characters to search.");
      return;
    }
    const params = new URLSearchParams();
    params.set("kind", "all");
    params.set("search", search);
    showMessage("Searching…");
    fetch(cfg.searchUrl + "?" + params.toString(), {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Unable to search ledgers.");
          renderResults(data.rows || []);
        });
      })
      .catch(function (err) {
        showMessage(err.message || "Unable to search ledgers.");
      });
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
    hideResults();
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

  function scheduleSearch() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(searchLedgers, 280);
  }

  els.search?.addEventListener("input", function () {
    const value = (els.search.value || "").trim();
    if (value.length < 2) {
      hideResults();
      return;
    }
    scheduleSearch();
  });
  els.search?.addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
      event.preventDefault();
      clearTimeout(searchTimer);
      searchLedgers();
    } else if (event.key === "Escape") {
      hideResults();
    }
  });
  els.searchBtn?.addEventListener("click", function () {
    clearTimeout(searchTimer);
    searchLedgers();
  });
  els.results?.addEventListener("click", function (event) {
    const btn = event.target.closest(".dash-ledger-search-item");
    if (!btn) return;
    openPreview(btn.getAttribute("data-kind") || "", btn.getAttribute("data-id"));
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
    currentKind = "";
    currentId = "";
  });
  document.addEventListener("click", function (event) {
    if (!box.contains(event.target)) hideResults();
  });

  if (window.JTCSLedgerPreview && typeof window.JTCSLedgerPreview.setReloader === "function") {
    window.JTCSLedgerPreview.setReloader(function () {
      if (currentKind && currentId) openPreview(currentKind, currentId);
    });
  }
})();
