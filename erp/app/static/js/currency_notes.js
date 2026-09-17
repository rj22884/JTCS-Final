/**
 * Dashboard → Cash Closing Balance → Currency Notes Closing
 * Physical note count only. Does not change Cash Closing Balance.
 */
(function () {
  "use strict";

  const cfg = window.DASHBOARD || {};
  const DENOMS = [500, 200, 100, 50, 20, 10, 5, 2, 1];
  const btn = document.getElementById("dashCurrencyNotesBtn");
  const modalEl = document.getElementById("dashCurrencyNotesModal");
  if (!btn || !modalEl || !window.bootstrap) return;

  const els = {
    date: document.getElementById("dashNotesDate"),
    body: document.getElementById("dashNotesBody"),
    totalCount: document.getElementById("dashNotesTotalCount"),
    totalAmount: document.getElementById("dashNotesTotalAmount"),
    cardTotal: document.getElementById("dashCurrencyNotesTotal"),
    saveBtn: document.getElementById("dashNotesSaveBtn"),
  };
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);

  function parseAmount(el) {
    if (!el) return 0;
    const n = parseFloat(String(el.textContent || "").replace(/[^0-9.-]/g, ""));
    return Number.isFinite(n) ? n : 0;
  }

  function syncMatchEmojis() {
    const cashEl = document.querySelector('[data-metric-value="cash_closing_balance"]');
    const notesEl = els.cardTotal;
    const cashEmoji = document.getElementById("dashCashCloseEmoji");
    const notesEmoji = document.getElementById("dashNotesCloseEmoji");
    const cash = parseAmount(cashEl);
    const notes = parseAmount(notesEl);
    const match = Math.abs(cash - notes) < 0.005;
    const emoji = match ? "😊" : "😢";
    const title = match
      ? "Cash closing and currency notes match"
      : "Cash closing and currency notes differ";
    [cashEmoji, notesEmoji].forEach(function (span) {
      if (!span) return;
      span.textContent = emoji;
      span.title = title;
    });
    const cashBtn = document.querySelector(
      '.dash-today-closing[data-metric="cash_closing_balance"]'
    );
    if (cashBtn) cashBtn.classList.toggle("is-notes-mismatch", !match);
    if (btn) btn.classList.toggle("is-notes-mismatch", !match);
  }

  window.JTCSCurrencyNotesMatch = { sync: syncMatchEmojis };

  function formatMoney(value) {
    const num = Number(value || 0);
    return (
      "₹ " +
      Math.abs(num).toLocaleString("en-IN", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })
    );
  }

  function countsFromGrid() {
    const out = {};
    DENOMS.forEach(function (d) {
      const input = document.getElementById("dashNoteCount_" + d);
      out[d] = input ? parseInt(input.value, 10) || 0 : 0;
    });
    return out;
  }

  function recalc() {
    const counts = countsFromGrid();
    let notes = 0;
    let amount = 0;
    DENOMS.forEach(function (d) {
      const n = Math.max(0, counts[d] || 0);
      const lineAmt = d * n;
      notes += n;
      amount += lineAmt;
      const cell = document.getElementById("dashNoteAmt_" + d);
      if (cell) cell.textContent = formatMoney(lineAmt);
    });
    if (els.totalCount) els.totalCount.textContent = String(notes);
    if (els.totalAmount) els.totalAmount.textContent = formatMoney(amount);
    return { notes: notes, amount: amount };
  }

  function renderLines(lines) {
    const byDenom = {};
    (lines || []).forEach(function (row) {
      byDenom[Number(row.denomination)] = row;
    });
    if (!els.body) return;
    els.body.innerHTML = DENOMS.map(function (d) {
      const notes = byDenom[d] ? parseInt(byDenom[d].notes, 10) || 0 : 0;
      const amount = d * notes;
      return (
        "<tr>" +
        "<td>₹ " +
        d.toLocaleString("en-IN") +
        "</td>" +
        '<td class="text-end"><input type="number" min="0" step="1" class="form-control form-control-sm text-end dash-note-count" id="dashNoteCount_' +
        d +
        '" data-denom="' +
        d +
        '" value="' +
        notes +
        '"></td>' +
        '<td class="text-end" id="dashNoteAmt_' +
        d +
        '">' +
        formatMoney(amount) +
        "</td>" +
        "</tr>"
      );
    }).join("");
    recalc();
  }

  function loadForDate(iso) {
    const url = (cfg.notesUrl || "") + (iso ? "?date=" + encodeURIComponent(iso) : "");
    return fetch(url, {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load notes.");
          if (els.date && data.entry_date) els.date.value = data.entry_date;
          renderLines(data.lines || []);
          return data;
        });
      })
      .catch(function (err) {
        if (window.JTCSDialog && JTCSDialog.alert) {
          JTCSDialog.alert(err.message || "Unable to load currency notes.", "error");
        } else {
          alert(err.message || "Unable to load currency notes.");
        }
      });
  }

  function save() {
    const iso = (els.date && els.date.value) || cfg.systemDate || "";
    const counts = countsFromGrid();
    const lines = DENOMS.map(function (d) {
      return { denomination: d, notes: Math.max(0, counts[d] || 0) };
    });
    if (els.saveBtn) els.saveBtn.disabled = true;
    return fetch(cfg.notesSaveUrl || cfg.notesUrl, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": cfg.csrfToken || "",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({ entry_date: iso, lines: lines }),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Unable to save notes.");
          renderLines(data.lines || []);
          if (els.cardTotal && iso === (cfg.systemDate || iso)) {
            els.cardTotal.textContent = formatMoney(data.total_amount);
          }
          syncMatchEmojis();
          if (window.JTCSDialog && JTCSDialog.alert) {
            JTCSDialog.alert("Currency notes saved.", "success");
          }
          return data;
        });
      })
      .catch(function (err) {
        if (window.JTCSDialog && JTCSDialog.alert) {
          JTCSDialog.alert(err.message || "Unable to save currency notes.", "error");
        } else {
          alert(err.message || "Unable to save currency notes.");
        }
      })
      .finally(function () {
        if (els.saveBtn) els.saveBtn.disabled = false;
      });
  }

  btn.addEventListener("click", function (ev) {
    ev.preventDefault();
    ev.stopPropagation();
    const iso = cfg.systemDate || (els.date && els.date.value) || "";
    if (els.date && iso) els.date.value = iso;
    modal.show();
    loadForDate(iso);
  });

  els.body?.addEventListener("input", function (ev) {
    if (ev.target && ev.target.classList.contains("dash-note-count")) recalc();
  });

  els.date?.addEventListener("change", function () {
    loadForDate((els.date.value || "").trim());
  });

  els.saveBtn?.addEventListener("click", function () {
    save();
  });

  syncMatchEmojis();
})();
