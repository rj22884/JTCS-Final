(function (root) {
  "use strict";

  let linkedMoneyInOutApproved = false;

  async function alertMessage(message) {
    if (root.JTCSDialog && typeof root.JTCSDialog.alert === "function") {
      await root.JTCSDialog.alert(message, "warning");
    } else {
      root.alert(message);
    }
  }

  async function check(criteria) {
    linkedMoneyInOutApproved = false;
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
      if (!data.can_delete) {
        await alertMessage(data.error || "Payment has been received for this invoice.");
        return false;
      }
      if (data.requires_linked_receipt_delete) {
        const rows = data.entries || [];
        const details = rows.map(function (row) {
          const bits = [row.voucher_no || "Money In-Out"];
          if (row.invoice_no) bits.push("इनवॉइस " + row.invoice_no);
          if (row.work_date) bits.push(row.work_date);
          bits.push("Entry ₹" + Number(row.money_inout_transaction_amount || 0).toFixed(2));
          bits.push("इनवॉइस से जुड़ी राशि ₹" + Number(row.allocated_amount || 0).toFixed(2));
          const remaining = Number(row.remaining_money_inout_amount || 0);
          if (remaining > 0.005) bits.push("शेष ₹" + remaining.toFixed(2));
          return "• " + bits.join(" | ");
        });
        const message = [
          "इनवॉइस हटाने से पहले ये जुड़ी हुई मनी इन-आउट एंट्रियाँ हटेंगी:",
          "",
          details.join("\n"),
          "",
          "पूरी मनी इन-आउट एंट्री और उससे जुड़े लेजर रिकॉर्ड हटेंगे। उसके बाद इनवॉइस हटेगा। जारी रखें?",
        ].join("\n");
        const confirmed = root.JTCSDialog?.confirm
          ? await root.JTCSDialog.confirm(message, {
              title: "जुड़ी मनी इन-आउट एंट्रियाँ हटाएँ",
              okLabel: "एंट्री और इनवॉइस हटाएँ",
              cancelLabel: "रद्द करें",
              type: "danger",
            })
          : root.confirm(message);
        if (!confirmed) return false;
        linkedMoneyInOutApproved = true;
      }
      return true;
    } catch (error) {
      await alertMessage(error.message || "Could not check the invoice payment status.");
      return false;
    }
  }

  function applyDeleteOptions(payload) {
    const body = payload || {};
    if (linkedMoneyInOutApproved) {
      body.delete_linked_money_inout = true;
      linkedMoneyInOutApproved = false;
    }
    return body;
  }

  root.JtcsInvoiceDeleteGuard = {
    check: check,
    applyDeleteOptions: applyDeleteOptions,
  };
})(window);
