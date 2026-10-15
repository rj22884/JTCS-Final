(function () {
  const root = document.getElementById("apiMaster");
  if (!root) return;

  const csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  const saveUrl = root.dataset.saveUrl || "";
  const testUrl = root.dataset.testUrl || "";
  const tokenUrl = root.dataset.tokenUrl || "";

  function headers() {
    return {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": csrf,
      "X-CSRF-Token": csrf,
      "X-Requested-With": "XMLHttpRequest",
    };
  }

  function showPanel(id) {
    root.querySelectorAll("[data-panel]").forEach(function (panel) {
      const active = panel.getAttribute("data-panel") === id;
      panel.hidden = !active;
    });
    root.querySelectorAll("[data-nav]").forEach(function (button) {
      button.classList.toggle("is-active", button.getAttribute("data-nav") === id);
    });
  }

  root.querySelectorAll("[data-nav]").forEach(function (button) {
    button.addEventListener("click", function () {
      showPanel(button.getAttribute("data-nav"));
    });
  });

  function sectionValues(section) {
    const values = {};
    section.querySelectorAll("[data-key]").forEach(function (el) {
      const key = el.getAttribute("data-key");
      if (!key) return;
      if (el.type === "checkbox") values[key] = el.checked;
      else values[key] = el.value;
    });
    return values;
  }

  function note(section, text, ok) {
    const box = section.querySelector(".api-note");
    if (!box) return;
    box.textContent = text || "";
    box.className = "api-note small mt-2 " + (ok ? "text-success" : "text-danger");
  }

  function setBusy(section, busy) {
    section.querySelectorAll("button").forEach(function (button) {
      button.disabled = busy;
    });
  }

  function applyStatus(section, data) {
    if (!data || !data.status) return;
    const badge = section.querySelector("[data-status]");
    if (!badge) return;
    badge.textContent = data.status;
    badge.className = "badge " + (data.status_class || "text-bg-secondary");
  }

  async function post(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    let data = {};
    try {
      data = await response.json();
    } catch (err) {
      data = { ok: false, error: "Unexpected response from the server." };
    }
    if (!response.ok && data.ok !== true && !data.error && !data.message) {
      data.error = "Request failed.";
    }
    return data;
  }

  root.querySelectorAll("[data-save]").forEach(function (button) {
    button.addEventListener("click", async function () {
      const section = button.closest("[data-provider]");
      if (!section) return;
      setBusy(section, true);
      note(section, "Saving…", true);
      try {
        const data = await post(saveUrl, {
          provider: section.getAttribute("data-provider"),
          values: sectionValues(section),
        });
        if (data.ok) {
          note(section, data.message || "Saved.", true);
          applyStatus(section, data);
          const secrets = data.secret_configured || {};
          const fields = data.field_values || {};
          section.querySelectorAll("[data-key]").forEach(function (el) {
            const key = el.getAttribute("data-key");
            if (secrets[key] && el.type === "password") {
              el.value = fields[key] || "";
            }
          });
        } else {
          note(section, data.error || data.message || "Unable to save.", false);
        }
      } catch (err) {
        note(section, "Unable to reach the server.", false);
      } finally {
        setBusy(section, false);
      }
    });
  });

  root.querySelectorAll("[data-test]").forEach(function (button) {
    button.addEventListener("click", async function () {
      const section = button.closest("[data-provider]");
      if (!section) return;
      setBusy(section, true);
      note(section, "Testing connection…", true);
      try {
        const data = await post(testUrl, {
          provider: section.getAttribute("data-provider"),
          values: sectionValues(section),
        });
        note(section, data.message || data.error || "Test finished.", !!data.ok);
        applyStatus(section, data);
      } catch (err) {
        note(section, "Unable to reach the server.", false);
      } finally {
        setBusy(section, false);
      }
    });
  });

  root.querySelectorAll("[data-token]").forEach(function (button) {
    button.addEventListener("click", async function () {
      const section = button.closest("[data-provider]");
      if (!section) return;
      setBusy(section, true);
      note(section, "Generating verify token…", true);
      try {
        const data = await post(tokenUrl, {});
        if (data.ok && data.token) {
          const input = section.querySelector('[data-key="webhook_verify_token"]');
          if (input) {
            input.type = "text";
            input.value = data.token;
          }
          note(section, data.message || "Token generated. Copy it into Meta now.", true);
        } else {
          note(section, data.error || data.message || "Unable to generate a token.", false);
        }
      } catch (err) {
        note(section, "Unable to reach the server.", false);
      } finally {
        setBusy(section, false);
      }
    });
  });

  root.querySelectorAll("[data-copy]").forEach(function (button) {
    button.addEventListener("click", async function () {
      const input = document.getElementById(button.getAttribute("data-copy"));
      if (!input) return;
      try {
        await navigator.clipboard.writeText(input.value || "");
        button.textContent = "Copied";
        setTimeout(function () {
          button.textContent = "Copy";
        }, 1500);
      } catch (err) {
        input.focus();
        input.select();
      }
    });
  });
})();
