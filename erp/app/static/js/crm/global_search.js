(function () {
  "use strict";

  const header = document.querySelector(".jtcs-app-header");
  const input = document.getElementById("jtcsGlobalSearch");
  const resultsEl = document.getElementById("jtcsGlobalSearchResults");
  if (!header || !input || !resultsEl) return;

  const searchUrl = header.dataset.searchUrl || "/api/search";
  let debounceTimer = null;
  let abortCtrl = null;

  const GROUPS = [
    { key: "customers", label: "Customers", icon: "bi-person", fallbackHref: "/masters/customer" },
    { key: "ledgers", label: "Ledgers", icon: "bi-journal-text", fallbackHref: "/Reports_and_analysis/ledger_report" },
    { key: "items", label: "Items", icon: "bi-box-seam", fallbackHref: "/masters/item" },
    { key: "invoices", label: "Invoices", icon: "bi-receipt", fallbackHref: "/accounting/invoice/sale" },
    { key: "leads", label: "Leads", icon: "bi-person-plus", fallbackHref: "/crm/leads" },
    { key: "documents", label: "Documents", icon: "bi-folder", fallbackHref: "/crm/documents" },
  ];

  function hideResults() {
    resultsEl.classList.remove("show");
    input.setAttribute("aria-expanded", "false");
  }

  function showResults() {
    resultsEl.classList.add("show");
    input.setAttribute("aria-expanded", "true");
  }

  function pick(row, keys) {
    for (let i = 0; i < keys.length; i++) {
      const v = row[keys[i]];
      if (v != null && String(v).trim()) return String(v).trim();
    }
    return "";
  }

  function rowTitle(row) {
    return (
      pick(row, [
        "title",
        "customer_name",
        "CustomerName",
        "FullName",
        "item_name",
        "ItemName",
        "label",
        "InvoiceNo",
        "InvoiceNumber",
        "name",
      ]) || "Untitled"
    );
  }

  function rowSubtitle(row) {
    const direct = pick(row, ["subtitle"]);
    if (direct) return direct;
    if (row.GrandTotal != null) return "₹ " + row.GrandTotal;
    if (row.InvoiceValue != null) return "₹ " + row.InvoiceValue;
    return pick(row, [
      "mobile_number",
      "Mobile",
      "email_id",
      "Email",
      "pan_number",
      "item_code",
      "FolderType",
      "Status",
    ]);
  }

  function rowHref(row, group) {
    return pick(row, ["href"]) || group.fallbackHref || "#";
  }

  function renderResults(data) {
    const parts = [];
    GROUPS.forEach(function (g) {
      const rows = (data && data[g.key]) || [];
      if (!rows.length) return;
      parts.push(
        '<div class="jtcs-global-search-group">' + CrmCommon.escapeHtml(g.label) + "</div>"
      );
      rows.slice(0, 8).forEach(function (row) {
        const title = rowTitle(row);
        const sub = rowSubtitle(row);
        parts.push(
          '<a class="jtcs-global-search-item" href="' +
            CrmCommon.escapeHtml(rowHref(row, g)) +
            '">' +
            '<i class="bi ' +
            g.icon +
            ' me-1"></i>' +
            CrmCommon.escapeHtml(title) +
            (sub
              ? '<div class="small text-muted">' + CrmCommon.escapeHtml(sub) + "</div>"
              : "") +
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
