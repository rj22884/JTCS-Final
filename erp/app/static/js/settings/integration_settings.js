(function () {
  "use strict";

  function csrfToken(root) {
    if (root) {
      var fromPage = root.getAttribute("data-csrf");
      if (fromPage) return fromPage;
    }
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    var match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
    if (match) return decodeURIComponent(match[1]);
    match = document.cookie.match(/(?:^|;\s*)csrf-token=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  async function api(url, options, root) {
    var opts = Object.assign({ credentials: "same-origin" }, options || {});
    var headers = new Headers(opts.headers || {});
    var method = (opts.method || "GET").toUpperCase();
    var token = csrfToken(root);
    if (method !== "GET" && method !== "HEAD") {
      if (!token) {
        throw new Error("CSRF token missing. Refresh the page (Ctrl+F5) and try again.");
      }
      headers.set("X-CSRFToken", token);
      headers.set("X-CSRF-Token", token);
    }
    headers.set("Accept", "application/json");
    headers.set("X-Requested-With", "XMLHttpRequest");
    if (opts.body && typeof opts.body === "object" && !(opts.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
      opts.body = JSON.stringify(opts.body);
    }
    opts.headers = headers;
    var resp = await fetch(url, opts);
    var raw = await resp.text();
    var data = null;
    try {
      data = raw ? JSON.parse(raw) : {};
    } catch (_err) {
      var snippet = (raw || "").replace(/\s+/g, " ").trim().slice(0, 160);
      var csrfHint = /csrf/i.test(raw || "")
        ? " CSRF failed — refresh the page (Ctrl+F5) and try again."
        : "";
      throw new Error(
        (resp.ok ? "Invalid response." : "Request failed (" + resp.status + ").") +
          csrfHint +
          (snippet ? " " + snippet : "")
      );
    }
    if (!resp.ok) {
      throw new Error((data && data.error) || "Request failed (" + resp.status + ")");
    }
    return data;
  }

  function showAlert(el, message, type) {
    if (!el) return;
    el.className = "alert alert-" + (type || "info") + " intset-alert is-visible";
    el.textContent = message;
  }

  function collectValues(pane) {
    var values = {};
    pane.querySelectorAll("[data-setting-key]").forEach(function (input) {
      var key = input.getAttribute("data-setting-key");
      if (!key) return;
      values[key] = input.value;
    });
    return values;
  }

  function setStatusBadge(pane, status, statusCode) {
    var statusEl = pane.querySelector("[data-connection-status]");
    if (!statusEl) return;
    var text = status || "Not Configured";
    var code = statusCode || "not_configured";
    if (/connected/i.test(text)) code = "connected";
    else if (/partial/i.test(text)) code = "partial";
    else code = "not_configured";

    var icon = code === "connected" ? "🟢" : code === "partial" ? "🟡" : "🔴";
    statusEl.textContent = icon + " " + text;
    statusEl.classList.remove("is-connected", "is-partial", "is-missing", "is-not-configured");
    if (code === "connected") statusEl.classList.add("is-connected");
    else if (code === "partial") statusEl.classList.add("is-partial");
    else statusEl.classList.add("is-not-configured");

    var hidden = pane.querySelector('[data-setting-key="connection_status"]');
    if (hidden) hidden.value = text;
  }

  function setMissing(pane, labels) {
    var box = pane.querySelector("[data-missing-box]");
    var list = pane.querySelector("[data-missing-list]");
    if (!box || !list) return;
    if (!labels || !labels.length) {
      box.classList.add("d-none");
      list.textContent = "";
      return;
    }
    box.classList.remove("d-none");
    list.textContent = labels.join(", ");
  }

  function looksLikeAccessToken(value) {
    var text = value == null ? "" : String(value).trim();
    if (!text) return false;
    if (/^(EAA|YA|IG)/.test(text)) return true;
    if (text.length >= 80 && /[A-Za-z]/.test(text) && /\d/.test(text)) return true;
    return false;
  }

  function isMetaObjectId(value) {
    return /^\d{5,30}$/.test(String(value == null ? "" : value).trim());
  }

  function applyValues(pane, values, meta) {
    if (!values) return;
    Object.keys(values).forEach(function (key) {
      var input = pane.querySelector('[data-setting-key="' + key + '"]');
      if (!input) return;
      var raw = values[key] == null ? "" : String(values[key]);
      // Never place Access Token into Business ID / WABA ID / Phone Number ID.
      if (
        (key === "business_id" || key === "waba_id" || key === "phone_number_id") &&
        (looksLikeAccessToken(raw) || (raw && !isMetaObjectId(raw)))
      ) {
        input.value = "";
        return;
      }
      if (key === "access_token" && raw && !looksLikeAccessToken(raw) && isMetaObjectId(raw)) {
        // Do not put Graph object ids into Access Token.
        return;
      }
      input.value = raw;
    });
    setStatusBadge(pane, values.connection_status, meta && meta.status_code);
    if (meta && meta.missing_labels) setMissing(pane, meta.missing_labels);
  }

  function showChecks(pane, checks) {
    var wrap = pane.querySelector("[data-test-checks]");
    if (!wrap) return;
    if (!checks || !checks.length) {
      wrap.innerHTML = "";
      return;
    }
    var html = "<ul class='intset-checks mb-0'>";
    checks.forEach(function (c) {
      var cls = c.skipped ? "skip" : c.ok ? "ok" : "bad";
      var mark = c.skipped ? "○" : c.ok ? "✓" : "✗";
      html +=
        "<li class='" +
        cls +
        "'>" +
        mark +
        " <strong>" +
        (c.name || "") +
        ":</strong> " +
        (c.detail || "") +
        "</li>";
    });
    html += "</ul>";
    wrap.innerHTML = html;
  }

  function openSelectModal(title, items, valueKey, labelFn, onPick) {
    var modalEl = document.getElementById("intsetSelectModal");
    var titleEl = document.getElementById("intsetSelectTitle");
    var listEl = document.getElementById("intsetSelectList");
    if (!modalEl || !listEl) return;
    titleEl.textContent = title;
    listEl.innerHTML = "";
    if (!items || !items.length) {
      listEl.innerHTML = "<div class='p-3 text-muted'>No items found.</div>";
    } else {
      items.forEach(function (item) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "list-group-item list-group-item-action";
        btn.textContent = labelFn(item);
        btn.addEventListener("click", function () {
          var modal = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
          modal.hide();
          onPick(item[valueKey], item);
        });
        listEl.appendChild(btn);
      });
    }
    var modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
  }

  function openGuideModal(data) {
    var modalEl = document.getElementById("intsetGuideModal");
    var body = document.getElementById("intsetGuideBody");
    var title = document.getElementById("intsetGuideTitle");
    if (!modalEl || !body) return;
    title.textContent = data.title || "Permanent Access Token Guide";
    var html = "<ol>";
    (data.steps || []).forEach(function (s) {
      html += "<li class='mb-2'>" + s + "</li>";
    });
    html += "</ol>";
    if (data.notes && data.notes.length) {
      html += "<div class='small text-muted'><strong>Notes</strong><ul>";
      data.notes.forEach(function (n) {
        html += "<li>" + n + "</li>";
      });
      html += "</ul></div>";
    }
    body.innerHTML = html;
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  async function handlePendingStep(root, pane, alertEl, urls) {
    var data = await api(urls.pendingStep, {}, root);
    var pending = data.pending;
    if (!pending) return;
    showAlert(alertEl, pending.message || "Continue WhatsApp setup.", "success");
    if (pending.step === "select_business") {
      if ((pending.businesses || []).length === 1) {
        await pickBusiness(root, pane, alertEl, urls, pending.businesses[0].id);
      } else {
        openSelectModal(
          "Select Business Account",
          pending.businesses || [],
          "id",
          function (b) {
            return (b.name || "Business") + " (" + b.id + ")";
          },
          function (id) {
            pickBusiness(root, pane, alertEl, urls, id);
          }
        );
      }
    }
  }

  async function pickBusiness(root, pane, alertEl, urls, businessId) {
    var data = await api(
      urls.selectBusiness,
      {
        method: "POST",
        body: { business_id: businessId },
      },
      root
    );
    if (data.field_values) applyValues(pane, data.field_values, data);
    var wabas = data.wabas || [];
    if (wabas.length === 1) {
      await pickWaba(root, pane, alertEl, urls, wabas[0].id);
    } else {
      openSelectModal(
        "Select WhatsApp Business Account",
        wabas,
        "id",
        function (w) {
          return (w.name || "WABA") + " (" + w.id + ")";
        },
        function (id) {
          pickWaba(root, pane, alertEl, urls, id);
        }
      );
    }
  }

  async function pickWaba(root, pane, alertEl, urls, wabaId) {
    var data = await api(urls.selectWaba, { method: "POST", body: { waba_id: wabaId } }, root);
    if (data.field_values) applyValues(pane, data.field_values, data);
    var phones = data.phones || [];
    if (phones.length === 1) {
      await pickPhone(root, pane, alertEl, urls, phones[0].id);
    } else {
      openSelectModal(
        "Select Phone Number",
        phones,
        "id",
        function (p) {
          return (
            (p.display_name || p.display_phone_number || "Phone") +
            " — " +
            (p.display_phone_number || "") +
            " (" +
            p.id +
            ")"
          );
        },
        function (id) {
          pickPhone(root, pane, alertEl, urls, id);
        }
      );
    }
  }

  async function pickPhone(root, pane, alertEl, urls, phoneId) {
    var data = await api(
      urls.selectPhone,
      {
        method: "POST",
        body: { phone_number_id: phoneId },
      },
      root
    );
    applyValues(pane, data.field_values || {}, data);
    setMissing(pane, data.missing_labels || []);
    showAlert(alertEl, data.message || "Phone selected and fields populated.", "success");
  }

  function init() {
    var root = document.getElementById("intsetPage");
    if (!root) return;

    var urls = {
      settings: root.getAttribute("data-api-settings"),
      generate: root.getAttribute("data-api-generate-token"),
      test: root.getAttribute("data-api-test-whatsapp"),
      connect: root.getAttribute("data-api-connect"),
      pendingStep: root.getAttribute("data-api-pending-step"),
      selectBusiness: root.getAttribute("data-api-select-business"),
      selectWaba: root.getAttribute("data-api-select-waba"),
      selectPhone: root.getAttribute("data-api-select-phone"),
      tokenGuide: root.getAttribute("data-api-token-guide"),
    };
    var alertEl = document.getElementById("intsetAlert");

    root.querySelectorAll("[data-intset-save]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        var provider = btn.getAttribute("data-intset-save");
        var pane = root.querySelector('[data-provider-pane="' + provider + '"]');
        if (!pane) return;
        btn.disabled = true;
        try {
          var data = await api(
            urls.settings,
            {
              method: "POST",
              body: { provider: provider, values: collectValues(pane) },
            },
            root
          );
          applyValues(pane, data.field_values || data.values || {}, data);
          setMissing(pane, data.missing_labels || []);
          showAlert(alertEl, "Settings saved for " + provider + ".", "success");
        } catch (err) {
          showAlert(alertEl, err.message || "Save failed", "danger");
        } finally {
          btn.disabled = false;
        }
      });
    });

    var genBtn = root.querySelector("[data-intset-generate-token]");
    if (genBtn) {
      genBtn.addEventListener("click", async function () {
        genBtn.disabled = true;
        try {
          var data = await api(urls.generate, { method: "POST", body: {} }, root);
          var pane = root.querySelector('[data-provider-pane="whatsapp_meta"]');
          applyValues(pane, data.field_values || {}, data);
          var input = pane && pane.querySelector('[data-setting-key="webhook_verify_token"]');
          if (input && data.webhook_verify_token) input.value = data.webhook_verify_token;
          showAlert(alertEl, data.message || "Verify token generated.", "success");
        } catch (err) {
          showAlert(alertEl, err.message || "Generate failed", "danger");
        } finally {
          genBtn.disabled = false;
        }
      });
    }

    var testBtn = root.querySelector("[data-intset-test-whatsapp]");
    if (testBtn) {
      testBtn.addEventListener("click", async function () {
        var pane = root.querySelector('[data-provider-pane="whatsapp_meta"]');
        testBtn.disabled = true;
        try {
          var sendMsg = !!(
            pane &&
            pane.querySelector("[data-send-test-message]") &&
            pane.querySelector("[data-send-test-message]").checked
          );
          var toNumber =
            pane && pane.querySelector("[data-test-to-number]")
              ? pane.querySelector("[data-test-to-number]").value
              : "";
          var data = await api(
            urls.test,
            {
              method: "POST",
              body: { send_test_message: sendMsg, test_to_number: toNumber },
            },
            root
          );
          applyValues(pane, data.field_values || {}, data);
          setMissing(pane, data.missing_labels || []);
          showChecks(pane, data.checks || []);
          showAlert(alertEl, data.message || "Connection check finished.", data.ok ? "success" : "warning");
        } catch (err) {
          showAlert(alertEl, err.message || "Test failed", "danger");
        } finally {
          testBtn.disabled = false;
        }
      });
    }

    var connectBtn = root.querySelector("[data-intset-connect-meta]");
    if (connectBtn) {
      connectBtn.addEventListener("click", async function () {
        connectBtn.disabled = true;
        try {
          var data = await api(
            urls.connect + (urls.connect.indexOf("?") >= 0 ? "&" : "?") + "format=json",
            {},
            root
          );
          if (data.authorize_url) {
            window.location.href = data.authorize_url;
            return;
          }
          showAlert(alertEl, data.error || "Unable to start Connect Meta.", "danger");
        } catch (err) {
          showAlert(alertEl, err.message || "Connect Meta failed", "danger");
        } finally {
          connectBtn.disabled = false;
        }
      });
    }

    var guideBtn = root.querySelector("[data-intset-token-guide]");
    if (guideBtn) {
      guideBtn.addEventListener("click", async function () {
        try {
          var data = await api(urls.tokenGuide, {}, root);
          openGuideModal(data);
        } catch (err) {
          showAlert(alertEl, err.message || "Unable to load guide", "danger");
        }
      });
    }

    // Init status badges / missing from server-rendered data attributes
    root.querySelectorAll("[data-provider-pane]").forEach(function (pane) {
      var status = pane.getAttribute("data-initial-status") || "";
      var code = pane.getAttribute("data-initial-status-code") || "";
      setStatusBadge(pane, status, code);
      var missingRaw = pane.getAttribute("data-initial-missing") || "";
      if (missingRaw) setMissing(pane, missingRaw.split("|").filter(Boolean));
    });

    if (new URLSearchParams(window.location.search).get("wa_connect") === "1") {
      var waPane = root.querySelector('[data-provider-pane="whatsapp_meta"]');
      handlePendingStep(root, waPane, alertEl, urls).catch(function (err) {
        showAlert(alertEl, err.message || "Continue setup failed", "danger");
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
