/**
 * Global stylish centered dialogs for alert / message feedback.
 * Overrides window.alert so existing modules keep working unchanged.
 *
 * Optional API:
 *   JTCSDialog.alert(message, type?)  // type: error|warning|invalid|success|info
 *   JTCSDialog.show({ message, type, title? })
 */
(function () {
  "use strict";

  var nativeAlert = window.alert.bind(window);
  var queue = [];
  var busy = false;
  var els = null;
  var keyHandler = null;

  var TYPE_META = {
    error: {
      title: "Error",
      icon: "bi-x-circle-fill",
      btn: "btn-danger",
    },
    danger: {
      title: "Error",
      icon: "bi-x-circle-fill",
      btn: "btn-danger",
    },
    warning: {
      title: "Warning",
      icon: "bi-exclamation-triangle-fill",
      btn: "btn-warning",
    },
    invalid: {
      title: "Invalid",
      icon: "bi-slash-circle-fill",
      btn: "btn-warning",
    },
    success: {
      title: "Success",
      icon: "bi-check-circle-fill",
      btn: "btn-success",
    },
    info: {
      title: "Message",
      icon: "bi-info-circle-fill",
      btn: "btn-primary",
    },
  };

  function ensureDom() {
    if (els && els.overlay) return els;

    var overlay = document.getElementById("jtcsDialogOverlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = "jtcsDialogOverlay";
      overlay.className = "jtcs-dialog-overlay";
      overlay.setAttribute("hidden", "");
      overlay.setAttribute("role", "alertdialog");
      overlay.setAttribute("aria-modal", "true");
      overlay.setAttribute("aria-labelledby", "jtcsDialogTitle");
      overlay.setAttribute("aria-describedby", "jtcsDialogMessage");
      overlay.innerHTML =
        '<div class="jtcs-dialog" role="document">' +
        '  <div class="jtcs-dialog-accent" aria-hidden="true"></div>' +
        '  <div class="jtcs-dialog-header">' +
        '    <span class="jtcs-dialog-icon" id="jtcsDialogIcon" aria-hidden="true"><i class="bi bi-info-circle-fill"></i></span>' +
        '    <h5 class="jtcs-dialog-title" id="jtcsDialogTitle">Message</h5>' +
        "  </div>" +
        '  <div class="jtcs-dialog-body">' +
        '    <p class="jtcs-dialog-message" id="jtcsDialogMessage"></p>' +
        "  </div>" +
        '  <div class="jtcs-dialog-footer">' +
        '    <button type="button" class="btn btn-sm jtcs-dialog-ok" id="jtcsDialogOkBtn">OK</button>' +
        "  </div>" +
        "</div>";
      document.body.appendChild(overlay);
    }

    els = {
      overlay: overlay,
      dialog: overlay.querySelector(".jtcs-dialog"),
      accent: overlay.querySelector(".jtcs-dialog-accent"),
      icon: overlay.querySelector("#jtcsDialogIcon"),
      title: overlay.querySelector("#jtcsDialogTitle"),
      message: overlay.querySelector("#jtcsDialogMessage"),
      okBtn: overlay.querySelector("#jtcsDialogOkBtn"),
    };

    els.okBtn.addEventListener("click", closeCurrent);
    els.overlay.addEventListener("click", function (e) {
      if (e.target === els.overlay) closeCurrent();
    });

    return els;
  }

  function inferType(message) {
    var text = String(message || "").toLowerCase();
    if (
      /duplicate|already exists|conflict|failed|unable|denied|forbidden|not allowed|error|exception/.test(
        text
      )
    ) {
      return "error";
    }
    if (
      /invalid|required|must be|please select|please enter|missing|not found|cannot|can't|blocked/.test(
        text
      )
    ) {
      return "invalid";
    }
    if (/warning|warn|caution|attention/.test(text)) {
      return "warning";
    }
    if (
      /saved|success|deleted|updated|created|copied|exported|imported|done\b/.test(
        text
      )
    ) {
      return "success";
    }
    return "info";
  }

  function normalizeType(type, message) {
    var key = String(type || "").toLowerCase().trim();
    if (key === "danger") key = "error";
    if (TYPE_META[key]) return key;
    return inferType(message);
  }

  function applyType(type) {
    var meta = TYPE_META[type] || TYPE_META.info;
    var node = ensureDom();
    node.dialog.setAttribute("data-type", type);
    node.title.textContent = meta.title;
    node.icon.innerHTML = '<i class="bi ' + meta.icon + '"></i>';
    node.okBtn.className = "btn btn-sm jtcs-dialog-ok " + meta.btn;
  }

  function closeCurrent() {
    if (!els || !busy) return;
    if (keyHandler) {
      document.removeEventListener("keydown", keyHandler, true);
      keyHandler = null;
    }
    els.overlay.setAttribute("hidden", "");
    els.overlay.classList.remove("is-open");
    document.body.classList.remove("jtcs-dialog-open");
    busy = false;
    if (queue.length) {
      var next = queue.shift();
      // Allow paint between stacked messages
      setTimeout(function () {
        openDialog(next.message, next.type, next.title);
      }, 40);
    }
  }

  function openDialog(message, type, title) {
    var node = ensureDom();
    var resolved = normalizeType(type, message);
    var meta = TYPE_META[resolved] || TYPE_META.info;

    applyType(resolved);
    if (title) node.title.textContent = title;
    else node.title.textContent = meta.title;
    node.message.textContent = String(message == null ? "" : message);

    busy = true;
    node.overlay.removeAttribute("hidden");
    // Force reflow so CSS transition runs
    void node.overlay.offsetWidth;
    node.overlay.classList.add("is-open");
    document.body.classList.add("jtcs-dialog-open");

    keyHandler = function (e) {
      if (e.key === "Escape" || e.key === "Enter") {
        e.preventDefault();
        e.stopPropagation();
        closeCurrent();
      }
    };
    document.addEventListener("keydown", keyHandler, true);

    setTimeout(function () {
      node.okBtn.focus();
    }, 60);
  }

  function show(options) {
    options = options || {};
    var message = options.message;
    if (message == null) message = "";
    var type = options.type;
    var title = options.title || null;

    if (!document.body) {
      nativeAlert(String(message));
      return;
    }

    if (busy) {
      queue.push({ message: message, type: type, title: title });
      return;
    }
    openDialog(message, type, title);
  }

  function alertMessage(message, type) {
    show({ message: message, type: type });
  }

  window.JTCSDialog = {
    show: show,
    alert: alertMessage,
    inferType: inferType,
  };

  window.alert = function (message) {
    try {
      alertMessage(message);
    } catch (err) {
      nativeAlert(String(message == null ? "" : message));
    }
  };
})();
