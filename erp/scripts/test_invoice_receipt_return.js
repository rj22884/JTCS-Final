/**
 * Non-mutating checks for invoice-triggered Money In-Out close/return.
 * Does not create, update, or delete receipts, invoices, allocations, or double-entry rows.
 */
"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");

const api = require("../app/static/js/invoice_receipt_return.js");
const root = path.join(__dirname, "..");

const MODULES = [
  {
    origin: "MISC",
    page: "/activities/miscellaneous",
    withQuery: "/activities/miscellaneous?load_entry=12",
    alias: "/activities/misc_new?load_entry=4",
  },
  {
    origin: "GST",
    page: "/gst/followup",
    withQuery: "/gst/followup?load_entry=8",
  },
  {
    origin: "TDS",
    page: "/tds/followup",
    withQuery: "/tds/followup?load_entry=3",
  },
  {
    origin: "ITR",
    page: "/itr/followup",
    withQuery: "/itr/followup?load_entry=5",
  },
  {
    origin: "DSC",
    page: "/dsc/followup",
    withQuery: "/dsc/followup?load_entry=9",
  },
];

function read(rel) {
  return fs.readFileSync(path.join(root, rel), "utf8");
}

function hostFor(mode) {
  const calls = [];
  return {
    calls: calls,
    hideReceiptModal: function () {
      calls.push("hide-receipt");
    },
    disarmRelaunch: function (plan) {
      calls.push("disarm:" + plan.origin + ":" + plan.returnTo);
    },
    hasInvoicePageWindow: function () {
      return mode === "page-window";
    },
    finishInvoiceWindow: function (returnTo) {
      calls.push("close-invoice-window:" + returnTo);
    },
    isEmbeddedInvoice: function () {
      return mode === "embedded";
    },
    notifyOriginClose: function (plan) {
      calls.push("notify:" + plan.origin + ":" + plan.returnTo);
    },
    navigateToOrigin: function (returnTo) {
      calls.push("navigate:" + returnTo);
    },
    openNewForm: function () {
      calls.push("open-new-form");
    },
  };
}

function followupAccepts(moduleCode, message) {
  const origin = String((message && message.receipt_origin) || "").trim().toUpperCase();
  if (origin !== String(moduleCode || "").trim().toUpperCase()) return false;
  return !!api.normalizeOrigin(origin);
}

function miscAccepts(forceKind, message) {
  if (String(forceKind || "") !== "Misc.") return false;
  return String((message && message.receipt_origin) || "").trim().toUpperCase() === "MISC";
}

let passed = 0;

function check(name, fn) {
  fn();
  passed += 1;
  console.log("ok  " + name);
}

