(function () {
  "use strict";

  const root = document.getElementById("jtcsMarketTicker");
  if (!root) return;

  const quotesUrl = root.getAttribute("data-quotes-url") || "/api/market/quotes";
  const liveBtn = document.getElementById("jtcsMarketLive");
  const itemsEl = document.getElementById("jtcsMarketItems");
  const LIVE_MS = 60 * 1000;
  const IDLE_MS = 5 * 60 * 1000;
  let timer = null;
  let isLive = false;

  function fmtPrice(n) {
    return Number(n || 0).toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function fmtChg(n) {
    const v = Number(n || 0);
    const sign = v > 0 ? "+" : "";
    return sign + v.toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function makeItem(row) {
    const el = document.createElement("span");
    const chg = Number(row.change || 0);
    el.className =
      "jtcs-market-item " +
      (row.ok ? (chg > 0 ? "is-up" : chg < 0 ? "is-down" : "is-flat") : "is-flat");
    el.setAttribute("role", "listitem");
    el.title =
      (row.label || "") +
      (row.note ? " — " + row.note : "") +
      (row.updated ? " · " + row.updated : "");
    const nm = document.createElement("span");
    nm.className = "nm";
    nm.textContent = row.short || row.label || "";
    const px = document.createElement("span");
    px.className = "px";
    px.textContent = row.ok ? fmtPrice(row.price) : "—";
    const ch = document.createElement("span");
    ch.className = "chg";
    ch.textContent = row.ok ? fmtChg(row.change) + " (" + fmtChg(row.percent) + "%)" : "";
    el.appendChild(nm);
    el.appendChild(px);
    el.appendChild(ch);
    return el;
  }

  function render(data) {
    root.hidden = false;
    isLive = !!(data && data.live);
    if (liveBtn) {
      liveBtn.classList.toggle("is-live", isLive);
      liveBtn.textContent = "";
      const dot = document.createElement("span");
      dot.className = "jtcs-market-live-dot";
      liveBtn.appendChild(dot);
      liveBtn.appendChild(document.createTextNode(isLive ? " LIVE" : " OFF"));
      liveBtn.title = isLive
        ? "Live — quotes refresh every 1 minute"
        : "Market closed — quotes pause until the next session";
    }
    if (!itemsEl) return;
    itemsEl.innerHTML = "";
    const row1 = document.createElement("div");
    row1.className = "jtcs-market-row";
    const row2 = document.createElement("div");
    row2.className = "jtcs-market-row";
    const rows = (data && data.indices) || [];
    rows.forEach(function (row) {
      const target = Number(row.row) === 2 ? row2 : row1;
      target.appendChild(makeItem(row));
    });
    itemsEl.appendChild(row1);
    if (row2.childElementCount) itemsEl.appendChild(row2);
  }

  async function refresh() {
    try {
      const res = await fetch(quotesUrl, {
        credentials: "same-origin",
        headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await res.json();
      render(data);
    } catch (e) {
      render({ ok: false, live: false, indices: [] });
    }
    schedule();
  }

  function schedule() {
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(refresh, isLive ? LIVE_MS : IDLE_MS);
  }

  refresh();
})();
