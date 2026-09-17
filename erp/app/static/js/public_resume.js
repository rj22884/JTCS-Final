(function () {
  "use strict";

  var captchaCode = "";
  var otpState = { otp_ref: "", session_id: "", record_id: "", continue_url: "" };

  var els = {
    modeMobile: document.getElementById("resumeModeMobile"),
    modeAppMobile: document.getElementById("resumeModeAppMobile"),
    refWrap: document.getElementById("resumeRefWrap"),
    refNo: document.getElementById("resumeRefNo"),
    mobile: document.getElementById("resumeMobile"),
    captcha: document.getElementById("resumeCaptcha"),
    canvas: document.getElementById("resumeCaptchaCanvas"),
    error: document.getElementById("resumeError"),
    validate: document.getElementById("resumeValidate"),
    otpModal: document.getElementById("resumeOtpModal"),
    otp: document.getElementById("resumeOtp"),
    otpMobile: document.getElementById("resumeOtpMobile"),
    otpError: document.getElementById("resumeOtpError"),
    otpVerify: document.getElementById("resumeOtpVerify"),
    continueForm: document.getElementById("resumeContinueForm"),
  };

  function selectedMode() {
    var checked = document.querySelector('input[name="resumeMode"]:checked');
    return checked ? checked.value : "mobile";
  }

  function setError(text) {
    if (!els.error) return;
    els.error.textContent = text || "";
  }

  function syncMode() {
    var appMode = selectedMode() === "app_mobile";
    if (els.refWrap) els.refWrap.hidden = !appMode;
    if (!appMode && els.refNo) els.refNo.value = "";
    if (els.captcha) els.captcha.value = "";
    generateCaptcha();
    setError("");
  }

  function generateCaptcha() {
    captchaCode = String(Math.floor(100000 + Math.random() * 900000));
    var canvas = els.canvas;
    if (!canvas || !canvas.getContext) return;
    var ctx = canvas.getContext("2d");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.font = "bold 28px Times New Roman, serif";
    ctx.fillStyle = "#111827";
    ctx.fillText(captchaCode, 16, 34);
  }

  function queryValue(name) {
    try {
      return String(new URLSearchParams(window.location.search).get(name) || "").trim();
    } catch (err) {
      return "";
    }
  }

  function applyQueryPrefill() {
    var applicationId = queryValue("applicationId");
    var mobile = queryValue("mobile");
    if (!applicationId || !mobile) return;
    if (els.modeAppMobile) {
      els.modeAppMobile.checked = true;
      els.modeAppMobile.dispatchEvent(new Event("change", { bubbles: true }));
    }
    if (els.refNo) els.refNo.value = applicationId;
    if (els.mobile) els.mobile.value = mobile.replace(/\D/g, "").slice(-10) || mobile;
    if (els.captcha) els.captcha.value = "";
  }

  function postJson(url, payload) {
    return fetch(url, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    }).then(function (res) {
      return res.json().then(function (data) {
        return { res: res, data: data };
      });
    });
  }

  async function onValidate() {
    setError("");
    var appMode = selectedMode() === "app_mobile";
    var ref = els.refNo ? String(els.refNo.value || "").trim() : "";
    var mobile = els.mobile ? String(els.mobile.value || "").replace(/\D/g, "") : "";
    var captcha = els.captcha ? String(els.captcha.value || "").trim() : "";
    if (appMode && !ref) {
      setError("Please Enter Reference No");
      return;
    }
    if (appMode && ref.length < 7) {
      setError("Please Enter valid Reference No");
      return;
    }
    if (!mobile) {
      setError("Please Enter Mobile No");
      return;
    }
    if (mobile.length < 10) {
      setError("Please Enter valid Mobile No");
      return;
    }
    if (!captcha) {
      setError("Please Enter image text");
      return;
    }
    if (captcha !== captchaCode) {
      setError("Captcha verification Failed !");
      if (els.captcha) els.captcha.value = "";
      generateCaptcha();
      return;
    }
    if (els.validate) els.validate.disabled = true;
    try {
      var result = await postJson("/resume/vkyc", {
        applicationId: ref,
        mobile: mobile,
        mode: selectedMode(),
      });
      if (!result.res.ok || result.data.ok === false) {
        throw new Error(result.data.error || "Unable to validate.");
      }
      otpState.otp_ref = result.data.otp_ref || "";
      otpState.session_id = result.data.session_id || "";
      otpState.record_id = result.data.record_id || "";
      otpState.continue_url = result.data.continue_url || "";
      if (els.otp) els.otp.value = "";
      if (els.otpError) els.otpError.textContent = "";
      if (els.otpMobile) els.otpMobile.textContent = mobile;
      if (els.otpModal && window.bootstrap) {
        window.bootstrap.Modal.getOrCreateInstance(els.otpModal).show();
      }
    } catch (err) {
      setError(err.message || "Unable to validate.");
      generateCaptcha();
      if (els.captcha) els.captcha.value = "";
    } finally {
      if (els.validate) els.validate.disabled = false;
    }
  }

  async function onVerifyOtp() {
    if (els.otpError) els.otpError.textContent = "";
    var otp = els.otp ? String(els.otp.value || "").replace(/\D/g, "") : "";
    if (!otp) {
      if (els.otpError) els.otpError.textContent = "Enter the OTP received on mobile.";
      return;
    }
    if (els.otpVerify) els.otpVerify.disabled = true;
    try {
      var result = await postJson("/resume/otp", { otp: otp, otp_ref: otpState.otp_ref });
      if (!result.res.ok || result.data.ok === false) {
        throw new Error(result.data.error || "OTP verification failed.");
      }
      if (!els.continueForm || !otpState.continue_url) {
        throw new Error("Unable to continue video recording.");
      }
      els.continueForm.action = otpState.continue_url;
      els.continueForm.innerHTML =
        '<input type="hidden" name="recordid" value="' + String(otpState.record_id || "").replace(/"/g, "") + '">' +
        '<input type="hidden" name="SessionId" value="' + String(otpState.session_id || "").replace(/"/g, "") + '">';
      els.continueForm.submit();
    } catch (err) {
      if (els.otpError) els.otpError.textContent = err.message || "OTP verification failed.";
    } finally {
      if (els.otpVerify) els.otpVerify.disabled = false;
    }
  }

  document.querySelectorAll('input[name="resumeMode"]').forEach(function (radio) {
    radio.addEventListener("change", syncMode);
  });
  if (els.validate) els.validate.addEventListener("click", onValidate);
  if (els.otpVerify) els.otpVerify.addEventListener("click", onVerifyOtp);

  syncMode();
  applyQueryPrefill();
})();
