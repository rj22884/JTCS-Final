/* WhatsApp Inbox Merge & Link dialog helpers. No network and no customer writes. */
(function (root, factory) {
  var api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.JtcsWaMergeLink = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  function escapeHtml(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function rowsOf(matches) {
    return (matches || []).filter(function (row) {
      return row && row.customer_id;
    });
  }

  function decideMergeLink(matches) {
    var rows = rowsOf(matches);
    if (!rows.length) return { kind: "none", matches: [] };
    if (rows.length === 1) {
      return {
        kind: "auto",
        mainId: Number(rows[0].customer_id),
        mergeIds: [],
        matches: rows,
      };
    }
    return { kind: "choose", matches: rows };
  }

  function payloadForSelection(matches, mainId, mergeIds) {
    var rows = rowsOf(matches);
    var ids = rows.map(function (row) {
      return Number(row.customer_id);
    });
    var main = Number(mainId);
    if (!main || ids.indexOf(main) < 0) {
      return { ok: false, error: "Select one main customer." };
    }
    var merge = [];
    var invalid = false;
    (mergeIds || []).forEach(function (raw) {
      var id = Number(raw);
      if (!id || id === main) return;
      if (ids.indexOf(id) < 0) {
        invalid = true;
        return;
      }
      if (merge.indexOf(id) < 0) merge.push(id);
    });
    if (invalid) {
      return { ok: false, error: "A selected duplicate is not a matching customer." };
    }
    return {
      ok: true,
      body: {
        action: "merge_and_link",
        customer_id: main,
        merge_customer_ids: merge,
      },
    };
  }

  function detailLine(row) {
    var parts = [];
    if (row.mobile_number) parts.push("Mobile " + row.mobile_number);
    else if (row.mobile) parts.push("Mobile " + row.mobile);
    if (row.whatsapp_number) parts.push("WhatsApp " + row.whatsapp_number);
    if (row.alternate_mobile) parts.push("Alternate " + row.alternate_mobile);
    if (row.email) parts.push(row.email);
    if (row.city) parts.push(row.city);
    if (row.customer_group) parts.push(row.customer_group);
    parts.push("Customer ID " + row.customer_id);
    return parts.join(" · ");
  }

  function customerBlock(row) {
    return (
      "<strong>" +
      escapeHtml(row.customer_name || "Customer") +
      "</strong><div class=\"small text-muted\">" +
      escapeHtml(detailLine(row)) +
      "</div>"
    );
  }

  function choiceHtml(matches, mainId, mergeIds) {
    var selectedMerge = (mergeIds || []).map(Number);
    return rowsOf(matches)
      .map(function (row) {
        var id = Number(row.customer_id);
        var isMain = Number(mainId) === id;
        var mergeOn = !isMain && selectedMerge.indexOf(id) >= 0;
        return (
          '<div class="list-group-item wa-merge-choice">' +
          '<div class="wa-merge-picks">' +
          '<label class="form-check mb-1"><input class="form-check-input" type="radio" name="crmWaMain" value="' +
          id +
          '"' +
          (isMain ? " checked" : "") +
          "> Main</label>" +
          '<label class="form-check mb-0"><input class="form-check-input" type="checkbox" name="crmWaMerge" value="' +
          id +
          '"' +
          (mergeOn ? " checked" : "") +
          (isMain ? " disabled" : "") +
          "> Merge</label></div><div>" +
          customerBlock(row) +
          "</div></div>"
        );
      })
      .join("");
  }

  function reviewHtml(matches, mainId, mergeIds) {
    var rows = rowsOf(matches);
    var main = null;
    var extras = [];
    var wanted = (mergeIds || []).map(Number);
    rows.forEach(function (row) {
      var id = Number(row.customer_id);
      if (id === Number(mainId)) main = row;
      else if (wanted.indexOf(id) >= 0) extras.push(row);
    });
    var html = "<p class=\"mb-1\"><strong>Main customer</strong></p>";
    html += "<div class=\"mb-2\">" + (main ? customerBlock(main) : "<span>Select one main customer.</span>") + "</div>";
    html += "<p class=\"mb-1\"><strong>Records to merge</strong></p>";
    if (!extras.length) {
      html += "<p class=\"small text-muted mb-2\">No duplicate customer records will be merged.</p>";
    } else {
      html +=
        "<ul class=\"small mb-2\">" +
        extras
          .map(function (row) {
            return "<li>" + customerBlock(row) + "</li>";
          })
          .join("") +
        "</ul>";
    }
    html +=
      "<p class=\"small mb-0\">This WhatsApp contact will be linked only to the main customer. " +
      "Duplicate records use the existing Customer Master phone merge.</p>";
    return html;
  }

  function renderDialog(state) {
    var phase = state && state.phase === "review" ? "review" : "choose";
    var matches = (state && state.matches) || [];
    var mainId = state && state.mainId;
    var mergeIds = (state && state.mergeIds) || [];
    if (phase === "review") {
      return {
        title: "Confirm merge and link",
        message: "Check the main customer and the records that will be merged before continuing.",
        choicesHtml: "",
        reviewHtml: reviewHtml(matches, mainId, mergeIds),
        showChoices: false,
        showReview: true,
        actionsHtml:
          '<button type="button" class="btn btn-outline-secondary btn-sm" data-wa-link="back-merge">Back</button>' +
          '<button type="button" class="btn btn-primary btn-sm" data-wa-link="confirm-merge">Confirm merge &amp; link</button>' +
          '<button type="button" class="btn btn-outline-secondary btn-sm" data-bs-dismiss="modal">Cancel</button>',
      };
    }
    return {
      title: "Select the main customer",
      message:
        "More than one Customer Master record matches this WhatsApp contact. Select one main customer. Tick Merge on any other matching record that should be merged into that customer.",
      choicesHtml: choiceHtml(matches, mainId, mergeIds),
      reviewHtml: "",
      showChoices: true,
      showReview: false,
      actionsHtml:
        '<button type="button" class="btn btn-primary btn-sm" data-wa-link="review-merge">Review</button>' +
        '<button type="button" class="btn btn-outline-secondary btn-sm" data-bs-dismiss="modal">Cancel</button>',
    };
  }

  function resultMessage(result) {
    if (result && result.message) return String(result.message);
    var name = (result && result.customer_name) || "Customer";
    var count = (result && result.merged_count) || 0;
    if (count) {
      return (
        "Main customer " +
        name +
        " is linked to this WhatsApp contact. " +
        count +
        " duplicate record(s) merged into that customer."
      );
    }
    if (result && result.auto) {
      return "One Customer Master match: " + name + ". Linked this WhatsApp contact to that main customer.";
    }
    return "Linked this WhatsApp contact to main customer " + name + ".";
  }

  function cancelMergeLink() {
    return { changed: false, main_customer_id: null, merge_customer_ids: [] };
  }

  return {
    decideMergeLink: decideMergeLink,
    payloadForSelection: payloadForSelection,
    renderDialog: renderDialog,
    resultMessage: resultMessage,
    cancelMergeLink: cancelMergeLink,
    detailLine: detailLine,
  };
});
