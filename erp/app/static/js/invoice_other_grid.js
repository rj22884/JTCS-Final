(function () {
  "use strict";

  const api = window.INVOICE_OTHER_API;
  if (!api) return;

  const els = {
    body: document.getElementById("invOtherBody"),
    empty: document.getElementById("invOtherEmpty"),
    count: document.getElementById("invOtherCount"),
    search: document.getElementById("invOtherSearch"),
    refresh: document.getElementById("invOtherRefresh"),
  };

  let timer = null;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function money(n) {
    return Number(n || 0).toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function fmtDate(raw) {
    if (window.formatDisplaySmart) return window.formatDisplaySmart(raw, "—");
    if (!raw) return "—";
    const s = String(raw).slice(0, 10);
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
    if (!m) return escapeHtml(s);
    return m[3] + "/" + m[2] + "/" + m[1];
  }

  function render(rows) {
    if (!els.body) return;
    els.body.innerHTML = "";
    if (!rows.length) {
      els.empty?.classList.remove("d-none");
      if (els.count) els.count.textContent = "0 entries";
      return;
    }
    els.empty?.classList.add("d-none");
    if (els.count) {
      els.count.textContent = rows.length + " entr" + (rows.length === 1 ? "y" : "ies");
    }
    rows.forEach(function (row) {
      const href =
        api.openUrl + "?load_entry=" + encodeURIComponent(row.entry_id || "");
      const tr = document.createElement("tr");
      tr.innerHTML =
        "<td><code>" +
        escapeHtml(row.voucher_no) +
        "</code></td>" +
        "<td>" +
        fmtDate(row.work_date) +
        "</td>" +
        "<td>" +
        escapeHtml(row.purpose || "—") +
        "</td>" +
        "<td>" +
        escapeHtml(row.credit_account || "—") +
        "</td>" +
        "<td>" +
        escapeHtml(row.debit_account || "—") +
        "</td>" +
        '<td class="text-end fw-semibold">' +
        money(row.amount) +
        "</td>" +
        '<td class="text-end">' +
        '<a class="btn btn-outline-primary btn-sm" href="' +
        escapeHtml(href) +
        '"><i class="bi bi-box-arrow-up-right"></i></a>' +
        "</td>";
      els.body.appendChild(tr);
    });
  }

  async function load() {
    const url = new URL(api.list, window.location.origin);
    const q = (els.search?.value || "").trim();
    if (q) url.searchParams.set("search", q);
    const res = await fetch(url.toString(), { credentials: "same-origin" });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Unable to load Other Voucher grid");
    render(data.rows || []);
  }

  els.refresh?.addEventListener("click", function () {
    load().catch(function (err) {
      window.alert(err.message || String(err));
    });
  });

  els.search?.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(function () {
      load().catch(function (err) {
        window.alert(err.message || String(err));
      });
    }, 300);
  });

  load().catch(function (err) {
    window.alert(err.message || String(err));
  });
})();
