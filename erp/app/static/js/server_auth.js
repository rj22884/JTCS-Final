/**
 * Server User create / login / reset validation.
 * Errors use JTCSDialog (same popup used across JTCS ERP).
 */
(function () {
  "use strict";

  var ID_RE = /^[A-Za-z0-9]{1,80}$/;

  function showDialog(message, type) {
    var text = String(message || "").trim();
    if (!text) return;
    if (window.JTCSDialog && typeof window.JTCSDialog.alert === "function") {
      window.JTCSDialog.alert(text, type || "invalid");
      return;
    }
    window.alert(text);
  }

  function fieldValue(id) {
    var el = document.getElementById(id);
    return el ? String(el.value || "") : "";
  }

  function validateLoginId(loginId, appLogin, appLocal) {
    var value = String(loginId || "").trim();
    if (!value) {
      return "Please enter a Server User ID.";
    }
    if (!ID_RE.test(value)) {
      return "Server User ID can contain letters and numbers only. Special characters are not allowed.";
    }
    var lower = value.toLowerCase();
    var login = String(appLogin || "").trim().toLowerCase();
    var local = String(appLocal || "").trim().toLowerCase();
    if ((login && lower === login) || (local && lower === local)) {
      return "Server User ID cannot be the same as the application login ID.";
    }
    return "";
  }

  function validateNewPassword(password, confirm) {
    if (!password) {
      return "Please enter a Server password.";
    }
    if (!confirm) {
      return "Please confirm the Server password.";
    }
    if (password !== confirm) {
      return "Passwords do not match.";
    }
    return "";
  }

  function onSubmitCreate(event) {
    var form = event.currentTarget;
    var error =
      validateLoginId(
        fieldValue("login_id"),
        form.getAttribute("data-app-login"),
        form.getAttribute("data-app-login-local")
      ) || validateNewPassword(fieldValue("password"), fieldValue("confirm_password"));
    if (error) {
      event.preventDefault();
      showDialog(error, "invalid");
    }
  }

  function onSubmitLogin(event) {
    var loginId = fieldValue("login_id").trim();
    var password = fieldValue("password");
    var error = "";
    if (!loginId) {
      error = "Please enter a Server User ID.";
    } else if (!password) {
      error = "Please enter a Server password.";
    }
    if (error) {
      event.preventDefault();
      showDialog(error, "invalid");
    }
  }

  function onSubmitReset(event) {
    var error = validateNewPassword(fieldValue("password"), fieldValue("confirm_password"));
    if (error) {
      event.preventDefault();
      showDialog(error, "invalid");
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var boot = document.getElementById("saDialogBoot");
    if (boot) {
      showDialog(boot.getAttribute("data-message"), boot.getAttribute("data-type") || "invalid");
    }

    var createForm = document.getElementById("saCreateForm");
    if (createForm) createForm.addEventListener("submit", onSubmitCreate);

    var loginForm = document.getElementById("saLoginForm");
    if (loginForm) loginForm.addEventListener("submit", onSubmitLogin);

    var resetForm = document.getElementById("saResetForm");
    if (resetForm) resetForm.addEventListener("submit", onSubmitReset);
  });
})();
