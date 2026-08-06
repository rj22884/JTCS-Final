(function () {
  "use strict";

  const api = window.CP_API || {};
  const loadingEl = document.getElementById("cpLoading");
  const alertEl = document.getElementById("cpAlert");
  const duplicateToastEl = document.getElementById("cpDuplicateToast");
  const duplicateListEl = document.getElementById("cpDuplicateList");
  const detectedTypeEl = document.getElementById("cpDetectedType");
  let duplicateToast = null;

  function setLoading(on) {
    if (!loadingEl) return;
    loadingEl.classList.toggle("d-none", !on);
  }

  function showAlert(message, type) {
    if (!alertEl) return;
    const text = String(message || "").replace(/\n/g, "<br>");
    alertEl.className = "alert alert-" + (type || "danger");
    alertEl.innerHTML = text;
    alertEl.classList.remove("d-none");
  }

  function clearAlert() {
    if (!alertEl) return;
    alertEl.classList.add("d-none");
    alertEl.innerHTML = "";
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function showDuplicateToast(duplicates) {
    if (!duplicateToastEl || !duplicateListEl) return;
    const rows = Array.isArray(duplicates) ? duplicates : [];
    duplicateListEl.innerHTML = rows
      .map(function (row) {
        return (
          '<div class="cp-duplicate-item">' +
          '<div class="name">' +
          escapeHtml(row.customer_name || "Customer") +
          "</div>" +
          '<div class="pan">' +
          escapeHtml(row.masked_pan || "XXXXXXXXXX") +
          "</div>" +
          "</div>"
        );
      })
      .join("");
    if (!duplicateToast) {
      duplicateToast = new bootstrap.Toast(duplicateToastEl, { autohide: false });
    }
    duplicateToast.show();
  }

  function detectType(value) {
    const raw = String(value || "").trim();
    if (!raw) return "";
    if (raw.indexOf("@") >= 0) return "EMAIL";
    const digits = raw.replace(/\D/g, "");
    if (/^\d{12}$/.test(digits)) return "AADHAAR";
    if (/^\d{10}$/.test(digits) || (digits.length >= 10 && digits.length <= 12)) return "MOBILE";
    if (/^[A-Za-z]{5}[0-9]{4}[A-Za-z]$/.test(raw.replace(/\s+/g, ""))) return "PAN";
    return "";
  }

  function updateDetectedType() {
    if (!detectedTypeEl) return;
    const input = document.getElementById("cpUserId");
    const type = detectType(input && input.value);
    detectedTypeEl.textContent = type ? ("Detected: " + type) : "";
  }

  async function postJson(url, payload) {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": api.csrfToken || "",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(payload || {}),
      credentials: "same-origin",
    });
    let data = {};
    try {
      data = await response.json();
    } catch (err) {
      data = { ok: false, error: "Unexpected server response." };
    }
    data.status = response.status;
    return data;
  }

  function handleErrorResult(data) {
    if (data && data.error_code === "duplicate") {
      showDuplicateToast(data.duplicates || []);
      showAlert(data.error || "Duplicate customer records found.", "warning");
      return;
    }
    showAlert((data && data.error) || "Request failed.", "danger");
  }

  // Theme toggle (dark mode compatible)
  const themeKey = "jtcs-cp-theme";
  function applyTheme(theme) {
    document.documentElement.setAttribute("data-bs-theme", theme);
    document.querySelectorAll(".cp-theme-toggle i").forEach(function (icon) {
      icon.className = theme === "dark" ? "bi bi-sun" : "bi bi-moon-stars";
    });
  }
  applyTheme(localStorage.getItem(themeKey) || "light");
  document.querySelectorAll(".cp-theme-toggle").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const next = document.documentElement.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
      localStorage.setItem(themeKey, next);
      applyTheme(next);
    });
  });

  document.querySelectorAll("[data-cp-toggle-password]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const sel = btn.getAttribute("data-cp-toggle-password");
      const input = sel ? document.querySelector(sel) : null;
      if (!input) return;
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      const icon = btn.querySelector("i");
      if (icon) icon.className = show ? "bi bi-eye-slash" : "bi bi-eye";
    });
  });

  const userIdInput = document.getElementById("cpUserId");
  if (userIdInput) {
    userIdInput.addEventListener("input", updateDetectedType);
    updateDetectedType();
  }

  const loginForm = document.getElementById("cpLoginForm");
  if (loginForm) {
    loginForm.addEventListener("submit", async function (event) {
      event.preventDefault();
      clearAlert();
      const userId = (document.getElementById("cpUserId")?.value || "").trim();
      const password = document.getElementById("cpPassword")?.value || "";
      if (!userId || !password) {
        showAlert("User ID and Password are required.", "warning");
        return;
      }
      setLoading(true);
      try {
        const data = await postJson(api.login, { user_id: userId, password: password });
        if (!data.ok) {
          handleErrorResult(data);
          return;
        }
        window.location.href = data.redirect || api.dashboard;
      } catch (err) {
        showAlert("Unable to login. Please try again.", "danger");
      } finally {
        setLoading(false);
      }
    });
  }

  const resetBtn = document.getElementById("cpResetBtn");
  if (resetBtn) {
    resetBtn.addEventListener("click", async function () {
      clearAlert();
      const userId = (document.getElementById("cpUserId")?.value || "").trim();
      if (!userId) {
        showAlert("Enter your User ID to reset password.", "warning");
        return;
      }
      setLoading(true);
      try {
        const data = await postJson(api.resetPassword, { user_id: userId });
        if (!data.ok) {
          handleErrorResult(data);
          return;
        }
        showAlert(data.message || "Default password reset successfully.", "success");
      } catch (err) {
        showAlert("Unable to reset password. Please try again.", "danger");
      } finally {
        setLoading(false);
      }
    });
  }

  const changeForm = document.getElementById("cpChangePasswordForm");
  if (changeForm) {
    changeForm.addEventListener("submit", async function (event) {
      event.preventDefault();
      clearAlert();
      const payload = {
        old_password: document.getElementById("cpOldPassword")?.value || "",
        new_password: document.getElementById("cpNewPassword")?.value || "",
        confirm_password: document.getElementById("cpConfirmPassword")?.value || "",
      };
      if (payload.new_password.length < 8) {
        showAlert("New Password must be at least 8 characters.", "warning");
        return;
      }
      if (payload.new_password !== payload.confirm_password) {
        showAlert("New Password and Confirm Password must match.", "warning");
        return;
      }
      setLoading(true);
      try {
        const data = await postJson(api.changePassword, payload);
        if (!data.ok) {
          handleErrorResult(data);
          return;
        }
        window.location.href = data.redirect || api.dashboard;
      } catch (err) {
        showAlert("Unable to save password. Please try again.", "danger");
      } finally {
        setLoading(false);
      }
    });
  }
})();
