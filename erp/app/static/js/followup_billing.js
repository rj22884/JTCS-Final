(function () {
  "use strict";

  const els = {
    workDate: document.getElementById("fuBillWorkDate"),
    billNo: document.getElementById("fuBillNo"),
    billDate: document.getElementById("fuBillDate"),
    billAmount: document.getElementById("fuBillAmount"),
    refreshBtn: document.getElementById("fuBillRefreshNo"),
    applyBtn: document.getElementById("fuBillApplyBtn"),
  };

  function refreshBillNo() {
    const params = new URLSearchParams();
    if (els.workDate?.value) params.set("work_date", els.workDate.value);
    const url = window.FU_BILLING.nextBillApi + "?" + params.toString();
    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "Unable to fetch bill number.");
        if (els.billNo) els.billNo.value = data.bill_no || "";
      });
  }

  function applyToEntry() {
    const amount = (els.billAmount?.value || "").trim();
    if (!amount || Number(amount) <= 0) {
      alert("Please enter a valid bill amount.");
      return;
    }
    const payload = {
      bill_no: (els.billNo?.value || "").trim(),
      bill_amount: amount,
      bill_date: els.billDate?.value || "",
    };
    if (!payload.bill_no) {
      alert("Bill number is required.");
      return;
    }
    if (window.opener && typeof window.opener.FU_applyBillingResult === "function") {
      window.opener.FU_applyBillingResult(payload);
      window.close();
      return;
    }
    alert("Bill details ready:\nBill No: " + payload.bill_no + "\nAmount: " + payload.bill_amount);
  }

  els.refreshBtn?.addEventListener("click", refreshBillNo);
  els.workDate?.addEventListener("change", refreshBillNo);
  els.applyBtn?.addEventListener("click", applyToEntry);
})();
