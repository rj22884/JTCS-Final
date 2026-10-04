(function () {
  "use strict";

  const slot = document.getElementById("dashCustomSlot");
  const board = document.getElementById("dashCustomCards");
  const addBtn = document.getElementById("dashCustomAdd");
  const removeBtn = document.getElementById("dashCustomRemove");
  if (!slot || !board || !addBtn || !removeBtn) return;

  const userId = slot.getAttribute("data-user-id") || "0";
  const storageKey = "jtcsDashCustomCards:" + userId;
  const searchUrl = (window.LEDGER_REPORT && window.LEDGER_REPORT.searchUrl) || "";
  const modalEl = document.getElementById("dashCustomModal");
  const modal = modalEl && window.bootstrap ? bootstrap.Modal.getOrCreateInstance(modalEl) : null;
  const sourceEl = document.getElementById("dashCustomSource");
  const searchEl = document.getElementById("dashCustomSearch");
  const pickList = document.getElementById("dashCustomPickList");
  const pickWrap = document.getElementById("dashCustomPickWrap");
  const fieldWrap = document.getElementById("dashCustomFieldWrap");
  const nameEl = document.getElementById("dashCustomName");
  const calcEl = document.getElementById("dashCustomCalc");
  const saveBtn = document.getElementById("dashCustomSave");

  let cards = [];
  let selectedId = "";
  let picked = null;
  let searchTimer = null;

  function loadCards() {
    try {
      cards = JSON.parse(localStorage.getItem(storageKey) || "[]");
    } catch (_err) {
      cards = [];
    }
    if (!Array.isArray(cards)) cards = [];
  }

  function saveCards() {
    localStorage.setItem(storageKey, JSON.stringify(cards));
  }

  function money(value) {
    const num = Number(String(value == null ? "" : value).replace(/,/g, ""));
    if (!Number.isFinite(num)) return "—";
    return "₹ " + num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function metricNumber(key) {
    const node = document.querySelector('[data-metric-value="' + key + '"]');
    if (!node) return 0;
    const raw = (node.textContent || "").replace(/[₹,\s]/g, "");
    const num = Number(raw);
    return Number.isFinite(num) ? num : 0;
  }

  function customValue(card) {
    if (card.calc === "income_minus_expense") {
      return money(metricNumber("total_income") - metricNumber("total_expenses"));
    }
    const node = document.querySelector('[data-metric-value="' + card.calc + '"]');
    return node ? node.textContent.trim() : "—";
  }

  function render() {
    board.innerHTML = cards
      .map(function (card) {
        const selected = card.id === selectedId ? " is-selected" : "";
        const value = card.source === "custom" ? customValue(card) : card.valueText || "…";
        return (
          '<button type="button" class="dash-custom-card' +
          selected +
          '" data-card-id="' +
          card.id +
          '"><span class="dash-custom-label"></span><span class="dash-custom-value"></span></button>'
        );
      })
      .join("");
    Array.prototype.forEach.call(board.querySelectorAll(".dash-custom-card"), function (btn, index) {
      const card = cards[index];
      btn.querySelector(".dash-custom-label").textContent = card.title || "Card";
      btn.querySelector(".dash-custom-value").textContent =
        card.source === "custom" ? customValue(card) : card.valueText || "…";
    });
  }

  function refreshValues() {
    const jobs = cards.filter(function (card) {
      return card.source === "ledger" || card.source === "work";
    });
    if (!searchUrl || !jobs.length) {
      render();
      return;
    }
    Promise.all(
      jobs.map(function (card) {
        const url =
          searchUrl +
          "?kind=" +
          encodeURIComponent(card.source === "work" ? "work" : "all") +
          "&search=" +
          encodeURIComponent(card.label || "");
        return fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
          .then(function (res) {
            return res.json();
          })
          .then(function (data) {
            const rows = (data && data.rows) || [];
            const match =
              rows.find(function (row) {
                return String(row.id) === String(card.ref) && (!card.kind || row.kind === card.kind);
              }) || rows[0];
            if (!match) {
              card.valueText = "—";
              return;
            }
            if (card.calc === "count") card.valueText = String(match.txn_count || 0);
            else card.valueText = money(match.closing);
          })
          .catch(function () {
            card.valueText = "—";
          });
      })
    ).then(function () {
      saveCards();
      render();
    });
  }

  board.addEventListener("click", function (event) {
    const card = event.target.closest(".dash-custom-card");
    if (!card) return;
    selectedId = card.getAttribute("data-card-id") || "";
    render();
  });

  removeBtn.addEventListener("click", function () {
    if (!selectedId) return;
    cards = cards.filter(function (card) {
      return card.id !== selectedId;
    });
    selectedId = "";
    saveCards();
    render();
  });

  function toggleSource() {
    const custom = sourceEl && sourceEl.value === "custom";
    if (pickWrap) pickWrap.classList.toggle("d-none", custom);
    if (fieldWrap) fieldWrap.classList.toggle("d-none", !custom);
  }

  function renderPicks(rows) {
    if (!pickList) return;
    pickList.innerHTML = "";
    (rows || []).slice(0, 8).forEach(function (row) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "list-group-item list-group-item-action";
      btn.setAttribute("data-id", String(row.id));
      btn.setAttribute("data-kind", row.kind || "");
      btn.setAttribute("data-label", row.label || "");
      btn.textContent = row.label || "";
      pickList.appendChild(btn);
    });
  }

  if (sourceEl) sourceEl.addEventListener("change", toggleSource);
  if (searchEl) {
    searchEl.addEventListener("input", function () {
      picked = null;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () {
        const term = (searchEl.value || "").trim();
        if (!searchUrl || term.length < 1) {
          renderPicks([]);
          return;
        }
        const kind = sourceEl && sourceEl.value === "work" ? "work" : "all";
        fetch(
          searchUrl + "?kind=" + encodeURIComponent(kind) + "&search=" + encodeURIComponent(searchEl.value || ""),
          { credentials: "same-origin", headers: { Accept: "application/json" } }
        )
          .then(function (res) {
            return res.json();
          })
          .then(function (data) {
            renderPicks((data && data.rows) || []);
          })
          .catch(function () {
            renderPicks([]);
          });
      }, 250);
    });
  }
  if (pickList) {
    pickList.addEventListener("click", function (event) {
      const btn = event.target.closest("[data-id]");
      if (!btn) return;
      picked = {
        id: btn.getAttribute("data-id"),
        kind: btn.getAttribute("data-kind"),
        label: btn.getAttribute("data-label"),
      };
      if (searchEl) searchEl.value = picked.label || "";
      pickList.innerHTML = "";
    });
  }

  addBtn.addEventListener("click", function () {
    picked = null;
    if (searchEl) searchEl.value = "";
    if (nameEl) nameEl.value = "";
    if (pickList) pickList.innerHTML = "";
    toggleSource();
    if (modal) modal.show();
  });

  if (saveBtn) {
    saveBtn.addEventListener("click", function () {
      const source = sourceEl ? sourceEl.value : "ledger";
      let card = null;
      if (source === "custom") {
        const title = (nameEl && nameEl.value.trim()) || "Custom";
        card = {
          id: String(Date.now()),
          source: "custom",
          title: title,
          calc: calcEl ? calcEl.value : "total_income",
        };
      } else if (picked) {
        card = {
          id: String(Date.now()),
          source: source,
          title: picked.label,
          label: picked.label,
          ref: picked.id,
          kind: picked.kind,
          calc: "closing",
          valueText: "…",
        };
      }
      if (!card) return;
      cards.push(card);
      selectedId = card.id;
      saveCards();
      if (modal) modal.hide();
      refreshValues();
    });
  }

  loadCards();
  refreshValues();
})();
