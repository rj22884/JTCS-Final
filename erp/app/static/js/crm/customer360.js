(function () {
  "use strict";

  const page = document.getElementById("crmCustomer360Page");
  if (!page) return;

  const searchApi = page.dataset.searchApi;
  const profileApi = page.dataset.profileApi;
  const searchInput = document.getElementById("crmC360Search");
  const resultsEl = document.getElementById("crmC360SearchResults");
  const contentEl = document.getElementById("crmC360Content");
  const emptyEl = document.getElementById("crmC360Empty");
  let debounceTimer = null;

  function navigateToCustomer(id) {
    window.location.href = "/crm/customer-360/" + id;
  }

  function hideResults() {
    resultsEl.classList.remove("show");
  }

  function showResults() {
    resultsEl.classList.add("show");
  }

  async function runSearch(q) {
    if (!q || q.length < 2) {
      resultsEl.innerHTML = "";
      hideResults();
      return;
    }
    try {
      const data = await CrmCommon.apiFetch(searchApi + "?q=" + encodeURIComponent(q));
      const customers = data.customers || [];
      if (!customers.length) {
        resultsEl.innerHTML = '<div class="dropdown-item text-muted">No customers found.</div>';
      } else {
        resultsEl.innerHTML = customers
          .slice(0, 10)
          .map(function (c) {
            const id = c.CustomerID || c.customer_id;
            const name = c.CustomerName || c.customer_name || "Customer";
            const sub = c.MobileNumber || c.PANNumber || "";
            return (
              '<button type="button" class="dropdown-item crm-c360-pick" data-id="' + id + '">' +
              CrmCommon.escapeHtml(name) +
              (sub ? '<div class="small text-muted">' + CrmCommon.escapeHtml(sub) + "</div>" : "") +
              "</button>"
            );
          })
          .join("");
      }
      showResults();
    } catch (_err) {
      resultsEl.innerHTML = '<div class="dropdown-item text-muted">Search failed.</div>';
      showResults();
    }
  }

  if (searchInput) {
    searchInput.addEventListener("input", function () {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(function () {
        runSearch(searchInput.value.trim());
      }, 280);
    });
    searchInput.addEventListener("keydown", function (e) {
      if (e.key === "Escape") hideResults();
    });
  }

  if (resultsEl) {
    resultsEl.addEventListener("click", function (e) {
      const btn = e.target.closest(".crm-c360-pick");
      if (!btn) return;
      navigateToCustomer(btn.dataset.id);
    });
  }

  document.addEventListener("click", function (e) {
    if (!e.target.closest("#crmC360Search") && !e.target.closest("#crmC360SearchResults")) hideResults();
  });

  const initialId = page.dataset.customerId;
  if (initialId && contentEl) {
    contentEl.classList.remove("d-none");
    if (emptyEl) emptyEl.classList.add("d-none");
  }
})();
