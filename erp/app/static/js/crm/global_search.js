(function () {
  "use strict";

  const header = document.querySelector(".jtcs-app-header");
  const input = document.getElementById("jtcsGlobalSearch");
  const resultsEl = document.getElementById("jtcsGlobalSearchResults");
  if (!header || !input || !resultsEl) return;

  const searchUrl = header.dataset.searchUrl || "/api/search";
  let debounceTimer = null;
  let abortCtrl = null;

  function hideResults() {
    resultsEl.classList.remove("show");
    input.setAttribute("aria-expanded", "false");
  }

  function showResults() {
    resultsEl.classList.add("show");
    input.setAttribute("aria-expanded", "true");
  }

  function renderResults(data) {
    const parts = [];
    const groups = [
      { key: "customers", label: "Customers", icon: "bi-person", href: (r) => "/crm/customer-360/" + (r.CustomerID || r.customer_id) },
      { key: "leads", label: "Leads", icon: "bi-person-plus", href: (r) => "/crm/leads/" + (r.LeadID || r.lead_id) },
      { key: "invoices", label: "Invoices", icon: "bi-receipt", href: () => "/accounting/reports" },
      { key: "documents", label: "Documents", icon: "bi-folder", href: () => "/crm/documents" },
    ];

    groups.forEach(function (g) {
      const rows = data[g.key] || [];
      if (!rows.length) return;
      parts.push('<div class="jtcs-global-search-group">' + CrmCommon.escapeHtml(g.label) + "</div>");
      rows.slice(0, 6).forEach(function (row) {
        const title =
          row.CustomerName ||
          row.FullName ||
          row.InvoiceNumber ||
          row.Title ||
          row.DocumentTitle ||
          row.name ||
          "Item";
        let sub = row.Mobile || row.Email || row.FolderType || row.Status || "";
        if (!sub && row.GrandTotal != null) sub = "₹ " + row.GrandTotal;
        parts.push(
          '<a class="jtcs-global-search-item" href="' +
            CrmCommon.escapeHtml(g.href(row)) +
            '">' +
            '<i class="bi ' +
            g.icon +
            ' me-1"></i>' +
            CrmCommon.escapeHtml(title) +
            (sub ? '<div class="small text-muted">' + CrmCommon.escapeHtml(String(sub)) + "</div>" : "") +
            "</a>"
        );
      });
    });

    if (!parts.length) {
      parts.push('<div class="jtcs-notify-empty px-3 py-2">No results found.</div>');
    }
    resultsEl.innerHTML = parts.join("");
    showResults();
  }

  async function runSearch(q) {
    if (abortCtrl) abortCtrl.abort();
    if (!q || q.length < 2) {
      resultsEl.innerHTML = "";
      hideResults();
      return;
    }
    abortCtrl = new AbortController();
    try {
      const data = await CrmCommon.apiFetch(searchUrl + "?q=" + encodeURIComponent(q), {
        signal: abortCtrl.signal,
      });
      renderResults(data);
    } catch (err) {
      if (err.name === "AbortError") return;
      resultsEl.innerHTML = '<div class="jtcs-notify-empty px-3 py-2">Search failed.</div>';
      showResults();
    }
  }

  input.addEventListener("input", function () {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function () {
      runSearch(input.value.trim());
    }, 280);
  });

  input.addEventListener("focus", function () {
    if (input.value.trim().length >= 2 && resultsEl.innerHTML) showResults();
  });

  document.addEventListener("click", function (e) {
    if (!e.target.closest(".jtcs-global-search")) hideResults();
  });

  input.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      hideResults();
      input.blur();
    }
  });
})();
