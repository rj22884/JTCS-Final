(function () {
  "use strict";

  if (window.self !== window.top) {
    document.documentElement.classList.add("jtcs-embed");
    if (document.body) document.body.classList.add("jtcs-embed");
    return;
  }

  var zSeed = 20;
  var dragState = null;
  var windowsEl = null;
  var taskbarEl = null;

  function skipUrl(href) {
    if (!href || href === "#" || href.indexOf("javascript:") === 0) return true;
    var path = "";
    try {
      path = new URL(href, window.location.origin).pathname.toLowerCase();
    } catch (err) {
      return true;
    }
    return path.indexOf("/logout") !== -1 || path.indexOf("/login") !== -1 || path.indexOf("/auth/") !== -1;
  }

  function isDesktopUrl(href) {
    try {
      var path = new URL(href, window.location.origin).pathname.replace(/\/+$/, "").toLowerCase();
      return path === "/dashboard" || path === "/admin/dashboard";
    } catch (err) {
      return false;
    }
  }

  function windowKey(href) {
    try {
      var url = new URL(href, window.location.origin);
      return url.pathname.replace(/\/+$/, "") + url.search;
    } catch (err) {
      return href;
    }
  }

  function ensureHosts() {
    windowsEl = document.getElementById("jtcsPageWindows");
    taskbarEl = document.getElementById("jtcsPageTaskbar");
    if (!windowsEl) {
      windowsEl = document.createElement("div");
      windowsEl.id = "jtcsPageWindows";
      windowsEl.className = "jtcs-page-windows";
      document.body.appendChild(windowsEl);
    }
    if (!taskbarEl) {
      taskbarEl = document.createElement("div");
      taskbarEl.id = "jtcsPageTaskbar";
      taskbarEl.className = "jtcs-page-taskbar";
      taskbarEl.hidden = true;
      document.body.appendChild(taskbarEl);
    }
  }

  function allWindows() {
    return windowsEl ? Array.prototype.slice.call(windowsEl.querySelectorAll(".jtcs-page-win")) : [];
  }

  function workArea() {
    var top = 0;
    var header = document.querySelector(".jtcs-app-header");
    var menu = document.querySelector(".jtcs-menu-bar");
    if (header) top = Math.max(top, header.getBoundingClientRect().bottom);
    if (menu) top = Math.max(top, menu.getBoundingClientRect().bottom);
    top = Math.round(top);
    var bottomGap = 0;
    if (taskbarEl && !taskbarEl.hidden) bottomGap = taskbarEl.getBoundingClientRect().height || 42;
    return {
      left: 0,
      top: top,
      width: window.innerWidth,
      height: Math.max(240, window.innerHeight - top - bottomGap),
    };
  }

  function defaultRestoreBox() {
    var area = workArea();
    var width = Math.max(720, Math.round(area.width * 0.86));
    var height = Math.max(480, Math.round(area.height * 0.86));
    width = Math.min(width, Math.max(420, area.width - 24));
    height = Math.min(height, Math.max(240, area.height - 24));
    return {
      left: area.left + Math.round((area.width - width) / 2),
      top: area.top + Math.round((area.height - height) / 2),
      width: width,
      height: height,
    };
  }

  function setBox(win, box) {
    win.style.position = "absolute";
    win.style.left = Math.round(box.left) + "px";
    win.style.top = Math.round(box.top) + "px";
    win.style.width = Math.round(box.width) + "px";
    win.style.height = Math.round(box.height) + "px";
    win.style.right = "auto";
    win.style.bottom = "auto";
  }

  function currentBox(win) {
    return {
      left: parseInt(win.style.left, 10) || 0,
      top: parseInt(win.style.top, 10) || 0,
      width: parseInt(win.style.width, 10) || win.offsetWidth,
      height: parseInt(win.style.height, 10) || win.offsetHeight,
    };
  }

  function applyState(win) {
    var state = win.dataset.state || "max";
    if (state === "min") {
      win.classList.add("is-min");
      win.classList.remove("is-max", "is-restored");
      return;
    }
    win.classList.remove("is-min");
    if (state === "restored") {
      win.classList.add("is-restored");
      win.classList.remove("is-max");
      setBox(win, win._jtcsRestore || defaultRestoreBox());
      return;
    }
    win.classList.add("is-max");
    win.classList.remove("is-restored");
    setBox(win, workArea());
  }

  function relayoutAll() {
    allWindows().forEach(function (win) {
      if ((win.dataset.state || "max") === "max") applyState(win);
    });
  }

  function refreshTaskbar() {
    if (!taskbarEl) return;
    taskbarEl.innerHTML = "";
    var wins = allWindows();
    var anyMin = wins.some(function (win) {
      return win.dataset.state === "min";
    });
    if (!wins.length || !anyMin) {
      taskbarEl.hidden = true;
      relayoutAll();
      if (!wins.length) return;
    } else {
      taskbarEl.hidden = false;
    }
    wins.forEach(function (win) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "jtcs-page-task-btn";
      if (win.classList.contains("is-active") && win.dataset.state !== "min") btn.classList.add("is-active");
      if (win.dataset.state === "min") btn.classList.add("is-min");
      btn.textContent = win.dataset.title || "Window";
      btn.title = win.dataset.title || "Window";
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        if (win.dataset.state === "min") restoreWindow(win);
        else if (win.classList.contains("is-active")) minimizeWindow(win);
        else focusWindow(win);
      });
      taskbarEl.appendChild(btn);
    });
    relayoutAll();
  }

  function focusWindow(win) {
    allWindows().forEach(function (other) {
      other.classList.remove("is-active");
    });
    win.classList.add("is-active");
    win.style.zIndex = String(++zSeed);
    refreshTaskbar();
  }

  function maximizeWindow(win) {
    if (win.dataset.state === "restored") win._jtcsRestore = currentBox(win);
    win.dataset.state = "max";
    applyState(win);
    focusWindow(win);
  }

  function restoreWindow(win) {
    if (!win._jtcsRestore) win._jtcsRestore = defaultRestoreBox();
    win.dataset.state = "restored";
    applyState(win);
    focusWindow(win);
  }

  function minimizeWindow(win) {
    if (win.dataset.state === "restored") win._jtcsRestore = currentBox(win);
    win._jtcsBeforeMin = win.dataset.state === "restored" ? "restored" : "max";
    win.dataset.state = "min";
    applyState(win);
    win.classList.remove("is-active");
    var visible = allWindows().filter(function (item) {
      return item.dataset.state !== "min";
    });
    if (visible.length) focusWindow(visible[visible.length - 1]);
    else refreshTaskbar();
  }

  function closeWindow(win) {
    if (win && win.parentNode) win.parentNode.removeChild(win);
    var remaining = allWindows();
    if (remaining.length) {
      var last = remaining[remaining.length - 1];
      if (last.dataset.state === "min") {
        if (last._jtcsBeforeMin === "max") maximizeWindow(last);
        else restoreWindow(last);
      } else {
        focusWindow(last);
      }
    } else {
      refreshTaskbar();
    }
  }

  function closeAllWindows() {
    allWindows().forEach(function (win) {
      if (win.parentNode) win.parentNode.removeChild(win);
    });
    refreshTaskbar();
  }

  function goBack(win) {
    var frame = win.querySelector("iframe");
    try {
      if (frame && frame.contentWindow && frame.contentWindow.history) {
        frame.contentWindow.history.back();
        return;
      }
    } catch (err) {}
    closeWindow(win);
  }

  function bindChrome(win, selector, handler) {
    var btn = win.querySelector(selector);
    if (!btn) return;
    btn.addEventListener("mousedown", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
    });
    btn.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      handler(win);
    });
  }

  function enableDrag(win) {
    var bar = win.querySelector(".jtcs-page-win-bar");
    if (!bar || bar.dataset.dragReady === "1") return;
    bar.dataset.dragReady = "1";
    bar.addEventListener("mousedown", function (ev) {
      if (ev.button !== 0) return;
      if (ev.target.closest("button")) return;
      focusWindow(win);
      if (win.dataset.state !== "restored") return;
      var box = currentBox(win);
      dragState = {
        win: win,
        startX: ev.clientX,
        startY: ev.clientY,
        origLeft: box.left,
        origTop: box.top,
      };
      ev.preventDefault();
    });
    bar.addEventListener("dblclick", function (ev) {
      if (ev.target.closest("button")) return;
      ev.preventDefault();
      if (win.dataset.state === "max") restoreWindow(win);
      else maximizeWindow(win);
    });
  }

  function findWindow(key) {
    return (
      allWindows().filter(function (win) {
        return win.dataset.key === key;
      })[0] || null
    );
  }

  function openPageWindow(href, title) {
    ensureHosts();
    var key = windowKey(href);
    var existing = findWindow(key);
    if (existing) {
      if (existing._jtcsBeforeMin === "restored") restoreWindow(existing);
      else maximizeWindow(existing);
      return existing;
    }

    var win = document.createElement("div");
    win.className = "jtcs-page-win is-max is-active";
    win.dataset.key = key;
    win.dataset.title = title || "Window";
    win.dataset.state = "max";
    win._jtcsRestore = defaultRestoreBox();

    win.innerHTML =
      '<div class="jtcs-page-win-bar">' +
      '<button type="button" class="jtcs-page-win-back" title="Back" aria-label="Back"><i class="bi bi-arrow-left"></i></button>' +
      '<span class="jtcs-page-win-title"></span>' +
      '<div class="jtcs-page-win-tools">' +
      '<button type="button" class="jtcs-page-win-min" title="Minimize" aria-label="Minimize"><i class="bi bi-dash-lg"></i></button>' +
      '<button type="button" class="jtcs-page-win-restore" title="Restore" aria-label="Restore"><i class="bi bi-copy"></i></button>' +
      '<button type="button" class="jtcs-page-win-max" title="Maximize" aria-label="Maximize"><i class="bi bi-square"></i></button>' +
      '<button type="button" class="jtcs-page-win-close" title="Close" aria-label="Close"><i class="bi bi-x-lg"></i></button>' +
      "</div></div>" +
      '<iframe class="jtcs-page-win-frame" title=""></iframe>';

    win.querySelector(".jtcs-page-win-title").textContent = title || "Window";
    var frame = win.querySelector("iframe");
    frame.title = title || "Window";
    frame.setAttribute("allow", "clipboard-read; clipboard-write");
    frame.addEventListener("load", function () {
      try {
        var doc = frame.contentDocument;
        if (doc && doc.documentElement) doc.documentElement.classList.add("jtcs-embed");
        if (doc && doc.body) doc.body.classList.add("jtcs-embed");
      } catch (err) {}
    });
    frame.src = href;

    bindChrome(win, ".jtcs-page-win-back", goBack);
    bindChrome(win, ".jtcs-page-win-min", minimizeWindow);
    bindChrome(win, ".jtcs-page-win-restore", restoreWindow);
    bindChrome(win, ".jtcs-page-win-max", maximizeWindow);
    bindChrome(win, ".jtcs-page-win-close", closeWindow);

    win.addEventListener("mousedown", function () {
      focusWindow(win);
    });

    enableDrag(win);
    windowsEl.appendChild(win);
    applyState(win);
    focusWindow(win);
    return win;
  }

  document.addEventListener("mousemove", function (ev) {
    if (!dragState) return;
    var area = workArea();
    var left = dragState.origLeft + (ev.clientX - dragState.startX);
    var top = dragState.origTop + (ev.clientY - dragState.startY);
    var win = dragState.win;
    var width = parseInt(win.style.width, 10) || 720;
    var height = parseInt(win.style.height, 10) || 480;
    left = Math.min(Math.max(area.left - width + 80, left), area.left + area.width - 80);
    top = Math.min(Math.max(area.top, top), area.top + area.height - 48);
    win.style.left = Math.round(left) + "px";
    win.style.top = Math.round(top) + "px";
  });

  document.addEventListener("mouseup", function () {
    if (dragState && dragState.win && dragState.win.dataset.state === "restored") {
      dragState.win._jtcsRestore = currentBox(dragState.win);
    }
    dragState = null;
  });

  window.addEventListener("resize", function () {
    relayoutAll();
  });

  document.addEventListener(
    "click",
    function (ev) {
      if (ev.defaultPrevented) return;
      if (ev.button !== 0) return;
      if (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.altKey) return;
      var link = ev.target.closest("a.jtcs-menu-link, a.jtcs-top-link");
      if (!link) return;
      var href = link.getAttribute("href") || "";
      if (skipUrl(href)) return;
      if (link.classList.contains("disabled") || link.getAttribute("aria-disabled") === "true") return;

      ev.preventDefault();
      ev.stopPropagation();

      var title = (link.textContent || "").replace(/\s+/g, " ").trim() || document.title;
      if (isDesktopUrl(href)) {
        closeAllWindows();
        var dest = link.href;
        var here = window.location.pathname.replace(/\/+$/, "").toLowerCase();
        var there = "";
        try {
          there = new URL(dest, window.location.origin).pathname.replace(/\/+$/, "").toLowerCase();
        } catch (err) {
          there = "";
        }
        if (here !== there) window.location.href = dest;
        return;
      }

      openPageWindow(link.href, title);
      document.querySelectorAll(".jtcs-top-item.open").forEach(function (item) {
        item.classList.remove("open");
        var btn = item.querySelector(".jtcs-top-link");
        if (btn) btn.setAttribute("aria-expanded", "false");
      });
      var topMenu = document.getElementById("jtcsTopMenu");
      if (topMenu) topMenu.classList.remove("open");
    },
    true
  );

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ensureHosts);
  } else {
    ensureHosts();
  }
})();