MODULES.forEach(function (mod) {
  check(mod.origin + " passes its own origin and return path", function () {
    const params = new URLSearchParams();
    const wrote = api.appendModuleReturn(params, mod.origin, mod.withQuery);
    assert.strictEqual(wrote, true);
    assert.strictEqual(params.get("receipt_origin"), mod.origin);
    assert.strictEqual(params.get("return_to"), mod.withQuery);
    const launch = api.receiptLaunchFromSearch(
      "receipt=1&customer_id=15&invoice_id=22&amount=70&" + params.toString()
    );
    assert.ok(launch);
    assert.strictEqual(launch.origin, mod.origin);
    assert.strictEqual(launch.returnTo, mod.withQuery);
    assert.strictEqual(launch.customerId, "15");
    assert.strictEqual(launch.invoiceId, "22");
  });

  check(mod.origin + " success closes receipt and invoice window on its own page", function () {
    const launch = { origin: mod.origin, returnTo: mod.withQuery };
    const plan = api.planSaveSuccess(launch);
    assert.strictEqual(plan.listed, true);
    assert.strictEqual(plan.hideReceipt, true);
    assert.strictEqual(plan.closeInvoiceWindow, true);
    assert.strictEqual(plan.openNewForm, false);
    assert.strictEqual(plan.reloadGrid, false);
    assert.strictEqual(plan.keepFormOpen, false);
    assert.strictEqual(plan.returnTo, mod.withQuery);
    assert.notStrictEqual(plan.returnTo, "/dashboard");

    const host = hostFor("page-window");
    const done = api.performListedReturn(launch, host);
    assert.strictEqual(done.returnTo, mod.withQuery);
    assert.ok(host.calls.indexOf("hide-receipt") !== -1);
    assert.ok(host.calls.indexOf("close-invoice-window:" + mod.withQuery) !== -1);
    assert.ok(!host.calls.some(function (item) { return item.indexOf("navigate:") === 0; }));
    assert.ok(!host.calls.some(function (item) { return item === "open-new-form"; }));
    assert.ok(!host.calls.some(function (item) { return item.indexOf("notify:") === 0; }));
  });

  check(mod.origin + " embedded invoice closes back on the same module", function () {
    const launch = { origin: mod.origin, returnTo: mod.page };
    const host = hostFor("embedded");
    api.performListedReturn(launch, host);
    assert.ok(host.calls.indexOf("notify:" + mod.origin + ":" + mod.page) !== -1);
    assert.ok(!host.calls.some(function (item) { return item.indexOf("navigate:") === 0; }));
    assert.ok(!host.calls.some(function (item) { return item.indexOf("close-invoice-window:") === 0; }));
    const message = { type: "jtcs-invoice-receipt-closed", receipt_origin: mod.origin, return_to: mod.page };
    if (mod.origin === "MISC") {
      assert.strictEqual(miscAccepts("Misc.", message), true);
      assert.strictEqual(miscAccepts("Income", message), false);
      assert.strictEqual(followupAccepts("GST", message), false);
    } else {
      assert.strictEqual(followupAccepts(mod.origin, message), true);
      MODULES.forEach(function (other) {
        if (other.origin === mod.origin || other.origin === "MISC") return;
        assert.strictEqual(followupAccepts(other.origin, message), false);
      });
      assert.strictEqual(miscAccepts("Misc.", message), false);
    }
  });

  check(mod.origin + " full-page receipt returns to that module only", function () {
    const launch = { origin: mod.origin, returnTo: mod.page };
    const host = hostFor("top");
    api.performListedReturn(launch, host);
    assert.deepStrictEqual(
      host.calls.filter(function (item) { return item.indexOf("navigate:") === 0; }),
      ["navigate:" + mod.page]
    );
    assert.ok(!host.calls.some(function (item) { return item === "open-new-form"; }));
  });

  check(mod.origin + " save and validation failure keep the receipt form open", function () {
    const plan = api.planSaveFailure({ origin: mod.origin, returnTo: mod.page });
    assert.strictEqual(plan.keepFormOpen, true);
    assert.strictEqual(plan.hideReceipt, false);
    assert.strictEqual(plan.closeInvoiceWindow, false);
    assert.strictEqual(plan.openNewForm, false);
    assert.strictEqual(plan.reloadGrid, false);
    assert.strictEqual(plan.disarmRelaunch, false);
    const host = hostFor("page-window");
    assert.strictEqual(api.planSaveFailure(plan).closeInvoiceWindow, false);
    assert.strictEqual(host.calls.length, 0);
  });

  check(mod.origin + " rejects another module and a generic page", function () {
    assert.strictEqual(api.safeReturnPath(mod.origin, "/dashboard"), mod.page);
    assert.strictEqual(api.safeReturnPath(mod.origin, "https://evil.example" + mod.page), mod.page);
    assert.strictEqual(api.safeReturnPath(mod.origin, "//evil.example" + mod.page), mod.page);
    const others = MODULES.filter(function (item) { return item.page !== mod.page; });
    others.forEach(function (other) {
      assert.strictEqual(api.safeReturnPath(mod.origin, other.page), mod.page);
    });
    if (mod.alias) {
      assert.strictEqual(api.safeReturnPath(mod.origin, mod.alias), mod.alias);
    }
  });
});

