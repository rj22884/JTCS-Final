(function () {
  "use strict";

  var cfg = window.WEBSITE_ANALYTICS || {};
  var PALETTE = ["#0f4c81", "#10b981", "#f97316", "#6f42c1", "#e11d48", "#64748b"];
  var charts = {};
  var series = "visitors";

  function doughnut(id, rows) {
    var canvas = document.getElementById(id);
    if (!canvas || !window.Chart) return;
    var labels = (rows || []).map(function (r) { return r.label; });
    var values = (rows || []).map(function (r) { return r.count; });
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart(canvas, {
      type: "doughnut",
      data: {
        labels: labels.length ? labels : ["No data"],
        datasets: [{ data: values.length ? values : [1], backgroundColor: PALETTE }],
      },
      options: {
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 12 } },
        },
      },
    });
  }

  function renderTrend() {
    var canvas = document.getElementById("waTrendChart");
    if (!canvas || !window.Chart) return;
    var rows = cfg.trend || [];
    var labels = rows.map(function (r) { return r.label; });
    var values = rows.map(function (r) { return series === "views" ? r.views : r.visitors; });
    if (charts.trend) charts.trend.destroy();
    charts.trend = new Chart(canvas, {
      type: "line",
      data: {
        labels: labels,
        datasets: [{
          label: series === "views" ? "Page Views" : "Visitors",
          data: values,
          borderColor: "#0f4c81",
          backgroundColor: "rgba(15,76,129,0.12)",
          fill: true,
          tension: 0.25,
          pointRadius: 3,
        }],
      },
      options: {
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
      },
    });
  }

  doughnut("waDeviceChart", cfg.devices);
  doughnut("waBrowserChart", cfg.browsers);
  doughnut("waOsChart", cfg.operatingSystems);
  doughnut("waSourceChart", cfg.sources);
  renderTrend();

  document.querySelectorAll("[data-wa-series]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      series = btn.getAttribute("data-wa-series") || "visitors";
      document.querySelectorAll("[data-wa-series]").forEach(function (el) {
        el.classList.toggle("active", el === btn);
      });
      renderTrend();
    });
  });

  var period = document.getElementById("waPeriod");
  var fromEl = document.getElementById("waFrom");
  var toEl = document.getElementById("waTo");

  function toggleCustomDates() {
    var isCustom = period && period.value === "custom";
    if (fromEl) fromEl.disabled = !isCustom;
    if (toEl) toEl.disabled = !isCustom;
  }

  if (period) {
    period.addEventListener("change", toggleCustomDates);
    toggleCustomDates();
  }

  document.querySelectorAll(".wa-export").forEach(function (el) {
    el.addEventListener("click", function (event) {
      event.preventDefault();
      var fmt = el.getAttribute("data-fmt") || "csv";
      var form = document.getElementById("waPeriodForm");
      var params = form ? new URLSearchParams(new FormData(form)) : new URLSearchParams();
      var base = String(cfg.exportBase || "")
        .replace(/\/csv$/i, "")
        .replace(/\/xlsx$/i, "")
        .replace(/\/pdf$/i, "");
      if (base.indexOf("/api/export") === -1) {
        base = base.replace(/\/?$/, "") + "/api/export";
      }
      window.location.href = base + "/" + encodeURIComponent(fmt) + "?" + params.toString();
    });
  });
})();
