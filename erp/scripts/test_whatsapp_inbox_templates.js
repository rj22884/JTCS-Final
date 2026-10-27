/* Fixture tests for the WhatsApp Inbox template dropdown. No network and no sends. */
const assert = require("assert");
const helpers = require("../app/static/js/crm/inbox_templates.js");

const numberChange = {
  Name: "number_change",
  Body: "Hello {{1}},\n\nOur WhatsApp service is now also available at this number: {{2}}.",
  LanguageCode: "en",
  Category: "MARKETING",
  Variables: [
    { key: "1", label: "Customer name", source: "customer_name" },
    { key: "2", label: "Business WhatsApp number", source: "business_whatsapp_number" },
  ],
};
const utility = {
  Name: "payment_reminder",
  Body: "Dear {{customer_name}}, payment is pending.",
  LanguageCode: "en",
  Category: "UTILITY",
  Variables: [],
};

const rendered = helpers.renderTemplateOptions([numberChange, utility], "");
assert.ok(rendered.html.indexOf("number_change") !== -1, "marketing template option");
assert.ok(rendered.html.indexOf("payment_reminder") !== -1, "utility template option");
assert.strictEqual(rendered.notice, "");

const failed = helpers.renderTemplateOptions([], "WhatsApp templates could not be loaded from Meta.");
assert.ok(failed.html.indexOf("Templates…") !== -1);
assert.ok(failed.html.indexOf("could not be loaded") !== -1, "error shown instead of a blank list");
assert.ok(failed.html.indexOf("disabled") !== -1);

const partial = helpers.renderTemplateOptions([utility], "Meta templates could not be loaded.");
assert.ok(partial.html.indexOf("payment_reminder") !== -1, "saved rows stay visible");
assert.strictEqual(partial.notice, "Meta templates could not be loaded.");

const fields = helpers.variableFields(
  numberChange,
  { business_whatsapp_number: "+91 00000 00000" },
  { Subject: "Multiple Customers Found", CustomerName: "Ravi Sharma" }
);
assert.deepStrictEqual(
  fields.map(function (field) { return field.label; }),
  ["Customer name", "Business WhatsApp number"]
);
assert.strictEqual(fields[0].value, "Ravi Sharma");
assert.strictEqual(fields[1].value, "+91 00000 00000");
assert.strictEqual(
  helpers.customerNameFromConversation({ Subject: "Multiple Customers Found" }),
  ""
);

const filled = helpers.fillTemplateBody(numberChange.Body, { 1: "Ravi Sharma", 2: "+91 00000 00000" });
assert.ok(filled.indexOf("Hello Ravi Sharma,") === 0);
assert.ok(filled.indexOf("+91 00000 00000") !== -1);
assert.ok(filled.indexOf("{{1}}") === -1 && filled.indexOf("{{2}}") === -1);

const empty = helpers.renderTemplateOptions([], "");
assert.strictEqual(empty.html, '<option value="">Templates…</option>');
assert.strictEqual(empty.notice, "");

console.log("ALL PASS");
