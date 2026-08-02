/**
 * Shared pincode + country → state / district / city / GST code autofill.
 * Integrated fields are locked (read-only) after a successful lookup.
 */
(function (global) {
  "use strict";

  function ensureSelectValue(selectEl, value) {
    if (!selectEl || value == null || value === "") return;
    const text = String(value);
    let found = false;
    for (let i = 0; i < selectEl.options.length; i++) {
      if (selectEl.options[i].value === text) {
        found = true;
        break;
      }
    }
    if (!found) {
      const opt = document.createElement("option");
      opt.value = text;
      opt.textContent = text;
      selectEl.appendChild(opt);
    }
    selectEl.value = text;
  }

  function setValue(el, value) {
    if (!el) return;
    const text = value == null ? "" : String(value);
    if (el.tagName === "SELECT") {
      ensureSelectValue(el, text || "India");
    } else {
      el.value = text;
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function setLocked(el, locked) {
    if (!el) return;
    if (el.tagName === "SELECT") {
      el.disabled = !!locked;
      el.classList.toggle("cm-integrated-locked", !!locked);
    } else {
      el.readOnly = !!locked;
      el.classList.toggle("cm-integrated-locked", !!locked);
    }
    if (locked) el.setAttribute("title", "Filled from pincode — not editable");
    else el.removeAttribute("title");
  }

  function isIndia(countryEl) {
    if (!countryEl) return true;
    return String(countryEl.value || "").trim().toLowerCase() === "india";
  }

  /**
   * @param {object} opts
   * @param {string|HTMLElement} opts.pincode
   * @param {string|HTMLElement} [opts.country]
   * @param {string|HTMLElement} [opts.state]
   * @param {string|HTMLElement} [opts.district]
   * @param {string|HTMLElement} [opts.city]
   * @param {string|HTMLElement} [opts.stateGstCode]
   * @param {string} opts.apiUrl
   * @param {boolean} [opts.lookupOnBind=true]
   */
  function bindPincodeAutofill(opts) {
    const resolve = function (ref) {
      if (!ref) return null;
      if (typeof ref === "string") return document.getElementById(ref) || document.querySelector(ref);
      return ref;
    };

    const pinField = resolve(opts.pincode);
    if (!pinField || !opts.apiUrl) return { destroy: function () {}, lookup: function () {}, resetCache: function () {} };

    const countryEl = resolve(opts.country);
    const stateEl = resolve(opts.state);
    const districtEl = resolve(opts.district);
    const cityEl = resolve(opts.city);
    const gstEl = resolve(opts.stateGstCode);
    const integrated = [stateEl, districtEl, cityEl, gstEl].filter(Boolean);

    let timer = null;
    let lastKey = "";
    let seq = 0;

    function unlockIntegrated() {
      integrated.forEach(function (el) {
        setLocked(el, false);
      });
    }

    function lockIntegrated() {
      integrated.forEach(function (el) {
        setLocked(el, true);
      });
    }

    function clearIntegrated() {
      integrated.forEach(function (el) {
        setLocked(el, false);
        if (el.tagName !== "SELECT") el.value = "";
      });
    }

    function lookup(force) {
      const pin = String(pinField.value || "").replace(/\D/g, "").slice(0, 6);
      if (pin && pin !== String(pinField.value || "").trim()) pinField.value = pin;

      if (pin.length !== 6) {
        lastKey = "";
        clearIntegrated();
        return;
      }

      if (!isIndia(countryEl)) {
        lastKey = "";
        unlockIntegrated();
        return;
      }

      const key = pin + "|" + String(countryEl ? countryEl.value : "India");
      if (!force && key === lastKey) return;

      const mySeq = ++seq;
      pinField.classList.add("cm-pincode-loading");
      fetch(String(opts.apiUrl) + "?pincode=" + encodeURIComponent(pin), {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      })
        .then(function (res) {
          return res.json().then(function (data) {
            return { res: res, data: data };
          });
        })
        .then(function (payload) {
          if (mySeq !== seq) return;
          if (!payload.res.ok || !payload.data || !payload.data.ok) {
            throw new Error((payload.data && payload.data.error) || "Pincode lookup failed.");
          }
          if (!isIndia(countryEl)) return;
          lastKey = key;
          // Keep selected country (user chose it); fill address parts from postal API.
          setValue(stateEl, payload.data.state || "");
          setValue(districtEl, payload.data.district || "");
          setValue(cityEl, payload.data.city || payload.data.district || "");
          setValue(gstEl, payload.data.state_gst_code || "");
          lockIntegrated();
        })
        .catch(function () {
          unlockIntegrated();
        })
        .finally(function () {
          if (mySeq === seq) pinField.classList.remove("cm-pincode-loading");
        });
    }

    function scheduleLookup() {
      clearTimeout(timer);
      timer = setTimeout(function () {
        lookup(false);
      }, 350);
    }

    function onPinInput() {
      const digits = String(pinField.value || "").replace(/\D/g, "").slice(0, 6);
      if (pinField.value !== digits) pinField.value = digits;
      if (digits.length < 6) {
        lastKey = "";
        clearIntegrated();
        return;
      }
      scheduleLookup();
    }

    function onCountryChange() {
      lastKey = "";
      if (!isIndia(countryEl)) {
        unlockIntegrated();
        return;
      }
      lookup(true);
    }

    pinField.setAttribute("inputmode", "numeric");
    pinField.setAttribute("autocomplete", "postal-code");
    pinField.setAttribute("maxlength", "6");
    pinField.addEventListener("input", onPinInput);
    pinField.addEventListener("blur", function () {
      lookup(false);
    });
    pinField.addEventListener("change", function () {
      lookup(true);
    });
    if (countryEl) {
      countryEl.addEventListener("change", onCountryChange);
    }

    if (opts.lookupOnBind !== false) {
      const pin = String(pinField.value || "").replace(/\D/g, "");
      if (pin.length === 6 && isIndia(countryEl)) {
        lookup(true);
      }
    }

    // If already filled (edit) with state value, lock integrated fields.
    if (stateEl && String(stateEl.value || "").trim() && isIndia(countryEl)) {
      lockIntegrated();
    }

    return {
      lookup: function () {
        lookup(true);
      },
      resetCache: function () {
        lastKey = "";
      },
      unlock: unlockIntegrated,
      destroy: function () {
        clearTimeout(timer);
        pinField.removeEventListener("input", onPinInput);
        if (countryEl) countryEl.removeEventListener("change", onCountryChange);
      },
    };
  }

  global.JtcsPincodeAutofill = {
    bind: bindPincodeAutofill,
    ensureSelectValue: ensureSelectValue,
  };
})(window);
