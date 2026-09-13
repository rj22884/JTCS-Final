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

  function setMaximized(dialog, modal, maximized) {
    dialog.classList.toggle("jtcs-win-maximized", maximized);
    if (modal) modal.classList.toggle("jtcs-win-maximized", maximized);
    dialog.classList.toggle("jtcs-win-dragged", false);
    dialog.style.left = "";
    dialog.style.top = "";
    dialog.style.margin = "";
    dialog.style.transform = "";
    var btn = dialog.querySelector(".jtcs-win-max-btn");
    if (btn) {
      var icon = btn.querySelector("i");
      btn.title = maximized ? "Restore" : "Maximize";
      btn.setAttribute("aria-label", maximized ? "Restore" : "Maximize");
      if (icon) {
        icon.className = maximized ? "bi bi-fullscreen-exit" : "bi bi-arrows-fullscreen";
      }
    }
  }

  function enableDrag(header, dialog, modal) {
    if (!header || header.dataset.jtcsWinDrag === "1") return;
    header.dataset.jtcsWinDrag = "1";
    header.classList.add("jtcs-win-drag");
    header.addEventListener("mousedown", function (ev) {
      if (ev.button !== 0) return;
      if (isInteractive(ev.target)) return;
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
    if (!isFull && !hasExistingMaximize(header)) {
      var maxBtn = document.createElement("button");
      maxBtn.type = "button";
      maxBtn.className = "btn btn-outline-secondary btn-sm jtcs-win-max-btn";
      maxBtn.title = "Maximize";
      maxBtn.setAttribute("aria-label", "Maximize");
      maxBtn.innerHTML = '<i class="bi bi-arrows-fullscreen"></i>';
      maxBtn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        setMaximized(dialog, modal, !dialog.classList.contains("jtcs-win-maximized"));
      });
      host.appendChild(maxBtn);
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
      setMaximized(dialog, modal, false);
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
    if (!header.querySelector(".jtcs-win-max-btn")) {
      var maxBtn = document.createElement("button");
      maxBtn.type = "button";
      maxBtn.className = "btn btn-outline-secondary btn-sm jtcs-win-max-btn";
      maxBtn.title = "Maximize";
      maxBtn.setAttribute("aria-label", "Maximize");
      maxBtn.innerHTML = '<i class="bi bi-arrows-fullscreen"></i>';
      maxBtn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        var next = !dialog.classList.contains("jtcs-win-maximized");
        setMaximized(dialog, overlay, next);
        overlay.classList.toggle("jtcs-win-maximized", next);
      });
      host.appendChild(maxBtn);
    }
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
