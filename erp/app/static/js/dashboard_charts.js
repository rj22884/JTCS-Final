/**
 * Dashboard analytics charts. Uses the selected Period (FY / month / custom).
 */
(function () {
  "use strict";

  var cfg = window.DASHBOARD || {};
  var EMPTY_MSG = "No transaction data available for the selected period.";
  var PALETTE = [
    "#2e5aac",
    "#10b981",
    "#f97316",
    "#0f766e",
    "#6f42c1",
    "#e11d48",
    "#e8a317",
    "#0f4c81",
    "#28a745",
    "#64748b",
  ];
  var charts = {};

  function rupee(value) {
    var n = Number(value || 0);
    var abs = Math.abs(n).toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    return (n < 0 ? "-₹ " : "₹ ") + abs;
  }

  function rupeeTick(value) {
    var n = Number(value || 0);
    var sign = n < 0 ? "-" : "";
    n = Math.abs(n);
    if (n >= 10000000) return sign + "₹" + (n / 10000000).toFixed(1) + "Cr";
    if (n >= 100000) return sign + "₹" + (n / 100000).toFixed(1) + "L";
    if (n >= 1000) return sign + "₹" + (n / 1000).toFixed(1) + "k";
    return sign + "₹" + n;
  }

  function setState(id, kind, message) {
    var state = document.getElementById(id + "State");
    var canvas = document.getElementById(id);
    if (state) {
      state.textContent = message || "";
      state.classList.toggle("d-none", kind === "ready");
      state.classList.toggle("is-error", kind === "error");
    }
    if (canvas) canvas.classList.toggle("d-none", kind !== "ready");
  }

  function setMeta(id, text) {
    var el = document.getElementById(id);
    if (!el) return;
    el.textContent = text || "";
    el.classList.toggle("d-none", !text);
  }

  function destroyChart(key) {
    if (charts[key]) {
      charts[key].destroy();
      charts[key] = null;
    }
  }

  function tooltipRupee(context) {
    var label = context.dataset.label ? context.dataset.label + ": " : "";
    return label + rupee(context.parsed.y != null ? context.parsed.y : context.parsed);
  }

  function tooltipRupeeIndex(context) {
    var label = context.label ? context.label + ": " : "";
    var parsed = context.parsed;
    var value;
    if (parsed && typeof parsed === "object") {
      value =
        context.chart.options.indexAxis === "y" ? parsed.x : parsed.y;
    } else {
      value = parsed;
    }
    return label + rupee(value);
  }

  function baseOptions() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          labels: { boxWidth: 10, boxHeight: 10, font: { size: 11 } },
        },
        tooltip: { callbacks: { label: tooltipRupee } },
      },
      scales: {
        x: {
          ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 10, font: { size: 10 } },
          grid: { display: false },
        },
        y: {
          beginAtZero: true,
          ticks: { callback: rupeeTick, font: { size: 10 } },
          grid: { color: "rgba(15, 76, 129, 0.08)" },
        },
      },
    };
  }

  function renderLine(canvasId, labels, values) {
    destroyChart(canvasId);
    var canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === "undefined") return;
    charts[canvasId] = new Chart(canvas.getContext("2d"), {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Collection",
            data: values,
            borderColor: "#2e5aac",
            backgroundColor: "rgba(46, 90, 172, 0.12)",
            fill: true,
            tension: 0.3,
            pointRadius: labels.length > 40 ? 0 : 2,
            pointHoverRadius: 4,
            borderWidth: 2,
          },
        ],
      },
      options: Object.assign(baseOptions(), {
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: tooltipRupee } },
        },
      }),
    });
  }

  function renderActivity(canvasId, labels, values, chartType) {
    destroyChart(canvasId);
    var canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === "undefined") return;
    var colors = labels.map(function (_label, i) {
      return PALETTE[i % PALETTE.length];
    });
    if (chartType === "bar") {
      charts[canvasId] = new Chart(canvas.getContext("2d"), {
        type: "bar",
        data: {
          labels: labels,
          datasets: [
            {
              label: "Collection",
              data: values,
              backgroundColor: colors,
              borderRadius: 4,
            },
          ],
        },
        options: {
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: { label: tooltipRupeeIndex } },
          },
          scales: {
            x: {
              beginAtZero: true,
              ticks: { callback: rupeeTick, font: { size: 10 } },
              grid: { color: "rgba(15, 76, 129, 0.08)" },
            },
            y: {
              ticks: { font: { size: 11 } },
              grid: { display: false },
            },
          },
        },
      });
      return;
    }
    charts[canvasId] = new Chart(canvas.getContext("2d"), {
      type: "doughnut",
      data: {
        labels: labels,
        datasets: [
          {
            data: values,
            backgroundColor: colors,
            borderWidth: 1,
            borderColor: "#fff",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "62%",
        plugins: {
          legend: {
            position: "bottom",
            labels: { boxWidth: 10, boxHeight: 10, font: { size: 11 } },
          },
          tooltip: { callbacks: { label: tooltipRupeeIndex } },
        },
      },
    });
  }

  function renderPl(canvasId, labels, income, expense, net) {
    destroyChart(canvasId);
    var canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === "undefined") return;
    charts[canvasId] = new Chart(canvas.getContext("2d"), {
      data: {
        labels: labels,
        datasets: [
          {
            type: "bar",
            label: "Income",
            data: income,
            backgroundColor: "rgba(16, 185, 129, 0.82)",
            borderRadius: 3,
          },
          {
            type: "bar",
            label: "Expense",
            data: expense,
            backgroundColor: "rgba(225, 29, 72, 0.78)",
            borderRadius: 3,
          },
          {
            type: "line",
            label: "Net",
            data: net,
            borderColor: "#0f4c81",
            backgroundColor: "#0f4c81",
            tension: 0.3,
            pointRadius: labels.length > 40 ? 0 : 2,
            borderWidth: 2,
          },
        ],
      },
      options: baseOptions(),
    });
  }

  function renderPay(canvasId, labels, values) {
    destroyChart(canvasId);
    var canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === "undefined") return;
    charts[canvasId] = new Chart(canvas.getContext("2d"), {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Collection",
            data: values,
            backgroundColor: "rgba(46, 90, 172, 0.82)",
            borderRadius: 4,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: tooltipRupeeIndex } },
        },
        scales: {
          x: {
            beginAtZero: true,
            ticks: { callback: rupeeTick, font: { size: 10 } },
            grid: { color: "rgba(15, 76, 129, 0.08)" },
          },
          y: {
            ticks: { font: { size: 11 } },
            grid: { display: false },
          },
        },
      },
    });
  }

  function paint(data) {
    var collection = data.daily_collection || {};
    if (collection.empty) {
      setState("dashChartCollection", "empty", EMPTY_MSG);
      setMeta("dashChartCollectionMeta", "");
      destroyChart("dashChartCollection");
    } else {
      setMeta("dashChartCollectionMeta", "Total " + rupee(collection.total));
      setState("dashChartCollection", "ready");
      renderLine("dashChartCollection", collection.labels || [], collection.values || []);
    }

    var activity = data.by_activity || {};
    if (activity.empty) {
      setState("dashChartActivity", "empty", EMPTY_MSG);
      setMeta("dashChartActivityMeta", "");
      destroyChart("dashChartActivity");
    } else {
      setMeta("dashChartActivityMeta", "Total " + rupee(activity.total));
      setState("dashChartActivity", "ready");
      renderActivity(
        "dashChartActivity",
        activity.labels || [],
        activity.values || [],
        activity.chart || "doughnut"
      );
    }

    var pl = data.income_expense || {};
    if (pl.empty) {
      setState("dashChartPl", "empty", EMPTY_MSG);
      setMeta("dashChartPlMeta", "");
      destroyChart("dashChartPl");
    } else {
      setMeta(
        "dashChartPlMeta",
        "Income " +
          rupee(pl.income_total) +
          "  ·  Expense " +
          rupee(pl.expense_total) +
          "  ·  Net " +
          rupee(pl.net_total)
      );
      setState("dashChartPl", "ready");
      renderPl(
        "dashChartPl",
        pl.labels || [],
        pl.income || [],
        pl.expense || [],
        pl.net || []
      );
    }

    var pay = data.payment_mode || {};
    if (pay.empty) {
      setState("dashChartPay", "empty", EMPTY_MSG);
      setMeta("dashChartPayMeta", "");
      destroyChart("dashChartPay");
    } else {
      setMeta("dashChartPayMeta", "Total " + rupee(pay.total));
      setState("dashChartPay", "ready");
      renderPay("dashChartPay", pay.labels || [], pay.values || []);
    }
  }

  function fail(message) {
    ["dashChartCollection", "dashChartActivity", "dashChartPl", "dashChartPay"].forEach(
      function (id) {
        setState(id, "error", message || "Unable to load analytics.");
      }
    );
  }

  function load() {
    if (!document.querySelector(".dash-analytics")) return;
    var url = cfg.analyticsUrl;
    if (!url) {
      fail("Analytics is not available.");
      return;
    }
    var params = new URLSearchParams();
    if (cfg.dateFrom) params.set("from", cfg.dateFrom);
    if (cfg.dateTo) params.set("to", cfg.dateTo);
    fetch(url + "?" + params.toString(), {
      credentials: "same-origin",
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        return res.json().then(function (body) {
          return { ok: res.ok, body: body };
        });
      })
      .then(function (result) {
        if (!result.body || !result.body.ok) {
          fail((result.body && result.body.error) || "Unable to load analytics.");
          return;
        }
        paint(result.body);
      })
      .catch(function () {
        fail("Unable to load analytics.");
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", load);
  } else {
    load();
  }
})();
