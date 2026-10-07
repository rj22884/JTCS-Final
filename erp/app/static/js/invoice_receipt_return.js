/* Invoice-triggered Money In-Out return for Miscellaneous, GST, TDS, ITR, and DSC.
   Standalone Money In-Out saves do not carry receipt_origin and keep the old path. */
(function (root, factory) {
  var api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.JtcsInvoiceReceiptReturn = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  var ORIGINS = {
    MISC: ["/activities/miscellaneous", "/activities/misc_new"],
    GST: ["/gst/followup"],
    TDS: ["/tds/followup"],
    ITR: ["/itr/followup"],
    DSC: ["/dsc/followup"],
  };
  var PENDING_KEY = "jtcs.invoiceReceiptReturn";

  function normalizeOrigin(value) {
    var key = String(value || "").trim().toUpperCase();
    return Object.prototype.hasOwnProperty.call(ORIGINS, key) ? key : "";
  }

  function safeReturnPath(origin, raw) {
    var key = normalizeOrigin(origin);
    if (!key) return "";
    var allowed = ORIGINS[key];
    var fallback = allowed[0];
    var value = String(raw || "").trim();
    if (!value || value.charAt(0) !== "/" || value.charAt(1) === "/" || value.indexOf("\\") !== -1) {
      return fallback;
    }
    var url;
    try {
      url = new URL(value, "http://local.test");
    } catch (_err) {
      return fallback;
    }
    if (url.origin !== "http://local.test") return fallback;
    var path = (url.pathname || "/").replace(/\/+$/, "") || "/";
    var matched = allowed.some(function (item) {
      return path.toLowerCase() === item;
    });
    if (!matched) return fallback;
    return path + url.search;
  }

  function appendModuleReturn(params, origin, returnTo) {
    var key = normalizeOrigin(origin);
    if (!key || !params || typeof params.set !== "function") return false;
    params.set("receipt_origin", key);
    params.set("return_to", safeReturnPath(key, returnTo));
    return true;
  }

  function receiptLaunchFromSearch(search) {
    var raw = String(search || "");
    if (raw.charAt(0) === "?") raw = raw.slice(1);
    var params = new URLSearchParams(raw);
    if (params.get("receipt") !== "1") return null;
    var customerId = (params.get("customer_id") || "").trim();
    if (!customerId) return null;
    var origin = normalizeOrigin(params.get("receipt_origin"));
    return {
      customerId: customerId,
      customerName: (params.get("customer_name") || "").replace(/\s+/g, " ").trim(),
      invoiceId: (params.get("invoice_id") || "").trim(),
      amount: (params.get("amount") || "").trim(),
      origin: origin,
      returnTo: origin ? safeReturnPath(origin, params.get("return_to") || "") : "",
    };
  }

  function planSaveSuccess(launch) {
    var origin = normalizeOrigin(launch && launch.origin);
    if (!origin) {
      return {
        listed: false,
        hideReceipt: true,
        reloadGrid: true,
        closeInvoiceWindow: false,
        openNewForm: false,
        disarmRelaunch: false,
        keepFormOpen: false,
        origin: "",
        returnTo: "",
      };
    }
    return {
      listed: true,
      hideReceipt: true,
      reloadGrid: false,
      closeInvoiceWindow: true,
      openNewForm: false,
      disarmRelaunch: true,
      keepFormOpen: false,
      origin: origin,
      returnTo: safeReturnPath(origin, launch.returnTo),
    };
  }

  function planSaveFailure(launch) {
    return {
      listed: !!normalizeOrigin(launch && launch.origin),
      hideReceipt: false,
      reloadGrid: false,
      closeInvoiceWindow: false,
      openNewForm: false,
      disarmRelaunch: false,
      keepFormOpen: true,
      origin: normalizeOrigin(launch && launch.origin),
      returnTo: "",
    };
  }

  function disarmSearch() {
    return "receipt_return=1";
  }

  function pendingRecord(plan, now) {
    if (!plan || !plan.listed) return null;
    return {
      origin: plan.origin,
      returnTo: plan.returnTo,
      expires: (now || Date.now()) + 20000,
    };
  }

  function readPendingReturn(raw, search, now) {
    var query = String(search || "");
    if (query.charAt(0) === "?") query = query.slice(1);
    var params = new URLSearchParams(query);
    if (params.get("receipt_return") !== "1") return null;
    if (!raw) return null;
    var data;
    try {
      data = JSON.parse(raw);
    } catch (_err) {
      return null;
    }
    var origin = normalizeOrigin(data && data.origin);
    if (!origin) return null;
    if (data.expires && now && Number(data.expires) < now) return null;
    return {
      origin: origin,
      returnTo: safeReturnPath(origin, data.returnTo),
    };
  }

  function shouldOpenReceiptOnLoad(search) {
    var query = String(search || "");
    if (query.charAt(0) === "?") query = query.slice(1);
    var params = new URLSearchParams(query);
    if (params.get("receipt_return") === "1") return false;
    var launch = receiptLaunchFromSearch(search);
    return !!(launch && launch.customerId);
  }

  function performListedReturn(launch, host) {
    var plan = planSaveSuccess(launch || {});
    if (!plan.listed) return plan;
    if (!host) return plan;
    if (typeof host.hideReceiptModal === "function") host.hideReceiptModal();
    if (typeof host.disarmRelaunch === "function") host.disarmRelaunch(plan);
    if (typeof host.hasInvoicePageWindow === "function" && host.hasInvoicePageWindow()) {
      if (typeof host.finishInvoiceWindow === "function") host.finishInvoiceWindow(plan.returnTo);
      return plan;
    }
    if (typeof host.isEmbeddedInvoice === "function" && host.isEmbeddedInvoice()) {
      if (typeof host.notifyOriginClose === "function") host.notifyOriginClose(plan);
      return plan;
    }
    if (typeof host.navigateToOrigin === "function") host.navigateToOrigin(plan.returnTo);
    return plan;
  }

  return {
    PENDING_KEY: PENDING_KEY,
    ORIGINS: ORIGINS,
    normalizeOrigin: normalizeOrigin,
    safeReturnPath: safeReturnPath,
    appendModuleReturn: appendModuleReturn,
    receiptLaunchFromSearch: receiptLaunchFromSearch,
    planSaveSuccess: planSaveSuccess,
    planSaveFailure: planSaveFailure,
    disarmSearch: disarmSearch,
    pendingRecord: pendingRecord,
    readPendingReturn: readPendingReturn,
    shouldOpenReceiptOnLoad: shouldOpenReceiptOnLoad,
    performListedReturn: performListedReturn,
  };
});
