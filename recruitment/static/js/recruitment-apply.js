(function () {
  "use strict";

  var form = document.getElementById("recApplyForm");
  if (!form) return;

  var submit = document.getElementById("recSubmit");
  var previewBtn = document.getElementById("recPreview");
  var previewPdfBtn = document.getElementById("recPreviewPdf");
  var modal = document.getElementById("recPreviewModal");
  var previewBody = document.getElementById("recPreviewBody");
  var submitting = false;
  var heldResume = null;
  var MAX_RESUME_BYTES = 5 * 1024 * 1024;
  var STATUS_URL = "/careers/application-status";

  function fillIds() {
    var rec = window.JTCSRecruitment;
    if (!rec) return;
    var vid = document.getElementById("visitor_id");
    var sid = document.getElementById("session_id");
    if (vid && !vid.value) vid.value = rec.visitorId();
    if (sid && !sid.value) sid.value = rec.sessionId();
  }

  function resumeFromInput() {
    var file = document.getElementById("resume");
    return file && file.files && file.files[0] ? file.files[0] : null;
  }

  function resumeFile() {
    return resumeFromInput() || heldResume;
  }

  function updateResumeName() {
    var chosen = resumeFile();
    var out = document.getElementById("recResumeName");
    var err = document.getElementById("resumeError");
    if (!out) return;
    if (chosen) {
      var kb = Math.max(1, Math.round(chosen.size / 1024));
      out.hidden = false;
      out.textContent = "Selected: " + chosen.name + " (" + kb + " KB)";
      if (err) err.textContent = "";
    } else {
      out.hidden = true;
      out.textContent = "";
    }
  }

  function buildFormData() {
    fillIds();
    var fd = new FormData(form);
    var file = resumeFile();
    if (file) {
      fd.set("resume", file, file.name);
    }
    return fd;
  }

  function scrollToField(el) {
    if (!el) return;
    try {
      el.scrollIntoView({ block: "center", behavior: "smooth" });
    } catch (err) {
      window.scrollTo(0, Math.max(0, el.getBoundingClientRect().top + window.pageYOffset - 140));
    }
    if (el.focus) {
      try { el.focus({ preventScroll: true }); } catch (err2) { el.focus(); }
    }
    if (el.reportValidity) el.reportValidity();
  }

  function firstInvalidField(opts) {
    opts = opts || {};
    var fields = Array.prototype.slice.call(form.querySelectorAll("input, select, textarea"));
    for (var i = 0; i < fields.length; i++) {
      var el = fields[i];
      if (el.type === "hidden" || el.disabled) continue;
      if (opts.skipDeclaration && el.name === "declaration") continue;
      if (el.type === "file") continue;
      if (!el.checkValidity()) return el;
    }
    if (!resumeFile()) return document.getElementById("resume");
    return null;
  }

  function validateForm(opts) {
    var invalid = firstInvalidField(opts);
    if (invalid) {
      if (invalid.name === "resume") {
        var err = document.getElementById("resumeError");
        if (err) err.textContent = "Please upload your resume (PDF, DOC or DOCX, max 5 MB).";
      }
      scrollToField(invalid);
      return false;
    }
    var chosen = resumeFile();
    if (chosen && chosen.size > MAX_RESUME_BYTES) {
      alert("Resume must be 5 MB or smaller.");
      scrollToField(document.getElementById("resume"));
      return false;
    }
    return true;
  }

  function val(name) {
    var el = form.elements[name];
    if (!el) return "";
    if (el.type === "checkbox") return el.checked ? "Yes" : "No";
    if (el.length && el[0] && el[0].type === "radio") {
      for (var i = 0; i < el.length; i++) {
        if (el[i].checked) return el[i].value;
      }
      return "";
    }
    return (el.value || "").trim();
  }

  function esc(text) {
    return String(text || "").replace(/[&<>"']/g, function (ch) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch];
    });
  }

  function section(title, rows) {
    var html = "<h3>" + esc(title) + "</h3><dl>";
    rows.forEach(function (row) {
      html += "<dt>" + esc(row[0]) + "</dt><dd>" + esc(row[1] || "—") + "</dd>";
    });
    return html + "</dl>";
  }

  function buildPreview() {
    var chosen = resumeFile();
    var resumeName = chosen ? chosen.name : "Not selected";
    previewBody.innerHTML =
      section("Personal Information", [
        ["Full Name", val("name")],
        ["Father's Name", val("father_name")],
        ["Date of Birth", val("dob")],
        ["Gender", val("gender")],
        ["Mobile Number", val("mobile")],
        ["Email Address", val("email")],
        ["Address", val("address")],
        ["City", val("city")],
        ["State", val("state")],
        ["PIN Code", val("pin_code")]
      ]) +
      section("Educational Information", [
        ["Highest Educational Qualification", val("highest_qualification")],
        ["Last Educational Qualification", val("last_qualification")],
        ["Academic Qualification / Degree", val("last_qualification")],
        ["University / Board", val("university_board")],
        ["Year of Passing", val("passing_year")],
        ["Percentage / CGPA", val("percentage_cgpa")]
      ]) +
      section("Professional Information", [
        ["Sales Experience", val("sales_experience_years") + " years " + val("sales_experience_months") + " months"],
        ["Previous Company", val("previous_company")],
        ["Previous Designation", val("previous_designation")],
        ["Previous Job Responsibilities", val("responsibilities")],
        ["Total Work Experience", val("total_work_experience")],
        ["Software / IT Sales Experience", val("software_sales_experience")],
        ["B2B Sales Experience", val("b2b_sales_experience")],
        ["Tax / Accounting / ERP Sales Experience", val("tax_accounting_erp_sales_experience")]
      ]) +
      section("Skills", [
        ["Communication Skills", val("communication_skills")],
        ["Computer Knowledge", val("computer_knowledge")],
        ["MS Excel Knowledge", val("ms_excel_knowledge")],
        ["CRM/ERP Knowledge", val("crm_erp_knowledge")],
        ["Digital Marketing Knowledge", val("digital_marketing_knowledge")],
        ["Other Skills", val("other_skills")]
      ]) +
      section("Other Information", [
        ["Expected Salary", val("expected_salary")],
        ["Notice Period", val("notice_period")],
        ["Current Employment Status", val("current_employment_status")],
        ["Willing to Work in Haldwani", val("willing_to_work_haldwani")],
        ["Willing to Travel for Sales", val("willing_to_travel")],
        ["How did you hear about this opportunity?", val("source")],
        ["About Yourself", val("about_candidate")],
        ["Why do you think you are suitable for this position?", val("suitability_answer")]
      ]) +
      section("Resume", [["Resume", resumeName]]);
  }

  function openPreview() {
    if (!validateForm({ skipDeclaration: true })) return;
    buildPreview();
    modal.hidden = false;
    modal.classList.add("is-open");
  }

  function closePreview() {
    modal.classList.remove("is-open");
    modal.hidden = true;
  }

  function setFieldError(name, message) {
    var span = document.getElementById(name + "Error");
    var field = document.getElementById(name) || form.elements[name];
    if (field && field.length && field[0]) field = field[0];
    if (!span && field && field.closest) {
      var group = field.closest(".form-group") || field.closest(".rec-section");
      span = group && group.querySelector(".rec-error");
    }
    if (span) span.textContent = message || "";
    if (field && field.classList) {
      if (message) field.classList.add("is-invalid");
      else field.classList.remove("is-invalid");
    }
  }

  function clearFieldErrors() {
    Array.prototype.forEach.call(form.querySelectorAll(".rec-error"), function (el) {
      el.textContent = "";
    });
    Array.prototype.forEach.call(form.querySelectorAll(".is-invalid"), function (el) {
      el.classList.remove("is-invalid");
    });
  }

  function showFormAlert(message, duplicate, fieldMessages) {
    var box = document.getElementById("recFormErrors");
    if (!box) return;
    if (!message && !(fieldMessages && fieldMessages.length)) {
      box.hidden = true;
      box.innerHTML = "";
      return;
    }
    box.hidden = false;
    var html = message ? "<p>" + esc(message) + "</p>" : "";
    if (fieldMessages && fieldMessages.length) {
      html += "<ul class=\"rec-alert-list\">";
      fieldMessages.forEach(function (item) {
        html += "<li><a href=\"#" + esc(item.id || "") + "\">" + esc(item.text) + "</a></li>";
      });
      html += "</ul>";
    }
    if (duplicate) {
      html += '<p class="rec-alert-action"><a class="btn-jtcs btn-secondary-jtcs" href="' + STATUS_URL + '">Check Application Status</a></p>';
    }
    box.innerHTML = html;
    if (box.scrollIntoView) box.scrollIntoView({ block: "center" });
  }

  function showServerErrors(errors, duplicate) {
    errors = errors || {};
    clearFieldErrors();
    var fieldMessages = [];
    Object.keys(errors).forEach(function (key) {
      if (key === "form" || !errors[key]) return;
      setFieldError(key, errors[key]);
      fieldMessages.push({ id: key, text: errors[key] });
    });
    showFormAlert(
      errors.form || "Please correct the highlighted fields, then submit again.",
      duplicate,
      fieldMessages
    );
    var first = fieldMessages[0];
    if (!first) return;
    var target = document.getElementById(first.id);
    if (first.id === "resume") updateResumeName();
    if (target) scrollToField(target);
  }

  function checkDuplicates(done) {
    var finished = false;
    function finish(ok) {
      if (finished) return;
      finished = true;
      done(ok);
    }
    var api = (window.JTCSRecruitment && window.JTCSRecruitment.apiBase) ? window.JTCSRecruitment.apiBase() : "";
    var timer = setTimeout(function () { finish(true); }, 4000);
    fetch(api + "/api/recruitment/apply-check", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ slug: "sales-executive", mobile: val("mobile"), email: val("email") }),
      credentials: "omit"
    })
      .then(function (res) { return res.ok ? res.json() : null; })
      .then(function (data) {
        clearTimeout(timer);
        var errors = (data && data.errors) || {};
        setFieldError("mobile", errors.mobile || "");
        setFieldError("email", errors.email || "");
        if (data && data.duplicate) {
          showFormAlert("An application with this mobile number or email address already exists. Please check your application status.", true);
          scrollToField(document.getElementById(errors.mobile ? "mobile" : "email"));
          finish(false);
          return;
        }
        finish(true);
      })
      .catch(function () {
        clearTimeout(timer);
        finish(true);
      });
  }

  function resetSubmitButton() {
    submitting = false;
    if (submit) {
      submit.disabled = false;
      submit.textContent = "Confirm & Submit Application";
    }
  }

  function postApplication(fd) {
    submitting = true;
    if (submit) {
      submit.disabled = true;
      submit.textContent = "Submitting your application...";
    }
    fetch(form.getAttribute("action") || window.location.href, {
      method: "POST",
      body: fd,
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest"
      }
    })
      .then(function (res) {
        if (res.status === 413) throw new Error("too-large");
        var ctype = res.headers.get("content-type") || "";
        if (ctype.indexOf("application/json") !== -1) {
          return res.json().then(function (data) {
            return { ok: res.ok, data: data };
          });
        }
        if (res.redirected && res.url) {
          window.location.href = res.url;
          return null;
        }
        throw new Error("submit");
      })
      .then(function (payload) {
        if (!payload) return;
        if (payload.data && payload.data.ok && payload.data.redirect) {
          window.location.href = payload.data.redirect;
          return;
        }
        resetSubmitButton();
        showServerErrors((payload.data && payload.data.errors) || {}, payload.data && payload.data.duplicate);
      })
      .catch(function (err) {
        resetSubmitButton();
        if (err && err.message === "too-large") {
          showFormAlert("The uploaded file is too large. Please upload a resume of 5 MB or smaller.");
          scrollToField(document.getElementById("resume"));
          return;
        }
        showFormAlert("The application could not be submitted. Please check the form and try again.");
      });
  }

  if (previewBtn) previewBtn.addEventListener("click", openPreview);
  var editBtn = document.getElementById("recPreviewEdit");
  if (editBtn) editBtn.addEventListener("click", closePreview);
  var confirmBtn = document.getElementById("recPreviewSubmit");
  if (confirmBtn) confirmBtn.addEventListener("click", function () {
    closePreview();
    if (submit) submit.click();
  });

  function downloadPreviewPdf() {
    if (!validateForm({ skipDeclaration: true })) return;
    if (previewPdfBtn) {
      previewPdfBtn.disabled = true;
      previewPdfBtn.textContent = "Preparing preview PDF...";
    }
    var action = (form.getAttribute("action") || window.location.pathname).replace(/\/?$/, "") + "/preview-pdf";
    fetch(action, { method: "POST", body: buildFormData(), credentials: "same-origin" })
      .then(function (res) {
        if (!res.ok) throw new Error("pdf");
        return res.blob();
      })
      .then(function (blob) {
        var url = URL.createObjectURL(blob);
        var a = document.createElement("a");
        a.href = url;
        a.download = "JTCS-Sales-Executive-Application-PREVIEW.pdf";
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
      })
      .catch(function () {
        alert("Preview PDF could not be created. Please check the form and try again.");
      })
      .finally(function () {
        if (previewPdfBtn) {
          previewPdfBtn.disabled = false;
          previewPdfBtn.textContent = "Download Preview PDF";
        }
      });
  }

  document.querySelectorAll("#recPreviewPdf, #recPreviewPdfModal").forEach(function (pdfBtn) {
    pdfBtn.addEventListener("click", downloadPreviewPdf);
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (submitting) return;
    fillIds();
    if (!validateForm()) return;
    var declared = form.querySelector('[name="declaration"]');
    if (!declared || !declared.checked) {
      alert("Please agree to the declaration before submitting.");
      scrollToField(declared);
      return;
    }
    var fd = buildFormData();
    if (!resumeFile()) {
      var err = document.getElementById("resumeError");
      if (err) err.textContent = "Please upload your resume (PDF, DOC or DOCX, max 5 MB).";
      scrollToField(document.getElementById("resume"));
      return;
    }
    checkDuplicates(function (ok) {
      if (!ok) return;
      postApplication(fd);
    });
  });

  var resumeInput = form.querySelector("#resume");
  if (resumeInput) {
    resumeInput.addEventListener("change", function () {
      heldResume = resumeFromInput();
      updateResumeName();
    });
  }
  updateResumeName();
  fillIds();

  var firstError = form.querySelector(".rec-error");
  if (document.getElementById("recFormErrors") && !document.getElementById("recFormErrors").hidden) {
    document.getElementById("recFormErrors").scrollIntoView({ block: "center" });
  } else if (firstError && firstError.textContent.trim()) {
    firstError.scrollIntoView({ block: "center" });
  }
})();
