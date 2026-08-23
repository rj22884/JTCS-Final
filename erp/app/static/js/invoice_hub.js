(function () {
  "use strict";

  const api = window.INVOICE_HUB_API;
  if (!api) return;

  const els = {
    body: document.getElementById("invHubBody"),
    empty: document.getElementById("invHubEmpty"),
    count: document.getElementById("invHubCount"),
    search: document.getElementById("invHubSearch"),
    refresh: document.getElementById("invHubRefresh"),
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

  function typeBadge(kind) {
    const k = String(kind || "").toUpperCase();
    if (k === "PURCHASE") return '<span class="badge text-bg-warning">Purchase</span>';
    if (k === "OTHER") return '<span class="badge text-bg-secondary">Other</span>';
    return '<span class="badge text-bg-primary">Sale</span>';
  }

  function openHref(row) {
    const kind = String(row.kind || "").toUpperCase();
    if (kind === "PURCHASE") {
      return api.purchaseUrl + "?edit=" + encodeURIComponent(row.ref_id || "");
    }
    if (kind === "OTHER") {
      return api.otherUrl + "?load_entry=" + encodeURIComponent(row.ref_id || "");
    }
    return api.saleUrl + "?edit=" + encodeURIComponent(row.ref_id || "");
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
      const tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" +
        typeBadge(row.kind) +
        "</td>" +
        "<td><code>" +
        escapeHtml(row.voucher_no) +
        "</code></td>" +
        "<td>" +
        fmtDate(row.work_date) +
        "</td>" +
        "<td>" +
        escapeHtml(row.party || "—") +
        "</td>" +
        '<td class="text-end fw-semibold">' +
        money(row.amount) +
        "</td>" +
        '<td class="text-end">' +
        '<a class="btn btn-outline-primary btn-sm" href="' +
        escapeHtml(openHref(row)) +
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
    if (!data.ok) throw new Error(data.error || "Unable to load hub grid");
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
