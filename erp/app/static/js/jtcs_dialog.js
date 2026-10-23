/**
 * Global stylish centered dialogs (replaces native alert / confirm / prompt).
 *
 *   JTCSDialog.alert(message, type?)
 *   JTCSDialog.confirm(message, options?)  → Promise<boolean>
 *   JTCSDialog.prompt(message, defaultValue?, options?)  → Promise<string|null>
 *   JTCSDialog.show({ message, type, title? })
 *
 * window.alert is overridden. window.confirm cannot be overridden safely
 * (native confirm is synchronous) — callers must use JTCSDialog.confirm.
 */
(function () {
  "use strict";

  var nativeAlert = window.alert.bind(window);
  var nativeConfirm = window.confirm.bind(window);
  var nativePrompt = window.prompt.bind(window);
  var queue = [];
  var busy = false;
  var current = null;
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
    if (els && els.overlay && els.okBtn && els.cancelBtn) return els;

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
        '    <input type="text" class="form-control form-control-sm jtcs-dialog-prompt" id="jtcsDialogPrompt" hidden>' +
        "  </div>" +
        '  <div class="jtcs-dialog-footer">' +
        '    <button type="button" class="btn btn-sm btn-outline-secondary jtcs-dialog-cancel" id="jtcsDialogCancelBtn" hidden>Cancel</button>' +
        '    <button type="button" class="btn btn-sm jtcs-dialog-ok" id="jtcsDialogOkBtn">OK</button>' +
        "  </div>" +
        "</div>";
      document.body.appendChild(overlay);
    } else {
      var body = overlay.querySelector(".jtcs-dialog-body");
      var footer = overlay.querySelector(".jtcs-dialog-footer");
      if (body && !overlay.querySelector("#jtcsDialogPrompt")) {
        var input = document.createElement("input");
        input.type = "text";
        input.className = "form-control form-control-sm jtcs-dialog-prompt";
        input.id = "jtcsDialogPrompt";
        input.hidden = true;
        body.appendChild(input);
      }
      if (footer && !overlay.querySelector("#jtcsDialogCancelBtn")) {
        var cancel = document.createElement("button");
        cancel.type = "button";
        cancel.className = "btn btn-sm btn-outline-secondary jtcs-dialog-cancel";
        cancel.id = "jtcsDialogCancelBtn";
        cancel.hidden = true;
        cancel.textContent = "Cancel";
        var okExisting = overlay.querySelector("#jtcsDialogOkBtn");
        if (okExisting) footer.insertBefore(cancel, okExisting);
        else footer.appendChild(cancel);
      }
    }

    els = {
      overlay: overlay,
      dialog: overlay.querySelector(".jtcs-dialog"),
      accent: overlay.querySelector(".jtcs-dialog-accent"),
      icon: overlay.querySelector("#jtcsDialogIcon"),
      title: overlay.querySelector("#jtcsDialogTitle"),
      message: overlay.querySelector("#jtcsDialogMessage"),
      prompt: overlay.querySelector("#jtcsDialogPrompt"),
      cancelBtn: overlay.querySelector("#jtcsDialogCancelBtn"),
      okBtn: overlay.querySelector("#jtcsDialogOkBtn"),
    };

    if (els.okBtn && !els.okBtn.dataset.jtcsBound) {
      els.okBtn.dataset.jtcsBound = "1";
      els.okBtn.addEventListener("click", function () {
        acceptCurrent();
      });
    }
    if (els.cancelBtn && !els.cancelBtn.dataset.jtcsBound) {
      els.cancelBtn.dataset.jtcsBound = "1";
      els.cancelBtn.addEventListener("click", function () {
        finishCurrent(false);
      });
    }
    if (els.overlay && !els.overlay.dataset.jtcsBound) {
      els.overlay.dataset.jtcsBound = "1";
      els.overlay.addEventListener("click", function (e) {
        if (e.target !== els.overlay) return;
        if (current && current.kind === "alert") finishCurrent(true);
      });
    }
    if (els.prompt && !els.prompt.dataset.jtcsBound) {
      els.prompt.dataset.jtcsBound = "1";
      els.prompt.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          e.preventDefault();
          acceptCurrent();
        }
      });
    }

    return els;
  }

  function inferType(message) {
    var text = String(message || "").toLowerCase();
    if (
      /stop:|cannot be deleted|cannot delete|in use and cannot|still reference|linked to other|linked to existing/.test(
        text
      )
    ) {
      return "error";
    }
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

  function inferConfirmType(message) {
    var text = String(message || "").toLowerCase();
    if (
      /delete|permanently|cannot be undone|remove |overwrite|replace |restore|deactivate|inactive|clear /.test(
        text
      )
    ) {
      return "warning";
    }
    return "info";
  }

  function normalizeType(type, message, kind) {
    var key = String(type || "").toLowerCase().trim();
    if (key === "danger") key = "error";
    if (TYPE_META[key]) return key;
    if (kind === "confirm" || kind === "prompt") return inferConfirmType(message);
    return inferType(message);
  }

  function applyType(type) {
    var meta = TYPE_META[type] || TYPE_META.info;
    var node = ensureDom();
    node.dialog.setAttribute("data-type", type);
    node.title.textContent = meta.title;
    if (node.icon) node.icon.innerHTML = '<i class="bi ' + meta.icon + '"></i>';
    if (node.okBtn) node.okBtn.className = "btn btn-sm jtcs-dialog-ok " + meta.btn;
  }

  function hideOverlay() {
    if (!els) return;
    els.overlay.setAttribute("hidden", "");
    els.overlay.classList.remove("is-open");
    document.body.classList.remove("jtcs-dialog-open");
  }

  function finishCurrent(result) {
    if (!busy) return;
    if (keyHandler) {
      document.removeEventListener("keydown", keyHandler, true);
      keyHandler = null;
    }
    var item = current;
    current = null;
    hideOverlay();
    busy = false;
    if (item && typeof item.resolve === "function") {
      var value = result;
      if (item.kind === "prompt") {
        value = result ? String(els.prompt ? els.prompt.value : "") : null;
      } else if (item.kind === "confirm") {
        value = !!result;
      }
      try {
        item.resolve(value);
      } catch (_err) {
        /* ignore resolver errors */
      }
    }
    if (queue.length) {
      var next = queue.shift();
      setTimeout(function () {
        openItem(next);
      }, 40);
    }
  }

  function acceptCurrent() {
    if (current && current.kind === "prompt") {
      finishCurrent(true);
      return;
    }
    finishCurrent(true);
  }

  function openItem(item) {
    if (!document.body) {
      nativeFallback(item);
      return;
    }
    var node = ensureDom();
    var kind = item.kind || "alert";
    var resolved = normalizeType(item.type, item.message, kind);
    var meta = TYPE_META[resolved] || TYPE_META.info;

    current = item;
    busy = true;
    applyType(resolved);

    if (item.okClass && node.okBtn) {
      node.okBtn.className = "btn btn-sm jtcs-dialog-ok " + item.okClass;
    }

    if (kind === "confirm") {
      node.title.textContent = item.title || "Confirm";
      if (node.okBtn) node.okBtn.textContent = item.okLabel || "OK";
      if (node.cancelBtn) {
        node.cancelBtn.textContent = item.cancelLabel || "Cancel";
        node.cancelBtn.hidden = false;
      }
      node.overlay.setAttribute("role", "dialog");
    } else if (kind === "prompt") {
      node.title.textContent = item.title || "Input";
      if (node.okBtn) node.okBtn.textContent = item.okLabel || "OK";
      if (node.cancelBtn) {
        node.cancelBtn.textContent = item.cancelLabel || "Cancel";
        node.cancelBtn.hidden = false;
      }
      node.overlay.setAttribute("role", "dialog");
    } else {
      node.title.textContent = item.title || meta.title;
      if (node.okBtn) node.okBtn.textContent = item.okLabel || "OK";
      if (node.cancelBtn) node.cancelBtn.hidden = true;
      node.overlay.setAttribute("role", "alertdialog");
    }

    node.message.textContent = String(item.message == null ? "" : item.message);
    if (node.prompt) {
      if (kind === "prompt") {
        node.prompt.hidden = false;
        node.prompt.type = item.inputType === "password" ? "password" : "text";
        node.prompt.placeholder = item.placeholder || "";
        node.prompt.value = item.defaultValue == null ? "" : String(item.defaultValue);
      } else {
        node.prompt.hidden = true;
        node.prompt.placeholder = "";
        node.prompt.value = "";
      }
    }

    node.overlay.removeAttribute("hidden");
    void node.overlay.offsetWidth;
    node.overlay.classList.add("is-open");
    document.body.classList.add("jtcs-dialog-open");

    keyHandler = function (e) {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        finishCurrent(kind === "alert");
        return;
      }
      if (e.key === "Enter" && kind !== "prompt") {
        e.preventDefault();
        e.stopPropagation();
        acceptCurrent();
      }
    };
    document.addEventListener("keydown", keyHandler, true);

    setTimeout(function () {
      if (kind === "prompt" && node.prompt) node.prompt.focus();
      else node.okBtn.focus();
    }, 60);
  }

  function nativeFallback(item) {
    var msg = String(item.message == null ? "" : item.message);
    var result;
    if (item.kind === "confirm") {
      result = nativeConfirm(msg);
    } else if (item.kind === "prompt") {
      result = nativePrompt(msg, item.defaultValue == null ? "" : String(item.defaultValue));
    } else {
      nativeAlert(msg);
      result = true;
    }
    if (typeof item.resolve === "function") item.resolve(result);
  }

  function enqueue(item) {
    if (busy) {
      queue.push(item);
      return;
    }
    openItem(item);
  }

  function show(options) {
    options = options || {};
    enqueue({
      kind: "alert",
      message: options.message == null ? "" : options.message,
      type: options.type,
      title: options.title || null,
      okLabel: options.okLabel,
    });
  }

  function alertMessage(message, type, options) {
    options = options || {};
    return new Promise(function (resolve) {
      enqueue({
        kind: "alert",
        message: message == null ? "" : message,
        type: type || options.type,
        title: options.title || null,
        okLabel: options.okLabel || "OK",
        resolve: function () {
          resolve(true);
        },
      });
    });
  }

  function confirmMessage(message, options) {
    options = options || {};
    return new Promise(function (resolve) {
      enqueue({
        kind: "confirm",
        message: message == null ? "" : message,
        type: options.type,
        title: options.title || "Confirm",
        okLabel: options.okLabel || "OK",
        cancelLabel: options.cancelLabel || "Cancel",
        okClass: options.okClass,
        resolve: resolve,
      });
    });
  }

  function promptMessage(message, defaultValue, options) {
    options = options || {};
    return new Promise(function (resolve) {
      enqueue({
        kind: "prompt",
        message: message == null ? "" : message,
        defaultValue: defaultValue,
        type: options.type,
        title: options.title || "Input",
        okLabel: options.okLabel || "OK",
        cancelLabel: options.cancelLabel || "Cancel",
        inputType: options.inputType || "text",
        placeholder: options.placeholder || "",
        resolve: resolve,
      });
    });
  }

  document.addEventListener(
    "submit",
    function (e) {
      var form = e.target;
      if (!(form instanceof HTMLFormElement)) return;
      if (!form.classList.contains("jtcs-confirm-form")) return;
      if (form.dataset.jtcsConfirmOk === "1") {
        delete form.dataset.jtcsConfirmOk;
        return;
      }
      var message = form.getAttribute("data-confirm-message") || "Continue?";
      e.preventDefault();
      e.stopPropagation();
      confirmMessage(message, {
        title: form.getAttribute("data-confirm-title") || "Confirm",
        okLabel: form.getAttribute("data-confirm-ok") || "OK",
        cancelLabel: form.getAttribute("data-confirm-cancel") || "Cancel",
        type: form.getAttribute("data-confirm-type") || undefined,
      }).then(function (ok) {
        if (!ok) return;
        form.dataset.jtcsConfirmOk = "1";
        if (typeof form.requestSubmit === "function") form.requestSubmit();
        else form.submit();
      });
    },
    true
  );

  window.JTCSDialog = {
    show: show,
    alert: alertMessage,
    confirm: confirmMessage,
    prompt: promptMessage,
    inferType: inferType,
  };

  function getErrorText(el) {
    return String(el && (el.innerText || el.textContent) || "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function isVisible(el) {
    if (!el || !document.documentElement.contains(el)) return false;
    if (el.hidden || el.closest("[hidden], .d-none")) return false;
    var style = window.getComputedStyle(el);
    return style.display !== "none" && style.visibility !== "hidden" && el.getClientRects().length > 0;
  }

  function installErrorPopupRouting() {
    if (!document.body || window.__JTCS_ERROR_POPUP_ROUTING__) return;
    window.__JTCS_ERROR_POPUP_ROUTING__ = true;

    var seenMessages = new WeakMap();
    var recentPopups = new Map();
    var selector = ".alert-danger, .invalid-feedback, [role=\"alert\"].text-danger, [id*=\"error\" i], .text-danger";
    var explicitErrorSelector = ".alert-danger, .invalid-feedback, [role=\"alert\"].text-danger, [id*=\"error\" i]";
    var errorMessagePattern = /\b(error|failed|unable|cannot|can't|could not|not found|invalid|required|missing|denied|blocked|unavailable|expired|please select|please enter)\b/i;

    function showErrorPopup(message) {
      var now = Date.now();
      var lastShown = recentPopups.get(message) || 0;
      if (now - lastShown < 700) return;
      recentPopups.forEach(function (shownAt, shownMessage) {
        if (now - shownAt >= 700) recentPopups.delete(shownMessage);
      });
      recentPopups.set(message, now);
      alertMessage(message, "error");
    }

    function showErrorSurface(el) {
      if (!el || !el.matches || !el.matches(selector)) return;
      if (el.parentElement && el.parentElement.closest(selector)) return;
      var message = getErrorText(el);
      if (!el.matches(explicitErrorSelector) && !errorMessagePattern.test(message)) return;
      if (!message || !isVisible(el)) {
        seenMessages.delete(el);
        return;
      }
      if (seenMessages.get(el) === message) return;
      seenMessages.set(el, message);
      showErrorPopup(message);
    }

    function inspect(node) {
      if (!node) return;
      if (node.nodeType === 3) node = node.parentElement;
      if (!node || node.nodeType !== 1) return;
      showErrorSurface(node);
      var parent = node.closest(selector);
      if (parent && parent !== node) showErrorSurface(parent);
      if (node.querySelectorAll) node.querySelectorAll(selector).forEach(showErrorSurface);
    }

    document.querySelectorAll(selector).forEach(showErrorSurface);
    new MutationObserver(function (records) {
      records.forEach(function (record) {
        inspect(record.target);
        record.addedNodes && record.addedNodes.forEach(inspect);
      });
    }).observe(document.documentElement, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["class", "hidden", "style", "aria-hidden"],
    });

    var validationPopupPending = false;
    document.addEventListener("invalid", function (event) {
      var field = event.target;
      if (!field || !field.validationMessage) return;
      event.preventDefault();
      if (validationPopupPending) return;
      validationPopupPending = true;
      showErrorPopup(field.validationMessage);
      Promise.resolve().then(function () {
        validationPopupPending = false;
      });
    }, true);

    window.addEventListener("error", function (event) {
      var message = event.error && event.error.message || event.message;
      if (!message || message === "Script error.") return;
      showErrorPopup(message);
    });

    window.addEventListener("unhandledrejection", function (event) {
      var reason = event.reason;
      var message = reason && reason.message ? reason.message : String(reason || "Unexpected application error.");
      showErrorPopup(message);
    });
  }

  installErrorPopupRouting();

  window.alert = function (message) {
    try {
      alertMessage(message);
    } catch (err) {
      nativeAlert(String(message == null ? "" : message));
    }
  };
})();
