(function () {
  "use strict";

  const modalEl = document.getElementById("scopedCustomerModal");
  const form = document.getElementById("scopedCustomerForm");
  if (!modalEl || !form || !window.bootstrap) return;

  const modal = new bootstrap.Modal(modalEl);
  const saveBtn = document.getElementById("scopedCustomerSaveBtn");
  const errorEl = document.getElementById("scopedCustomerFormError");
  let pincodeBinder = null;
  let activeTarget = "primary";

  function showError(message) {
    if (!errorEl) return;
    errorEl.textContent = message || "Unable to add customer.";
    errorEl.classList.remove("d-none");
  }

  function resetForm() {
    form.reset();
    const country = document.getElementById("scopedCustCountry");
    if (country) country.value = "India";
    if (errorEl) {
      errorEl.textContent = "";
      errorEl.classList.add("d-none");
    }
    pincodeBinder?.unlock?.();
    pincodeBinder?.resetCache?.();
  }

  if (window.JtcsPincodeAutofill && window.SCOPED_CUSTOMER_PINCODE_LOOKUP) {
    pincodeBinder = window.JtcsPincodeAutofill.bind({
      pincode: "scopedCustPincode",
      postOffice: "scopedCustPostOffice",
      district: "scopedCustDistrict",
      state: "scopedCustState",
      country: "scopedCustCountry",
      fillCountry: true,
      lockAddressFields: true,
      apiUrl: window.SCOPED_CUSTOMER_PINCODE_LOOKUP,
      lookupOnBind: false,
    });
  }

  document.querySelectorAll("[data-scoped-customer-add]").forEach(function (button) {
    button.addEventListener("click", function () {
      activeTarget = button.dataset.scopedCustomerAdd || "primary";
      resetForm();
      modal.show();
    });
  });

  saveBtn?.addEventListener("click", function () {
    if (!form.reportValidity()) return;
    const payload = Object.fromEntries(new FormData(form).entries());
    if (saveBtn) saveBtn.disabled = true;
    if (errorEl) {
      errorEl.textContent = "";
      errorEl.classList.add("d-none");
    }
    fetch(window.SCOPED_CUSTOMER_CREATE_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": payload.csrf_token || window.SCOPED_CUSTOMER_CSRF || "",
      },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Unable to add customer.");
          return data;
        });
      })
      .then(function (data) {
        const customer = data.customer || {};
        modal.hide();
        resetForm();
        window.dispatchEvent(new CustomEvent("jtcs:scoped-customer-created", {
          detail: { customer: customer, target: activeTarget },
        }));
      })
      .catch(function (err) {
        showError(err.message || "Unable to add customer.");
      })
      .finally(function () {
        if (saveBtn) saveBtn.disabled = false;
      });
  });
})();