check("standalone Money In-Out save does not close an invoice or leave the page", function () {
  ["", "ACCOUNTING", "INCOME", "FOLLOWUP"].forEach(function (origin) {
    const plan = api.planSaveSuccess({ origin: origin, returnTo: "/gst/followup" });
    assert.strictEqual(plan.listed, false, origin || "(blank)");
    assert.strictEqual(plan.hideReceipt, true);
    assert.strictEqual(plan.reloadGrid, true);
    assert.strictEqual(plan.closeInvoiceWindow, false);
    assert.strictEqual(plan.openNewForm, false);
    assert.strictEqual(plan.disarmRelaunch, false);
    assert.strictEqual(plan.returnTo, "");
  });
  const host = hostFor("page-window");
  const done = api.performListedReturn({ origin: "", returnTo: "/gst/followup" }, host);
  assert.strictEqual(done.listed, false);
  assert.deepStrictEqual(host.calls, []);
  const plain = api.receiptLaunchFromSearch("receipt=1&customer_id=9&invoice_id=3&amount=10");
  assert.strictEqual(plain.origin, "");
  assert.strictEqual(plain.returnTo, "");
  assert.strictEqual(api.normalizeOrigin("ACCOUNTING"), "");
});

check("receipt relaunch is suppressed after a listed save, including reload", function () {
  const plan = api.planSaveSuccess({ origin: "GST", returnTo: "/gst/followup?load_entry=8" });
  const record = api.pendingRecord(plan, 1000);
  assert.strictEqual(api.disarmSearch(), "receipt_return=1");
  assert.strictEqual(api.shouldOpenReceiptOnLoad("?receipt=1&customer_id=9&receipt_origin=GST"), true);
  assert.strictEqual(api.shouldOpenReceiptOnLoad("?receipt_return=1"), false);
  assert.strictEqual(api.shouldOpenReceiptOnLoad(""), false);
  const pending = api.readPendingReturn(JSON.stringify(record), "?receipt_return=1", 1000);
  assert.strictEqual(pending.origin, "GST");
  assert.strictEqual(pending.returnTo, "/gst/followup?load_entry=8");
  assert.strictEqual(api.readPendingReturn(JSON.stringify(record), "", 1000), null);
  assert.strictEqual(api.readPendingReturn(JSON.stringify(record), "?receipt_return=1", record.expires + 1), null);
});

check("page scripts wire origin only into the listed invoice receipt flow", function () {
  const bank = read("app/static/js/bank_cash_transactions.js");
  const saveStart = bank.indexOf("async function saveEntry");
  const saveEnd = bank.indexOf("async function deleteEntry");
  assert.ok(saveStart > 0 && saveEnd > saveStart);
  const saveFn = bank.slice(saveStart, saveEnd);
  assert.ok(saveFn.indexOf("els.form.reportValidity()") < saveFn.indexOf("fetch(window.OBC_API.save"));
  assert.ok(saveFn.indexOf("returnAfterListedReceipt") > saveFn.indexOf('alert(data.message || "Saved.")'));
  assert.ok(saveFn.indexOf("if (modal) modal.hide()") > saveFn.indexOf("returnAfterListedReceipt"));
  const catchAt = saveFn.indexOf("} catch");
  assert.ok(catchAt > saveFn.indexOf("returnAfterListedReceipt"));
  assert.strictEqual(saveFn.slice(catchAt).indexOf("returnAfterListedReceipt"), -1);
  assert.ok(saveFn.indexOf("new FormData(els.form)") > 0);
  assert.strictEqual(saveFn.indexOf("receipt_origin"), -1);
  assert.ok(bank.indexOf("invoiceReceiptLaunch = null") < bank.indexOf("async function openEdit"));
  assert.ok(bank.indexOf("if (launch && launch.origin) invoiceReceiptLaunch = launch") > 0);

  const invoice = read("app/static/js/gst_invoice.js");
  assert.ok(invoice.indexOf("appendModuleReturn") > invoice.indexOf("function receiptFormUrl"));
  const followup = read("app/static/js/followup_activity.js");
  assert.strictEqual((followup.match(/appendReceiptOrigin\(params\)/g) || []).length, 3);
  const misc = read("app/static/js/income_expense_activity.js");
  assert.ok(misc.indexOf('=== "Misc." ? "MISC"') > 0);
  assert.strictEqual((misc.match(/appendMiscReceiptOrigin\(params\)/g) || []).length, 3);
  const pages = read("app/static/js/jtcs_page_windows.js");
  assert.ok(pages.indexOf("jtcsFinishInvoiceReceiptReturn") > 0);
  assert.ok(pages.indexOf("jtcsOpenPageWindow(href") === -1 || pages.indexOf("function (opts)") > 0);
});

console.log(passed + " checks passed");
console.log("no financial records were created, updated, or deleted");
