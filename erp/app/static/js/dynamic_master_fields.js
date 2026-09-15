(function (global) {
  "use strict";

  const EXTRA_KEYS = ["purchase_date", "depreciation_rate", "appreciation_rate"];
  const FIELD_ORDER = [
    "purchase_date",
    "depreciation_rate",
    "appreciation_rate",
    "investment_kind",
    "property_state",
    "property_district",
    "property_tehsil",
    "property_pincode",
    "property_village",
    "property_land_area",
    "property_land_unit",
    "property_land_value",
  ];
  const FIELD_RANK = {};
  FIELD_ORDER.forEach(function (key, idx) {
    FIELD_RANK[key] = idx;
  });

  function sortFields(fields) {
    return (fields || []).slice().sort(function (a, b) {
      const ia = FIELD_RANK[a && a.key];
      const ib = FIELD_RANK[b && b.key];
      if (ia == null && ib == null) return 0;
      if (ia == null) return 1;
      if (ib == null) return -1;
      return ia - ib;
    });
  }
  const EMPTY_EXTRAS = {
    purchase_date: "",
    depreciation_rate: "0",
    appreciation_rate: "0",
  };

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fieldSpec(config, key) {
    const fields = (config && config.fields) || {};
    return fields[key] || null;
  }

  function profileForSelect(select, config) {
    const id = String(select && select.value ? select.value : "").trim();
    if (!id) return "";
    const map = (config && config.group_profiles) || {};
    if (map[id]) return map[id];
    const opt = select.selectedOptions && select.selectedOptions[0];
    return (opt && (opt.getAttribute("data-dyn-profile") || "")) || "";
  }

  function visibleFields(config, profileKey) {
    const profile = ((config && config.profiles) || {})[profileKey];
    if (!profile) return [];
    const required = {};
    (profile.required || []).forEach(function (key) {
      required[key] = true;
    });
    return (profile.fields || [])
      .map(function (key) {
        const spec = fieldSpec(config, key);
        if (!spec) return null;
        const row = Object.assign({}, spec);
        row.required = !!spec.required || !!required[key];
        return row;
      })
      .filter(Boolean);
  }

  function emptyCollect() {
    return Object.assign({ values: {}, dyn_values: {} }, EMPTY_EXTRAS);
  }

  function bind(opts) {
    opts = opts || {};
    const select = opts.select;
    const mount = opts.mount;
    const includeCustomerFields = !!opts.includeCustomerFields;

    function liveConfig() {
      return global.JTCS_DYN_MASTER_FIELDS || opts.config || {};
    }

    function skipKeysMap() {
      const skipKeys = {};
      ((liveConfig().skip_keys) || ["customer_name", "customer_group"]).forEach(function (key) {
        skipKeys[key] = true;
      });
      return skipKeys;
    }
    if (!select || !mount) {
      return {
        collect: function () {
          return emptyCollect();
        },
        apply: function () {},
        validate: function () {
          return [];
        },
        sync: function () {},
        setReadonly: function () {},
        appendToFormData: function (fd) {
          const extras = emptyCollect();
          if (fd) {
            fd.set("purchase_date", extras.purchase_date);
            fd.set("PurchaseDate", extras.purchase_date);
            fd.set("depreciation_rate", extras.depreciation_rate);
            fd.set("DepreciationRate", extras.depreciation_rate);
            fd.set("appreciation_rate", extras.appreciation_rate);
            fd.set("AppreciationRate", extras.appreciation_rate);
          }
          return extras;
        },
        profileKey: function () {
          return "";
        },
      };
    }

    let values = {
      purchase_date: "",
      depreciation_rate: "0",
      appreciation_rate: "0",
    };
    let readonly = false;

    function entityName() {
      if (typeof opts.getEntityName === "function") {
        return String(opts.getEntityName() || "").trim();
      }
      return "";
    }

    function openingDateValue() {
      const el = opts.openingDateEl;
      return el && el.value ? String(el.value).slice(0, 10) : "";
    }

    function profileKey() {
      return profileForSelect(select, liveConfig());
    }

    function inputId(key) {
      return (opts.idPrefix || "jtcsDyn") + "_" + key;
    }

    function builtinId(key) {
      return (opts.builtinPrefix || "cm_") + key;
    }

    function isSkipped(key) {
      return !!skipKeysMap()[key];
    }

    function isBuiltinOnAllowedTab(field) {
      if (!includeCustomerFields) return false;
      if (typeof opts.isBuiltinShown === "function") {
        return !!opts.isBuiltinShown(field.key);
      }
      const el =
        document.getElementById(builtinId(field.key)) ||
        document.querySelector('[data-cm-field="' + field.key + '"]');
      if (!el) return false;
      const panel = el.closest(".cm-tab-panel");
      if (!panel) return true;
      const tab = panel.getAttribute("data-tab") || "";
      return !!(tab && document.querySelector('#cmTabNav [data-tab="' + tab + '"]'));
    }

    function fieldValueNow(key) {
      const el = document.getElementById(inputId(key));
      if (el) return String(el.value || "").trim();
      const builtin = document.getElementById(builtinId(key));
      if (builtin) return String(builtin.value || "").trim();
      return String(values[key] != null ? values[key] : "").trim();
    }

    function valueMatchesRule(current, allowed) {
      if (allowed === "*" || allowed === true) return !!current;
      if (Array.isArray(allowed)) return allowed.indexOf(current) >= 0;
      return current === String(allowed);
    }

    function matchesVisibleWhen(field) {
      const when = field.visible_when || {};
      const any = field.visible_when_any || {};
      const deps = Object.keys(when);
      const anyDeps = Object.keys(any);
      if (!deps.length && !anyDeps.length) return true;
      const allOk = deps.every(function (dep) {
        return valueMatchesRule(fieldValueNow(dep), when[dep]);
      });
      const anyOk =
        !anyDeps.length ||
        anyDeps.some(function (dep) {
          return valueMatchesRule(fieldValueNow(dep), any[dep]);
        });
      return allOk && anyOk;
    }

    function catalogPropertyFields() {
      const all = (liveConfig().fields) || {};
      return Object.keys(all)
        .map(function (key) {
          return Object.assign({}, all[key]);
        })
        .filter(function (row) {
          return row.section === "property" || row.source === "property";
        });
    }

    function expandPropertyBundle(fields) {
      if (!includeCustomerFields) return fields;
      const hasProperty = fields.some(function (field) {
        return field && (field.section === "property" || field.source === "property" || field.key === "investment_kind");
      });
      if (!hasProperty && profileKey() !== "investments") return fields;
      const seen = {};
      fields.forEach(function (field) {
        if (field && field.key) seen[field.key] = true;
      });
      catalogPropertyFields().forEach(function (row) {
        if (!row.key || seen[row.key]) return;
        seen[row.key] = true;
        fields.push(row);
      });
      return fields;
    }

    function currentFields() {
      const id = String(select && select.value ? select.value : "").trim();
      const cfg = liveConfig();
      const mapped = ((cfg && cfg.group_fields) || {})[id];
      let fields;
      if (mapped && mapped.configured) {
        fields = (mapped.fields || []).map(function (row) {
          return Object.assign({}, row);
        });
      } else {
        fields = visibleFields(cfg, profileKey());
      }
      fields = expandPropertyBundle(fields);
      return sortFields(
        fields.filter(function (field) {
          if (!field || !field.key || isSkipped(field.key)) return false;
          if (!includeCustomerFields && EXTRA_KEYS.indexOf(field.key) < 0) return false;
          if (!matchesVisibleWhen(field)) return false;
          return true;
        })
      );
    }

    function renderableFields() {
      return currentFields().filter(function (field) {
        return !isBuiltinOnAllowedTab(field);
      });
    }

    function readMountValues() {
      renderableFields().forEach(function (field) {
        const el = document.getElementById(inputId(field.key));
        if (!el) return;
        values[field.key] = el.value;
      });
    }

    function fieldLabel(field) {
      const name = entityName();
      if (name && field.label_template) {
        return String(field.label_template).replace("{entity}", name);
      }
      return String(field.label || field.key);
    }

    function selectOptionsHtml(field, current) {
      const src = document.getElementById(builtinId(field.key));
      let html = "";
      if (src && src.tagName === "SELECT") {
        Array.prototype.forEach.call(src.options, function (opt) {
          html +=
            '<option value="' +
            escapeHtml(opt.value) +
            '"' +
            (String(opt.value) === String(current) ? " selected" : "") +
            ">" +
            escapeHtml(opt.text) +
            "</option>";
        });
        return html;
      }
      html = '<option value=""></option>';
      (field.options || []).forEach(function (opt) {
        const value = typeof opt === "string" ? opt : opt.value;
        const label = typeof opt === "string" ? opt : opt.label || opt.value;
        html +=
          '<option value="' +
          escapeHtml(value) +
          '"' +
          (String(value) === String(current) ? " selected" : "") +
          ">" +
          escapeHtml(label) +
          "</option>";
      });
      return html;
    }

    function indiaLocLevel(field) {
      const feats = field.features || [];
      for (let i = 0; i < feats.length; i++) {
        const token = String(feats[i] || "");
        if (token.indexOf("india_loc:") === 0) return token.slice(10);
      }
      return "";
    }

    function inputHtml(field) {
      const id = inputId(field.key);
      const current = values[field.key] != null ? values[field.key] : "";
      const disabled = readonly ? " disabled" : "";
      const max = field.maxlength ? ' maxlength="' + escapeHtml(String(field.maxlength)) + '"' : "";
      const loc = indiaLocLevel(field);
      const name =
        ' name="' +
        escapeHtml(field.key) +
        '" data-dyn-field="' +
        escapeHtml(field.key) +
        '"' +
        (loc ? ' data-india-loc="' + escapeHtml(loc) + '"' : "");
      const type = field.type || "text";
      if (type === "percent") {
        return (
          '<div class="input-group input-group-sm">' +
          '<input type="number" class="form-control form-control-sm" id="' +
          id +
          '"' +
          name +
          ' step="0.01" min="0" max="100" value="' +
          escapeHtml(current || "0") +
          '"' +
          disabled +
          ">" +
          '<span class="input-group-text">%</span>' +
          "</div>"
        );
      }
      if (type === "money" || (field.features || []).indexOf("land_value_sync") >= 0) {
        return (
          '<div class="input-group input-group-sm">' +
          '<span class="input-group-text">₹</span>' +
          '<input type="number" class="form-control form-control-sm" id="' +
          id +
          '"' +
          name +
          ' step="0.01" min="0" value="' +
          escapeHtml(current || "") +
          '"' +
          disabled +
          ">" +
          '<button type="button" class="btn btn-outline-primary jtcs-dyn-land-sync"' +
          disabled +
          ' title="Fill from the public circle-rate / ready reckoner value">' +
          '<i class="bi bi-arrow-repeat"></i> Sync</button>' +
          "</div>" +
          '<div class="form-text jtcs-dyn-land-msg"></div>'
        );
      }
      if (type === "textarea") {
        return (
          '<textarea class="form-control form-control-sm" id="' +
          id +
          '"' +
          name +
          " rows=\"2\"" +
          max +
          disabled +
          ">" +
          escapeHtml(current) +
          "</textarea>"
        );
      }
      if (type === "select") {
        return (
          '<select class="form-select form-select-sm" id="' +
          id +
          '"' +
          name +
          disabled +
          ">" +
          selectOptionsHtml(field, current) +
          "</select>"
        );
      }
      const inputType =
        type === "date" ? "date" : type === "number" ? "number" : type === "email" ? "email" : "text";
      const extra = type === "number" ? ' step="any"' : type === "date" ? "" : max;
      const shown =
        type === "date" ? escapeHtml(String(current || "").slice(0, 10)) : escapeHtml(current);
      return (
        '<input type="' +
        inputType +
        '" class="form-control form-control-sm" id="' +
        id +
        '"' +
        name +
        extra +
        ' value="' +
        shown +
        '"' +
        disabled +
        ">"
      );
    }

    function render() {
      readMountValues();
      const fields = renderableFields();
      if (!fields.length) {
        mount.innerHTML = "";
        mount.classList.add("d-none");
        return;
      }
      mount.classList.remove("d-none");
      applyPropertyLandDefaults();
      function fieldBlock(field) {
        const req = field.required ? '<span class="text-danger">*</span>' : "";
        return (
          '<div class="col-6 col-md-3 jtcs-dyn-field">' +
          '<label class="form-label" for="' +
          inputId(field.key) +
          '"' +
          (field.hint ? ' title="' + escapeHtml(field.hint) + '"' : "") +
          ">" +
          escapeHtml(fieldLabel(field)) +
          req +
          "</label>" +
          inputHtml(field) +
          "</div>"
        );
      }
      mount.innerHTML =
        '<div class="row g-1 jtcs-dyn-master-fields-row jtcs-dyn-compact">' +
        fields.map(fieldBlock).join("") +
        "</div>";

      const purchaseEl = document.getElementById(inputId("purchase_date"));
      if (purchaseEl && !purchaseEl.value && openingDateValue()) {
        purchaseEl.value = openingDateValue();
        values.purchase_date = purchaseEl.value;
      }

      const landBtn = mount.querySelector(".jtcs-dyn-land-sync");
      if (landBtn) {
        landBtn.addEventListener("click", function () {
          syncLandPurchaseValue(true).catch(function (err) {
            if (typeof opts.onError === "function") opts.onError(err);
            else if (global.JTCSDialog && JTCSDialog.alert) JTCSDialog.alert(err.message || String(err), "error");
          });
        });
      }
      ["property_land_area", "property_land_unit"].forEach(function (key) {
        const el = document.getElementById(inputId(key));
        if (!el) return;
        el.addEventListener("change", function () {
          values[key] = el.value;
          scheduleLandValueSync();
        });
        if (key === "property_land_area") {
          el.addEventListener("blur", function () {
            values[key] = el.value;
            scheduleLandValueSync();
          });
        }
      });
      mount.querySelectorAll("[data-dyn-field]").forEach(function (el) {
        const key = el.getAttribute("data-dyn-field");
        if (key !== "investment_kind") return;
        el.addEventListener("change", function () {
          values[key] = el.value;
          render();
        });
      });
      bindIndiaLocationCascade();
      if (typeof opts.onChange === "function") opts.onChange(profileKey(), collect());
    }

    const DEFAULT_LAND_AREA = "1";
    const DEFAULT_LAND_UNIT = "Sq. Ft.";
    const INDIA_CHILD_KEYS = {
      property_state: ["property_district", "property_tehsil", "property_pincode", "property_village"],
      property_district: ["property_tehsil", "property_pincode", "property_village"],
      property_tehsil: ["property_pincode", "property_village"],
      property_pincode: ["property_village"],
    };
    const INDIA_CHILD_LEVELS = {
      property_state: ["districts", "talukas", "pincodes", "places"],
      property_district: ["talukas", "pincodes", "places"],
      property_tehsil: ["pincodes", "places"],
      property_pincode: ["places"],
    };
    const INDIA_FILL_ORDER = ["states", "districts", "talukas", "pincodes", "places"];
    const INDIA_PARENT_HINT = {
      districts: "Select State first",
      talukas: "Select District first",
      pincodes: "Select Tehsil / Taluka first",
      places: "Select Pincode first",
    };
    let indiaLocSeq = 0;
    let indiaFillLock = false;

    function applyPropertyLandDefaults() {
      if (fieldValueNow("investment_kind") !== "Property") return;
      const area = String(values.property_land_area != null ? values.property_land_area : "").trim();
      if (!area || area === "0" || area === "0.00") values.property_land_area = DEFAULT_LAND_AREA;
      if (!String(values.property_land_unit || "").trim()) values.property_land_unit = DEFAULT_LAND_UNIT;
    }

    function pinDigits(raw) {
      const match = String(raw || "").match(/\d{6}/);
      return match ? match[0] : "";
    }

    function indiaLocationUrl() {
      return (
        opts.indiaLocationUrl ||
        "/api/dynamic-master-fields/india-locations"
      );
    }

    function pickSavedLocValue(rows, current) {
      const want = String(current || "").trim();
      if (!want) return "";
      const fold = want.toLowerCase();
      const pin = pinDigits(want);
      for (let i = 0; i < rows.length; i++) {
        const value = String(rows[i].value || "");
        const label = String(rows[i].label || value);
        if (value === want || label === want) return value;
        if (value.toLowerCase() === fold || label.toLowerCase() === fold) return value;
        if (pin && pinDigits(value) === pin) return value;
      }
      return pin || want;
    }

    function setIndiaSelectOptions(el, rows, current, emptyLabel) {
      let keep = pickSavedLocValue(rows, current);
      if (!keep && rows && rows.length === 1) keep = String(rows[0].value || "");
      let html =
        '<option value="">' +
        escapeHtml(rows && rows.length ? "" : emptyLabel || "") +
        "</option>";
      let found = false;
      (rows || []).forEach(function (row) {
        const value = String(row.value || "");
        const label = String(row.label || value);
        if (value === keep) found = true;
        html +=
          '<option value="' +
          escapeHtml(value) +
          '"' +
          (value === keep ? " selected" : "") +
          ">" +
          escapeHtml(label) +
          "</option>";
      });
      if (keep && !found) {
        html +=
          '<option value="' +
          escapeHtml(keep) +
          '" selected>' +
          escapeHtml(keep) +
          "</option>";
      }
      const prevLock = indiaFillLock;
      indiaFillLock = true;
      el.innerHTML = html;
      el.value = keep;
      indiaFillLock = prevLock;
      const key = el.getAttribute("data-dyn-field");
      if (key) values[key] = keep;
    }

    function indiaParentReady(level) {
      const state = fieldValueNow("property_state");
      const district = fieldValueNow("property_district");
      const taluka = fieldValueNow("property_tehsil");
      const pincode = pinDigits(fieldValueNow("property_pincode"));
      if (level === "states") return true;
      if (level === "districts") return !!state;
      if (level === "talukas") return !!(state && district);
      if (level === "pincodes") return !!(state && district && taluka);
      if (level === "places") return !!pincode;
      return !!state;
    }

    function fillIndiaSelect(el) {
      const level = el.getAttribute("data-india-loc");
      if (!level) return Promise.resolve();
      const key = el.getAttribute("data-dyn-field");
      const current = (key && values[key] != null ? values[key] : el.value) || "";
      if (!indiaParentReady(level)) {
        setIndiaSelectOptions(el, [], "", INDIA_PARENT_HINT[level] || "");
        return Promise.resolve();
      }
      const params = new URLSearchParams();
      params.set("level", level);
      const state = fieldValueNow("property_state");
      const district = fieldValueNow("property_district");
      const taluka = fieldValueNow("property_tehsil");
      const pincode = pinDigits(fieldValueNow("property_pincode"));
      if (state) params.set("state", state);
      if (district) params.set("district", district);
      if (taluka) params.set("taluka", taluka);
      if (pincode) params.set("pincode", pincode);
      const prevLock = indiaFillLock;
      indiaFillLock = true;
      el.innerHTML = '<option value="">Loading…</option>';
      indiaFillLock = prevLock;
      return fetch(indiaLocationUrl() + "?" + params.toString(), {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      })
        .then(function (res) {
          return res.json().then(function (data) {
            if (!res.ok || data.ok === false) throw new Error(data.error || "Lookup failed");
            return data;
          });
        })
        .then(function (data) {
          const rows = data.rows || [];
          setIndiaSelectOptions(el, rows, current, rows.length ? "" : "No options found");
        })
        .catch(function () {
          setIndiaSelectOptions(el, [], current, "Unable to load");
        });
    }

    function fillIndiaLevels(levels) {
      const seq = ++indiaLocSeq;
      const want = levels || INDIA_FILL_ORDER;
      const nodes = Array.prototype.slice.call(mount.querySelectorAll("[data-india-loc]"));
      if (!nodes.length) return Promise.resolve();
      indiaFillLock = true;
      let chain = Promise.resolve();
      want.forEach(function (level) {
        chain = chain.then(function () {
          if (seq !== indiaLocSeq) return;
          return Promise.all(
            nodes
              .filter(function (el) {
                return el.getAttribute("data-india-loc") === level;
              })
              .map(function (el) {
                return fillIndiaSelect(el);
              })
          );
        });
      });
      return chain.finally(function () {
        if (seq === indiaLocSeq) indiaFillLock = false;
      }).then(function () {
        if (seq === indiaLocSeq) scheduleLandValueSync();
      });
    }

    function clearChildLocValues(parentKey) {
      (INDIA_CHILD_KEYS[parentKey] || []).forEach(function (key) {
        values[key] = "";
        const el = document.getElementById(inputId(key));
        if (el) el.value = "";
      });
    }

    function bindIndiaLocationCascade() {
      fillIndiaLevels(INDIA_FILL_ORDER);
      mount.querySelectorAll("[data-india-loc]").forEach(function (el) {
        el.addEventListener("change", function () {
          if (indiaFillLock) return;
          const key = el.getAttribute("data-dyn-field");
          values[key] = el.value;
          clearChildLocValues(key);
          fillIndiaLevels(INDIA_CHILD_LEVELS[key] || []);
        });
      });
    }

    let landSyncTimer = null;
    let landSyncBusy = false;

    function landValueUrl() {
      return opts.landValueSyncUrl || "/api/dynamic-master-fields/land-value-sync";
    }

    function landSyncReady() {
      if (fieldValueNow("investment_kind") !== "Property") return false;
      if (!fieldValueNow("property_state") || !fieldValueNow("property_district")) return false;
      if (!fieldValueNow("property_tehsil")) return false;
      if (!pinDigits(fieldValueNow("property_pincode"))) return false;
      if (!fieldValueNow("property_village")) return false;
      if (!fieldValueNow("property_land_area") || !fieldValueNow("property_land_unit")) return false;
      return true;
    }

    function scheduleLandValueSync() {
      if (landSyncTimer) global.clearTimeout(landSyncTimer);
      landSyncTimer = global.setTimeout(function () {
        if (!landSyncReady()) return;
        syncLandPurchaseValue(false).catch(function () {});
      }, 500);
    }

    function applyLandValueToMaster(amount) {
      const ob = opts.openingBalanceEl || document.getElementById("cm_opening_balance");
      if (ob) ob.value = amount;
      const purchase = fieldValueNow("purchase_date") || openingDateValue();
      const obd = opts.openingDateEl || document.getElementById("cm_opening_balance_date");
      if (obd && purchase && !obd.value) obd.value = purchase;
      const dr = document.getElementById("cm_opening_balance_dr");
      if (dr) dr.checked = true;
    }

    function syncLandPurchaseValue(manual) {
      if (!landSyncReady()) {
        if (manual) throw new Error("Fill State → District → Tehsil → Pincode → Village/Area first.");
        return Promise.resolve();
      }
      if (landSyncBusy && !manual) return Promise.resolve();
      landSyncBusy = true;
      const params = new URLSearchParams();
      params.set("state", fieldValueNow("property_state"));
      params.set("district", fieldValueNow("property_district"));
      params.set("tehsil", fieldValueNow("property_tehsil"));
      params.set("village", fieldValueNow("property_village"));
      params.set("land_area", fieldValueNow("property_land_area"));
      params.set("land_unit", fieldValueNow("property_land_unit"));
      const btn = mount.querySelector(".jtcs-dyn-land-sync");
      const msg = mount.querySelector(".jtcs-dyn-land-msg");
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
      }
      if (msg) msg.textContent = "Looking up public land value…";
      return fetch(landValueUrl() + "?" + params.toString(), {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      })
        .then(function (res) {
          return res.json().then(function (data) {
            if (!res.ok || data.ok === false) throw new Error(data.error || "Land value lookup failed.");
            return data;
          });
        })
        .then(function (data) {
          const amount = data.value || "";
          const el = document.getElementById(inputId("property_land_value"));
          if (el) el.value = amount;
          values.property_land_value = amount;
          applyLandValueToMaster(amount);
          if (msg) {
            msg.textContent =
              (data.unit_rate_label ? data.unit_rate_label + " × " + fieldValueNow("property_land_area") + " = " : "") +
              "₹" +
              amount +
              (data.matched_place ? " — " + data.matched_place : "");
          }
        })
        .finally(function () {
          landSyncBusy = false;
          if (btn) {
            btn.disabled = readonly;
            btn.innerHTML = '<i class="bi bi-arrow-repeat"></i> Sync';
          }
        });
    }

    function copyDynToBuiltin(field) {
      const dynEl = document.getElementById(inputId(field.key));
      const cmEl = document.getElementById(builtinId(field.key));
      if (!dynEl || !cmEl) return;
      if (cmEl.type === "radio") {
        const radios = document.querySelectorAll('[data-cm-field="' + field.key + '"]');
        radios.forEach(function (radio) {
          radio.checked = String(radio.value) === String(dynEl.value);
        });
        return;
      }
      cmEl.value = dynEl.value;
    }

    function collect() {
      readMountValues();
      const rendered = {};
      renderableFields().forEach(function (field) {
        rendered[field.key] = true;
        copyDynToBuiltin(field);
      });
      if (rendered.purchase_date && !values.purchase_date && openingDateValue()) {
        values.purchase_date = openingDateValue();
      }
      const visible = {};
      currentFields().forEach(function (field) {
        visible[field.key] = true;
      });
      const collected = {};
      const dynValues = {};
      renderableFields().forEach(function (field) {
        const raw = values[field.key] != null ? values[field.key] : "";
        collected[field.key] = raw;
        if (field.source === "custom" || field.source === "property") dynValues[field.key] = raw;
      });
      const catalog = (liveConfig().fields) || {};
      Object.keys(values).forEach(function (key) {
        const spec = catalog[key];
        if (!spec || (spec.source !== "custom" && spec.source !== "property")) return;
        if (dynValues[key] == null) dynValues[key] = values[key] != null ? values[key] : "";
      });
      return {
        purchase_date: visible.purchase_date ? values.purchase_date || "" : "",
        depreciation_rate: visible.depreciation_rate ? values.depreciation_rate || "0" : "0",
        appreciation_rate: visible.appreciation_rate ? values.appreciation_rate || "0" : "0",
        values: collected,
        dyn_values: dynValues,
      };
    }

    function apply(record) {
      record = record || {};
      values.purchase_date = String(record.purchase_date || "").slice(0, 10);
      values.depreciation_rate = record.depreciation_rate != null ? String(record.depreciation_rate) : "0";
      values.appreciation_rate = record.appreciation_rate != null ? String(record.appreciation_rate) : "0";
      const dyn = record.dyn_values || {};
      Object.keys(dyn).forEach(function (key) {
        if (dyn[key] != null) values[key] = String(dyn[key]);
      });
      currentFields().forEach(function (field) {
        if (record[field.key] != null && record[field.key] !== "") {
          values[field.key] = String(record[field.key]);
        }
      });
      render();
    }

    function fieldValue(field) {
      const extras = collect();
      if (field.key in extras) return extras[field.key];
      if (extras.values && extras.values[field.key] != null) return extras.values[field.key];
      if (extras.dyn_values && extras.dyn_values[field.key] != null) return extras.dyn_values[field.key];
      const cmEl = document.getElementById(builtinId(field.key));
      if (cmEl) return cmEl.value;
      return values[field.key] != null ? values[field.key] : "";
    }

    function validate() {
      const errors = [];
      currentFields().forEach(function (field) {
        if (!field.required) return;
        const raw = String(fieldValue(field) || "").trim();
        const empty = field.type === "percent" ? raw === "" || raw === "0" || raw === "0.00" || raw === "0.0" : !raw;
        if (empty) errors.push((field.label || field.key) + " is required.");
      });
      return errors;
    }

    function setReadonly(flag) {
      readonly = !!flag;
      render();
    }

    select.addEventListener("change", render);
    if (opts.entityNameEl) {
      opts.entityNameEl.addEventListener("input", render);
    }
    if (opts.openingDateEl) {
      opts.openingDateEl.addEventListener("change", function () {
        const purchaseEl = document.getElementById(inputId("purchase_date"));
        if (purchaseEl && !purchaseEl.value && this.value) {
          purchaseEl.value = this.value;
          values.purchase_date = this.value;
        }
      });
    }
    render();

    function appendToFormData(fd) {
      const extras = collect();
      const aliases = {
        purchase_date: "PurchaseDate",
        depreciation_rate: "DepreciationRate",
        appreciation_rate: "AppreciationRate",
      };
      EXTRA_KEYS.forEach(function (key) {
        fd.set(key, extras[key]);
        if (aliases[key]) fd.set(aliases[key], extras[key]);
      });
      return extras;
    }

    function isGroupConfigured() {
      const id = String(select && select.value ? select.value : "").trim();
      const mapped = ((liveConfig().group_fields) || {})[id];
      return !!(mapped && mapped.configured);
    }

    function allowedKeys() {
      const keys = { customer_name: true, customer_group: true };
      currentFields().forEach(function (field) {
        if (field && field.key) keys[field.key] = true;
      });
      return keys;
    }

    return {
      collect: collect,
      apply: apply,
      validate: validate,
      sync: render,
      setReadonly: setReadonly,
      profileKey: profileKey,
      appendToFormData: appendToFormData,
      isGroupConfigured: isGroupConfigured,
      allowedKeys: allowedKeys,
    };
  }

  global.JTCSDynamicMasterFields = {
    bind: bind,
    profileForSelect: profileForSelect,
    visibleFields: visibleFields,
  };
})(window);
