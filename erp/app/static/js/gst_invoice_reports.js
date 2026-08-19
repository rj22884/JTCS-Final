(function () {
  "use strict";

  const api = window.INVOICE_REPORT_API;
  if (!api) return;

  const els = {
    search: document.getElementById("rptSearch"),
    from: document.getElementById("rptFrom"),
    to: document.getElementById("rptTo"),
    refresh: document.getElementById("rptRefreshBtn"),
    body: document.getElementById("rptBody"),
    empty: document.getElementById("rptEmpty"),
    count: document.getElementById("rptCount"),
    status: document.getElementById("rptStatus"),
  };

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function apiUrl(template, id) {
    return String(template || "").replace(/\/0(?=$|\/)/, "/" + String(id));
  }

  function fmtDate(iso) {
    if (!iso || iso.length < 10) return iso || "";
    const p = iso.slice(0, 10).split("-");
    return p[2] + "/" + p[1] + "/" + p[0];
  }

  function money(v) {
    return Number(v || 0).toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function showStatus(message, type) {
    if (!els.status) return;
    if (!message) {
      els.status.classList.add("d-none");
      return;
    }
    els.status.textContent = message;
    els.status.className = "alert py-2 small mb-3 alert-" + (type || "success");
    els.status.classList.remove("d-none");
  }

  function taxAmt(row) {
    if (row.tax_type === "CGST_SGST") {
      return Number(row.cgst_amount || 0) + Number(row.sgst_amount || 0);
    }
    return Number(row.igst_amount || 0);
  }

  function render(rows) {
    els.body.innerHTML = "";
    if (!rows.length) {
      els.empty?.classList.remove("d-none");
      if (els.count) els.count.textContent = "0 invoices";
      return;
    }
    els.empty?.classList.add("d-none");
    if (els.count) {
      els.count.textContent = rows.length + " invoice" + (rows.length === 1 ? "" : "s");
    }
    rows.forEach(function (row) {
      const tr = document.createElement("tr");
      const taxLabel =
        row.tax_type === "CGST_SGST"
          ? "CGST+SGST"
          : "IGST " + Number(row.igst_rate || 0).toFixed(0) + "%";
      tr.innerHTML =
        "<td><code>" +
        escapeHtml(row.invoice_no) +
        "</code></td>" +
        "<td>" +
        escapeHtml(fmtDate(row.invoice_date)) +
        "</td>" +
        "<td>" +
        escapeHtml(row.customer_name) +
        "</td>" +
        "<td>" +
        escapeHtml(row.customer_gstin || "—") +
        "</td>" +
        "<td>" +
        escapeHtml(taxLabel) +
        "</td>" +
        '<td class="text-end">' +
        money(row.taxable_value) +
        "</td>" +
        '<td class="text-end">' +
        money(taxAmt(row)) +
        "</td>" +
        '<td class="text-end fw-semibold">' +
        money(row.invoice_value) +
        "</td>" +
        '<td class="text-end text-nowrap">' +
        '<a class="btn btn-outline-primary btn-sm me-1" href="' +
        apiUrl(api.pdf, row.invoice_id) +
        '" target="_blank"><i class="bi bi-file-earmark-pdf"></i></a>' +
        '<button type="button" class="btn btn-outline-danger btn-sm rpt-del" data-id="' +
        row.invoice_id +
        '"><i class="bi bi-trash"></i></button>' +
        "</td>";
      els.body.appendChild(tr);
    });
  }

  async function load() {
    const url = new URL(api.list, window.location.origin);
    const q = (els.search?.value || "").trim();
    if (q) url.searchParams.set("search", q);
    if (els.from?.value) url.searchParams.set("date_from", els.from.value);
    if (els.to?.value) url.searchParams.set("date_to", els.to.value);
    const res = await fetch(url.toString(), { credentials: "same-origin" });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Load failed");
    render(data.rows || []);
  }

  els.refresh?.addEventListener("click", function () {
    load().catch(function (err) {
      showStatus(err.message || String(err), "danger");
    });
  });
  els.search?.addEventListener("keydown", function (ev) {
    if (ev.key === "Enter") {
      ev.preventDefault();
      load().catch(function (err) {
        showStatus(err.message || String(err), "danger");
      });
    }
  });

  els.body?.addEventListener("click", function (ev) {
    const btn = ev.target.closest(".rpt-del");
    if (!btn) return;
    deleteReportInvoice(btn.getAttribute("data-id")).catch(function (err) {
      showStatus(err.message || String(err), "danger");
    });
  });

  async function deleteReportInvoice(id) {
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!(await JTCSDialog.confirm("Delete this invoice?"))) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: "Delete this invoice?" });
      if (!creds) return;
    }
    const res = await fetch(apiUrl(api.delete, id), {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": api.csrf || "",
      },
      body: JSON.stringify(creds ? window.JTCSDeleteConfirm.withCreds({}, creds) : {}),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Delete failed");
    showStatus(data.message || "Deleted.", "success");
    await load();
  }

  load().catch(function (err) {
    showStatus(err.message || String(err), "danger");
  });
})();
