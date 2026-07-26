(function () {
  "use strict";

  function displayDate(value) {
    if (typeof window.formatDisplayDate === "function") {
      return window.formatDisplayDate(value);
    }
    return value || "—";
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  var els = {
    fileInput: document.getElementById("ecourtTestPdfInput"),
    readBtn: document.getElementById("ecourtTestReadPdfBtn"),
    status: document.getElementById("ecourtTestStatus"),
    panel: document.getElementById("ecourtTestPreviewPanel"),
    meta: document.getElementById("ecourtTestMeta"),
    count: document.getElementById("ecourtTestCount"),
    body: document.getElementById("ecourtTestGridBody"),
    excludedPanel: document.getElementById("ecourtTestExcludedPanel"),
    excludedBody: document.getElementById("ecourtTestExcludedBody"),
  };

  /** Original Amount+Date groups from PDF parse (receipt objects shared with partitions). */
  var sourceGroups = [];
  /** Ready-to-import partitions (keys: r0, r1, …) */
  var lastReady = [];
  /** Already-imported partitions (keys: i0, i1, …) */
  var lastImported = [];
  /** Fully sold stationery numbers (uppercase) — show in red */
  var soldStationery = new Set();
  var importMeta = {
    file_name: "",
    report_from: "",
    report_to: "",
    state_name: "",
    total_amount: "",
  };
  /** Stationery numbers already used in this preview session */
  var usedStationery = new Set();

  if (!els.readBtn || !window.ECOURT_IMPORT_TEST_URLS) return;

  function setStatus(text, isError) {
    if (!els.status) return;
    els.status.textContent = text || "";
    els.status.classList.toggle("text-danger", !!isError);
    els.status.classList.toggle("text-muted", !isError);
  }

  function normalizeStationery(value) {
    return String(value || "").trim();
  }

  function isStationerySold(value) {
    var stn = normalizeStationery(value);
    return !!stn && soldStationery.has(stn.toUpperCase());
  }

  function formatStationeryHtml(value) {
    var stn = normalizeStationery(value);
    if (!stn) return "—";
    if (isStationerySold(stn)) {
      return (
        '<span class="ecourt-test-stn-sold" title="Sold">' +
        escapeHtml(stn) +
        "</span>"
      );
    }
    return escapeHtml(stn);
  }

  function formatStationeryListHtml(stationeries) {
    if (!stationeries || !stationeries.length) return "—";
    return stationeries
      .map(function (stn) {
        return formatStationeryHtml(stn);
      })
      .join(", ");
  }

  function groupKey(side, index) {
    return (side === "imported" ? "i" : "r") + index;
  }

  function getGroup(key) {
    var match = String(key || "").match(/^([ri])(\d+)$/);
    if (!match) return null;
    var list = match[1] === "i" ? lastImported : lastReady;
    return list[Number(match[2])] || null;
  }

  function flattenReceipts(group) {
    var out = [];
    (group.pages || []).forEach(function (page) {
      (page.receipts || []).forEach(function (rec) {
        out.push(rec);
      });
    });
    if (!out.length && Array.isArray(group.receipts)) {
      out = group.receipts.slice();
    }
    return out;
  }

  function resolveAmountBand(group, receipts) {
    if (group && group.amount_band) return group.amount_band;
    var sample = Number(
      (receipts && receipts[0] && receipts[0].amount) || group?.per_record_amt || 0
    );
    if (Number.isNaN(sample) || sample <= 10) return "small";
    if (sample <= 999999999) return "mid";
    return "over";
  }

  function resolvePageSize(group, receipts) {
    if (group && group.page_size) return Number(group.page_size) || 20;
    return resolveAmountBand(group, receipts) === "small" ? 20 : 1;
  }

  function buildPagedGroup(base, receipts, pageSize, forceImported) {
    var pages = [];
    var amountBand = resolveAmountBand(base, receipts);
    var size = pageSize || (amountBand === "small" ? 20 : 1);
    var autoBand = amountBand === "mid" || !!base.auto_stationery;
    for (var start = 0; start < receipts.length; start += size) {
      var chunk = receipts.slice(start, start + size);
      var importedInPage = chunk.filter(function (rec) {
        return !!rec.imported;
      }).length;
      var pageFullyImported =
        forceImported || (importedInPage === chunk.length && chunk.length > 0);
      var pending = chunk.filter(function (rec) {
        return !rec.imported;
      });
      var pageStationery = "";
      var applied = false;
      var pageAuto =
        autoBand ||
        pending.some(function (rec) {
          return !!rec.auto_stationery;
        });
      if (pageFullyImported) {
        applied = true;
        pageAuto = false;
        for (var i = 0; i < chunk.length; i++) {
          if (chunk[i].stationerynumber) {
            pageStationery = chunk[i].stationerynumber;
            break;
          }
        }
      } else if (
        pending.length &&
        pending.every(function (rec) {
          return (
            !!rec.stationery_applied &&
            !!normalizeStationery(rec.stationerynumber) &&
            normalizeStationery(rec.stationerynumber) ===
              normalizeStationery(pending[0].stationerynumber)
          );
        })
      ) {
        applied = true;
        pageStationery = normalizeStationery(pending[0].stationerynumber);
      } else if (pending.length) {
        pageStationery = normalizeStationery(pending[0].stationerynumber || "");
      }
      var pageAutoFinal = pageAuto && !pageFullyImported;
      pages.push({
        page_no: pages.length + 1,
        count: chunk.length,
        receipts: chunk,
        imported: pageFullyImported,
        applied: applied,
        stationery_saved: applied || pageFullyImported || pageAutoFinal,
        stationerynumber: pageStationery,
        auto_stationery: pageAutoFinal,
        amount_band: amountBand,
        already_imported_count: importedInPage,
        ready_count: chunk.length - importedInPage,
      });
    }
    return {
      per_record_amt: base.per_record_amt,
      date: base.date,
      total: receipts.length,
      page_count: pages.length,
      page_size: size,
      amount_band: amountBand,
      auto_stationery: autoBand,
      pages: pages,
    };
  }

  function partitionGroups(groups) {
    lastReady = [];
    lastImported = [];
    (groups || []).forEach(function (group) {
      var receipts = flattenReceipts(group);
      var readyRecs = receipts.filter(function (rec) {
        return !rec.imported;
      });
      var importedRecs = receipts.filter(function (rec) {
        return !!rec.imported;
      });
      var pageSize = resolvePageSize(group, receipts);
      if (readyRecs.length) {
        lastReady.push(buildPagedGroup(group, readyRecs, pageSize, false));
      }
      if (importedRecs.length) {
        lastImported.push(buildPagedGroup(group, importedRecs, pageSize, true));
      }
    });
  }

  function renderExcludedRows(rows) {
    if (!els.excludedPanel || !els.excludedBody) return;
    var list = rows || [];
    if (!list.length) {
      els.excludedBody.innerHTML = "";
      els.excludedPanel.classList.add("d-none");
      return;
    }
    var html = "";
    list.forEach(function (row, idx) {
      html +=
        "<tr>" +
        "<td>" +
        (idx + 1) +
        "</td>" +
        "<td>" +
        escapeHtml(row.receipt_no || "—") +
        "</td>" +
        "<td>" +
        escapeHtml(displayDate(row.receipt_date)) +
        "</td>" +
        '<td class="text-end">' +
        escapeHtml(row.amount || "—") +
        "</td>" +
        "<td>" +
        escapeHtml(row.reason || "Outside amount range.") +
        "</td>" +
        "</tr>";
    });
    els.excludedBody.innerHTML = html;
    els.excludedPanel.classList.remove("d-none");
  }

  function emptyReadyCells() {
    return (
      '<td class="ecourt-test-side-empty text-muted">—</td>' +
      '<td class="ecourt-test-side-empty text-muted text-end">—</td>' +
      '<td class="ecourt-test-side-empty text-muted text-end">—</td>' +
      '<td class="ecourt-test-side-empty text-muted text-end">—</td>'
    );
  }

  function emptyImportedCells() {
    return (
      emptyReadyCells() +
      '<td class="ecourt-test-side-empty text-muted">—</td>'
    );
  }

  /** Unique stationery numbers in page order (1 per A4 / 20 receipts when amt ≤ 10). */
  function stationeryNumbersForGroup(group) {
    var seen = [];
    var seenKey = {};
    function pushStn(value) {
      var stn = normalizeStationery(value);
      if (!stn) return;
      var key = stn.toUpperCase();
      if (seenKey[key]) return;
      seenKey[key] = true;
      seen.push(stn);
    }
    (group.pages || []).forEach(function (page) {
      pushStn(page.stationerynumber);
      (page.receipts || []).forEach(function (rec) {
        pushStn(rec.stationerynumber);
      });
    });
    return seen;
  }

  function sideCells(group, sideClass, withStationery) {
    if (!group) {
      return withStationery ? emptyImportedCells() : emptyReadyCells();
    }
    var html =
      '<td class="' +
      sideClass +
      '">' +
      escapeHtml(displayDate(group.date)) +
      "</td>" +
      '<td class="' +
      sideClass +
      ' text-end">' +
      escapeHtml(group.per_record_amt) +
      "</td>" +
      '<td class="' +
      sideClass +
      ' text-end"><strong>' +
      escapeHtml(group.total) +
      "</strong></td>" +
      '<td class="' +
      sideClass +
      ' text-end">' +
      escapeHtml(group.page_count || 0) +
      "</td>";
    if (withStationery) {
      var stationeries = stationeryNumbersForGroup(group);
      html +=
        '<td class="' +
        sideClass +
        ' ecourt-test-stn-cell" title="' +
        escapeHtml(stationeries.join(", ")) +
        '">' +
        formatStationeryListHtml(stationeries) +
        "</td>";
    }
    return html;
  }

  function bandHelpText(group) {
    var band = group.amount_band || "";
    var pageSize = group.page_size || 20;
    var steps =
      band === "mid"
        ? "Pehle <strong>Apply</strong>, phir <strong>Import</strong>."
        : "Pehle <strong>Save</strong>, phir <strong>Apply</strong>, phir <strong>Import</strong>.";
    var base =
      (group.page_count || (group.pages || []).length) +
      " page(s) · Total " +
      escapeHtml(group.total) +
      " receipt(s). " +
      steps;
    if (band === "mid") {
      return (
        "Amount 11–999999999: 1 record/page · system stationery (disabled) · " +
        base
      );
    }
    if (band === "over") {
      return (
        "Amount above max: 1 record/page · enter stationery manually · " + base
      );
    }
    return (
      "Amount ≤10: " +
      pageSize +
      " records/A4 page · enter stationery · " +
      base
    );
  }

  function buildDetailHtml(group, groupKeyValue, heading) {
    var pages = group.pages || [];
    if (!pages.length) {
      return '<div class="small text-muted">No detail rows.</div>';
    }

    var html =
      '<div class="ecourt-test-detail" data-group="' +
      escapeHtml(groupKeyValue) +
      '">' +
      '<div class="ecourt-test-detail-heading">' +
      escapeHtml(heading) +
      "</div>" +
      '<div class="small text-muted mb-2">' +
      bandHelpText(group) +
      "</div>";

    pages.forEach(function (page, pageIndex) {
      var imported = !!page.imported;
      var applied = !!page.applied || imported;
      var autoStn = !!page.auto_stationery || !!group.auto_stationery;
      var stationery = page.stationerynumber || "";
      var saved = !!page.stationery_saved || autoStn || applied || imported;
      var inputDisabled = imported || applied || autoStn || saved;
      var saveDisabled = imported || applied || autoStn || saved;
      var editDisabled = imported || applied || autoStn || !saved;
      var applyDisabled = imported || applied || (!autoStn && !saved);
      var placeholder = autoStn
        ? "System generated"
        : "e.g. CK9000300001";
      html +=
        '<div class="ecourt-test-page-block' +
        (imported ? " ecourt-test-page-imported" : "") +
        (autoStn && !imported ? " ecourt-test-page-auto-stn" : "") +
        '" data-group="' +
        escapeHtml(groupKeyValue) +
        '" data-page="' +
        pageIndex +
        '">' +
        '<div class="ecourt-test-page-title">Page ' +
        escapeHtml(page.page_no) +
        " — " +
        escapeHtml(page.count) +
        " record(s)" +
        (autoStn && !imported ? " · System stationery" : "") +
        "</div>" +
        '<div class="ecourt-test-stationery-row">' +
        "<div>" +
        '<label for="ecourtTestStn_' +
        escapeHtml(groupKeyValue) +
        "_" +
        pageIndex +
        '">Stationery Number</label>' +
        '<input type="text" class="form-control form-control-sm ecourt-test-stationery-input" ' +
        'id="ecourtTestStn_' +
        escapeHtml(groupKeyValue) +
        "_" +
        pageIndex +
        '" data-group="' +
        escapeHtml(groupKeyValue) +
        '" data-page="' +
        pageIndex +
        '" value="' +
        escapeHtml(stationery) +
        '" placeholder="' +
        escapeHtml(placeholder) +
        '" ' +
        (inputDisabled ? "disabled" : "") +
        ">" +
        "</div>" +
        '<button type="button" class="btn btn-outline-secondary btn-sm ecourt-test-save" ' +
        'data-group="' +
        escapeHtml(groupKeyValue) +
        '" data-page="' +
        pageIndex +
        '" ' +
        (saveDisabled ? "disabled" : "") +
        ">" +
        (saved && !autoStn && !imported && !applied ? "Saved" : "Save") +
        "</button>" +
        '<button type="button" class="btn btn-outline-warning btn-sm ecourt-test-edit" ' +
        'data-group="' +
        escapeHtml(groupKeyValue) +
        '" data-page="' +
        pageIndex +
        '" ' +
        (editDisabled ? "disabled" : "") +
        ">Edit</button>" +
        '<button type="button" class="btn btn-outline-primary btn-sm ecourt-test-apply" ' +
        'data-group="' +
        escapeHtml(groupKeyValue) +
        '" data-page="' +
        pageIndex +
        '" ' +
        (applyDisabled ? "disabled" : "") +
        ">" +
        (applied && !imported ? "Applied" : "Apply") +
        "</button>" +
        '<button type="button" class="btn btn-success btn-sm ecourt-test-import" ' +
        'data-group="' +
        escapeHtml(groupKeyValue) +
        '" data-page="' +
        pageIndex +
        '" ' +
        (imported || !applied ? "disabled" : "") +
        ">" +
        (imported ? "Imported" : "Import") +
        "</button>" +
        "</div>" +
        '<table class="table table-sm table-bordered mb-0 ecourt-test-detail-table">' +
        "<thead><tr>" +
        '<th style="width:40px;">#</th>' +
        "<th>Receipt No.</th>" +
        '<th style="width:110px;">Date</th>' +
        '<th class="text-end" style="width:90px;">Amount</th>' +
        '<th style="width:140px;">Stationery</th>' +
        '<th style="width:140px;">Remark</th>' +
        "</tr></thead><tbody>";

      (page.receipts || []).forEach(function (rec, idx) {
        var remark = imported || rec.imported ? "Already Imported" : "Ready to Import";
        var remarkClass =
          imported || rec.imported
            ? "ecourt-test-remark-imported"
            : "ecourt-test-remark-ready";
        html +=
          "<tr>" +
          "<td>" +
          (idx + 1) +
          "</td>" +
          "<td>" +
          escapeHtml(rec.receipt_no) +
          "</td>" +
          "<td>" +
          escapeHtml(displayDate(rec.receipt_date)) +
          "</td>" +
          '<td class="text-end">' +
          escapeHtml(rec.amount) +
          "</td>" +
          "<td>" +
          formatStationeryHtml(rec.stationerynumber || stationery || "") +
          "</td>" +
          '<td class="' +
          remarkClass +
          '">' +
          escapeHtml(remark) +
          "</td>" +
          "</tr>";
      });

      html += "</tbody></table></div>";
    });

    html += "</div>";
    return html;
  }

  function buildRowDetailHtml(rowIndex) {
    var ready = lastReady[rowIndex];
    var imported = lastImported[rowIndex];
    var parts = [];
    if (ready) {
      parts.push(buildDetailHtml(ready, groupKey("ready", rowIndex), "Ready to import"));
    }
    if (imported) {
      parts.push(
        buildDetailHtml(imported, groupKey("imported", rowIndex), "Already Imported")
      );
    }
    if (!parts.length) {
      return '<div class="small text-muted">No detail rows.</div>';
    }
    return parts.join('<div class="ecourt-test-detail-split"></div>');
  }

  function renderGroups(groups) {
    if (!els.body) return;
    sourceGroups = groups || [];
    partitionGroups(sourceGroups);
    els.body.innerHTML = "";

    var rowCount = Math.max(lastReady.length, lastImported.length);
    if (!rowCount) {
      els.body.innerHTML =
        '<tr><td colspan="11" class="text-muted small py-4 text-center">PDF read ke baad grouped rows yahan full-width dikhengi.</td></tr>';
      return;
    }

    for (var index = 0; index < rowCount; index++) {
      var ready = lastReady[index] || null;
      var imported = lastImported[index] || null;
      var canExpand = !!(ready || imported);

      var parentTr = document.createElement("tr");
      parentTr.className = "ecourt-test-parent";
      parentTr.dataset.row = String(index);
      parentTr.innerHTML =
        '<td class="text-center">' +
        (canExpand
          ? '<button type="button" class="btn btn-link btn-sm p-0 ecourt-test-toggle" data-row="' +
            index +
            '" aria-label="Expand group">+</button>'
          : "") +
        "</td>" +
        "<td>" +
        (index + 1) +
        "</td>" +
        sideCells(ready, "ecourt-test-side-ready", false) +
        sideCells(imported, "ecourt-test-side-imported", true);
      els.body.appendChild(parentTr);

      var detailTr = document.createElement("tr");
      detailTr.className = "ecourt-test-child ecourt-test-child-" + index + " d-none";
      detailTr.dataset.row = String(index);
      if (ready) detailTr.dataset.ready = groupKey("ready", index);
      if (imported) detailTr.dataset.imported = groupKey("imported", index);
      detailTr.innerHTML =
        '<td colspan="11" class="ecourt-test-child-cell">' +
        buildRowDetailHtml(index) +
        "</td>";
      els.body.appendChild(detailTr);
    }
  }

  function refreshRowDetail(rowIndex) {
    var child = els.body?.querySelector(".ecourt-test-child-" + rowIndex);
    if (!child) return;
    var wasOpen = !child.classList.contains("d-none");
    child.innerHTML =
      '<td colspan="11" class="ecourt-test-child-cell">' +
      buildRowDetailHtml(rowIndex) +
      "</td>";
    if (wasOpen) child.classList.remove("d-none");
    var btn = els.body?.querySelector('.ecourt-test-toggle[data-row="' + rowIndex + '"]');
    if (btn) btn.textContent = wasOpen ? "−" : "+";
  }

  function refreshGroupDetail(groupKeyValue) {
    var match = String(groupKeyValue || "").match(/^([ri])(\d+)$/);
    if (!match) return;
    refreshRowDetail(Number(match[2]));
  }

  function toggleGroup(rowIndex) {
    var child = els.body?.querySelector(".ecourt-test-child-" + rowIndex);
    var btn = els.body?.querySelector('.ecourt-test-toggle[data-row="' + rowIndex + '"]');
    if (!child || !btn) return;
    var willExpand = child.classList.contains("d-none");
    child.classList.toggle("d-none", !willExpand);
    btn.textContent = willExpand ? "−" : "+";
  }

  function rowIndexFromGroupKey(groupKeyValue) {
    var match = String(groupKeyValue || "").match(/^([ri])(\d+)$/);
    return match ? Number(match[2]) : -1;
  }

  function saveStationery(groupKeyValue, pageIndex) {
    var group = getGroup(groupKeyValue);
    if (!group) return;
    var page = (group.pages || [])[pageIndex];
    if (!page) return;
    if (page.imported) {
      setStatus("This page is already imported.", true);
      return;
    }
    if (page.applied) {
      setStatus("Already applied. Now click Import.", true);
      return;
    }

    var autoStn = !!page.auto_stationery || !!group.auto_stationery;
    if (autoStn) {
      page.stationery_saved = true;
      refreshGroupDetail(groupKeyValue);
      setStatus("System stationery is ready. Click Apply.");
      return;
    }

    var input = document.getElementById(
      "ecourtTestStn_" + groupKeyValue + "_" + pageIndex
    );
    var stationery = normalizeStationery(input?.value);
    if (!stationery) {
      setStatus("Enter Stationery Number, then click Save.", true);
      input?.focus();
      return;
    }

    page.stationerynumber = stationery;
    page.stationery_saved = true;
    refreshGroupDetail(groupKeyValue);
    setStatus(
      "Saved stationery '" +
        stationery +
        "' on Page " +
        page.page_no +
        ". Check once, then Apply. Galat ho to Edit."
    );
  }

  function editStationery(groupKeyValue, pageIndex) {
    var group = getGroup(groupKeyValue);
    if (!group) return;
    var page = (group.pages || [])[pageIndex];
    if (!page) return;
    if (page.imported) {
      setStatus("This page is already imported.", true);
      return;
    }
    if (page.applied) {
      setStatus("Already applied. Edit nahi ho sakta — pehle Import ya naya page.", true);
      return;
    }

    var autoStn = !!page.auto_stationery || !!group.auto_stationery;
    if (autoStn) {
      setStatus("System stationery edit nahi hota.", true);
      return;
    }

    page.stationery_saved = false;
    refreshGroupDetail(groupKeyValue);
    var input = document.getElementById(
      "ecourtTestStn_" + groupKeyValue + "_" + pageIndex
    );
    input?.focus();
    input?.select?.();
    setStatus(
      "Editing stationery on Page " +
        page.page_no +
        ". Correct karke Save karo, phir Apply."
    );
  }

  function applyStationery(groupKeyValue, pageIndex) {
    var group = getGroup(groupKeyValue);
    if (!group) return;
    var page = (group.pages || [])[pageIndex];
    if (!page) return;
    if (page.imported) {
      setStatus("This page is already imported.", true);
      return;
    }
    if (page.applied) {
      setStatus("Already applied. Now click Import.", true);
      return;
    }

    var autoStn = !!page.auto_stationery || !!group.auto_stationery;
    if (!autoStn && !page.stationery_saved) {
      setStatus("Pehle Stationery Number Save karo, phir Apply.", true);
      return;
    }

    var input = document.getElementById(
      "ecourtTestStn_" + groupKeyValue + "_" + pageIndex
    );
    var stationery = normalizeStationery(
      autoStn
        ? page.stationerynumber || input?.value
        : page.stationerynumber || input?.value
    );
    if (!stationery) {
      setStatus(
        autoStn
          ? "System stationery missing. Read PDF again."
          : "Enter Stationery Number for this page.",
        true
      );
      if (!autoStn) input?.focus();
      return;
    }

    var stationeryKey = stationery.toUpperCase();
    if (usedStationery.has(stationeryKey)) {
      setStatus(
        "Stationery number '" + stationery + "' already used. Use another.",
        true
      );
      return;
    }

    usedStationery.add(stationeryKey);
    page.applied = true;
    page.stationery_saved = true;
    page.stationerynumber = stationery;
    (page.receipts || []).forEach(function (rec) {
      rec.stationerynumber = stationery;
      rec.stationery_applied = true;
      if (autoStn) rec.auto_stationery = true;
    });
    refreshGroupDetail(groupKeyValue);
    setStatus(
      "Applied stationery '" +
        stationery +
        "' on Page " +
        page.page_no +
        " (" +
        (page.count || page.receipts.length) +
        " records). Ab Import click karo."
    );
  }

  async function importPage(groupKeyValue, pageIndex) {
    var group = getGroup(groupKeyValue);
    if (!group) return;
    var page = (group.pages || [])[pageIndex];
    if (!page) return;
    if (page.imported) {
      setStatus("This A4 page is already imported.", true);
      return;
    }
    if (!page.applied || !normalizeStationery(page.stationerynumber)) {
      setStatus("Pehle Apply karo, phir Import.", true);
      return;
    }

    var stationery = normalizeStationery(page.stationerynumber);
    var rows = (page.receipts || [])
      .filter(function (rec) {
        return !rec.imported;
      })
      .map(function (rec) {
        return {
          receipt_no: rec.receipt_no,
          receipt_date: rec.receipt_date,
          amount: rec.amount,
          payment_mode: rec.payment_mode || "",
          receipt_status: rec.receipt_status || "",
          remarks: rec.remarks || "",
          stationerynumber: stationery,
        };
      });

    if (!rows.length) {
      setStatus("No receipts ready to import on this page.", true);
      return;
    }

    var importBtn = els.body?.querySelector(
      '.ecourt-test-import[data-group="' +
        groupKeyValue +
        '"][data-page="' +
        pageIndex +
        '"]'
    );
    if (importBtn) importBtn.disabled = true;
    setStatus("Importing page " + page.page_no + " with stationery " + stationery + "…");

    try {
      var res = await fetch(window.ECOURT_IMPORT_TEST_URLS.importPage, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": window.ECOURT_IMPORT_TEST_URLS.csrf || "",
        },
        body: JSON.stringify({
          file_name: importMeta.file_name,
          report_from: importMeta.report_from,
          report_to: importMeta.report_to,
          state_name: importMeta.state_name,
          total_amount: importMeta.total_amount,
          stationerynumber: stationery,
          rows: rows,
        }),
      });
      var data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.error || "Import failed.");
      }

      (page.receipts || []).forEach(function (rec) {
        if (!rec.imported) {
          rec.imported = true;
          rec.stationerynumber = stationery;
        }
      });
      page.imported = true;
      page.stationerynumber = stationery;

      // Re-split Ready / Already Imported after import.
      var openRow = rowIndexFromGroupKey(groupKeyValue);
      renderGroups(sourceGroups);
      if (openRow >= 0) {
        var child = els.body?.querySelector(".ecourt-test-child-" + openRow);
        var btn = els.body?.querySelector(
          '.ecourt-test-toggle[data-row="' + openRow + '"]'
        );
        if (child) child.classList.remove("d-none");
        if (btn) btn.textContent = "−";
      }

      setStatus("Import Successfully");
      window.alert("Import Successfully");
    } catch (err) {
      usedStationery.delete(stationery.toUpperCase());
      page.applied = false;
      var keepAuto = !!page.auto_stationery || !!group.auto_stationery;
      if (!keepAuto) {
        page.stationerynumber = "";
        page.stationery_saved = false;
      } else {
        page.stationery_saved = true;
      }
      (page.receipts || []).forEach(function (rec) {
        if (rec.imported) return;
        rec.stationery_applied = false;
        if (!keepAuto && !rec.auto_stationery) {
          rec.stationerynumber = "";
        }
      });
      refreshGroupDetail(groupKeyValue);
      setStatus(err.message || String(err), true);
    }
  }

  async function readPdf() {
    var file = els.fileInput?.files?.[0];
    if (!file) {
      setStatus("Select a PDF file first (top-right).", true);
      return;
    }

    var formData = new FormData();
    formData.append("receipt_pdf", file);

    els.readBtn.disabled = true;
    usedStationery = new Set();
    setStatus("Reading PDF…");
    try {
      var res = await fetch(window.ECOURT_IMPORT_TEST_URLS.parsePdf, {
        method: "POST",
        headers: {
          "X-CSRFToken": window.ECOURT_IMPORT_TEST_URLS.csrf || "",
        },
        body: formData,
      });
      var data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.error || "Unable to read PDF.");
      }

      importMeta = {
        file_name: data.file_name || file.name,
        report_from: data.report_from || "",
        report_to: data.report_to || "",
        state_name: data.state_name || "",
        total_amount: data.total_amount || "",
      };

      if (els.meta) {
        els.meta.textContent = [
          importMeta.file_name,
          importMeta.report_from && importMeta.report_to
            ? importMeta.report_from + " to " + importMeta.report_to
            : "",
          importMeta.state_name || "",
          importMeta.total_amount ? "PDF Total: " + importMeta.total_amount : "",
        ]
          .filter(Boolean)
          .join(" | ");
      }
      if (els.count) {
        els.count.textContent =
          (data.group_count || 0) +
          " group(s) · " +
          (data.record_count || 0) +
          " receipt(s)";
      }
      soldStationery = new Set(
        (data.sold_stationery_numbers || []).map(function (value) {
          return String(value || "").trim().toUpperCase();
        }).filter(Boolean)
      );
      renderGroups(data.groups || []);
      renderExcludedRows(data.excluded_rows || []);
      setStatus(data.message || "PDF read.");
      window.JTCSHotkeys?.refresh?.();
    } catch (err) {
      soldStationery = new Set();
      renderGroups([]);
      renderExcludedRows([]);
      setStatus(err.message || String(err), true);
    } finally {
      els.readBtn.disabled = false;
    }
  }

  els.readBtn.addEventListener("click", readPdf);
  els.body?.addEventListener("click", function (e) {
    var toggle = e.target.closest(".ecourt-test-toggle");
    if (toggle) {
      e.preventDefault();
      var row = Number(toggle.dataset.row);
      if (!Number.isNaN(row)) toggleGroup(row);
      return;
    }

    var saveBtn = e.target.closest(".ecourt-test-save");
    if (saveBtn) {
      e.preventDefault();
      var gs = saveBtn.dataset.group || "";
      var ps = Number(saveBtn.dataset.page);
      if (gs && !Number.isNaN(ps)) saveStationery(gs, ps);
      return;
    }

    var editBtn = e.target.closest(".ecourt-test-edit");
    if (editBtn) {
      e.preventDefault();
      var ge = editBtn.dataset.group || "";
      var pe = Number(editBtn.dataset.page);
      if (ge && !Number.isNaN(pe)) editStationery(ge, pe);
      return;
    }

    var applyBtn = e.target.closest(".ecourt-test-apply");
    if (applyBtn) {
      e.preventDefault();
      var g = applyBtn.dataset.group || "";
      var p = Number(applyBtn.dataset.page);
      if (g && !Number.isNaN(p)) applyStationery(g, p);
      return;
    }

    var importBtn = e.target.closest(".ecourt-test-import");
    if (importBtn) {
      e.preventDefault();
      var gi = importBtn.dataset.group || "";
      var pi = Number(importBtn.dataset.page);
      if (gi && !Number.isNaN(pi)) importPage(gi, pi);
    }
  });
})();
