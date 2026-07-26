(function () {
  "use strict";

  const cfg = window.LEDGER_EXPORT;
  if (!cfg) return;

  const els = {
    dateFrom: document.getElementById("ledgerDateFrom"),
    dateTo: document.getElementById("ledgerDateTo"),
    bankSearch: document.getElementById("bankSearch"),
    bankRefresh: document.getElementById("bankRefreshBtn"),
    bankBody: document.getElementById("bankGridBody"),
    bankCount: document.getElementById("bankCount"),
    customerSearch: document.getElementById("customerSearch"),
    customerRefresh: document.getElementById("customerRefreshBtn"),
    customerBody: document.getElementById("customerGridBody"),
    customerCount: document.getElementById("customerCount"),
    previewModalEl: document.getElementById("ledgerPreviewModal"),
    previewTitle: document.getElementById("ledgerPreviewModalTitle"),
    previewBody: document.getElementById("ledgerPreviewBody"),
  };

  const previewModal =
    els.previewModalEl && window.bootstrap
      ? bootstrap.Modal.getOrCreateInstance(els.previewModalEl)
      : null;

  let bankTimer = null;
  let customerTimer = null;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function apiUrl(template, id) {
    return String(template || "").replace(/\/0(?=$|[/?#])/, "/" + String(id));
  }

  function dateQuery() {
    const params = new URLSearchParams();
    const from = (els.dateFrom?.value || "").trim();
    const to = (els.dateTo?.value || "").trim();
    if (from) params.set("date_from", from);
    if (to) params.set("date_to", to);
    const q = params.toString();
    return q ? "?" + q : "";
  }

  function exportButtons(kind, id) {
    // Use data-ledger-fmt so Excel/PDF clicks never get mixed up.
    return (
      '<div class="btn-group btn-group-sm" role="group">' +
      '<button type="button" class="btn btn-outline-info ledger-preview-btn" data-kind="' +
      escapeHtml(kind) +
      '" data-id="' +
      escapeHtml(id) +
      '" title="Preview">' +
      '<i class="bi bi-eye"></i> Preview</button>' +
      '<button type="button" class="btn btn-outline-success ledger-dl-btn" data-kind="' +
      escapeHtml(kind) +
      '" data-id="' +
      escapeHtml(id) +
      '" data-ledger-fmt="xlsx" title="Excel">' +
      '<i class="bi bi-file-earmark-excel"></i> Excel</button>' +
      '<button type="button" class="btn btn-outline-danger ledger-dl-btn" data-kind="' +
      escapeHtml(kind) +
      '" data-id="' +
      escapeHtml(id) +
      '" data-ledger-fmt="pdf" title="PDF">' +
      '<i class="bi bi-file-earmark-pdf"></i> PDF</button>' +
      "</div>"
    );
  }

  function renderBanks(rows) {
    if (!els.bankBody) return;
    if (!rows.length) {
      els.bankBody.innerHTML =
        '<tr><td colspan="5" class="text-center text-muted py-4">No bank accounts found.</td></tr>';
      if (els.bankCount) els.bankCount.textContent = "0 accounts";
      return;
    }
    if (els.bankCount) {
      els.bankCount.textContent = rows.length + " account" + (rows.length === 1 ? "" : "s");
    }
    els.bankBody.innerHTML = rows
      .map(function (row) {
        return (
          "<tr>" +
          "<td><strong>" +
          escapeHtml(row.label) +
          "</strong>" +
          (row.active ? "" : ' <span class="badge text-bg-secondary">Inactive</span>') +
          "</td>" +
          "<td>" +
          escapeHtml(row.account_type || "—") +
          "</td>" +
          "<td>" +
          escapeHtml(row.account_holder || "—") +
          "</td>" +
          '<td class="text-end">' +
          escapeHtml(row.txn_count) +
          "</td>" +
          '<td class="text-end">' +
          exportButtons("bank", row.account_id) +
          "</td>" +
          "</tr>"
        );
      })
      .join("");
  }

  function renderCustomers(rows) {
    if (!els.customerBody) return;
    if (!rows.length) {
      els.customerBody.innerHTML =
        '<tr><td colspan="5" class="text-center text-muted py-4">No customers found.</td></tr>';
      if (els.customerCount) els.customerCount.textContent = "0 customers";
      return;
    }
    if (els.customerCount) {
      els.customerCount.textContent = rows.length + " customer" + (rows.length === 1 ? "" : "s");
    }
    els.customerBody.innerHTML = rows
      .map(function (row) {
        return (
          "<tr>" +
          "<td><strong>" +
          escapeHtml(row.customer_name) +
          "</strong></td>" +
          "<td>" +
          escapeHtml(row.mobile_number || "—") +
          "</td>" +
          "<td>" +
          escapeHtml(row.pan_number || "—") +
          "</td>" +
          '<td class="text-end">' +
          escapeHtml(row.txn_count) +
          "</td>" +
          '<td class="text-end">' +
          exportButtons("customer", row.customer_id) +
          "</td>" +
          "</tr>"
        );
      })
      .join("");
  }

  function loadBanks() {
    const q = (els.bankSearch?.value || "").trim();
    const url = cfg.banksUrl + (q ? "?search=" + encodeURIComponent(q) : "");
    return fetch(url, { headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" } })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load banks.");
          renderBanks(data.rows || []);
        });
      })
      .catch(function (err) {
        alert(err.message || "Unable to load banks.");
      });
  }

  function loadCustomers() {
    const q = (els.customerSearch?.value || "").trim();
    if (q.length < 2) {
      if (els.customerBody) {
        els.customerBody.innerHTML =
          '<tr><td colspan="5" class="text-center text-muted py-4">Search a customer to export their ledger.</td></tr>';
      }
      if (els.customerCount) els.customerCount.textContent = "Type to search";
      return Promise.resolve();
    }
    const url = cfg.customersUrl + "?search=" + encodeURIComponent(q);
    return fetch(url, { headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" } })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load customers.");
          renderCustomers(data.rows || []);
        });
      })
      .catch(function (err) {
        alert(err.message || "Unable to load customers.");
      });
  }

  function downloadLedger(kind, id, fmt) {
    const base = kind === "bank" ? cfg.bankDownload : cfg.customerDownload;
    // Path-based format: /download/customer/159/pdf  (avoids query-param mixups)
    const url = apiUrl(base, id).replace(/\/?$/, "/") + encodeURIComponent(fmt || "xlsx");
    window.location.href = url + dateQuery();
  }

  async function openLedgerPreview(kind, id) {
    if (!previewModal || !els.previewBody) {
      alert("Preview is not available.");
      return;
    }
    const base = kind === "bank" ? cfg.bankPreview : cfg.customerPreview;
    if (!base) {
      alert("Preview URL is not configured.");
      return;
    }
    if (els.previewTitle) els.previewTitle.textContent = "Ledger Preview";
    els.previewBody.innerHTML =
      '<div class="text-muted small py-4 text-center">Loading preview…</div>';
    previewModal.show();
    try {
      const res = await fetch(apiUrl(base, id) + dateQuery(), {
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
    } catch (err) {
      els.previewBody.innerHTML =
        '<div class="alert alert-danger mb-0">' +
        escapeHtml(err.message || "Unable to load preview.") +
        "</div>";
    }
  }

  function onExportClick(event) {
    const previewBtn = event.target.closest(".ledger-preview-btn");
    if (previewBtn) {
      event.preventDefault();
      event.stopPropagation();
      const kind = previewBtn.getAttribute("data-kind") || "customer";
      const id = previewBtn.getAttribute("data-id");
      if (!id) return;
      openLedgerPreview(kind, id);
      return;
    }
    const btn = event.target.closest(".ledger-dl-btn");
    if (!btn) return;
    event.preventDefault();
    event.stopPropagation();
    const kind = btn.getAttribute("data-kind") || "customer";
    const id = btn.getAttribute("data-id");
    const fmt = (btn.getAttribute("data-ledger-fmt") || "xlsx").toLowerCase();
    if (!id) return;
    downloadLedger(kind, id, fmt === "pdf" ? "pdf" : "xlsx");
  }

  els.bankSearch?.addEventListener("input", function () {
    clearTimeout(bankTimer);
    bankTimer = setTimeout(loadBanks, 250);
  });
  els.bankRefresh?.addEventListener("click", loadBanks);
  els.bankBody?.addEventListener("click", onExportClick);

  els.customerSearch?.addEventListener("input", function () {
    clearTimeout(customerTimer);
    customerTimer = setTimeout(loadCustomers, 250);
  });
  els.customerRefresh?.addEventListener("click", loadCustomers);
  els.customerBody?.addEventListener("click", onExportClick);

  // Upgrade initial bank rows (server-rendered) to include PDF + data-ledger-fmt
  if (els.bankBody) {
    els.bankBody.querySelectorAll("tr").forEach(function (tr) {
      const oldBtn = tr.querySelector(".ledger-export-bank, .ledger-dl-btn");
      if (!oldBtn) return;
      const id = oldBtn.getAttribute("data-id");
      const td = oldBtn.closest("td");
      if (td && id) td.innerHTML = exportButtons("bank", id);
    });
  }
})();
