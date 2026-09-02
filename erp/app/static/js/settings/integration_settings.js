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
    var timeoutMs = Number(opts.timeoutMs) || 0;
    delete opts.timeoutMs;
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
    var timer = null;
    if (timeoutMs && typeof AbortController !== "undefined") {
      var controller = new AbortController();
      opts.signal = controller.signal;
      timer = setTimeout(function () {
        controller.abort();
      }, timeoutMs);
    }
    var resp;
    try {
      resp = await fetch(url, opts);
    } catch (err) {
      if (err && (err.name === "AbortError" || err.name === "TimeoutError")) {
        throw new Error("Request timed out. Meta Graph did not respond in time. Try again.");
      }
      throw err;
    } finally {
      if (timer) clearTimeout(timer);
    }
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
      throw new Error(
        (data && (data.error || data.message)) || "Request failed (" + resp.status + ")"
      );
    }
    return data;
  }

  function showAlert(el, message, type) {
    if (!el) return;
    el.className = "alert alert-" + (type || "info") + " intset-alert is-visible";
    el.textContent = message;
  }

  function showToast(message, type) {
    var toastEl = document.getElementById("intsetToast");
    var body = document.getElementById("intsetToastBody");
    if (!toastEl || !body || typeof bootstrap === "undefined" || !bootstrap.Toast) {
      return false;
    }
    body.textContent = message || "Settings saved successfully";
    toastEl.classList.remove("text-bg-success", "text-bg-danger", "text-bg-warning", "text-bg-info");
    toastEl.classList.add(
      "text-bg-" +
        (type === "danger" ? "danger" : type === "warning" ? "warning" : type === "info" ? "info" : "success")
    );
    bootstrap.Toast.getOrCreateInstance(toastEl, { delay: 3200 }).show();
    return true;
  }

  var SECRET_MASK = "*********************";

  function isSecretMask(value) {
    var text = String(value == null ? "" : value).trim();
    return !text || /^\*+$/.test(text);
  }

  function collectValues(pane) {
    var values = {};
    pane.querySelectorAll("[data-setting-key]").forEach(function (input) {
      var key = input.getAttribute("data-setting-key");
      if (!key) return;
      if (input.getAttribute("data-input-type") === "checkbox" || input.type === "checkbox") {
        values[key] = input.checked ? "true" : "false";
        return;
      }
      if (input.getAttribute("data-secret") === "1" && isSecretMask(input.value)) {
        values[key] = input.getAttribute("data-has-secret") === "1" ? SECRET_MASK : "";
        return;
      }
      values[key] = input.value;
    });
    return values;
  }

  function clearSecretInputs(pane, secretConfigured) {
    if (!pane) return;
    pane.querySelectorAll("[data-secret='1']").forEach(function (input) {
      input.type = "password";
      var key = input.getAttribute("data-setting-key");
      var configured =
        secretConfigured && key && Object.prototype.hasOwnProperty.call(secretConfigured, key)
          ? !!secretConfigured[key]
          : input.getAttribute("data-has-secret") === "1";
      input.setAttribute("data-has-secret", configured ? "1" : "0");
      if (configured) {
        input.value = SECRET_MASK;
        input.placeholder = "Saved (encrypted)";
      } else {
        input.value = "";
        input.placeholder = "Enter new password";
      }
      var badge = pane.querySelector('[data-secret-badge="' + key + '"]');
      if (badge) badge.classList.toggle("d-none", !configured);
      var toggleBtn = pane.querySelector(
        '[data-intset-toggle-secret][data-target="#' + input.id + '"]'
      );
      if (toggleBtn) {
        var icon = toggleBtn.querySelector("i");
        if (icon) icon.className = "bi bi-eye";
      }
    });
  }

  function resolveStatusCode(status, statusCode) {
    var text = status || "Not Configured";
    var code = statusCode || "";
    if (code) return { text: text, code: code };
    if (/connected/i.test(text) && !/disconnect/i.test(text)) code = "connected";
    else if (/expired/i.test(text)) code = "token_expired";
    else if (/invalid/i.test(text)) code = "invalid_token";
    else if (/webhook/i.test(text) && /fail/i.test(text)) code = "webhook_failed";
    else if (/fail/i.test(text)) code = "failed";
    else if (/permission/i.test(text)) code = "permission_missing";
    else if (/disconnect/i.test(text)) code = "disconnected";
    else if (/partial/i.test(text)) code = "partial";
    else code = "not_configured";
    return { text: text, code: code };
  }

  function setStatusBadge(pane, status, statusCode) {
    var statusEl = pane.querySelector("[data-connection-status]");
    if (!statusEl) return;
    var resolved = resolveStatusCode(status, statusCode);
    var text = resolved.text;
    var code = resolved.code;
    var icon =
      code === "connected" ? "🟢" : code === "partial" ? "🟡" : "🔴";
    statusEl.textContent = icon + " " + text;
    statusEl.className = "intset-status";
    if (code === "connected") statusEl.classList.add("is-connected");
    else if (code === "partial") statusEl.classList.add("is-partial");
    else if (code === "token_expired" || code === "invalid_token" || code === "failed")
      statusEl.classList.add("is-expired");
    else statusEl.classList.add("is-not-configured");

    var hidden = pane.querySelector('[data-setting-key="connection_status"]');
    if (hidden) hidden.value = text;

    var waBadge = document.querySelector("[data-wa-status-badge]");
    if (waBadge) {
      waBadge.textContent = icon + " " + text;
      waBadge.className = "intset-status";
      if (code === "connected") waBadge.classList.add("is-connected");
      else if (code === "partial") waBadge.classList.add("is-partial");
      else if (code === "token_expired" || code === "invalid_token") waBadge.classList.add("is-expired");
      else waBadge.classList.add("is-not-configured");
    }
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
      if (input.getAttribute("data-secret") === "1") {
        return;
      }
      if (input.getAttribute("data-input-type") === "checkbox" || input.type === "checkbox") {
        input.checked = /^(1|true|yes|on)$/i.test(raw);
        return;
      }
      input.value = raw;
    });
    if (meta && meta.secret_configured) {
      clearSecretInputs(pane, meta.secret_configured);
    } else if (meta && meta.clear_secrets) {
      clearSecretInputs(pane, meta.secret_configured || null);
    }
    setStatusBadge(pane, values.connection_status, meta && meta.status_code);
    if (meta && meta.missing_labels) setMissing(pane, meta.missing_labels);
  }

  function showChecks(pane, checks) {
    var wraps = [];
    if (pane) {
      var a = pane.querySelector("[data-test-checks], [data-test-checks-form]");
      if (a) wraps.push(a);
    }
    var panel = document.querySelector("[data-wa-panel] [data-test-checks]");
    if (panel && wraps.indexOf(panel) < 0) wraps.push(panel);
    if (!wraps.length) return;
    var html = "";
    if (!checks || !checks.length) {
      wraps.forEach(function (w) {
        w.innerHTML = "<div class='text-muted small'>No check details returned.</div>";
      });
      return;
    }
    html = "<ul class='intset-checks mb-0'>";
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
    wraps.forEach(function (w) {
      w.innerHTML = html;
    });
  }

  function applyWaCard(card) {
    if (!card) return;
    function set(sel, val) {
      var el = document.querySelector(sel);
      if (el) el.textContent = val == null || val === "" ? "—" : String(val);
    }
    set("[data-wa-business-name]", card.business_name || "Meta WhatsApp");
    set("[data-wa-display-name]", card.display_name || "—");
    set("[data-wa-phone]", card.phone_number || "No phone selected");
    set("[data-wa-quality]", card.quality_rating);
    set("[data-wa-limit]", card.messaging_limit);
    set("[data-wa-account]", card.account_status);
    set("[data-wa-token-display]", card.token_display);
    set("[data-wa-token-expires]", card.token_expires_at);
    set("[data-wa-last-sync]", card.last_sync_at);
    set("[data-wa-webhook-url]", (card.webhook && card.webhook.webhook_url) || "—");
    var warn = document.querySelector("[data-wa-localhost-warn]");
    if (warn) {
      var msg = card.webhook && card.webhook.localhost_warning;
      warn.textContent = msg || "";
      warn.classList.toggle("d-none", !msg);
    }
    var events = document.querySelector("[data-wa-events]");
    if (events) {
      var fields = (card.webhook && card.webhook.subscribed_fields) || [];
      events.innerHTML = fields.length
        ? fields
            .map(function (ev) {
              return '<span class="badge text-bg-light border">' + ev + "</span>";
            })
            .join(" ")
        : '<span class="text-muted">None yet</span>';
    }
    var pane = document.querySelector('[data-provider-pane="whatsapp_meta"]');
    if (pane) setStatusBadge(pane, card.connection_status, card.status_code);
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
    var msg = data.message || "Phone selected and fields populated.";
    if (data.localhost_warning) msg += " " + data.localhost_warning;
    showAlert(alertEl, msg, data.localhost_warning ? "warning" : "success");
    if (urls.accountCard) {
      try {
        applyWaCard(await api(urls.accountCard, {}, root));
      } catch (_e) {}
    }
  }

  function init() {
    var root = document.getElementById("intsetPage");
    if (!root) return;

    var urls = {
      settings: root.getAttribute("data-api-settings"),
      generate: root.getAttribute("data-api-generate-token"),
      test: root.getAttribute("data-api-test-whatsapp"),
      testSmtp: root.getAttribute("data-api-test-smtp"),
      testField: root.getAttribute("data-api-test-field"),
      smtpAudit: root.getAttribute("data-api-smtp-audit"),
      connect: root.getAttribute("data-api-connect"),
      pendingStep: root.getAttribute("data-api-pending-step"),
      selectBusiness: root.getAttribute("data-api-select-business"),
      selectWaba: root.getAttribute("data-api-select-waba"),
      selectPhone: root.getAttribute("data-api-select-phone"),
      tokenGuide: root.getAttribute("data-api-token-guide"),
      refresh: root.getAttribute("data-api-refresh"),
      tokenHealth: root.getAttribute("data-api-token-health"),
      subscribe: root.getAttribute("data-api-subscribe"),
      unsubscribe: root.getAttribute("data-api-unsubscribe"),
      audit: root.getAttribute("data-api-audit"),
      accountCard: root.getAttribute("data-api-account-card"),
    };
    var alertEl = document.getElementById("intsetAlert");

    root.addEventListener("click", function (ev) {
      var toggleBtn = ev.target.closest("[data-intset-toggle-secret]");
      if (toggleBtn) {
        var toggleTarget = document.querySelector(toggleBtn.getAttribute("data-target") || "");
        if (!toggleTarget) return;
        var show = toggleTarget.type === "password";
        toggleTarget.type = show ? "text" : "password";
        var tIcon = toggleBtn.querySelector("i");
        if (tIcon) tIcon.className = show ? "bi bi-eye-slash" : "bi bi-eye";
        return;
      }
      var copyBtnSecret = ev.target.closest("[data-intset-copy-secret]");
      if (copyBtnSecret) {
        var copyTarget = document.querySelector(copyBtnSecret.getAttribute("data-target") || "");
        if (!copyTarget) return;
        var typed = copyTarget.value || "";
        if (!typed || isSecretMask(typed)) {
          showAlert(alertEl, "Nothing to copy — type a new value first. Saved secrets are never copied.", "warning");
          return;
        }
        var done = function () {
          showToast("Copied typed value", "success");
          showAlert(alertEl, "Copied typed value only (stored secret was not used).", "success");
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(typed).then(done).catch(function () {
            showAlert(alertEl, "Unable to copy.", "danger");
          });
        } else {
          copyTarget.type = "text";
          copyTarget.select();
          document.execCommand("copy");
          copyTarget.type = "password";
          done();
        }
      }
    });

    async function saveProvider(provider, btn) {
      var pane = root.querySelector('[data-provider-pane="' + provider + '"]');
      if (!pane) return;
      if (btn) btn.disabled = true;
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
        clearSecretInputs(pane, data.secret_configured || null);

        var msg = data.message || "Settings saved successfully";
        showToast(msg, "success");
        showAlert(alertEl, msg, "success");
      } catch (err) {
        showAlert(alertEl, err.message || "Save failed", "danger");
        showToast(err.message || "Save failed", "danger");
      } finally {
        if (btn) btn.disabled = false;
      }
    }

    root.querySelectorAll("[data-intset-save]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        saveProvider(btn.getAttribute("data-intset-save"), btn);
      });
    });

    document.addEventListener("keydown", function (ev) {
      if (!(ev.ctrlKey || ev.metaKey) || String(ev.key).toLowerCase() !== "s") return;
      var smtpPane = root.querySelector('[data-provider-pane="smtp"]');
      if (!smtpPane || !smtpPane.classList.contains("active")) return;
      ev.preventDefault();
      var saveBtn = smtpPane.querySelector('[data-intset-save="smtp"]');
      saveProvider("smtp", saveBtn);
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
          clearSecretInputs(pane, data.secret_configured || { webhook_verify_token: true });
          showAlert(alertEl, data.message || "Verify token generated.", "success");
          if (data.webhook_verify_token_plain) {
            var tokInput = document.getElementById("intsetVerifyTokenValue");
            if (tokInput) tokInput.value = data.webhook_verify_token_plain;
            var modalEl = document.getElementById("intsetVerifyTokenModal");
            if (modalEl) bootstrap.Modal.getOrCreateInstance(modalEl).show();
          }
        } catch (err) {
          showAlert(alertEl, err.message || "Generate failed", "danger");
        } finally {
          genBtn.disabled = false;
        }
      });
    }

    var copyBtn = document.getElementById("intsetVerifyTokenCopy");
    if (copyBtn) {
      copyBtn.addEventListener("click", function () {
        var tokInput = document.getElementById("intsetVerifyTokenValue");
        if (!tokInput || !tokInput.value) return;
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(tokInput.value).then(function () {
            showAlert(alertEl, "Verify token copied.", "success");
          });
        } else {
          tokInput.select();
          document.execCommand("copy");
          showAlert(alertEl, "Verify token copied.", "success");
        }
      });
    }

    function bindSimplePost(selector, urlKey, okMsg) {
      var btn = root.querySelector(selector);
      if (!btn || !urls[urlKey]) return;
      btn.addEventListener("click", async function () {
        btn.disabled = true;
        try {
          var data = await api(urls[urlKey], { method: "POST", body: {} }, root);
          showAlert(alertEl, data.message || okMsg, data.ok === false ? "warning" : "success");
          if (data.field_values) {
            var pane = root.querySelector('[data-provider-pane="whatsapp_meta"]');
            applyValues(pane, data.field_values, data);
          }
          if (urls.accountCard) applyWaCard(await api(urls.accountCard, {}, root));
        } catch (err) {
          showAlert(alertEl, err.message || "Request failed", "danger");
        } finally {
          btn.disabled = false;
        }
      });
    }
    bindSimplePost("[data-intset-refresh-meta]", "refresh", "Metadata refreshed.");
    bindSimplePost("[data-intset-subscribe]", "subscribe", "Webhooks subscribed.");
    bindSimplePost("[data-intset-unsubscribe]", "unsubscribe", "Webhooks unsubscribed.");

    var healthBtn = root.querySelector("[data-intset-token-health]");
    if (healthBtn && urls.tokenHealth) {
      healthBtn.addEventListener("click", async function () {
        healthBtn.disabled = true;
        try {
          var data = await api(urls.tokenHealth, {}, root);
          var pane = root.querySelector('[data-provider-pane="whatsapp_meta"]');
          if (pane) setStatusBadge(pane, data.status, data.status_code);
          showAlert(alertEl, data.message || data.status || "Token checked.", data.ok ? "success" : "warning");
          if (urls.accountCard) applyWaCard(await api(urls.accountCard, {}, root));
        } catch (err) {
          showAlert(alertEl, err.message || "Token check failed", "danger");
        } finally {
          healthBtn.disabled = false;
        }
      });
    }

    var auditBtn = root.querySelector("[data-intset-load-audit]");
    if (auditBtn && urls.audit) {
      auditBtn.addEventListener("click", async function () {
        try {
          var data = await api(urls.audit + "?limit=20", {}, root);
          var box = document.getElementById("intsetAuditBox");
          if (!box) return;
          var rows = data.rows || [];
          if (!rows.length) {
            box.innerHTML = "<span class='text-muted'>No audit entries.</span>";
            return;
          }
          box.innerHTML =
            "<div class='table-responsive'><table class='table table-sm mb-0'><thead><tr><th>When</th><th>Key</th><th>By</th></tr></thead><tbody>" +
            rows
              .map(function (r) {
                return (
                  "<tr><td>" +
                  (r.CreatedOn || "") +
                  "</td><td>" +
                  (r.SettingKey || "") +
                  "</td><td>" +
                  (r.ChangedByUserName || r.ChangedByUserID || "") +
                  "</td></tr>"
                );
              })
              .join("") +
            "</tbody></table></div>";
        } catch (err) {
          showAlert(alertEl, err.message || "Audit load failed", "danger");
        }
      });
    }

    function escapeFieldTest(text) {
      return String(text == null ? "" : text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function setFieldTestResult(el, ok, message) {
      if (!el) return;
      el.className = "intset-field-test-result " + (ok ? "is-ok" : "is-bad");
      el.innerHTML =
        "<span class='intset-field-test-mark'>" +
        (ok ? "✓" : "✕") +
        "</span> " +
        escapeFieldTest(message || (ok ? "OK" : "Failed"));
    }

    root.querySelectorAll("[data-intset-field-test]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        if (!urls.testField) return;
        var provider = btn.getAttribute("data-intset-field-test") || "";
        var field = btn.getAttribute("data-field-key") || "";
        var pane = root.querySelector('[data-provider-pane="' + provider + '"]');
        var resultEl = root.querySelector(
          '[data-field-test-result="' + provider + "-" + field + '"]'
        );
        btn.disabled = true;
        if (resultEl) {
          resultEl.className = "intset-field-test-result is-busy";
          resultEl.textContent = "Testing…";
        }
        try {
          var data = await api(
            urls.testField,
            {
              method: "POST",
              body: {
                provider: provider,
                field: field,
                values: pane ? collectValues(pane) : {},
              },
            },
            root
          );
          setFieldTestResult(resultEl, !!data.ok, data.message || data.error || "");
        } catch (err) {
          setFieldTestResult(resultEl, false, err.message || "Test failed");
        } finally {
          btn.disabled = false;
        }
      });
    });

    var testBtn = root.querySelector("[data-intset-test-whatsapp]");
    if (testBtn) {
      testBtn.addEventListener("click", async function () {
        var pane = root.querySelector('[data-provider-pane="whatsapp_meta"]');
        if (!pane) return;
        if (!urls.test) {
          showAlert(alertEl, "Test Connection URL missing. Refresh the page.", "danger");
          return;
        }
        var resultBox = pane.querySelector("[data-whatsapp-test-result]");
        var checksBox = pane.querySelector("[data-test-checks-form]");
        var busyMsg = "Testing Meta WhatsApp connection… this can take up to a minute.";
        var prevHtml = testBtn.innerHTML;
        testBtn.disabled = true;
        testBtn.innerHTML =
          '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Testing…';
        if (resultBox) {
          resultBox.innerHTML = '<div class="alert alert-info py-2 small mb-0">' + busyMsg + "</div>";
          try {
            resultBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
          } catch (_e) {}
        } else if (checksBox) {
          checksBox.innerHTML = '<div class="text-muted small">' + busyMsg + "</div>";
        }
        showToast("Testing WhatsApp connection…", "info");
        try {
          var sendMsg = !!(
            pane.querySelector("[data-send-test-message]") &&
            pane.querySelector("[data-send-test-message]").checked
          );
          var toNumber = pane.querySelector("[data-test-to-number]")
            ? pane.querySelector("[data-test-to-number]").value
            : "";
          var data = await api(
            urls.test,
            {
              method: "POST",
              timeoutMs: 90000,
              body: { send_test_message: sendMsg, test_to_number: toNumber },
            },
            root
          );
          applyValues(pane, data.field_values || {}, data);
          setMissing(pane, data.missing_labels || []);
          showChecks(pane, data.checks || []);
          var ok = !!data.ok;
          var msg = data.message || (ok ? "Connection check finished." : "Some checks failed.");
          if (resultBox) {
            resultBox.innerHTML =
              '<div class="alert alert-' +
              (ok ? "success" : "warning") +
              ' py-2 small mb-0">' +
              (ok ? "✔ " : "⚠ ") +
              msg +
              "</div>";
            try {
              resultBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
            } catch (_e2) {}
          }
          showToast(msg, ok ? "success" : "warning");
          showAlert(alertEl, msg, ok ? "success" : "warning");
        } catch (err) {
          var failMsg = err.message || "Test failed";
          showChecks(pane, [{ name: "Connection test", ok: false, detail: failMsg }]);
          if (resultBox) {
            resultBox.innerHTML =
              '<div class="alert alert-danger py-2 small mb-0">❌ ' + failMsg + "</div>";
            try {
              resultBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
            } catch (_e3) {}
          }
          showToast(failMsg, "danger");
          showAlert(alertEl, failMsg, "danger");
        } finally {
          testBtn.innerHTML = prevHtml;
          testBtn.disabled = false;
        }
      });
    }

    var smtpTestBtn = root.querySelector("[data-intset-test-smtp]");
    if (smtpTestBtn && urls.testSmtp) {
      smtpTestBtn.addEventListener("click", async function () {
        var pane = root.querySelector('[data-provider-pane="smtp"]');
        if (!pane) return;
        smtpTestBtn.disabled = true;
        var resultBox = pane.querySelector("[data-smtp-test-result]");
        if (resultBox) resultBox.innerHTML = '<div class="text-muted small">Testing SMTP connection…</div>';
        try {
          var data = await api(
            urls.testSmtp,
            { method: "POST", body: { values: collectValues(pane) } },
            root
          );
          applyValues(pane, data.field_values || data.values || {}, data);
          setMissing(pane, data.missing_labels || []);
          clearSecretInputs(pane, data.secret_configured || null);
          var ok = !!data.ok;
          var msg = data.message || (ok ? "Connection Successful" : "Connection failed");
          if (resultBox) {
            resultBox.innerHTML =
              '<div class="alert alert-' +
              (ok ? "success" : "danger") +
              ' py-2 small mb-0">' +
              (ok ? "✔ " : "❌ ") +
              msg +
              "</div>";
          }
          showToast(msg, ok ? "success" : "danger");
          showAlert(alertEl, msg, ok ? "success" : "danger");
        } catch (err) {
          var failMsg = err.message || "Connection failed";
          if (resultBox) {
            resultBox.innerHTML =
              '<div class="alert alert-danger py-2 small mb-0">❌ ' + failMsg + "</div>";
          }
          showToast(failMsg, "danger");
          showAlert(alertEl, failMsg, "danger");
        } finally {
          smtpTestBtn.disabled = false;
        }
      });
    }

    var smtpAuditBtn = root.querySelector("[data-intset-load-smtp-audit]");
    if (smtpAuditBtn && urls.smtpAudit) {
      smtpAuditBtn.addEventListener("click", async function () {
        try {
          var data = await api(urls.smtpAudit + "?limit=20", {}, root);
          var box = document.getElementById("intsetSmtpAuditBox");
          if (!box) return;
          var rows = data.rows || [];
          if (!rows.length) {
            box.innerHTML = "<span class='text-muted small'>No SMTP audit entries yet.</span>";
            return;
          }
          box.innerHTML =
            "<div class='table-responsive'><table class='table table-sm mb-0'><thead><tr><th>When</th><th>Key</th><th>By</th><th>IP</th></tr></thead><tbody>" +
            rows
              .map(function (r) {
                return (
                  "<tr><td>" +
                  (r.CreatedOn || "") +
                  "</td><td>" +
                  (r.SettingKey || "") +
                  "</td><td>" +
                  (r.ChangedByUserName || r.ChangedByUserID || "") +
                  "</td><td>" +
                  (r.IPAddress || "—") +
                  "</td></tr>"
                );
              })
              .join("") +
            "</tbody></table></div>";
        } catch (err) {
          showAlert(alertEl, err.message || "Audit load failed", "danger");
        }
      });
    }

    var connectBtn = root.querySelector("[data-intset-connect-meta]");
    if (connectBtn) {
      connectBtn.addEventListener("click", async function () {
        var pane = root.querySelector('[data-provider-pane="whatsapp_meta"]');
        connectBtn.disabled = true;
        try {
          if (pane) {
            var saved = await api(
              urls.settings,
              {
                method: "POST",
                body: { provider: "whatsapp_meta", values: collectValues(pane) },
              },
              root
            );
            applyValues(pane, saved.field_values || saved.values || {}, saved);
            setMissing(pane, saved.missing_labels || []);
            clearSecretInputs(pane, saved.secret_configured || null);
          }
          var data = await api(
            urls.connect + (urls.connect.indexOf("?") >= 0 ? "&" : "?") + "format=json",
            {},
            root
          );
          if (data.authorize_url) {
            showAlert(
              alertEl,
              "Facebook login page open ho rahi hai — password/OTP wahan daalein…",
              "info"
            );
            window.location.href = data.authorize_url;
            return;
          }
          showAlert(alertEl, data.error || "Unable to start Connect Facebook.", "danger");
        } catch (err) {
          showAlert(alertEl, err.message || "Connect Facebook failed", "danger");
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
      clearSecretInputs(pane, null);
    });

    root.querySelectorAll("[data-secret='1']").forEach(function (input) {
      input.addEventListener("focus", function () {
        if (input.getAttribute("data-has-secret") === "1" && isSecretMask(input.value)) {
          input.select();
        }
      });
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
