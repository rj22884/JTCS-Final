(function () {
  "use strict";

  const api = window.INVOICE_API;
  if (!api) return;

  const items = api.items || [];
  const taxPeriods = api.taxPeriods || [];
  const serviceQuarters = api.serviceQuarters || [];
  const quarterMonths = api.quarterMonths || {};
  const voucherType = (api.voucherType || "SALE").toString().toUpperCase() === "PURCHASE"
    ? "PURCHASE"
    : "SALE";
  const allMonths = [
    "April", "May", "June", "July", "August", "September",
    "October", "November", "December", "January", "February", "March",
  ];
  const els = {
    form: document.getElementById("invForm"),
    status: document.getElementById("invStatus"),
    modeBadge: document.getElementById("invModeBadge"),
    newBtn: document.getElementById("invNewBtn"),
    saveBtn: document.getElementById("invSaveBtn"),
    addLine: document.getElementById("invAddLine"),
    body: document.getElementById("invLinesBody"),
    customerSearch: document.getElementById("invCustomerSearch"),
    customerSuggest: document.getElementById("invCustomerSuggest"),
    customerId: document.getElementById("invCustomerId"),
    customerName: document.getElementById("invCustomerName"),
    contactPerson: document.getElementById("invContactPerson"),
    gstin: document.getElementById("invGstin"),
    address: document.getElementById("invAddress"),
    mobile: document.getElementById("invMobile"),
    email: document.getElementById("invEmail"),
    place: document.getElementById("invPlace"),
    placeCode: document.getElementById("invPlaceCode"),
    date: document.getElementById("invDate"),
    no: document.getElementById("invNo"),
    id: document.getElementById("invId"),
    rcm: document.getElementById("invRcm"),
    notes: document.getElementById("invNotes"),
    payBank: document.getElementById("invPayBank"),
    payDate: document.getElementById("invPayDate"),
    amountPaid: document.getElementById("invAmountPaid"),
    kindGst: document.getElementById("invKindGst"),
    kindNonGst: document.getElementById("invKindNonGst"),
    taxHint: document.getElementById("invTaxHint"),
    words: document.getElementById("invWords"),
    gridBody: document.getElementById("invGridBody"),
    gridEmpty: document.getElementById("invGridEmpty"),
    gridCount: document.getElementById("invGridCount"),
    gridSearch: document.getElementById("invGridSearch"),
    gridRefresh: document.getElementById("invGridRefresh"),
    previewBody: document.getElementById("invPreviewBody"),
    previewTitle: document.getElementById("invPreviewModalTitle"),
  };

  const previewModalEl = document.getElementById("invPreviewModal");
  const previewModal =
    previewModalEl && window.bootstrap
      ? bootstrap.Modal.getOrCreateInstance(previewModalEl)
      : null;

  let previewTimer = null;
  let searchTimer = null;
  let gridTimer = null;
  let editingId = null;

  function apiUrl(template, id) {
    return String(template || "").replace(/\/0(?=$|\/)/, "/" + String(id));
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function showStatus(message, type) {
    if (!els.status) return;
    if (!message) {
      els.status.classList.add("d-none");
      els.status.textContent = "";
      return;
    }
    els.status.textContent = message;
    els.status.className = "alert py-2 small mb-3 alert-" + (type || "success");
    els.status.classList.remove("d-none");
  }

  function setModeBadge(isEdit) {
    if (!els.modeBadge) return;
    els.modeBadge.textContent = isEdit ? "Edit" : "New";
    els.modeBadge.className = "badge " + (isEdit ? "text-bg-warning" : "text-bg-secondary");
  }

  function money(v) {
    return Number(v || 0).toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function fmtDate(iso) {
    if (!iso || iso.length < 10) return iso || "";
    const p = iso.slice(0, 10).split("-");
    return p[2] + "/" + p[1] + "/" + p[0];
  }

  function digitsOnly(value) {
    return String(value || "").replace(/\D/g, "");
  }

  function selectedInvoiceKind() {
    if (els.kindGst?.checked) return "GST";
    if (els.kindNonGst?.checked) return "NON_GST";
    return "NON_GST";
  }

  function setInvoiceKind(kind, lock) {
    const isGst = String(kind || "").toUpperCase() === "GST";
    if (els.kindGst) els.kindGst.checked = isGst;
    if (els.kindNonGst) els.kindNonGst.checked = !isGst;
    const disabled = !!lock;
    if (els.kindGst) els.kindGst.disabled = disabled;
    if (els.kindNonGst) els.kindNonGst.disabled = disabled;
  }

  async function refreshInvoiceNo() {
    if (editingId) return;
    // Purchase: invoice number is entered manually (supplier bill no).
    if (voucherType === "PURCHASE") {
      if (els.no && !els.no.value) els.no.value = "";
      return;
    }
    try {
      const url = new URL(api.nextNo, window.location.origin);
      if (els.date?.value) url.searchParams.set("date", els.date.value);
      url.searchParams.set("kind", selectedInvoiceKind());
      const res = await fetch(url.toString(), { credentials: "same-origin" });
      const data = await res.json();
      if (data.ok && els.no) els.no.value = data.invoice_no;
      else if (els.no) els.no.value = api.nextInvoiceNo || "";
    } catch (_err) {
      if (els.no) els.no.value = api.nextInvoiceNo || "";
    }
  }

  function itemOptionsHtml(selectedId) {
    let html = '<option value="">— Select item —</option>';
    items.forEach(function (it) {
      html +=
        '<option value="' +
        it.item_id +
        '"' +
        (String(selectedId) === String(it.item_id) ? " selected" : "") +
        ">" +
        escapeHtml(it.label || it.item_name) +
        "</option>";
    });
    return html;
  }

  function periodOptionsHtml(selected) {
    let html = '<option value="">—</option>';
    taxPeriods.forEach(function (p) {
      html +=
        '<option value="' +
        escapeHtml(p) +
        '"' +
        (selected === p ? " selected" : "") +
        ">" +
        escapeHtml(p) +
        "</option>";
    });
    return html;
  }

  function quarterOptionsHtml(selected) {
    let html = '<option value="">—</option>';
    serviceQuarters.forEach(function (q) {
      html +=
        '<option value="' +
        escapeHtml(q) +
        '"' +
        (selected === q ? " selected" : "") +
        ">" +
        escapeHtml(q) +
        "</option>";
    });
    return html;
  }

  function monthOptionsHtml(quarter, selected) {
    const months = quarter && quarterMonths[quarter] ? quarterMonths[quarter] : allMonths;
    let html = '<option value="">—</option>';
    months.forEach(function (m) {
      html +=
        '<option value="' +
        escapeHtml(m) +
        '"' +
        (selected === m ? " selected" : "") +
        ">" +
        escapeHtml(m) +
        "</option>";
    });
    return html;
  }

  function syncLineMonthOptions(tr, selectedMonth) {
    const quarter = tr.querySelector(".inv-quarter")?.value || "";
    const monthSel = tr.querySelector(".inv-month");
    if (!monthSel) return;
    monthSel.innerHTML = monthOptionsHtml(quarter, selectedMonth || "");
  }

  function isServiceItem(it) {
    // SAC (Service) in Item Master HSN/SAC Type
    return String((it && it.hsn_sac_type) || "").toUpperCase() === "SAC";
  }

  function syncServicePeriodFields(tr) {
    const id = tr.querySelector(".inv-item")?.value || "";
    const it = items.find(function (x) {
      return String(x.item_id) === String(id);
    });
    const enabled = !!(it && isServiceItem(it));
    ["inv-period", "inv-quarter", "inv-month"].forEach(function (cls) {
      const sel = tr.querySelector("." + cls);
      if (!sel) return;
      sel.disabled = !enabled;
      if (!enabled) sel.value = "";
    });
    if (enabled) syncLineMonthOptions(tr, tr.querySelector(".inv-month")?.value || "");
  }

  async function servicePeriodReviewWarning() {
    const missing = [];
    els.body?.querySelectorAll(".inv-line").forEach(function (tr, idx) {
      const id = tr.querySelector(".inv-item")?.value || "";
      const it = items.find(function (x) {
        return String(x.item_id) === String(id);
      });
      if (!it || !isServiceItem(it)) return;
      const taxYear = (tr.querySelector(".inv-period")?.value || "").trim();
      const quarter = (tr.querySelector(".inv-quarter")?.value || "").trim();
      const month = (tr.querySelector(".inv-month")?.value || "").trim();
      if (!taxYear && !quarter && !month) {
        missing.push(idx + 1);
      }
    });
    if (!missing.length) return true;
    return JTCSDialog.confirm(
      "Review warning: Service item line(s) " +
        missing.join(", ") +
        " have no Tax Year / Quarter / Month selected.\n\n" +
        "At least one is recommended for review. Continue save anyway?"
    );
  }

  function clearLines() {
    if (els.body) els.body.innerHTML = "";
  }

  function addLine(pref) {
    pref = pref || {};
    const tr = document.createElement("tr");
    tr.className = "inv-line";
    tr.innerHTML =
      '<td><select class="form-select form-select-sm inv-item">' +
      itemOptionsHtml(pref.item_id) +
      "</select></td>" +
      '<td><select class="form-select form-select-sm inv-period">' +
      periodOptionsHtml(pref.tax_period || "") +
      "</select></td>" +
      '<td><select class="form-select form-select-sm inv-quarter">' +
      quarterOptionsHtml(pref.quarter || "") +
      "</select></td>" +
      '<td><select class="form-select form-select-sm inv-month">' +
      monthOptionsHtml(pref.quarter || "", pref.month || "") +
      "</select></td>" +
      '<td><input type="text" class="form-control form-control-sm inv-particulars" value="' +
      escapeHtml(pref.particulars || "") +
      '"></td>' +
      '<td><input type="text" class="form-control form-control-sm inv-hsn" value="' +
      escapeHtml(pref.hsn_sac || "") +
      '"></td>' +
      '<td><input type="text" class="form-control form-control-sm inv-unit" value="' +
      escapeHtml(pref.unit || "NOS") +
      '"></td>' +
      '<td><input type="number" step="0.001" min="0" class="form-control form-control-sm inv-qty" value="' +
      (pref.qty != null ? pref.qty : "1") +
      '"></td>' +
      '<td><input type="number" step="0.01" min="0" class="form-control form-control-sm inv-rate" value="' +
      (pref.rate != null ? pref.rate : "0") +
      '"></td>' +
      '<td><input type="number" step="0.01" min="0" class="form-control form-control-sm inv-disc" value="' +
      (pref.discount_amount != null ? pref.discount_amount : "0") +
      '"></td>' +
      '<td><input type="number" step="0.01" min="0" class="form-control form-control-sm inv-gst" value="' +
      (pref.gst_rate_percent != null ? pref.gst_rate_percent : "18") +
      '"></td>' +
      '<td class="text-end inv-taxable">0.00</td>' +
      '<td><button type="button" class="btn btn-outline-danger btn-sm inv-remove"><i class="bi bi-x"></i></button></td>';
    els.body.appendChild(tr);
    bindLine(tr);
    syncServicePeriodFields(tr);
    if (pref.tax_period || pref.quarter || pref.month) {
      const periodSel = tr.querySelector(".inv-period");
      const quarterSel = tr.querySelector(".inv-quarter");
      if (periodSel && pref.tax_period) periodSel.value = pref.tax_period;
      if (quarterSel && pref.quarter) quarterSel.value = pref.quarter;
      syncLineMonthOptions(tr, pref.month || "");
      syncServicePeriodFields(tr);
    }
    recalcLocal(tr);
    schedulePreview();
  }

  function bindLine(tr) {
    const itemSel = tr.querySelector(".inv-item");
    itemSel?.addEventListener("change", function () {
      const id = itemSel.value;
      const it = items.find(function (x) {
        return String(x.item_id) === String(id);
      });
      if (!it) {
        syncServicePeriodFields(tr);
        return;
      }
      tr.querySelector(".inv-hsn").value = it.hsn_sac || "";
      tr.querySelector(".inv-unit").value = it.unit || "NOS";
      tr.querySelector(".inv-rate").value = it.default_rate != null ? it.default_rate : 0;
      tr.querySelector(".inv-gst").value = it.gst_rate_percent != null ? it.gst_rate_percent : 18;
      syncServicePeriodFields(tr);
      recalcLocal(tr);
      schedulePreview();
    });
    tr.querySelector(".inv-quarter")?.addEventListener("change", function () {
      syncLineMonthOptions(tr, "");
    });
    tr.querySelectorAll("input").forEach(function (inp) {
      inp.addEventListener("input", function () {
        recalcLocal(tr);
        schedulePreview();
      });
    });
    tr.querySelector(".inv-remove")?.addEventListener("click", function () {
      tr.remove();
      schedulePreview();
    });
  }

  function recalcLocal(tr) {
    const qty = parseFloat(tr.querySelector(".inv-qty")?.value || "0") || 0;
    const rate = parseFloat(tr.querySelector(".inv-rate")?.value || "0") || 0;
    const disc = parseFloat(tr.querySelector(".inv-disc")?.value || "0") || 0;
    const taxable = Math.max(0, qty * rate - disc);
    const cell = tr.querySelector(".inv-taxable");
    if (cell) cell.textContent = taxable.toFixed(2);
  }

  function collectPayload() {
    const lines = [];
    els.body.querySelectorAll(".inv-line").forEach(function (tr) {
      lines.push({
        item_id: tr.querySelector(".inv-item")?.value || "",
        tax_period: tr.querySelector(".inv-period")?.value || "",
        quarter: tr.querySelector(".inv-quarter")?.value || "",
        month: tr.querySelector(".inv-month")?.value || "",
        particulars: tr.querySelector(".inv-particulars")?.value || "",
        hsn_sac: tr.querySelector(".inv-hsn")?.value || "",
        unit: tr.querySelector(".inv-unit")?.value || "NOS",
        qty: tr.querySelector(".inv-qty")?.value || "1",
        rate: tr.querySelector(".inv-rate")?.value || "0",
        discount_amount: tr.querySelector(".inv-disc")?.value || "0",
        gst_rate_percent: tr.querySelector(".inv-gst")?.value || "18",
      });
    });
    return {
      invoice_no: els.no?.value || "",
      invoice_date: els.date?.value || "",
      invoice_kind: selectedInvoiceKind(),
      voucher_type: voucherType,
      customer_id: els.customerId?.value || "",
      customer_name: els.customerName?.value || "",
      contact_person: els.contactPerson?.value || "",
      customer_gstin: els.gstin?.value || "",
      billing_address: els.address?.value || "",
      contact_mobile: els.mobile?.value || "",
      contact_email: els.email?.value || "",
      place_of_supply: els.place?.value || "",
      place_of_supply_code: els.placeCode?.value || "",
      reverse_charge: els.rcm?.value || "0",
      notes: els.notes?.value || "",
      payment_bank_account_id: els.payBank?.value || "",
      payment_date: els.payDate?.value || "",
      amount_paid: els.amountPaid?.value === "" || els.amountPaid?.value == null
        ? ""
        : els.amountPaid.value,
      lines: lines,
    };
  }

  function applyTotals(t) {
    if (!t) return;
    document.getElementById("totList").textContent = Number(t.list_price || 0).toFixed(2);
    document.getElementById("totDisc").textContent = Number(t.discount_amount || 0).toFixed(2);
    document.getElementById("totTaxable").textContent = Number(t.taxable_value || 0).toFixed(2);
    document.getElementById("totCgst").textContent = Number(t.cgst_amount || 0).toFixed(2);
    document.getElementById("totSgst").textContent = Number(t.sgst_amount || 0).toFixed(2);
    document.getElementById("totIgst").textContent = Number(t.igst_amount || 0).toFixed(2);
    document.getElementById("totValue").textContent = Number(t.invoice_value || 0).toFixed(2);
    document.getElementById("lblCgst").textContent =
      "CGST @ " + Number(t.cgst_rate || 0).toFixed(2) + "%";
    document.getElementById("lblSgst").textContent =
      "SGST @ " + Number(t.sgst_rate || 0).toFixed(2) + "%";
    document.getElementById("lblIgst").textContent =
      "IGST @ " + Number(t.igst_rate || 0).toFixed(2) + "%";
    const intra = t.tax_type === "CGST_SGST";
    document.getElementById("rowCgst").classList.toggle("d-none", !intra);
    document.getElementById("rowSgst").classList.toggle("d-none", !intra);
    document.getElementById("rowIgst").classList.toggle("d-none", intra);
    if (els.words) els.words.textContent = t.amount_in_words || "";
    if (els.taxHint) {
      const kindLabel = selectedInvoiceKind() === "NON_GST" ? "Non GST series" : "GST series";
      els.taxHint.textContent = intra
        ? kindLabel + ": Intra-state CGST + SGST applied."
        : kindLabel + ": Inter-state IGST applied.";
    }
  }

  function schedulePreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(runTotalsPreview, 350);
  }

  async function runTotalsPreview() {
    const payload = collectPayload();
    if (!payload.lines.length || !payload.customer_name) return;
    try {
      const res = await fetch(api.preview, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": api.csrf || "",
        },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.ok) applyTotals(data.totals);
    } catch (_err) {
      /* ignore */
    }
  }

  function fillRecord(record) {
    editingId = record.invoice_id || null;
    if (els.id) els.id.value = String(record.invoice_id || "");
    if (els.no) els.no.value = record.invoice_no || "";
    setInvoiceKind(record.invoice_kind || "NON_GST", true);
    if (els.date) els.date.value = (record.invoice_date || "").slice(0, 10);
    if (els.customerId) els.customerId.value = record.customer_id || "";
    if (els.customerSearch) els.customerSearch.value = record.customer_name || "";
    if (els.customerName) els.customerName.value = record.customer_name || "";
    if (els.contactPerson) els.contactPerson.value = record.contact_person || "";
    if (els.gstin) els.gstin.value = record.customer_gstin || "";
    if (els.address) els.address.value = record.billing_address || "";
    if (els.mobile) els.mobile.value = record.contact_mobile || "";
    if (els.email) els.email.value = record.contact_email || "";
    if (els.place) els.place.value = record.place_of_supply || "";
    if (els.placeCode) els.placeCode.value = record.place_of_supply_code || "";
    if (els.rcm) els.rcm.value = record.reverse_charge ? "1" : "0";
    if (els.notes) els.notes.value = record.notes || "";
    if (els.payBank) {
      const payId = record.payment_bank_account_id
        ? String(record.payment_bank_account_id)
        : "";
      if (payId) {
        const exists = Array.from(els.payBank.options).some(function (opt) {
          return opt.value === payId;
        });
        if (!exists && record.pay_account_number) {
          const opt = document.createElement("option");
          opt.value = payId;
          opt.textContent =
            (record.pay_bank_name || "Bank") +
            " · " +
            record.pay_account_number +
            (record.pay_upi_id ? " · UPI: " + record.pay_upi_id : "");
          els.payBank.appendChild(opt);
        }
        els.payBank.value = payId;
      } else {
        els.payBank.value = "";
      }
    }
    if (els.payDate) {
      els.payDate.value = (record.payment_date || api.today || "").slice(0, 10);
    }
    if (els.amountPaid) {
      els.amountPaid.value =
        record.amount_paid === null || record.amount_paid === undefined || record.amount_paid === ""
          ? ""
          : String(record.amount_paid);
    }

    clearLines();
    const lines = record.lines || [];
    if (lines.length) {
      lines.forEach(function (ln) {
        addLine(ln);
      });
    } else {
      addLine();
    }

    applyTotals({
      list_price: record.list_price,
      discount_amount: record.discount_amount,
      taxable_value: record.taxable_value,
      cgst_rate: record.cgst_rate,
      cgst_amount: record.cgst_amount,
      sgst_rate: record.sgst_rate,
      sgst_amount: record.sgst_amount,
      igst_rate: record.igst_rate,
      igst_amount: record.igst_amount,
      invoice_value: record.invoice_value,
      amount_in_words: record.amount_in_words,
      tax_type: record.tax_type,
      invoice_kind: record.invoice_kind,
    });
    setModeBadge(true);
    if (els.saveBtn) {
      els.saveBtn.innerHTML = '<i class="bi bi-save"></i> Update Invoice';
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function startNew() {
    editingId = null;
    if (els.id) els.id.value = "";
    setInvoiceKind("NON_GST", false);
    if (els.customerId) els.customerId.value = "";
    if (els.customerSearch) els.customerSearch.value = "";
    if (els.customerName) els.customerName.value = "";
    if (els.contactPerson) els.contactPerson.value = "";
    if (els.gstin) els.gstin.value = "";
    if (els.address) els.address.value = "";
    if (els.mobile) els.mobile.value = "";
    if (els.email) els.email.value = "";
    if (els.place) els.place.value = "";
    if (els.placeCode) els.placeCode.value = "";
    if (els.rcm) els.rcm.value = "0";
    if (els.notes) els.notes.value = "";
    if (els.payBank) els.payBank.value = "";
    if (els.payDate) els.payDate.value = api.today || new Date().toISOString().slice(0, 10);
    if (els.amountPaid) els.amountPaid.value = "";
    if (els.date) {
      // Purchase: user enters supplier invoice date; Sale defaults to today.
      els.date.value =
        voucherType === "PURCHASE"
          ? ""
          : api.today || new Date().toISOString().slice(0, 10);
    }
    if (els.no && voucherType === "PURCHASE") els.no.value = "";
    if (els.words) els.words.textContent = "";
    clearLines();
    addLine();
    applyTotals({
      list_price: 0,
      discount_amount: 0,
      taxable_value: 0,
      cgst_rate: 0,
      cgst_amount: 0,
      sgst_rate: 0,
      sgst_amount: 0,
      igst_rate: 0,
      igst_amount: 0,
      invoice_value: 0,
      amount_in_words: "",
      tax_type: "IGST",
      invoice_kind: "NON_GST",
    });
    await refreshInvoiceNo();
    setModeBadge(false);
    if (els.saveBtn) {
      els.saveBtn.innerHTML = '<i class="bi bi-save"></i> Save Invoice';
    }
    showStatus("New invoice form ready.", "info");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function saveInvoice() {
    const payload = collectPayload();
    if (!payload.invoice_kind) {
      showStatus("Select GST Invoice or Non GST Invoice.", "danger");
      return;
    }
    if (voucherType === "PURCHASE") {
      if (!(payload.invoice_no || "").trim()) {
        showStatus("Enter Supplier Invoice No.", "danger");
        els.no?.focus();
        return;
      }
      if (!(payload.invoice_date || "").trim()) {
        showStatus("Enter Invoice Date.", "danger");
        els.date?.focus();
        return;
      }
    }
    if (!payload.customer_id && !(editingId && payload.customer_name)) {
      showStatus(
        "Select a " +
          (voucherType === "PURCHASE" ? "supplier" : "customer") +
          " from the list to bill that party only.",
        "danger"
      );
      els.customerSearch?.focus();
      return;
    }
    if (!payload.customer_name) {
      showStatus((voucherType === "PURCHASE" ? "Supplier" : "Customer") + " Name is required.", "danger");
      return;
    }
    if (!payload.lines.length) {
      showStatus("Add at least one line item.", "danger");
      return;
    }
    if (!payload.payment_bank_account_id) {
      showStatus("Payment Bank Account is required.", "danger");
      els.payBank?.focus();
      return;
    }
    if (!(await servicePeriodReviewWarning())) {
      showStatus("Save cancelled. Select Tax Year / Quarter / Month for service item review.", "warning");
      return;
    }
    showStatus("Saving...", "info");
    const url = editingId ? apiUrl(api.update, editingId) : api.create;
    const res = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": api.csrf || "",
      },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Save failed");
    showStatus(data.message || "Saved.", "success");
    await loadGrid();
    await startNew();
  }

  async function loadForEdit(id) {
    const res = await fetch(apiUrl(api.get, id), { credentials: "same-origin" });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Load failed");
    fillRecord(data.record);
    showStatus("Editing " + (data.record.invoice_no || ""), "info");
  }

  async function deleteInvoice(id) {
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!(await JTCSDialog.confirm("Delete this invoice?"))) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: "Delete this invoice?" });
      if (!creds) return;
    }
    const res = await fetch(apiUrl(api.delete, id), {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": api.csrf || "",
      },
      body: JSON.stringify(creds ? window.JTCSDeleteConfirm.withCreds({}, creds) : {}),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Delete failed");
    showStatus(data.message || "Deleted.", "success");
    if (editingId && String(editingId) === String(id)) {
      await startNew();
    }
    await loadGrid();
  }

  function openWhatsApp(row) {
    const mobile = digitsOnly(row.contact_mobile || "");
    let phone = mobile;
    if (phone.length === 10) phone = "91" + phone;
    const company = api.companyName || "JTCS";
    const msg =
      "Dear " +
      (row.customer_name || "Customer") +
      ",\n\n" +
      "Your tax invoice from " +
      company +
      ":\n" +
      "Invoice No: " +
      (row.invoice_no || "") +
      "\n" +
      "Date: " +
      fmtDate(row.invoice_date) +
      "\n" +
      "Amount: Rs. " +
      money(row.invoice_value) +
      "\n\n" +
      "Thank you.";
    const url =
      "https://wa.me/" +
      (phone || "") +
      "?text=" +
      encodeURIComponent(msg);
    window.open(url, "_blank");
  }

  function renderGrid(rows) {
    if (!els.gridBody) return;
    els.gridBody.innerHTML = "";
    if (!rows.length) {
      els.gridEmpty?.classList.remove("d-none");
      if (els.gridCount) els.gridCount.textContent = "0 invoices";
      return;
    }
    els.gridEmpty?.classList.add("d-none");
    if (els.gridCount) {
      els.gridCount.textContent = rows.length + " invoice" + (rows.length === 1 ? "" : "s");
    }
    rows.forEach(function (row) {
      const taxLabel =
        row.tax_type === "CGST_SGST"
          ? "CGST+SGST"
          : "IGST " + Number(row.igst_rate || 0).toFixed(0) + "%";
      const tr = document.createElement("tr");
      tr.innerHTML =
        "<td><code>" +
        escapeHtml(row.invoice_no) +
        "</code></td>" +
        "<td>" +
        escapeHtml(fmtDate(row.invoice_date)) +
        "</td>" +
        "<td>" +
        escapeHtml(row.customer_name) +
        "</td>" +
        "<td>" +
        escapeHtml(row.contact_mobile || "—") +
        "</td>" +
        "<td>" +
        escapeHtml(taxLabel) +
        "</td>" +
        '<td class="text-end fw-semibold">' +
        money(row.invoice_value) +
        "</td>" +
        '<td class="text-end text-nowrap">' +
        '<button type="button" class="btn btn-outline-primary btn-sm me-1 inv-g-edit" data-id="' +
        row.invoice_id +
        '" title="Edit"><i class="bi bi-pencil"></i></button>' +
        '<button type="button" class="btn btn-outline-danger btn-sm me-1 inv-g-del" data-id="' +
        row.invoice_id +
        '" title="Delete"><i class="bi bi-trash"></i></button>' +
        '<button type="button" class="btn btn-outline-info btn-sm me-1 inv-g-preview" data-id="' +
        row.invoice_id +
        '" data-no="' +
        escapeHtml(row.invoice_no || "") +
        '" title="Preview"><i class="bi bi-eye"></i></button>' +
        '<a class="btn btn-outline-secondary btn-sm me-1" href="' +
        apiUrl(api.pdf, row.invoice_id) +
        '" target="_blank" rel="noopener" title="PDF"><i class="bi bi-file-earmark-pdf"></i></a>' +
        '<button type="button" class="btn btn-outline-success btn-sm inv-g-wa" data-id="' +
        row.invoice_id +
        '" title="WhatsApp"><i class="bi bi-whatsapp"></i></button>' +
        "</td>";
      tr.querySelector(".inv-g-wa").dataset.row = JSON.stringify({
        invoice_id: row.invoice_id,
        invoice_no: row.invoice_no,
        invoice_date: row.invoice_date,
        customer_name: row.customer_name,
        contact_mobile: row.contact_mobile,
        invoice_value: row.invoice_value,
      });
      els.gridBody.appendChild(tr);
    });
  }

  async function loadGrid() {
    const url = new URL(api.list, window.location.origin);
    const q = (els.gridSearch?.value || "").trim();
    if (q) url.searchParams.set("search", q);
    if (voucherType) url.searchParams.set("voucher_type", voucherType);
    const res = await fetch(url.toString(), { credentials: "same-origin" });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Grid load failed");
    renderGrid(data.rows || []);
  }

  async function searchCustomers(q) {
    const url = new URL(api.customers, window.location.origin);
    if (q) url.searchParams.set("q", q);
    const res = await fetch(url.toString(), { credentials: "same-origin" });
    const data = await res.json();
    return data.rows || [];
  }

  function hideSuggest() {
    els.customerSuggest?.classList.add("d-none");
    if (els.customerSuggest) els.customerSuggest.innerHTML = "";
  }

  async function pickCustomer(id) {
    const res = await fetch(apiUrl(api.customer, id), { credentials: "same-origin" });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Customer load failed");
    const r = data.record;
    els.customerId.value = r.customer_id || "";
    els.customerName.value = r.customer_name || "";
    els.customerSearch.value = r.customer_name || "";
    els.contactPerson.value = r.contact_person || "";
    els.gstin.value = r.customer_gstin || "";
    els.address.value = r.billing_address || "";
    els.mobile.value = r.contact_mobile || "";
    els.email.value = r.contact_email || "";
    els.place.value = r.place_of_supply || "";
    els.placeCode.value = r.place_of_supply_code || "";
    hideSuggest();
    schedulePreview();
  }

  function clearSelectedCustomer() {
    if (els.customerId) els.customerId.value = "";
    if (els.customerName) els.customerName.value = "";
    if (els.contactPerson) els.contactPerson.value = "";
    if (els.gstin) els.gstin.value = "";
    if (els.address) els.address.value = "";
    if (els.mobile) els.mobile.value = "";
    if (els.email) els.email.value = "";
    if (els.place) els.place.value = "";
    if (els.placeCode) els.placeCode.value = "";
  }

  els.customerSearch?.addEventListener("input", function () {
    // Typing a new query invalidates previous selection until a list item is chosen.
    if (els.customerId?.value) {
      clearSelectedCustomer();
    }
    clearTimeout(searchTimer);
    const q = (els.customerSearch.value || "").trim();
    searchTimer = setTimeout(async function () {
      if (q.length < 2) {
        hideSuggest();
        return;
      }
      try {
        const rows = await searchCustomers(q);
        if (!els.customerSuggest) return;
        els.customerSuggest.innerHTML = "";
        if (!rows.length) {
          hideSuggest();
          return;
        }
        rows.forEach(function (row) {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "list-group-item list-group-item-action py-1 small";
          btn.textContent =
            row.label +
            (row.gstin ? " · " + row.gstin : "") +
            (row.state ? " · " + row.state : "");
          btn.addEventListener("click", function () {
            pickCustomer(row.customer_id).catch(function (err) {
              showStatus(err.message || String(err), "danger");
            });
          });
          els.customerSuggest.appendChild(btn);
        });
        els.customerSuggest.classList.remove("d-none");
      } catch (err) {
        showStatus(err.message || String(err), "danger");
      }
    }, 250);
  });

  document.addEventListener("click", function (ev) {
    if (!ev.target.closest("#invCustomerSearch") && !ev.target.closest("#invCustomerSuggest")) {
      hideSuggest();
    }
  });

  ["invPlace", "invPlaceCode", "invCustomerName"].forEach(function (id) {
    document.getElementById(id)?.addEventListener("input", schedulePreview);
  });

  document.querySelectorAll('input[name="invKind"]').forEach(function (radio) {
    radio.addEventListener("change", function () {
      refreshInvoiceNo().catch(function () {});
      schedulePreview();
    });
  });

  els.date?.addEventListener("change", function () {
    refreshInvoiceNo().catch(function () {});
    schedulePreview();
  });

  els.addLine?.addEventListener("click", function () {
    addLine();
  });

  els.newBtn?.addEventListener("click", function () {
    startNew().catch(function (err) {
      showStatus(err.message || String(err), "danger");
    });
  });

  els.saveBtn?.addEventListener("click", function () {
    saveInvoice().catch(function (err) {
      showStatus(err.message || String(err), "danger");
    });
  });

  els.gridRefresh?.addEventListener("click", function () {
    loadGrid().catch(function (err) {
      showStatus(err.message || String(err), "danger");
    });
  });

  els.gridSearch?.addEventListener("input", function () {
    clearTimeout(gridTimer);
    gridTimer = setTimeout(function () {
      loadGrid().catch(function (err) {
        showStatus(err.message || String(err), "danger");
      });
    }, 300);
  });

  async function openHtmlPreview(invoiceId, invoiceNo) {
    if (!previewModal || !els.previewBody) {
      showStatus("Preview modal is not available.", "danger");
      return;
    }
    if (els.previewTitle) {
      els.previewTitle.textContent = invoiceNo
        ? "Invoice Preview — " + invoiceNo
        : "Invoice Preview";
    }
    els.previewBody.innerHTML =
      '<div class="text-muted small py-4 text-center">Loading preview…</div>';
    previewModal.show();
    try {
      const res = await fetch(apiUrl(api.previewHtml, invoiceId), {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "Preview failed");
      els.previewBody.innerHTML = data.html || "";
      if (els.previewTitle && data.invoice_no) {
        els.previewTitle.textContent = "Invoice Preview — " + data.invoice_no;
      }
    } catch (err) {
      els.previewBody.innerHTML =
        '<div class="alert alert-danger py-2 small mb-0">' +
        escapeHtml(err.message || String(err)) +
        "</div>";
    }
  }

  els.gridBody?.addEventListener("click", function (ev) {
    const editBtn = ev.target.closest(".inv-g-edit");
    const delBtn = ev.target.closest(".inv-g-del");
    const previewBtn = ev.target.closest(".inv-g-preview");
    const waBtn = ev.target.closest(".inv-g-wa");
    if (editBtn) {
      loadForEdit(editBtn.getAttribute("data-id")).catch(function (err) {
        showStatus(err.message || String(err), "danger");
      });
    }
    if (delBtn) {
      deleteInvoice(delBtn.getAttribute("data-id")).catch(function (err) {
        showStatus(err.message || String(err), "danger");
      });
    }
    if (previewBtn) {
      openHtmlPreview(
        previewBtn.getAttribute("data-id"),
        previewBtn.getAttribute("data-no") || ""
      ).catch(function (err) {
        showStatus(err.message || String(err), "danger");
      });
    }
    if (waBtn) {
      try {
        const row = JSON.parse(waBtn.dataset.row || "{}");
        openWhatsApp(row);
      } catch (err) {
        showStatus(err.message || String(err), "danger");
      }
    }
  });

  (async function init() {
    await startNew();
    await loadGrid();
    const params = new URLSearchParams(window.location.search || "");
    const editId = (params.get("edit") || "").trim();
    const deepCustomerId = (params.get("customer_id") || "").trim();
    if (editId) {
      await loadForEdit(editId);
    } else if (deepCustomerId) {
      await pickCustomer(deepCustomerId);
    }
  })().catch(function (err) {
    showStatus(err.message || String(err), "danger");
    addLine();
  });
})();
