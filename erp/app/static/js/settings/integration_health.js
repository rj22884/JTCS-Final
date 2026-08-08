/**
 * Integration Health Dashboard — tab inside Integration Settings.
 */
(function () {
  "use strict";

  function csrfToken(root) {
    if (root) {
      var fromPage = root.getAttribute("data-csrf");
      if (fromPage) return fromPage;
    }
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta && meta.content ? meta.content : "";
  }

  async function api(url, options, root) {
    var opts = Object.assign({ credentials: "same-origin" }, options || {});
    var headers = new Headers(opts.headers || {});
    var method = (opts.method || "GET").toUpperCase();
    var token = csrfToken(root);
    if (method !== "GET" && method !== "HEAD") {
      headers.set("X-CSRFToken", token);
      headers.set("X-CSRF-Token", token);
    }
    headers.set("Accept", "application/json");
    headers.set("X-Requested-With", "XMLHttpRequest");
    if (opts.body && typeof opts.body === "object" && !(opts.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
      opts.body = JSON.stringify(opts.body);
    }
    opts.headers = headers;
    var resp = await fetch(url, opts);
    var raw = await resp.text();
    var data = null;
    try {
      data = raw ? JSON.parse(raw) : {};
    } catch (_e) {
      throw new Error("Invalid response (" + resp.status + ")");
    }
    if (!resp.ok) throw new Error((data && data.error) || "Request failed");
    return data;
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function statusClass(code) {
    var map = {
      connected: "ih-ok",
      warning: "ih-warn",
      token_expiring: "ih-expire",
      disconnected: "ih-bad",
      not_configured: "ih-muted",
      failed: "ih-bad",
    };
    return map[code] || "ih-muted";
  }

  function scoreBarClass(score) {
    if (score >= 90) return "ih-bar-excellent";
    if (score >= 70) return "ih-bar-good";
    if (score >= 40) return "ih-bar-warn";
    return "ih-bar-critical";
  }

  function init() {
    var page = document.getElementById("intsetPage");
    var root = document.getElementById("ihDashboard");
    if (!page || !root) return;

    var urls = {
      dashboard: page.getAttribute("data-api-health-dashboard"),
      scan: page.getAttribute("data-api-health-scan"),
      detail: page.getAttribute("data-api-health-detail"),
      refresh: page.getAttribute("data-api-health-refresh"),
      test: page.getAttribute("data-api-health-test"),
      alerts: page.getAttribute("data-api-health-alerts"),
      history: page.getAttribute("data-api-health-history"),
      export: page.getAttribute("data-api-health-export"),
    };

    var state = { data: null, chart: null };
    var summaryEl = root.querySelector("[data-ih-summary]");
    var gridEl = root.querySelector("[data-ih-grid]");
    var alertsEl = root.querySelector("[data-ih-alerts]");
    var globalEl = root.querySelector("[data-ih-global]");
    var panel = document.getElementById("ihDetailPanel");
    var panelBody = panel ? panel.querySelector("[data-ih-panel-body]") : null;
    var canvas = root.querySelector("#ihHistoryChart");
    var loadedOnce = false;

    function renderSummary(s) {
      if (!summaryEl || !s) return;
      var cards = [
        { label: "Total Integrations", value: s.total, cls: "" },
        { label: "Connected", value: s.connected, cls: "ih-ok" },
        { label: "Disconnected", value: s.disconnected, cls: "ih-bad" },
        { label: "Warning", value: s.warning, cls: "ih-warn" },
        { label: "Failed", value: s.failed, cls: "ih-bad" },
        { label: "Expiring Soon", value: s.expiring_soon, cls: "ih-expire" },
        { label: "Last Health Scan", value: s.last_health_scan || "—", cls: "ih-scan", wide: true },
      ];
      summaryEl.innerHTML = cards
        .map(function (c) {
          return (
            '<div class="ih-summary-card ' +
            c.cls +
            (c.wide ? " ih-wide" : "") +
            '"><div class="ih-summary-label">' +
            esc(c.label) +
            '</div><div class="ih-summary-value">' +
            esc(c.value) +
            "</div></div>"
          );
        })
        .join("");
    }

    function renderGlobal(score, label) {
      if (!globalEl) return;
      var n = Number(score) || 0;
      globalEl.innerHTML =
        '<div class="ih-global-ring ' +
        scoreBarClass(n) +
        '"><span>' +
        esc(n) +
        '%</span></div><div><div class="fw-semibold">Global Health Score</div><div class="text-muted small">' +
        esc(label || "") +
        "</div></div>";
    }

    function renderAlerts(alerts) {
      if (!alertsEl) return;
      if (!alerts || !alerts.length) {
        alertsEl.innerHTML = '<div class="text-muted small">No open alerts.</div>';
        return;
      }
      alertsEl.innerHTML = alerts
        .slice(0, 12)
        .map(function (a) {
          return (
            '<div class="ih-alert-item sev-' +
            esc((a.severity || "warning").toLowerCase()) +
            '"><strong>' +
            esc(a.title) +
            '</strong><div class="small text-muted">' +
            esc(a.message || "") +
            "</div></div>"
          );
        })
        .join("");
    }

    function cardHtml(c) {
      var score = Number(c.health_score) || 0;
      return (
        '<article class="ih-card ' +
        statusClass(c.status_code) +
        '" data-ih-card="' +
        esc(c.code) +
        '" tabindex="0" role="button">' +
        '<div class="ih-card-head">' +
        '<div class="ih-logo"><i class="bi ' +
        esc(c.icon || "bi-plugin") +
        '"></i></div>' +
        "<div><div class=\"ih-name\">" +
        esc(c.label) +
        '</div><div class="ih-cat small text-muted">' +
        esc(c.category || "") +
        "</div></div>" +
        '<span class="ih-badge">' +
        esc(c.connection_status) +
        "</span></div>" +
        '<div class="ih-score-row"><div class="ih-score-num">' +
        esc(score) +
        '% <span class="small">' +
        esc(c.status_label) +
        '</span></div>' +
        '<div class="progress ih-progress"><div class="progress-bar ' +
        scoreBarClass(score) +
        '" style="width:' +
        score +
        '%"></div></div></div>' +
        '<dl class="ih-meta">' +
        "<div><dt>Token</dt><dd>" +
        esc(c.token_status) +
        "</dd></div>" +
        "<div><dt>API</dt><dd>" +
        esc(c.api_version) +
        "</dd></div>" +
        "<div><dt>Webhook</dt><dd>" +
        esc(c.webhook_status) +
        "</dd></div>" +
        "<div><dt>Last sync</dt><dd>" +
        esc(c.last_sync_at || "—") +
        "</dd></div>" +
        "<div><dt>Next check</dt><dd>" +
        esc(c.next_auto_check || "—") +
        "</dd></div>" +
        "<div><dt>Avg response</dt><dd>" +
        esc(c.avg_response_ms != null ? c.avg_response_ms + " ms" : "—") +
        "</dd></div>" +
        "</dl>" +
        (c.last_error
          ? '<div class="ih-error small">' + esc(c.last_error) + "</div>"
          : "") +
        '<div class="ih-actions" onclick="event.stopPropagation()">' +
        '<button type="button" class="btn btn-sm btn-outline-primary" data-ih-configure="' +
        esc(c.code) +
        '">Configure</button>' +
        '<button type="button" class="btn btn-sm btn-outline-success" data-ih-test="' +
        esc(c.code) +
        '">Test Connection</button>' +
        '<button type="button" class="btn btn-sm btn-outline-secondary" data-ih-refresh="' +
        esc(c.code) +
        '">Refresh</button>' +
        '<button type="button" class="btn btn-sm btn-outline-secondary" data-ih-reconnect="' +
        esc(c.code) +
        '">Reconnect</button>' +
        '<button type="button" class="btn btn-sm btn-outline-secondary" data-ih-logs="' +
        esc(c.code) +
        '">View Logs</button>' +
        "</div></article>"
      );
    }

    function renderGrid(list) {
      if (!gridEl) return;
      gridEl.innerHTML = (list || []).map(cardHtml).join("");
    }

    function openPanel() {
      if (!panel) return;
      panel.classList.add("is-open");
      panel.setAttribute("aria-hidden", "false");
    }

    function closePanel() {
      if (!panel) return;
      panel.classList.remove("is-open");
      panel.setAttribute("aria-hidden", "true");
    }

    async function showDetail(code) {
      if (!panelBody || !urls.detail) return;
      panelBody.innerHTML = '<div class="p-3 text-muted">Loading…</div>';
      openPanel();
      var data = await api(urls.detail.replace("__PROVIDER__", code), null, page);
      var card = data.card || {};
      var usage = data.usage || {};
      var html = "";
      html += '<h3 class="h5 mb-2">' + esc(card.label || code) + "</h3>";
      html +=
        '<div class="mb-3"><span class="ih-badge ' +
        statusClass(card.status_code) +
        '">' +
        esc(card.connection_status) +
        "</span> · Health " +
        esc(card.health_score) +
        "% (" +
        esc(card.status_label) +
        ")</div>";
      html += "<h4 class=\"h6\">Configuration</h4><dl class=\"ih-detail-dl\">";
      Object.keys(data.configuration || {}).forEach(function (k) {
        html +=
          "<div><dt>" +
          esc(k) +
          "</dt><dd class=\"text-break\">" +
          esc(data.configuration[k] || "—") +
          "</dd></div>";
      });
      html += "</dl>";
      html +=
        "<h4 class=\"h6 mt-3\">Token / Webhook</h4><dl class=\"ih-detail-dl\">" +
        "<div><dt>Token expiry</dt><dd>" +
        esc(data.token_expiry || "—") +
        "</dd></div>" +
        "<div><dt>Webhook URL</dt><dd class=\"text-break\">" +
        esc(data.webhook_url || "—") +
        "</dd></div>" +
        "<div><dt>Permissions</dt><dd>" +
        esc((data.permissions || []).join(", ") || "—") +
        "</dd></div></dl>";
      html +=
        "<h4 class=\"h6 mt-3\">API usage (from health history)</h4><dl class=\"ih-detail-dl\">" +
        "<div><dt>Avg / Slow / Fast</dt><dd>" +
        esc(usage.avg_response_ms ?? "—") +
        " / " +
        esc(usage.slowest_ms ?? "—") +
        " / " +
        esc(usage.fastest_ms ?? "—") +
        " ms</dd></div>" +
        "<div><dt>Today OK / Fail</dt><dd>" +
        esc(usage.successful_today) +
        " / " +
        esc(usage.failed_today) +
        "</dd></div></dl>";
      html += "<h4 class=\"h6 mt-3\">Error history</h4>";
      if (!(data.error_history || []).length) {
        html += '<div class="small text-muted mb-2">No recent errors.</div>';
      } else {
        html += '<ul class="ih-timeline">';
        (data.error_history || []).forEach(function (e) {
          html +=
            "<li><span class=\"time\">" +
            esc(e.checked_on) +
            "</span> " +
            esc(e.error) +
            "</li>";
        });
        html += "</ul>";
      }
      html += "<h4 class=\"h6 mt-3\">Audit log</h4>";
      if (!(data.audit || []).length) {
        html += '<div class="small text-muted">No audit rows.</div>';
      } else {
        html += '<div class="table-responsive"><table class="table table-sm"><thead><tr><th>When</th><th>User</th><th>Action</th><th>IP</th></tr></thead><tbody>';
        (data.audit || []).slice(0, 25).forEach(function (a) {
          html +=
            "<tr><td>" +
            esc(a.at) +
            "</td><td>" +
            esc(a.user || "—") +
            "</td><td>" +
            esc(a.key) +
            "</td><td>" +
            esc(a.ip || "—") +
            "</td></tr>";
        });
        html += "</tbody></table></div>";
      }
      panelBody.innerHTML = html;
    }

    async function loadHistory() {
      if (!urls.history || !canvas || typeof Chart === "undefined") return;
      try {
        var hist = await api(urls.history + "?period=daily", null, page);
        if (state.chart) state.chart.destroy();
        state.chart = new Chart(canvas.getContext("2d"), {
          type: "line",
          data: {
            labels: hist.labels || [],
            datasets: [
              {
                label: "Availability %",
                data: hist.availability || [],
                borderColor: "#0b5cab",
                backgroundColor: "rgba(11,92,171,.12)",
                tension: 0.3,
                fill: true,
              },
              {
                label: "Errors",
                data: hist.errors || [],
                borderColor: "#b45309",
                tension: 0.3,
                yAxisID: "y1",
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
              y: { min: 0, max: 100 },
              y1: { position: "right", min: 0, grid: { drawOnChartArea: false } },
            },
            plugins: { legend: { position: "bottom" } },
          },
        });
      } catch (_e) {
        /* chart optional */
      }
    }

    async function loadDashboard(force) {
      root.classList.add("is-loading");
      try {
        var url = urls.dashboard + (force ? "?force=1" : "");
        var data = await api(url, null, page);
        state.data = data;
        renderSummary(data.summary);
        renderGlobal(data.global_health_score, data.global_label);
        renderAlerts(data.alerts);
        renderGrid(data.integrations);
        await loadHistory();
        // Browser notification for critical alerts (permission-gated)
        maybeNotify(data.alerts || []);
      } finally {
        root.classList.remove("is-loading");
      }
    }

    function maybeNotify(alerts) {
      var critical = alerts.filter(function (a) {
        return /critical|error|high/i.test(a.severity || "");
      });
      if (!critical.length || !("Notification" in window)) return;
      if (Notification.permission === "granted") {
        critical.slice(0, 2).forEach(function (a) {
          try {
            new Notification(a.title || "Integration alert", { body: a.message || "" });
          } catch (_e) {}
        });
      }
    }

    function switchToConfigure(code) {
      var primary = document.querySelector('#intsetPrimaryTab-config');
      if (primary) primary.click();
      var tab = document.querySelector('#tab-' + code);
      if (tab) tab.click();
      var pane = document.querySelector('#pane-' + code);
      if (pane) pane.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    root.addEventListener("click", async function (ev) {
      var t = ev.target.closest("[data-ih-card],[data-ih-configure],[data-ih-test],[data-ih-refresh],[data-ih-reconnect],[data-ih-logs],[data-ih-scan],[data-ih-export],[data-ih-notify-enable]");
      if (!t) return;

      if (t.hasAttribute("data-ih-scan")) {
        if (urls.scan) {
          root.classList.add("is-loading");
          try {
            var scanned = await api(urls.scan, { method: "POST", body: {} }, page);
            state.data = scanned;
            renderSummary(scanned.summary);
            renderGlobal(scanned.global_health_score, scanned.global_label);
            renderAlerts(scanned.alerts);
            renderGrid(scanned.integrations);
            await loadHistory();
            maybeNotify(scanned.alerts || []);
          } finally {
            root.classList.remove("is-loading");
          }
        } else {
          await loadDashboard(true);
        }
        return;
      }
      if (t.hasAttribute("data-ih-export")) {
        var fmt = t.getAttribute("data-ih-export") || "csv";
        window.location.href = urls.export + "?format=" + encodeURIComponent(fmt);
        return;
      }
      if (t.hasAttribute("data-ih-notify-enable")) {
        if ("Notification" in window) Notification.requestPermission();
        return;
      }

      var code =
        t.getAttribute("data-ih-configure") ||
        t.getAttribute("data-ih-test") ||
        t.getAttribute("data-ih-refresh") ||
        t.getAttribute("data-ih-reconnect") ||
        t.getAttribute("data-ih-logs") ||
        t.getAttribute("data-ih-card");

      if (t.hasAttribute("data-ih-configure") || t.hasAttribute("data-ih-reconnect")) {
        switchToConfigure(code);
        return;
      }
      if (t.hasAttribute("data-ih-test")) {
        t.disabled = true;
        try {
          await api(urls.test.replace("__PROVIDER__", code), { method: "POST", body: {} }, page);
          await loadDashboard(false);
        } finally {
          t.disabled = false;
        }
        return;
      }
      if (t.hasAttribute("data-ih-refresh")) {
        t.disabled = true;
        try {
          await api(urls.refresh.replace("__PROVIDER__", code), { method: "POST", body: {} }, page);
          await loadDashboard(false);
        } finally {
          t.disabled = false;
        }
        return;
      }
      if (t.hasAttribute("data-ih-logs") || t.hasAttribute("data-ih-card")) {
        showDetail(code).catch(function (err) {
          if (panelBody) panelBody.innerHTML = '<div class="p-3 text-danger">' + esc(err.message) + "</div>";
        });
      }
    });

    if (panel) {
      panel.querySelectorAll("[data-ih-close]").forEach(function (btn) {
        btn.addEventListener("click", closePanel);
      });
    }

    // Load when Health tab becomes visible
    var healthTab = document.querySelector('#intsetPrimaryTab-health');
    if (healthTab) {
      healthTab.addEventListener("shown.bs.tab", function () {
        if (!loadedOnce) {
          loadedOnce = true;
          loadDashboard(false);
        }
      });
      // Deep link ?tab=health
      if (/[?&]tab=health/i.test(location.search)) {
        healthTab.click();
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
