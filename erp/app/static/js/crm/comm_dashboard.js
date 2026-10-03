(function () {
  "use strict";
  const page = document.getElementById("crmCommDashboard");
  if (page && page.dataset.apiStats) {
    // Stats are server-rendered; optional soft refresh for live counters.
    setInterval(async function () {
      try {
        const data = await CrmCommon.apiFetch(page.dataset.apiStats);
        if (!data || !data.ok) return;
        /* Keep SSR values; badge polling handles live unread. */
      } catch (_e) {}
    }, 60000);
  }

  const block = document.getElementById("crmWaCredsBlock");
  const form = document.getElementById("crmWaCredsForm");
  if (!block || !form) return;

  const SECRET_MASK = block.dataset.secretMask || "*********************";
  const saveUrl = block.dataset.apiSave || "/admin/integrations/api/settings";
  const testUrl = block.dataset.apiTest || "/admin/integrations/api/whatsapp/test-connection";
  const hint = document.getElementById("crmWaCredsHint");
  const saveBtn = document.getElementById("crmWaCredsSaveBtn");
  const connectBtn = document.getElementById("crmWaConnectBtn");

  function csrfToken() {
    return block.dataset.csrf || "";
  }

  function setHint(text, kind) {
    if (!hint) return;
    hint.textContent = text || "";
    hint.classList.remove("is-error", "is-ok");
    if (kind) hint.classList.add(kind);
  }

  function isConnectedStatus(status) {
    return String(status || "")
      .trim()
      .toLowerCase() === "connected";
  }

  function setConnectButton(connected) {
    if (!connectBtn) return;
    const on = !!connected;
    connectBtn.dataset.connected = on ? "1" : "0";
    connectBtn.classList.toggle("is-connected", on);
    connectBtn.classList.toggle("is-disconnected", !on);
    connectBtn.innerHTML = on
      ? '<span class="crm-wa-connect-dot" aria-hidden="true">🟢</span> Connected'
      : '<span class="crm-wa-connect-dot" aria-hidden="true">🔴</span> Disconnected';
  }

  function collectValues() {
    const values = {};
    form.querySelectorAll("[name]").forEach(function (input) {
      const key = input.getAttribute("name");
      if (!key || input.readOnly) return;
      if (input.type === "password") {
        const raw = (input.value || "").trim();
        if (!raw) {
          values[key] = input.getAttribute("data-has-secret") === "1" ? SECRET_MASK : "";
        } else if (raw === SECRET_MASK) {
          values[key] = SECRET_MASK;
        } else {
          values[key] = raw;
        }
        return;
      }
      values[key] = input.value || "";
    });
    return values;
  }

  function applyMaskedValues(data) {
    const vals = data.field_values || data.values || {};
    const secrets = data.secret_configured || {};
    form.querySelectorAll("[name]").forEach(function (input) {
      const key = input.name;
      if (!(key in vals)) return;
      if (input.type === "password") {
        const configured =
          !!secrets[key] || !!(vals[key] && String(vals[key]).indexOf("*") >= 0);
        input.value = configured ? SECRET_MASK : "";
        input.setAttribute("data-has-secret", configured ? "1" : "0");
        input.placeholder = configured ? "Saved (encrypted)" : input.placeholder;
      } else if (!input.readOnly) {
        input.value = vals[key] || "";
      }
    });
    const status = vals.connection_status || data.connection_status || "";
    setConnectButton(isConnectedStatus(status));
    return { vals: vals, missing: data.missing_labels || [] };
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    if (saveBtn) saveBtn.disabled = true;
    setHint("Saving…", "");
    fetch(saveUrl, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({
        provider: "whatsapp_meta",
        values: collectValues(),
      }),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { res: res, data: data };
        });
      })
      .then(function (result) {
        const data = result.data || {};
        if (!result.res.ok || data.ok === false) {
          throw new Error(data.error || "Unable to save WhatsApp credentials.");
        }
        const applied = applyMaskedValues(data);
        setHint(
          applied.missing.length
            ? "Saved. Missing: " + applied.missing.join(", ")
            : "Credentials saved.",
          applied.missing.length ? "is-error" : "is-ok"
        );
      })
      .catch(function (err) {
        setHint(err.message || "Save failed.", "is-error");
        setConnectButton(false);
      })
      .finally(function () {
        if (saveBtn) saveBtn.disabled = false;
      });
  });

  connectBtn?.addEventListener("click", function () {
    connectBtn.disabled = true;
    setHint("Checking WhatsApp connection…", "");
    fetch(testUrl, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({ send_test_message: false }),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { res: res, data: data };
        });
      })
      .then(function (result) {
        const data = result.data || {};
        if (data.field_values || data.values) {
          applyMaskedValues(data);
        }
        const status =
          data.connection_status ||
          (data.field_values || data.values || {}).connection_status ||
          "";
        const connected = status
          ? isConnectedStatus(status)
          : !!data.ok && !(data.missing || []).length;
        setConnectButton(connected);
        setHint(
          data.message || (connected ? "WhatsApp Connected." : "WhatsApp Disconnected."),
          connected ? "is-ok" : "is-error"
        );
      })
      .catch(function (err) {
        setConnectButton(false);
        setHint(err.message || "Connection check failed.", "is-error");
      })
      .finally(function () {
        connectBtn.disabled = false;
      });
  });
})();
