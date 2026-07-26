/**
 * Global delete re-auth: User ID (prefilled) + Password modal.
 * Usage:
 *   const creds = await JTCSDeleteConfirm.ask({ message: "Delete this record?" });
 *   if (!creds) return; // cancelled
 *   // send creds.user_id + creds.password with the delete request
 */
(function () {
  "use strict";

  function byId(id) {
    return document.getElementById(id);
  }

  var els = {
    modal: byId("jtcsDeleteConfirmModal"),
    form: byId("jtcsDeleteConfirmForm"),
    message: byId("jtcsDeleteConfirmMessage"),
    userId: byId("jtcsDeleteConfirmUserId"),
    password: byId("jtcsDeleteConfirmPassword"),
    error: byId("jtcsDeleteConfirmError"),
    confirmBtn: byId("jtcsDeleteConfirmBtn"),
    cancelBtn: byId("jtcsDeleteConfirmCancelBtn"),
  };

  var modalInstance = null;
  var pending = null;

  function getModal() {
    if (!els.modal || !window.bootstrap) return null;
    if (!modalInstance) {
      modalInstance = bootstrap.Modal.getOrCreateInstance(els.modal);
    }
    return modalInstance;
  }

  function setError(text) {
    if (!els.error) return;
    els.error.textContent = text || "";
    els.error.classList.toggle("d-none", !text);
  }

  function resolvePending(value) {
    if (!pending) return;
    var resolver = pending;
    pending = null;
    resolver(value);
  }

  function ask(options) {
    options = options || {};
    var message =
      options.message ||
      "This will delete the selected record. Enter your password to confirm.";

    if (!els.modal) {
      var userId = window.prompt(
        "User ID:",
        window.JTCS_CURRENT_LOGIN_ID || ""
      );
      if (userId == null) return Promise.resolve(null);
      var password = window.prompt("Password:");
      if (password == null) return Promise.resolve(null);
      return Promise.resolve({
        user_id: String(userId || "").trim(),
        password: String(password || ""),
      });
    }

    return new Promise(function (resolve) {
      if (pending) {
        resolvePending(null);
      }
      pending = resolve;

      if (els.message) els.message.textContent = message;
      if (els.userId) {
        els.userId.value = window.JTCS_CURRENT_LOGIN_ID || "";
        els.userId.readOnly = true;
      }
      if (els.password) els.password.value = "";
      setError("");
      if (els.confirmBtn) els.confirmBtn.disabled = false;

      var modal = getModal();
      if (modal) {
        modal.show();
        setTimeout(function () {
          els.password?.focus();
        }, 200);
      } else {
        resolvePending(null);
      }
    });
  }

  function submitConfirm() {
    var userId = String(els.userId?.value || "").trim();
    var password = String(els.password?.value || "");
    if (!userId) {
      setError("User ID is required.");
      els.userId?.focus();
      return;
    }
    if (!password) {
      setError("Password is required.");
      els.password?.focus();
      return;
    }
    var creds = { user_id: userId, password: password };
    // Resolve before hide so hidden.bs.modal does not treat this as cancel.
    resolvePending(creds);
    getModal()?.hide();
  }

  function cancelConfirm() {
    getModal()?.hide();
    resolvePending(null);
  }

  /** Merge credentials into a JSON body object. */
  function withCreds(body, creds) {
    var out = body && typeof body === "object" ? Object.assign({}, body) : {};
    if (creds) {
      out.user_id = creds.user_id;
      out.password = creds.password;
    }
    return out;
  }

  /** Append credentials to FormData. */
  function appendCreds(formData, creds) {
    if (!formData || !creds) return formData;
    formData.append("user_id", creds.user_id);
    formData.append("password", creds.password);
    return formData;
  }

  els.confirmBtn?.addEventListener("click", submitConfirm);
  els.cancelBtn?.addEventListener("click", cancelConfirm);
  els.form?.addEventListener("submit", function (e) {
    e.preventDefault();
    submitConfirm();
  });
  els.modal?.addEventListener("hidden.bs.modal", function () {
    if (els.password) els.password.value = "";
    setError("");
    // If still pending, user dismissed modal
    if (pending) resolvePending(null);
  });

  // Intercept classic form POSTs marked for delete re-auth
  document.addEventListener(
    "submit",
    function (e) {
      var form = e.target;
      if (!(form instanceof HTMLFormElement)) return;
      if (!form.classList.contains("jtcs-delete-reauth-form")) return;
      if (form.dataset.jtcsDeleteAuthed === "1") {
        delete form.dataset.jtcsDeleteAuthed;
        return;
      }
      e.preventDefault();
      e.stopPropagation();
      var message =
        form.getAttribute("data-delete-message") ||
        "Enter your password to confirm delete.";
      ask({ message: message }).then(function (creds) {
        if (!creds) return;
        form.querySelectorAll(".jtcs-delete-reauth-field").forEach(function (node) {
          node.remove();
        });
        ["user_id", "password"].forEach(function (name) {
          var input = document.createElement("input");
          input.type = "hidden";
          input.name = name;
          input.value = creds[name];
          input.className = "jtcs-delete-reauth-field";
          form.appendChild(input);
        });
        form.dataset.jtcsDeleteAuthed = "1";
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit();
        } else {
          form.submit();
        }
      });
    },
    true
  );

  window.JTCSDeleteConfirm = {
    ask: ask,
    withCreds: withCreds,
    appendCreds: appendCreds,
  };
})();
