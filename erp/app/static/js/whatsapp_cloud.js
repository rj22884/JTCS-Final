(function () {
  const cfg = window.WA_CLOUD || {};
  const form = document.getElementById("waForm");
  if (!form || !cfg.saveUrl) return;

  const fields = form.querySelectorAll("[data-wa-field]");
  function actionButtons(name) {
    return Array.from(document.querySelectorAll('[data-wa-action="' + name + '"]'));
  }
  function setActionDisabled(name, disabled) {
    actionButtons(name).forEach(function (btn) {
      btn.disabled = disabled;
    });
  }
  const generateBtn = document.getElementById("waGenerateToken");
  const copyBtn = document.getElementById("waCopyWebhook");
  const result = document.getElementById("waResult");
  const missing = document.getElementById("waMissing");
  const badge = document.getElementById("waStatusBadge");
  const verifyInput = document.getElementById("webhook_verify_token");

  function csrfToken() {
    const input = form.querySelector('[name="csrf_token"]');
    if (input && input.value) return input.value;
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") || "" : "";
  }

  function showResult(text, ok) {
    result.classList.remove("d-none", "text-danger", "text-success");
    result.classList.add(ok ? "text-success" : "text-danger");
    result.style.whiteSpace = "pre-wrap";
    result.textContent = text;
  }

  function setEditing(on) {
    fields.forEach(function (el) {
      el.disabled = !on;
    });
    setActionDisabled("save", !on);
    setActionDisabled("edit", on);
  }

  function applyValues(data) {
    const values = (data && data.field_values) || {};
    fields.forEach(function (el) {
      if (!el.name || !Object.prototype.hasOwnProperty.call(values, el.name)) return;
      if (el.name === "graph_api_version" && !values[el.name]) {
        el.value = "v21.0";
        return;
      }
      const next = values[el.name] == null ? "" : String(values[el.name]);
      if (!next && el.value) return;
      if (el.getAttribute("data-wa-secret") != null && next && /^[*]+$/.test(next)) {
        el.placeholder = "Saved. Blank chhodo to purana secret rahega.";
        return;
      }
      el.value = next;
    });
    const status = (values.connection_status || "").trim() || "Not Configured";
    if (badge) badge.textContent = status;
    const labels = data.missing_labels || [];
    if (missing) {
      if (labels.length) {
        missing.classList.remove("d-none");
        missing.textContent = "Abhi baaki: " + labels.join(", ");
      } else {
        missing.classList.add("d-none");
        missing.textContent = "";
      }
    }
    const secrets = data.secret_configured || {};
    const hasSaved = !!(
      (values.app_id || "").trim() ||
      (values.phone_number_id || "").trim() ||
      (values.waba_id || "").trim() ||
      secrets.access_token ||
      secrets.app_secret ||
      secrets.webhook_verify_token
    );
    setActionDisabled("delete", !hasSaved);
    return hasSaved;
  }

  async function postJson(url, body, options) {
    const allowFailed = !!(options && options.allowFailed);
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(body || {}),
    });
    const contentType = res.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      throw new Error("Server ne JSON nahi bheja. Page refresh karke dubara try karein.");
    }
    const data = await res.json();
    if (!allowFailed && (!res.ok || data.ok === false)) {
      throw new Error(data.error || data.message || "Request failed.");
    }
    if (allowFailed && !res.ok && data.ok !== false) {
      throw new Error(data.error || data.message || "Request failed.");
    }
    return data;
  }

  function collectValues() {
    const values = {};
    fields.forEach(function (el) {
      if (el.name) values[el.name] = el.value;
    });
    return values;
  }

  setEditing(true);
  setActionDisabled("delete", !cfg.hasSaved);

  actionButtons("edit").forEach(function (editBtn) {
    editBtn.addEventListener("click", function () {
      setEditing(true);
    });
  });

  actionButtons("save").forEach(function (saveBtn) {
    if (saveBtn.type === "submit") return;
    saveBtn.addEventListener("click", function () {
      if (typeof form.requestSubmit === "function") form.requestSubmit();
    });
  });

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    setActionDisabled("save", true);
    try {
      const data = await postJson(cfg.saveUrl, { values: collectValues() });
      applyValues(data);
      setEditing(true);
      showResult(data.message || "Credentials saved.", true);
    } catch (err) {
      showResult(err.message || "Save failed.", false);
    } finally {
      setActionDisabled("save", false);
    }
  });

  actionButtons("delete").forEach(function (deleteBtn) {
    deleteBtn.addEventListener("click", async function () {
      if (!window.confirm("Saved WhatsApp token, App Secret, aur Phone Number ID is app se delete ho jayenge. Continue?")) {
        return;
      }
      setActionDisabled("delete", true);
      try {
        const data = await postJson(cfg.deleteUrl, {});
        applyValues(data);
        const version = document.getElementById("graph_api_version");
        if (version && !version.value) version.value = "v21.0";
        setEditing(true);
        showResult(data.message || "Credentials deleted.", true);
      } catch (err) {
        showResult(err.message || "Delete failed.", false);
        setActionDisabled("delete", false);
      }
    });
  });

  actionButtons("test").forEach(function (testBtn) {
    testBtn.addEventListener("click", async function () {
      setActionDisabled("test", true);
      try {
        const data = await postJson(cfg.testUrl, {
          send_test_message: !!document.getElementById("send_test_message").checked,
          test_to_number: (document.getElementById("test_to_number").value || "").trim(),
        }, { allowFailed: true });
        if (data.field_values) applyValues(data);
        const lines = (data.checks || []).map(function (item) {
          const mark = item.ok ? "OK" : item.skipped ? "SKIP" : "FAIL";
          return mark + " — " + (item.name || "Check") + (item.detail ? ": " + item.detail : "");
        });
        const head = data.message || data.connection_status || (data.ok ? "Connected." : "Test failed.");
        showResult([head].concat(lines).join("\n"), !!data.ok);
      } catch (err) {
        showResult(err.message || "Test failed.", false);
      } finally {
        setActionDisabled("test", false);
      }
    });
  });

  if (generateBtn) {
    generateBtn.addEventListener("click", async function () {
      generateBtn.disabled = true;
      try {
        const data = await postJson(cfg.generateUrl, {});
        if (verifyInput && data.webhook_verify_token_plain) {
          verifyInput.type = "text";
          verifyInput.value = data.webhook_verify_token_plain;
        }
        if (data.field_values) {
          applyValues({ field_values: data.field_values, secret_configured: { webhook_verify_token: true } });
          if (verifyInput && data.webhook_verify_token_plain) {
            verifyInput.value = data.webhook_verify_token_plain;
          }
        }
        showResult(data.message || "Verify token generated. Meta dashboard me copy karein.", true);
      } catch (err) {
        showResult(err.message || "Could not generate verify token.", false);
      } finally {
        generateBtn.disabled = false;
      }
    });
  }

  if (copyBtn) {
    copyBtn.addEventListener("click", async function () {
      const url = cfg.webhookUrl || "";
      try {
        await navigator.clipboard.writeText(url);
        showResult("Webhook URL copy ho gaya.", true);
      } catch (err) {
        showResult(url, true);
      }
    });
  }
})();
