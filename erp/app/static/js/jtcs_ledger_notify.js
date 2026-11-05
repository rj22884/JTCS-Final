/**
 * After a ledger entry is saved in a page window, tell the dashboard to
 * reload its cards. Entry screens themselves are unchanged.
 */
(function () {
  "use strict";

  if (window.__jtcsLedgerNotify) return;
  window.__jtcsLedgerNotify = true;

  var MESSAGE = "jtcs-ledger-changed";

  function pathOf(url) {
    try {
      var path = new URL(url, window.location.origin).pathname;
      if (path.length > 1 && path.charAt(path.length - 1) === "/") path = path.slice(0, -1);
      return path.toLowerCase();
    } catch (err) {
      return "";
    }
  }

  function isLedgerWrite(url, method) {
    var verb = String(method || "GET").toUpperCase();
    if (verb === "GET" || verb === "HEAD" || verb === "OPTIONS") return false;
    var path = pathOf(url);
    if (!path) return false;
    return (
      path === "/shcil/stamp-activity" ||
      /^\/shcil\/stamp-activity\/delete\/\d+$/.test(path) ||
      path === "/shcil/ecourt-activity/sell" ||
      path === "/shcil/ecourt-activity/unsell" ||
      path === "/shcil/ecourt-activity/manual" ||
      path === "/shcil/ecourt-activity/update-entry" ||
      path === "/shcil/ecourt-activity/delete-stationery" ||
      path === "/shcil/ecourt-activity/import" ||
      path === "/shcil/ecourt-activity/import/import-page" ||
      path === "/others/income-expense/save" ||
      /^\/others\/income-expense\/records\/\d+\/delete$/.test(path) ||
      path === "/others/bank-cash-transactions/save" ||
      /^\/others\/bank-cash-transactions\/delete\/\d+$/.test(path) ||
      path === "/activities/miscellaneous/save" ||
      path === "/activities/misc_new/save" ||
      /^\/activities\/(miscellaneous|misc_new)\/records\/\d+\/delete$/.test(path) ||
      path === "/activities/miscellaneous/payment-received" ||
      path === "/activities/misc_new/payment-received" ||
      path === "/activities/miscellaneous/generate-bill/invoice/delete" ||
      path === "/activities/misc_new/generate-bill/invoice/delete" ||
      /^\/(itr|dsc|tds|gst)\/followup\/records$/.test(path) ||
      /^\/(itr|dsc|tds|gst)\/followup\/records\/\d+\/delete$/.test(path) ||
      path === "/others/income/printing-scanning" ||
      path === "/others/expense/printing-scanning" ||
      /^\/others\/(income|expense)\/printing-scanning\/records\/\d+\/delete$/.test(path) ||
      path === "/accounting/api/invoices" ||
      /^\/accounting\/api\/invoices\/\d+$/.test(path) ||
      /^\/accounting\/api\/invoices\/\d+\/delete$/.test(path) ||
      /^\/accounting\/api\/invoices\/\d+\/workflow$/.test(path) ||
      path === "/dashboard/api/manual-entries" ||
      /^\/dashboard\/api\/manual-entries\/\d+$/.test(path) ||
      /^\/dashboard\/api\/manual-entries\/\d+\/delete$/.test(path) ||
      path.indexOf("/dashboard/api/source/") === 0
    );
  }

  function notifyDashboard() {
    var msg = { type: MESSAGE };
    var origin = window.location.origin;
    var targets = [];
    targets.push(window.top || window);
    try {
      if (window.opener && !window.opener.closed) {
        targets.push(window.opener.top || window.opener);
      }
    } catch (err) {}
    var seen = [];
    targets.forEach(function (win) {
      if (!win || seen.indexOf(win) !== -1) return;
      seen.push(win);
      try {
        win.postMessage(msg, origin);
      } catch (err) {}
    });
  }

  function savedFlashOnScreen() {
    if (document.querySelector(".alert-danger.alert-dismissible")) return false;
    return !!document.querySelector(".alert-success.alert-dismissible");
  }

  if (savedFlashOnScreen() && isLedgerWrite(window.location.href, "POST")) {
    notifyDashboard();
  }

  var origFetch = window.fetch;
  if (typeof origFetch === "function") {
    window.fetch = function (input, init) {
      var method = "GET";
      var url = "";
      if (typeof input === "string") {
        url = input;
      } else if (input && typeof input.url === "string") {
        url = input.url;
        method = input.method || method;
      }
      if (init && init.method) method = init.method;
      var pending = origFetch.apply(this, arguments);
      if (!isLedgerWrite(url, method)) return pending;
      return pending.then(function (res) {
        try {
          if (res && res.ok && typeof res.clone === "function") {
            res
              .clone()
              .json()
              .then(function (data) {
                if (data && data.ok === false) return;
                notifyDashboard();
              })
              .catch(function () {});
          }
        } catch (err) {}
        return res;
      });
    };
  }

  if (window.top === window.self) {
    var timer = null;
    window.addEventListener("message", function (ev) {
      if (ev.origin !== window.location.origin) return;
      var data = ev.data;
      if (!data || data.type !== MESSAGE) return;
      clearTimeout(timer);
      timer = setTimeout(function () {
        if (typeof window.jtcsRefreshDashboard === "function") {
          window.jtcsRefreshDashboard();
        }
      }, 200);
    });
  }
})();
