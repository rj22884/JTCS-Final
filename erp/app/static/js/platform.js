(function (global) {
  "use strict";

  var STORAGE_KEY = "JTCS_RUNTIME";

  function detect() {
    var ua = navigator.userAgent || "";
    var touch = (navigator.maxTouchPoints || 0) > 0 || "ontouchstart" in window;
    var os = "other";
    if (/Windows/i.test(ua)) os = "windows";
    else if (/Android/i.test(ua)) os = "android";
    else if (/iPhone|iPod/i.test(ua)) os = "ios";
    else if (/iPad/i.test(ua) || (/Macintosh|Mac OS/i.test(ua) && (navigator.maxTouchPoints || 0) > 1)) os = "ios";
    else if (/Mac OS|Macintosh/i.test(ua)) os = "macos";
    else if (/CrOS/i.test(ua)) os = "chromeos";
    else if (/Linux/i.test(ua)) os = "linux";

    var width = window.innerWidth || 1200;
    var height = window.innerHeight || 800;
    var minSide = Math.min(width, height);
    var form = "desktop";
    if (width < 576) form = "phone";
    else if (width < 992) form = "tablet";
    if (os === "android" || os === "ios") {
      form = minSide >= 600 ? "tablet" : "phone";
    }

    var osNames = {
      windows: "Windows",
      macos: "macOS",
      linux: "Linux",
      chromeos: "ChromeOS",
      android: "Android",
      ios: "iOS",
      other: "Other",
    };
    var label;
    if (os === "android") label = form === "tablet" ? "Android Tablet" : "Android Phone";
    else if (os === "ios") label = form === "tablet" ? "iPad" : "iPhone";
    else if (form === "phone") label = (osNames[os] || "Other") + " (phone layout)";
    else if (form === "tablet") label = (osNames[os] || "Other") + " (tablet layout)";
    else label = (osNames[os] || "Other") + " Desktop";

    return {
      os: os,
      form: form,
      label: label,
      touch: !!touch,
      width: width,
      height: height,
      standalone:
        window.matchMedia &&
        (window.matchMedia("(display-mode: standalone)").matches ||
          window.navigator.standalone === true),
    };
  }

  function apply(info) {
    var html = document.documentElement;
    var body = document.body;
    ["jtcs-os-windows", "jtcs-os-macos", "jtcs-os-linux", "jtcs-os-chromeos", "jtcs-os-android", "jtcs-os-ios", "jtcs-os-other",
      "jtcs-form-desktop", "jtcs-form-tablet", "jtcs-form-phone"].forEach(function (cls) {
      html.classList.remove(cls);
      if (body) body.classList.remove(cls);
    });
    html.classList.add("jtcs-os-" + info.os, "jtcs-form-" + info.form);
    html.setAttribute("data-jtcs-os", info.os);
    html.setAttribute("data-jtcs-form", info.form);
    if (body) {
      body.classList.add("jtcs-os-" + info.os, "jtcs-form-" + info.form);
      if (info.touch) body.classList.add("jtcs-touch");
    }
    var chip = document.getElementById("jtcsRuntimeDevice");
    if (chip) chip.textContent = info.label;
    var ver = document.getElementById("jtcsRuntimeVersion");
    if (ver && info.version) ver.textContent = info.version;
  }

  function readStored() {
    try {
      var raw = sessionStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (err) {
      return null;
    }
  }

  function persist(info) {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(info));
    } catch (err) {
      /* ignore quota */
    }
  }

  function fetchVersion(api, fallback, build) {
    if (!api) {
      return Promise.resolve({ version: fallback || "", build_number: build || 1, source: "page" });
    }
    return fetch(api, { headers: { Accept: "application/json" }, credentials: "same-origin" })
      .then(function (res) {
        if (!res.ok) throw new Error("runtime " + res.status);
        return res.json();
      })
      .then(function (data) {
        if (!data || data.ok === false) throw new Error("runtime failed");
        return {
          version: data.version || fallback || "",
          build_number: data.build_number || build || 1,
          source: data.source || "api",
          app_name: data.app_name || "JTCS ERP",
        };
      });
  }

  function boot(options) {
    var opts = options || {};
    var device = detect();
    apply(device);
    return fetchVersion(opts.api, opts.fallbackVersion, opts.build).then(function (ver) {
      var info = Object.assign({}, device, ver, { detected_at: Date.now() });
      persist(info);
      apply(info);
      return info;
    });
  }

  function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    var host = location.hostname;
    var secure = location.protocol === "https:" || host === "localhost" || host === "127.0.0.1";
    if (!secure) return;
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {
      /* ignore */
    });
  }

  function initPage() {
    var device = detect();
    var stored = readStored();
    var info = Object.assign({}, device, stored || {});
    apply(info);
    registerServiceWorker();
    window.addEventListener("resize", function () {
      apply(Object.assign({}, info, detect()));
    });
  }

  global.JTCSPlatform = {
    detect: detect,
    apply: apply,
    boot: boot,
    initPage: initPage,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPage);
  } else {
    initPage();
  }
})(window);
