(function (global) {
  "use strict";

  function getCookie(name) {
    const match = document.cookie.match(new RegExp("(?:^|; )" + name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "=([^;]*)"));
    return match ? decodeURIComponent(match[1]) : "";
  }

  function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    return getCookie("csrf_token") || getCookie("csrf-token") || "";
  }

  function formatDate(value, options) {
    if (value == null || value === "") return "—";
    if (options && options.dateOnly && global.formatDisplayDate) {
      return global.formatDisplayDate(value, "—");
    }
    if (global.formatDisplaySmart) return global.formatDisplaySmart(value, "—");
    if (global.formatDisplayDate) return global.formatDisplayDate(value, "—");
    const d = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    const opts = options || { dateStyle: "medium", timeStyle: "short" };
    try {
      return new Intl.DateTimeFormat("en-GB", opts).format(d);
    } catch (_e) {
      return d.toLocaleString("en-GB");
    }
  }

  function formatDateOnly(value) {
    if (global.formatDisplayDate) return global.formatDisplayDate(value, "—");
    return formatDate(value, { dateOnly: true, dateStyle: "medium" });
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text == null ? "" : String(text);
    return div.innerHTML;
  }

  async function apiFetch(url, options) {
    const opts = Object.assign({ credentials: "same-origin" }, options || {});
    const headers = new Headers(opts.headers || {});
    const method = (opts.method || "GET").toUpperCase();
    const token = getCsrfToken();
    if (token && method !== "GET" && method !== "HEAD") {
      headers.set("X-CSRFToken", token);
    }
    if (opts.body && typeof opts.body === "object" && !(opts.body instanceof FormData) && !(opts.body instanceof Blob)) {
      headers.set("Content-Type", "application/json");
      opts.body = JSON.stringify(opts.body);
    }
    opts.headers = headers;
    const resp = await fetch(url, opts);
    let data = null;
    const ct = resp.headers.get("content-type") || "";
    if (ct.indexOf("application/json") !== -1) {
      data = await resp.json();
    } else {
      data = { ok: resp.ok, text: await resp.text() };
    }
    if (!resp.ok) {
      const err = new Error((data && data.error) || resp.statusText || "Request failed");
      err.status = resp.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  function urlTemplate(template, id) {
    return String(template || "").replace(/\/0(\/|$|\?)/, "/" + id + "$1").replace(/0$/, String(id));
  }

  function showAlert(message, type) {
    if (global.JTCSDialog && typeof global.JTCSDialog.alert === "function") {
      global.JTCSDialog.alert(message, type === "danger" ? "error" : "info");
      return;
    }
    window.alert(message);
  }

  global.CrmCommon = {
    getCsrfToken: getCsrfToken,
    apiFetch: apiFetch,
    formatDate: formatDate,
    formatDateOnly: formatDateOnly,
    escapeHtml: escapeHtml,
    urlTemplate: urlTemplate,
    showAlert: showAlert,
  };
})(window);
