(function (root) {
  "use strict";

  async function alertMessage(message) {
    if (root.JTCSDialog && typeof root.JTCSDialog.alert === "function") {
      await root.JTCSDialog.alert(message, "warning");
    } else {
      root.alert(message);
    }
  }

  async function check(criteria) {
    const url = new URL("/accounting/api/invoices/delete-check", root.location.origin);
    Object.keys(criteria || {}).forEach(function (key) {
      const value = criteria[key];
      if (value != null && String(value).trim()) url.searchParams.set(key, String(value).trim());
    });
    try {
      const response = await root.fetch(url.toString(), {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.error || "Could not check the invoice payment status.");
      }
      if (data.can_delete) return true;
      await alertMessage(data.error || "Payment has been received for this invoice.");
      return false;
    } catch (error) {
      await alertMessage(error.message || "Could not check the invoice payment status.");
      return false;
    }
  }

  root.JtcsInvoiceDeleteGuard = { check: check };
})(window);
