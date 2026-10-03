/**
 * JTCS window chrome for every Bootstrap modal and JTCS dialog:
 * drag, maximize/restore, and close.
 */
(function () {
  "use strict";

  var dragState = null;

  function isInteractive(el) {
    if (!el || !el.closest) return false;
    return !!el.closest(
      "button, a, input, select, textarea, label, .dropdown-menu, .btn-close, .jtcs-win-tools"
    );
  }

  function hasExistingMaximize(header) {
    if (!header) return false;
    if (header.querySelector(".jtcs-win-max-btn")) return true;
    if (header.querySelector("[id$='MaximizeBtn'], [id$='maximizeBtn']")) return true;
    var icons = header.querySelectorAll("i.bi-arrows-fullscreen, i.bi-fullscreen, i.bi-fullscreen-exit");
    return icons.length > 0;
  }

  function hasClose(header, root) {
    if (header && header.querySelector(".btn-close, [data-bs-dismiss='modal']")) return true;
    if (root && root.querySelector(".modal-footer [data-bs-dismiss='modal']")) return true;
    return false;
  }

  function toolsHost(header) {
    var existing = header.querySelector(".jtcs-win-tools");
    if (existing) return existing;
    var auto = header.querySelector(":scope > .ms-auto, :scope > .d-flex.ms-auto");
    if (auto) {
      auto.classList.add("jtcs-win-tools-host");
      return auto;
    }
    var host = document.createElement("div");
    host.className = "jtcs-win-tools d-flex align-items-center gap-1 ms-auto";
    header.appendChild(host);
    return host;
  }

  function isMaximizedLook(dialog, modal) {
    if (!dialog) return false;
    if (dialog.classList.contains("jtcs-win-maximized")) return true;
    if (dialog.classList.contains("ledger-modal-maximized")) return true;
    if (dialog.classList.contains("modal-fullscreen")) return true;
    if (modal && modal.classList.contains("jtcs-win-maximized")) return true;
    if (modal && modal.classList.contains("dash-modal-maximized")) return true;
    if (modal && modal.classList.contains("obc-modal-maximized")) return true;
    return false;
  }

  function setWindowState(dialog, modal, state) {
    if (!dialog) return;
    dialog.dataset.jtcsWinState = state;
    dialog.classList.remove("jtcs-win-maximized", "jtcs-win-minimized", "jtcs-win-dragged");
    if (modal) modal.classList.remove("jtcs-win-maximized", "jtcs-win-minimized");
    dialog.style.left = "";
    dialog.style.top = "";
    dialog.style.width = "";
    dialog.style.height = "";
    dialog.style.margin = "";
    dialog.style.transform = "";
    dialog.style.maxWidth = "";
    dialog.style.bottom = "";

    if (state === "max") {
      dialog.classList.add("jtcs-win-maximized");
      if (modal) modal.classList.add("jtcs-win-maximized");
      dialog.style.position = "fixed";
      dialog.style.left = "8px";
      dialog.style.top = "8px";
      dialog.style.width = Math.max(320, window.innerWidth - 16) + "px";
      dialog.style.height = Math.max(240, window.innerHeight - 16) + "px";
      dialog.style.margin = "0";
      dialog.style.maxWidth = "none";
      dialog.style.transform = "none";
    } else if (state === "min") {
      dialog.classList.add("jtcs-win-minimized");
      if (modal) modal.classList.add("jtcs-win-minimized");
      dialog.style.position = "fixed";
      dialog.style.left = "12px";
      dialog.style.top = "auto";
      dialog.style.bottom = "12px";
      dialog.style.width = "300px";
      dialog.style.height = "46px";
      dialog.style.margin = "0";
      dialog.style.maxWidth = "none";
      dialog.style.transform = "none";
    }

    var maxBtn = dialog.querySelector(".jtcs-win-max-btn");
    if (maxBtn) {
      var icon = maxBtn.querySelector("i");
      maxBtn.title = "Maximize";
      maxBtn.setAttribute("aria-label", "Maximize");
      if (icon) icon.className = "bi bi-arrows-fullscreen";
    }
  }

  function setMaximized(dialog, modal, maximized) {
    setWindowState(dialog, modal, maximized ? "max" : "restored");
  }

  function enableDrag(header, dialog, modal) {
    if (!header || header.dataset.jtcsWinDrag === "1") return;
    header.dataset.jtcsWinDrag = "1";
    header.classList.add("jtcs-win-drag");
    header.addEventListener("mousedown", function (ev) {
      if (ev.button !== 0) return;
      if (isInteractive(ev.target)) return;
      if ((dialog.dataset.jtcsWinState || "") === "min") return;
      if (isMaximizedLook(dialog, modal)) return;
      var rect = dialog.getBoundingClientRect();
      dialog.classList.add("jtcs-win-dragged");
      dialog.style.margin = "0";
      dialog.style.transform = "none";
      dialog.style.left = rect.left + "px";
      dialog.style.top = rect.top + "px";
      dragState = {
        dialog: dialog,
        startX: ev.clientX,
        startY: ev.clientY,
        origLeft: rect.left,
        origTop: rect.top,
      };
      ev.preventDefault();
    });
  }

  document.addEventListener("mousemove", function (ev) {
    if (!dragState) return;
    var left = dragState.origLeft + (ev.clientX - dragState.startX);
    var top = dragState.origTop + (ev.clientY - dragState.startY);
    var maxLeft = Math.max(8, window.innerWidth - 80);
    var maxTop = Math.max(8, window.innerHeight - 48);
    left = Math.min(Math.max(-40, left), maxLeft);
    top = Math.min(Math.max(0, top), maxTop);
    dragState.dialog.style.left = left + "px";
    dragState.dialog.style.top = top + "px";
  });

  document.addEventListener("mouseup", function () {
    dragState = null;
  });

  function ensureModalHeader(modal) {
    var header = modal.querySelector(".modal-header");
    if (header) return header;
    var content = modal.querySelector(".modal-content");
    if (!content) return null;
    header = document.createElement("div");
    header.className = "modal-header py-2 jtcs-win-injected-header";
    var title = document.createElement("h5");
    title.className = "modal-title";
    title.textContent = modal.getAttribute("aria-label") || "Window";
    header.appendChild(title);
    content.insertBefore(header, content.firstChild);
    return header;
  }

  function enhanceBootstrapModal(modal) {
    if (!modal || modal.dataset.jtcsWin === "1") return;
    var dialog = modal.querySelector(".modal-dialog");
    var header = ensureModalHeader(modal);
    if (!dialog || !header) return;
    modal.dataset.jtcsWin = "1";
    dialog.classList.add("jtcs-win-dialog");
    enableDrag(header, dialog, modal);

    var host = toolsHost(header);
    var isFull = dialog.classList.contains("modal-fullscreen");
    function addChromeBtn(cls, title, icon, onClick) {
      if (header.querySelector("." + cls)) return;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-outline-secondary btn-sm " + cls;
      btn.title = title;
      btn.setAttribute("aria-label", title);
      btn.innerHTML = '<i class="bi ' + icon + '"></i>';
      btn.addEventListener("mousedown", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
      });
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        onClick();
      });
      host.appendChild(btn);
    }
    if (!isFull) {
      addChromeBtn("jtcs-win-min-btn", "Minimize", "bi-dash-lg", function () {
        setWindowState(dialog, modal, "min");
      });
      addChromeBtn("jtcs-win-restore-btn", "Restore", "bi-copy", function () {
        setWindowState(dialog, modal, "restored");
      });
      if (!hasExistingMaximize(header)) {
        addChromeBtn("jtcs-win-max-btn", "Maximize", "bi-arrows-fullscreen", function () {
          setWindowState(dialog, modal, "max");
        });
      }
    }
    if (!hasClose(header, modal)) {
      var closeBtn = document.createElement("button");
      closeBtn.type = "button";
      closeBtn.className = "btn-close";
      closeBtn.setAttribute("data-bs-dismiss", "modal");
      closeBtn.setAttribute("aria-label", "Close");
      host.appendChild(closeBtn);
    }

    modal.addEventListener("hidden.bs.modal", function () {
      setWindowState(dialog, modal, "restored");
    });
  }

  function enhanceJtcsDialog() {
    var overlay = document.getElementById("jtcsDialogOverlay");
    if (!overlay || overlay.dataset.jtcsWin === "1") return;
    var dialog = overlay.querySelector(".jtcs-dialog");
    var header = overlay.querySelector(".jtcs-dialog-header");
    if (!dialog || !header) return;
    overlay.dataset.jtcsWin = "1";
    enableDrag(header, dialog, overlay);

    var host = toolsHost(header);
    function addDlgBtn(cls, title, icon, onClick) {
      if (header.querySelector("." + cls)) return;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-outline-secondary btn-sm " + cls;
      btn.title = title;
      btn.setAttribute("aria-label", title);
      btn.innerHTML = '<i class="bi ' + icon + '"></i>';
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        onClick();
      });
      host.appendChild(btn);
    }
    addDlgBtn("jtcs-win-min-btn", "Minimize", "bi-dash-lg", function () {
      setWindowState(dialog, overlay, "min");
    });
    addDlgBtn("jtcs-win-restore-btn", "Restore", "bi-copy", function () {
      setWindowState(dialog, overlay, "restored");
    });
    addDlgBtn("jtcs-win-max-btn", "Maximize", "bi-arrows-fullscreen", function () {
      setWindowState(dialog, overlay, "max");
      overlay.classList.add("jtcs-win-maximized");
    });
    if (!header.querySelector(".jtcs-win-close-btn")) {
      var closeBtn = document.createElement("button");
      closeBtn.type = "button";
      closeBtn.className = "btn-close jtcs-win-close-btn";
      closeBtn.setAttribute("aria-label", "Close");
      closeBtn.addEventListener("click", function (ev) {
        ev.preventDefault();
        var cancel = document.getElementById("jtcsDialogCancelBtn");
        var ok = document.getElementById("jtcsDialogOkBtn");
        if (cancel && !cancel.hidden) cancel.click();
        else if (ok) ok.click();
      });
      host.appendChild(closeBtn);
    }
  }

  function scan() {
    document.querySelectorAll(".modal").forEach(enhanceBootstrapModal);
    enhanceJtcsDialog();
  }

  document.addEventListener("show.bs.modal", function (ev) {
    if (ev && ev.target) enhanceBootstrapModal(ev.target);
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scan);
  } else {
    scan();
  }

  var obs = new MutationObserver(function (records) {
    for (var i = 0; i < records.length; i++) {
      var nodes = records[i].addedNodes;
      for (var j = 0; j < nodes.length; j++) {
        var n = nodes[j];
        if (!n || n.nodeType !== 1) continue;
        if (n.classList && n.classList.contains("modal")) enhanceBootstrapModal(n);
        if (n.id === "jtcsDialogOverlay" || (n.querySelector && n.querySelector("#jtcsDialogOverlay"))) {
          enhanceJtcsDialog();
        }
        if (n.querySelectorAll) n.querySelectorAll(".modal").forEach(enhanceBootstrapModal);
      }
    }
  });
  obs.observe(document.documentElement, { childList: true, subtree: true });
})();
