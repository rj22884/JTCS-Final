/* WhatsApp Inbox template dropdown helpers. No network and no send. */
(function (root, factory) {
  var api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.JtcsInboxTemplates = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  function escapeHtml(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function customerNameFromConversation(conv) {
    if (!conv) return "";
    return String(conv.CustomerName || conv.LeadName || "").trim();
  }

  function fillTemplateBody(body, values) {
    var text = String(body || "");
    var map = values || {};
    Object.keys(map).forEach(function (key) {
      var token = "{{" + key + "}}";
      var value = map[key] == null ? "" : String(map[key]);
      text = text.split(token).join(value);
    });
    return text;
  }

  function optionLabel(row, nameCounts) {
    var name = row.Name || "Template";
    var language = String(row.LanguageCode || "").trim();
    if (language && (nameCounts[name] || 0) > 1) {
      return name + " (" + language + ")";
    }
    return name;
  }

  function renderTemplateOptions(rows, metaError) {
    var list = rows || [];
    var nameCounts = {};
    list.forEach(function (row) {
      var name = row.Name || "Template";
      nameCounts[name] = (nameCounts[name] || 0) + 1;
    });
    var html = '<option value="">Templates…</option>';
    if (metaError && !list.length) {
      html += '<option value="" disabled>' + escapeHtml(metaError) + "</option>";
    }
    list.forEach(function (row, index) {
      html +=
        '<option value="' +
        escapeHtml(row.Body || "") +
        '" data-index="' +
        index +
        '">' +
        escapeHtml(optionLabel(row, nameCounts)) +
        "</option>";
    });
    return {
      html: html,
      notice: metaError && list.length ? String(metaError) : "",
    };
  }

  function variableFields(row, defaults, conv) {
    var variables = (row && row.Variables) || [];
    if (!Array.isArray(variables) || !variables.length) return [];
    var preset = defaults || {};
    return variables.map(function (item) {
      var source = item.source || "";
      var value = "";
      if (source === "customer_name") value = customerNameFromConversation(conv);
      else if (source === "business_whatsapp_number") value = preset.business_whatsapp_number || "";
      return {
        key: String(item.key || ""),
        label: item.label || ("Variable {{" + item.key + "}}"),
        value: value,
      };
    });
  }

  return {
    customerNameFromConversation: customerNameFromConversation,
    fillTemplateBody: fillTemplateBody,
    renderTemplateOptions: renderTemplateOptions,
    variableFields: variableFields,
  };
});
