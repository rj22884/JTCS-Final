/* WhatsApp Inbox Merge & Link UI planning. No network and no customer writes. */
const assert = require("assert");
const helpers = require("../app/static/js/crm/inbox_merge_link.js");

const one = [{ customer_id: 7, customer_name: "Ravi Sharma", mobile_number: "9876543210", city: "Jaipur" }];
const auto = helpers.decideMergeLink(one);
assert.strictEqual(auto.kind, "auto");
assert.strictEqual(auto.mainId, 7);
assert.deepStrictEqual(auto.mergeIds, []);

const none = helpers.decideMergeLink([]);
assert.strictEqual(none.kind, "none");

const many = [
  { customer_id: 1, customer_name: "Asha", mobile_number: "9876543210", city: "Ajmer", customer_group: "GST" },
  { customer_id: 2, customer_name: "Asha Stores", mobile_number: "9876543210", email: "asha@example.com" },
  { customer_id: 3, customer_name: "Other Asha", mobile_number: "9876543210", city: "Kota" },
];
assert.strictEqual(helpers.decideMergeLink(many).kind, "choose");

const missing = helpers.payloadForSelection(many, null, [1]);
assert.strictEqual(missing.ok, false);
assert.ok(missing.error.indexOf("main customer") !== -1);

const selected = helpers.payloadForSelection(many, 2, [1]);
assert.strictEqual(selected.ok, true);
assert.strictEqual(selected.body.action, "merge_and_link");
assert.strictEqual(selected.body.customer_id, 2);
assert.deepStrictEqual(selected.body.merge_customer_ids, [1]);
assert.ok(selected.body.merge_customer_ids.indexOf(3) === -1, "unselected duplicate stays out");

const self = helpers.payloadForSelection(many, 2, [2, 1]);
assert.deepStrictEqual(self.body.merge_customer_ids, [1]);

const stranger = helpers.payloadForSelection(many, 2, [99]);
assert.strictEqual(stranger.ok, false);

const choose = helpers.renderDialog({ phase: "choose", matches: many, mainId: null, mergeIds: [] });
assert.ok(choose.choicesHtml.indexOf("Asha Stores") !== -1);
assert.ok(choose.choicesHtml.indexOf("Ajmer") !== -1);
assert.ok(choose.choicesHtml.indexOf("asha@example.com") !== -1);
assert.ok(choose.choicesHtml.indexOf("Customer ID 3") !== -1);
assert.ok(choose.choicesHtml.indexOf('name="crmWaMain"') !== -1);
assert.ok(choose.choicesHtml.indexOf('name="crmWaMerge"') !== -1);
assert.ok(choose.actionsHtml.indexOf("Cancel") !== -1);
assert.ok(choose.actionsHtml.indexOf("confirm-merge") === -1);

const review = helpers.renderDialog({ phase: "review", matches: many, mainId: 2, mergeIds: [1] });
assert.ok(review.reviewHtml.indexOf("Asha Stores") !== -1);
assert.ok(review.reviewHtml.indexOf("Asha") !== -1);
assert.ok(review.reviewHtml.indexOf("Other Asha") === -1, "unselected customer is not in the review");
assert.ok(review.actionsHtml.indexOf("confirm-merge") !== -1);
assert.ok(review.actionsHtml.indexOf("Cancel") !== -1);

const linkOnly = helpers.renderDialog({ phase: "review", matches: many, mainId: 2, mergeIds: [] });
assert.ok(linkOnly.reviewHtml.indexOf("No duplicate customer records will be merged.") !== -1);

assert.deepStrictEqual(helpers.cancelMergeLink(), {
  changed: false,
  main_customer_id: null,
  merge_customer_ids: [],
});

const message = helpers.resultMessage({
  auto: true,
  customer_name: "Ravi Sharma",
  message: "One Customer Master match: Ravi Sharma (9876543210). Linked this WhatsApp contact to that main customer.",
});
assert.ok(message.indexOf("Ravi Sharma") !== -1);
assert.ok(message.indexOf("main customer") !== -1);

console.log("ALL PASS");
