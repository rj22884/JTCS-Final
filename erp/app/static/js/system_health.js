/**
 * System Health Mission Control — auto-refresh dashboard.
 */
(function () {
  "use strict";

  var REFRESH_MS = 30000;
  var charts = {};
  var timer = null;

  function csrf(root) {
    return (root && root.getAttribute("data-csrf")) ||
      (document.querySelector('meta[name="csrf-token"]') || {}).content ||
      "";
  }

  async function api(url, options, root) {
    var opts = Object.assign({ credentials: "same-origin" }, options || {});
    var headers = new Headers(opts.headers || {});
    var method = (opts.method || "GET").toUpperCase();
    if (method !== "GET" && method !== "HEAD") {
      var token = csrf(root);
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
    var data = raw ? JSON.parse(raw) : {};
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

  function gaugeClass(score) {
    if (score >= 90) return "ok";
    if (score >= 80) return "good";
    if (score >= 60) return "warn";
    return "bad";
  }

  function statusClass(code) {
    if (code === "ok") return "ok";
    if (code === "warn") return "warn";
    if (code === "bad") return "bad";
    return "muted";
  }

  function val(obj, path, fallback) {
    var cur = obj;
    var parts = path.split(".");
    for (var i = 0; i < parts.length; i++) {
      if (!cur || typeof cur !== "object") return fallback;
      cur = cur[parts[i]];
    }
    return cur == null || cur === "" ? fallback : cur;
  }

  function kv(pairs) {
    return (
      '<dl class="sh-kv">' +
      pairs
        .map(function (p) {
          return (
            "<div><dt>" +
            esc(p[0]) +
            "</dt><dd>" +
            esc(p[1]) +
            "</dd></div>"
          );
        })
        .join("") +
      "</dl>"
    );
  }

  function progressBar(pct) {
    var n = Number(pct);
    if (isNaN(n)) return '<span class="text-muted">N/A</span>';
    var cls = n >= 90 ? "bg-danger" : n >= 75 ? "bg-warning" : "bg-success";
    return (
      '<div class="d-flex align-items-center gap-2"><span class="fw-semibold">' +
      esc(n) +
      '%</span><div class="progress sh-progress flex-grow-1"><div class="progress-bar ' +
      cls +
      '" style="width:' +
      Math.min(100, n) +
      '%"></div></div></div>'
    );
  }

  function upsertChart(id, labels, values, color) {
    if (typeof Chart === "undefined") return;
    var canvas = document.getElementById(id);
    if (!canvas) return;
    if (charts[id]) {
      charts[id].data.labels = labels;
      charts[id].data.datasets[0].data = values;
      charts[id].update("none");
      return;
    }
    charts[id] = new Chart(canvas.getContext("2d"), {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            data: values,
            borderColor: color,
            backgroundColor: color.replace(")", ",0.12)").replace("rgb", "rgba"),
            fill: true,
            tension: 0.35,
            pointRadius: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true } },
      },
    });
  }

  function init() {
    var root = document.getElementById("shPage");
    if (!root) return;

    var urls = {
      dashboard: root.getAttribute("data-api-dashboard"),
      scan: root.getAttribute("data-api-scan"),
      charts: root.getAttribute("data-api-charts"),
      logs: root.getAttribute("data-api-logs"),
      export: root.getAttribute("data-api-export"),
      clearCache: root.getAttribute("data-api-clear-cache"),
      backup: root.getAttribute("data-api-backup"),
      refreshConfig: root.getAttribute("data-api-refresh-config"),
      integrationHealth: root.getAttribute("data-url-integration-health"),
      backupConsole: root.getAttribute("data-url-backup"),
    };

    var summaryEl = root.querySelector("[data-sh-summary]");
    var alertsEl = root.querySelector("[data-sh-alerts]");
    var gaugeEl = root.querySelector("[data-sh-gauge]");
    var labelEl = root.querySelector("[data-sh-label]");
    var clockEl = root.querySelector("[data-sh-clock]");
    var statusEl = root.querySelector("[data-sh-status]");

    function setStatus(msg, type) {
      if (!statusEl) return;
      statusEl.className = "alert alert-" + (type || "info") + " py-2";
      statusEl.textContent = msg;
      statusEl.classList.remove("d-none");
      setTimeout(function () {
        statusEl.classList.add("d-none");
      }, 4000);
    }

    function renderSummary(summary, overall, label) {
      if (gaugeEl) {
        gaugeEl.className = "sh-gauge " + gaugeClass(Number(overall) || 0);
        gaugeEl.textContent = (overall == null ? "—" : overall) + "%";
      }
      if (labelEl) labelEl.textContent = label || "";
      if (!summaryEl) return;
      var order = [
        ["application_status", "Application Status"],
        ["database_status", "Database Status"],
        ["server_status", "Server Status"],
        ["cpu_usage", "CPU Usage"],
        ["memory_usage", "Memory Usage"],
        ["disk_usage", "Disk Usage"],
        ["network_status", "Network Status"],
        ["backup_status", "Backup Status"],
        ["api_health", "API Health"],
        ["security_status", "Security Status"],
        ["overall_health_score", "Overall Health Score"],
        ["last_system_scan", "Last System Scan"],
      ];
      summaryEl.innerHTML = order
        .map(function (pair) {
          var item = summary[pair[0]] || {};
          return (
            '<div class="sh-card ' +
            statusClass(item.status) +
            '"><div class="sh-card-label">' +
            esc(pair[1]) +
            '</div><div class="sh-card-value">' +
            esc(item.value != null ? item.value : "—") +
            "</div>" +
            (item.detail
              ? '<div class="small text-muted">' + esc(item.detail) + "</div>"
              : "") +
            "</div>"
          );
        })
        .join("");
    }

    function renderAlerts(alerts) {
      if (!alertsEl) return;
      if (!alerts || !alerts.length) {
        alertsEl.innerHTML = '<div class="text-muted small">No open alerts.</div>';
        return;
      }
      alertsEl.innerHTML = alerts
        .map(function (a) {
          return (
            '<div class="sh-alert sev-' +
            esc((a.severity || "").toLowerCase()) +
            '"><strong>' +
            esc(a.title) +
            '</strong><div class="small text-muted">' +
            esc(a.message || "") +
            "</div></div>"
          );
        })
        .join("");
    }

    function renderSections(data) {
      var app = data.application || {};
      var db = data.database || {};
      var server = data.server || {};
      var storage = data.storage || {};
      var services = data.background_services || {};
      var api = data.api_health || {};
      var security = data.security || {};
      var users = data.users || {};
      var backups = data.backups || {};
      var license = data.license || {};
      var network = data.network || {};

      root.querySelector("[data-sh-application]").innerHTML = kv([
        ["Status", app.status],
        ["Version", app.version],
        ["Environment", app.environment],
        ["Uptime", app.uptime_human],
        ["Server time", app.server_time],
        ["Timezone", app.timezone],
        ["Last restart", app.last_restart],
        ["Python", app.python_version],
        ["Flask", app.flask_version],
        ["Mode", app.mode],
      ]);

      root.querySelector("[data-sh-database]").innerHTML = kv([
        ["Status", db.status],
        ["Database", db.database_name],
        ["Server", db.server],
        ["Size (MB)", db.size_mb],
        ["Free space (MB)", db.free_space_mb],
        ["Connections", db.connections],
        ["Active sessions", db.active_sessions],
        ["Blocking / deadlocks", db.deadlocks],
        ["Slow queries", db.slow_queries],
        ["Failed queries", db.failed_queries],
      ]);

      var diskHtml = "";
      var disks = server.disks || {};
      Object.keys(disks).forEach(function (k) {
        var d = disks[k];
        if (!d) return;
        diskHtml +=
          "<div class=\"mb-2\"><div class=\"small text-muted\">" +
          esc(d.path) +
          "</div>" +
          progressBar(d.percent) +
          '<div class="small">' +
          esc(d.used_gb) +
          " / " +
          esc(d.total_gb) +
          " GB</div></div>";
      });

      root.querySelector("[data-sh-server]").innerHTML =
        kv([
          ["Hostname", server.hostname],
          ["OS", server.os_name],
          ["Version", server.windows_version],
          ["CPU", server.cpu_percent != null ? server.cpu_percent + "%" : "N/A (install psutil)"],
          ["Memory", server.memory_percent != null ? server.memory_percent + "%" : "N/A"],
          ["RAM available", server.ram_available_gb != null ? server.ram_available_gb + " GB" : "—"],
          ["Boot since", server.server_uptime_since || "—"],
        ]) + '<div class="mt-2">' + diskHtml + "</div>";

      var folders = storage.folders || {};
      root.querySelector("[data-sh-storage]").innerHTML =
        kv([
          ["Total (GB)", storage.total_storage_gb],
          ["Used (GB)", storage.used_storage_gb],
          ["Free (GB)", storage.free_storage_gb],
          ["Uploads MB", val(folders, "uploads.size_mb", "—")],
          ["Documents MB", val(folders, "documents.size_mb", "—")],
          ["Backups MB", val(folders, "backups.size_mb", "—")],
          ["Logs MB", val(folders, "logs.size_mb", "—")],
          ["Temp MB", val(folders, "temp.size_mb", "—")],
        ]) +
        '<ul class="small mb-0 mt-2">' +
        (storage.cleanup_suggestions || [])
          .map(function (t) {
            return "<li>" + esc(t) + "</li>";
          })
          .join("") +
        "</ul>";

      root.querySelector("[data-sh-services]").innerHTML = kv([
        ["Scheduler", val(services, "scheduler.status", "—")],
        ["Email pending/fail", val(services, "email_queue.pending", 0) + "/" + val(services, "email_queue.failed", 0)],
        ["WhatsApp pending/fail", val(services, "whatsapp_queue.pending", 0) + "/" + val(services, "whatsapp_queue.failed", 0)],
        ["SMS pending/fail", val(services, "sms_queue.pending", 0) + "/" + val(services, "sms_queue.failed", 0)],
        ["Notifications", val(services, "notification_queue.status", "—")],
        ["Worker", val(services, "background_jobs.worker_status", "—")],
        ["Pending jobs", val(services, "totals.pending_jobs", 0)],
        ["Failed jobs", val(services, "totals.failed_jobs", 0)],
      ]);

      var apiHtml = (api.integrations || [])
        .map(function (c) {
          var cls = /connected/i.test(c.status || "")
            ? "ok"
            : /warn|expir|partial/i.test(c.status || "")
              ? "warn"
              : /not configured/i.test(c.status || "")
                ? "muted"
                : "bad";
          return (
            '<span class="sh-api-chip ' +
            cls +
            '"><span class="dot"></span>' +
            esc(c.label) +
            " · " +
            esc(c.score) +
            "%</span>"
          );
        })
        .join("");
      root.querySelector("[data-sh-api]").innerHTML =
        '<div class="mb-2">Global API score: <strong>' +
        esc(api.global_health_score) +
        "% (" +
        esc(api.global_label) +
        ')</strong> · <a href="' +
        esc(urls.integrationHealth) +
        '">Open Integration Health</a></div>' +
        (apiHtml || '<span class="text-muted small">No integration summary.</span>');

      root.querySelector("[data-sh-security]").innerHTML = kv([
        ["Failed logins", security.failed_login_attempts],
        ["Blocked users", security.blocked_users],
        ["Suspicious", security.suspicious_activity],
        ["Password expiry", security.password_expiry],
        ["SSL", security.ssl_certificate],
        ["Encryption", security.encryption_status],
        ["Audit", security.audit_logs],
        ["Firewall", security.firewall_status],
      ]);

      var userRows = (users.recent || [])
        .slice(0, 8)
        .map(function (u) {
          return (
            "<tr><td>" +
            esc(u.user_name) +
            "</td><td>" +
            esc(u.last_login) +
            "</td><td>" +
            esc(u.status) +
            "</td></tr>"
          );
        })
        .join("");
      root.querySelector("[data-sh-users]").innerHTML =
        kv([
          ["Active users", users.active_users],
          ["Logged in (8h)", users.logged_in_recent],
          ["Idle (30d)", users.idle_users],
          ["Sessions", users.sessions_note],
        ]) +
        '<div class="table-responsive mt-2"><table class="table table-sm sh-table"><thead><tr><th>User</th><th>Last login</th><th>Status</th></tr></thead><tbody>' +
        (userRows || '<tr><td colspan="3" class="text-muted">No recent logins</td></tr>') +
        "</tbody></table></div>";

      var lastBak = backups.last_backup || {};
      root.querySelector("[data-sh-backups]").innerHTML =
        kv([
          ["Status", backups.status],
          ["Last backup", lastBak.name || lastBak.file_name || "—"],
          ["Size", lastBak.size_human || lastBak.size || "—"],
          ["Next backup", backups.next_backup],
          ["Location", val(backups, "backup_location.database_backup_dir", "—")],
        ]) +
        '<a class="btn btn-sm btn-outline-primary mt-2" href="' +
        esc(urls.backupConsole) +
        '">Open Backup Center</a>';

      root.querySelector("[data-sh-license]").innerHTML = kv([
        ["ERP version", license.erp_version],
        ["License", license.license_type],
        ["Expiry", license.expiry_date],
        ["Users allowed", license.users_allowed],
        ["Users active", license.users_active],
        ["Storage limit", license.storage_limit],
        ["Modules", (license.modules_activated || []).join(", ")],
      ]);

      root.querySelector("[data-sh-network]").innerHTML = kv([
        ["Network", network.status],
        ["Internet", network.internet_ok ? "OK" : "No"],
        ["Public health", network.public_health_ok == null ? "n/a" : network.public_health_ok ? "OK" : "FAIL"],
        ["Public URL", network.public_health_url],
      ]);
    }

    function renderLogs(logData) {
      var box = root.querySelector("[data-sh-logs]");
      if (!box) return;
      var entries = (logData && logData.entries) || [];
      if (!entries.length) {
        box.innerHTML = '<div class="text-muted small">No local log lines found.</div>';
        return;
      }
      box.innerHTML = entries
        .slice(0, 40)
        .map(function (e) {
          var cls =
            e.level === "Critical" || e.level === "Error"
              ? "sh-log-crit"
              : e.level === "Warning"
                ? "sh-log-warn"
                : "";
          return (
            '<div class="sh-log-line ' +
            cls +
            '">[' +
            esc(e.level) +
            "] " +
            esc(e.source) +
            ": " +
            esc(e.message) +
            "</div>"
          );
        })
        .join("");
    }

    async function loadCharts() {
      try {
        var data = await api(urls.charts, null, root);
        upsertChart("shChartCpu", data.cpu.labels, data.cpu.values, "rgb(11,92,171)");
        upsertChart("shChartMem", data.memory.labels, data.memory.values, "rgb(15,118,110)");
        upsertChart("shChartDisk", data.disk.labels, data.disk.values, "rgb(180,83,9)");
        upsertChart("shChartDb", data.db_sessions.labels, data.db_sessions.values, "rgb(124,58,237)");
        upsertChart("shChartApi", data.api_health.labels, data.api_health.values, "rgb(185,28,28)");
      } catch (_e) {}
    }

    async function loadDashboard(force) {
      root.classList.add("is-loading");
      try {
        var url = urls.dashboard + (force ? "?force=1" : "");
        var data = await api(url, null, root);
        renderSummary(data.summary || {}, data.overall_score, data.overall_label);
        renderAlerts(data.alerts || []);
        renderSections(data);
        renderLogs(data.logs || {});
        if (clockEl && data.application) {
          clockEl.textContent = data.application.server_time || data.live_clock || "";
        }
        await loadCharts();
      } catch (err) {
        setStatus(err.message || "Load failed", "danger");
      } finally {
        root.classList.remove("is-loading");
      }
    }

    root.addEventListener("click", async function (ev) {
      var t = ev.target.closest("[data-sh-action]");
      if (!t) return;
      var action = t.getAttribute("data-sh-action");
      t.disabled = true;
      try {
        if (action === "scan") {
          await api(urls.scan, { method: "POST", body: {} }, root);
          await loadDashboard(false);
          setStatus("Health scan completed.", "success");
        } else if (action === "clear-cache") {
          var r = await api(urls.clearCache, { method: "POST", body: {} }, root);
          setStatus(r.message || "Cache cleared.", "success");
        } else if (action === "backup") {
          var b = await api(urls.backup, { method: "POST", body: {} }, root);
          setStatus(b.message || "Backup created.", "success");
          await loadDashboard(true);
        } else if (action === "refresh-config") {
          await api(urls.refreshConfig, { method: "POST", body: {} }, root);
          await loadDashboard(false);
          setStatus("Configuration refreshed.", "success");
        } else if (action === "export") {
          var fmt = t.getAttribute("data-format") || "csv";
          window.location.href = urls.export + "?format=" + encodeURIComponent(fmt);
        } else if (action === "reload-logs") {
          var level = (root.querySelector("[data-sh-log-level]") || {}).value || "";
          var logs = await api(
            urls.logs + "?period=today" + (level ? "&level=" + encodeURIComponent(level) : ""),
            null,
            root
          );
          renderLogs(logs);
        }
      } catch (err) {
        setStatus(err.message || "Action failed", "danger");
      } finally {
        t.disabled = false;
      }
    });

    // Live clock tick
    setInterval(function () {
      if (!clockEl) return;
      try {
        clockEl.textContent = new Date().toLocaleString();
      } catch (_e) {}
    }, 1000);

    loadDashboard(true);
    timer = setInterval(function () {
      loadDashboard(false);
    }, REFRESH_MS);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
