(function () {
  "use strict";

  const cfg = window.MGB || {};
  const STORAGE_KEY = "oieMiscGenerateBill";

  const els = {
    form: document.getElementById("mgbForm"),
    date: document.getElementById("mgbDate"),
    taxYear: document.getElementById("mgbTaxYear"),
    invoiceNo: document.getElementById("mgbInvoiceNo"),
    invoiceId: document.getElementById("mgbInvoiceId"),
    customerId: document.getElementById("mgbCustomerId"),
    customerName: document.getElementById("mgbCustomerName"),
    item: document.getElementById("mgbItem"),
    itemDesc: document.getElementById("mgbItemDesc"),
    itemId: document.getElementById("mgbItemId"),
    rate: document.getElementById("mgbRate"),
    state: document.getElementById("mgbState"),
    placeCode: document.getElementById("mgbPlaceCode"),
    gstRate: document.getElementById("mgbGstRate"),
    cgst: document.getElementById("mgbCgst"),
    sgst: document.getElementById("mgbSgst"),
    igst: document.getElementById("mgbIgst"),
    amount: document.getElementById("mgbAmount"),
    address: document.getElementById("mgbAddress"),
    hsn: document.getElementById("mgbHsn"),
    unit: document.getElementById("mgbUnit"),
    tallyBillNo: document.getElementById("mgbTallyBillNo"),
    mobile: document.getElementById("mgbMobile"),
    taxHint: document.getElementById("mgbTaxHint"),
    error: document.getElementById("mgbError"),
    ok: document.getElementById("mgbOk"),
    previewBtn: document.getElementById("mgbPreviewBtn"),
    downloadBtn: document.getElementById("mgbDownloadBtn"),
    closeBtn: document.getElementById("mgbCloseBtn"),
    closeBtn2: document.getElementById("mgbCloseBtn2"),
    convertBtn: document.getElementById("mgbConvertBtn"),
    editBtn: document.getElementById("mgbEditBtn"),
    deleteBtn: document.getElementById("mgbDeleteBtn"),
    banks: document.getElementById("mgbBanks"),
    saveBtn: document.getElementById("mgbSaveBtn"),
    customerMode: document.getElementById("mgbCustomerMode"),
    billSame: document.getElementById("mgbBillSame"),
    billAnother: document.getElementById("mgbBillAnother"),
    linesWrap: document.getElementById("mgbLinesWrap"),
    lineBody: document.getElementById("mgbLineBody"),
    addLineBtn: document.getElementById("mgbAddLine"),
    customerList: document.getElementById("mgbCustomerList"),
    roundOffAmt: document.getElementById("mgbRoundOffAmt"),
    roundOffSign: document.getElementById("mgbRoundOffSign"),
    roundOffAdd: document.getElementById("mgbRoundOffAdd"),
    roundOffSub: document.getElementById("mgbRoundOffSub"),
  };

  const items = Array.isArray(cfg.items) ? cfg.items : [];
  let dscMode = false;
  let customerPickName = "";
  let billAnotherCustomer = false;
  let entryCustomer = { id: "", name: "" };

  function money(n) {
    const v = Number(n);
    if (!Number.isFinite(v)) return 0;
    return Math.round((v + Number.EPSILON) * 100) / 100;
  }

  function fmt(n) {
    return money(n).toFixed(2);
  }

  function roundOffMagnitude() {
    return Math.abs(parseFloat(els.roundOffAmt?.value || "0") || 0);
  }

  function roundOffSigned() {
    const mag = roundOffMagnitude();
    const sign = (els.roundOffSign?.value || "").toLowerCase();
    if (sign === "add") return mag;
    if (sign === "sub") return -mag;
    return 0;
  }

  function setRoundOffSign(sign) {
    const next = sign === "add" || sign === "sub" ? sign : "";
    if (els.roundOffSign) els.roundOffSign.value = next;
    els.roundOffAdd?.classList.toggle("is-on", next === "add");
    els.roundOffSub?.classList.toggle("is-on", next === "sub");
  }

  function applyRoundOff(sign) {
    if (!roundOffMagnitude()) {
      showError("Round off value enter karein, phir + ya − dabayein.");
      els.roundOffAmt?.focus();
      return;
    }
    showError("");
    setRoundOffSign(sign);
    computeTaxes();
  }

  function showError(msg) {
    if (els.ok) {
      els.ok.textContent = "";
      els.ok.classList.add("d-none");
    }
    if (!els.error) return;
    if (!msg) {
      els.error.textContent = "";
      els.error.classList.add("d-none");
      return;
    }
    els.error.textContent = msg;
    els.error.classList.remove("d-none");
  }

  function showOk(msg) {
    if (els.error) {
      els.error.textContent = "";
      els.error.classList.add("d-none");
    }
    if (!els.ok) return;
    if (!msg) {
      els.ok.textContent = "";
      els.ok.classList.add("d-none");
      return;
    }
    els.ok.textContent = msg;
    els.ok.classList.remove("d-none");
  }

  function selectedStateCode() {
    const opt = els.state?.options?.[els.state.selectedIndex];
    return (opt && opt.getAttribute("data-code")) || "";
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function itemById(id) {
    return items.find(function (it) {
      return String(it.item_id) === String(id);
    });
  }

  function itemDesc(it) {
    return String((it && it.description) || "").trim();
  }

  function optionList(kind, selectedId) {
    let html = '<option value="">— Select —</option>';
    items.forEach(function (it) {
      const label = kind === "desc" ? itemDesc(it) || it.item_name : it.item_name;
      html +=
        '<option value="' +
        escapeHtml(it.item_id) +
        '"' +
        (String(selectedId) === String(it.item_id) ? " selected" : "") +
        ">" +
        escapeHtml(label) +
        "</option>";
    });
    return html;
  }

  function lineRows() {
    return els.lineBody ? Array.from(els.lineBody.querySelectorAll(".mgb-line")) : [];
  }

  function applyItemToLine(tr, id) {
    const it = itemById(id);
    const itemSel = tr.querySelector(".mgb-line-item");
    const descSel = tr.querySelector(".mgb-line-desc");
    if (itemSel) itemSel.value = id ? String(id) : "";
    if (descSel) descSel.value = id ? String(id) : "";
    if (!it) {
      tr.dataset.hsn = "";
      tr.dataset.unit = "NOS";
      recalcDscLine(tr);
      return;
    }
    const rate = tr.querySelector(".mgb-line-rate");
    const gst = tr.querySelector(".mgb-line-gst");
    const qty = tr.querySelector(".mgb-line-qty");
    if (rate) rate.value = it.default_rate != null ? String(it.default_rate) : "0";
    if (gst) gst.value = it.gst_rate_percent != null ? String(it.gst_rate_percent) : "0";
    if (qty && !(qty.value || "").trim()) qty.value = "1";
    tr.dataset.hsn = it.hsn_sac || "";
    tr.dataset.unit = it.unit || "NOS";
    recalcDscLine(tr);
  }

  function recalcDscLine(tr) {
    const qty = Number(tr.querySelector(".mgb-line-qty")?.value);
    const rate = Number(tr.querySelector(".mgb-line-rate")?.value);
    const gst = Number(tr.querySelector(".mgb-line-gst")?.value);
    const taxable = money((Number.isFinite(qty) ? qty : 0) * (Number.isFinite(rate) ? rate : 0));
    const gstAmt = money((taxable * (Number.isFinite(gst) ? gst : 0)) / 100);
    const cell = tr.querySelector(".mgb-line-amt");
    if (cell) cell.textContent = fmt(taxable + gstAmt);
    tr.dataset.taxable = String(taxable);
    tr.dataset.gstAmt = String(gstAmt);
  }

  function addDscLine(pref) {
    pref = pref || {};
    if (!els.lineBody) return;
    const tr = document.createElement("tr");
    tr.className = "mgb-line";
    tr.innerHTML =
      "<td><select class=\"form-select form-select-sm mgb-line-item\">" +
      optionList("item", pref.item_id) +
      "</select></td>" +
      "<td><select class=\"form-select form-select-sm mgb-line-desc\">" +
      optionList("desc", pref.item_id) +
      "</select></td>" +
      "<td><input type=\"number\" class=\"form-control form-control-sm mgb-line-qty\" min=\"0\" step=\"0.001\" value=\"" +
      escapeHtml(pref.qty != null && pref.qty !== "" ? pref.qty : "1") +
      "\"></td>" +
      "<td><input type=\"number\" class=\"form-control form-control-sm mgb-line-rate\" min=\"0\" step=\"0.01\" value=\"" +
      escapeHtml(pref.rate != null ? pref.rate : "") +
      "\"></td>" +
      "<td><input type=\"number\" class=\"form-control form-control-sm mgb-line-gst\" min=\"0\" step=\"0.01\" readonly value=\"" +
      escapeHtml(pref.gst_rate_percent != null ? pref.gst_rate_percent : "") +
      "\"></td>" +
      "<td class=\"text-end mgb-line-amt\">0.00</td>" +
      "<td><button type=\"button\" class=\"btn btn-outline-danger btn-sm mgb-line-remove\" title=\"Remove\"><i class=\"bi bi-x\"></i></button></td>";
    els.lineBody.appendChild(tr);
    tr.querySelector(".mgb-line-item")?.addEventListener("change", function (event) {
      applyItemToLine(tr, event.target.value);
      computeTaxes();
    });
    tr.querySelector(".mgb-line-desc")?.addEventListener("change", function (event) {
      applyItemToLine(tr, event.target.value);
      computeTaxes();
    });
    tr.querySelectorAll(".mgb-line-qty, .mgb-line-rate").forEach(function (input) {
      input.addEventListener("input", function () {
        recalcDscLine(tr);
        computeTaxes();
      });
    });
    tr.querySelector(".mgb-line-remove")?.addEventListener("click", function () {
      if (lineRows().length <= 1) {
        applyItemToLine(tr, "");
        const qty = tr.querySelector(".mgb-line-qty");
        const rate = tr.querySelector(".mgb-line-rate");
        const gst = tr.querySelector(".mgb-line-gst");
        if (qty) qty.value = "1";
        if (rate) rate.value = "";
        if (gst) gst.value = "";
        recalcDscLine(tr);
      } else {
        tr.remove();
      }
      computeTaxes();
    });
    if (pref.item_id) {
      applyItemToLine(tr, pref.item_id);
      if (pref.rate != null && pref.rate !== "") {
        const rate = tr.querySelector(".mgb-line-rate");
        if (rate) rate.value = String(pref.rate);
      }
      if (pref.gst_rate_percent != null && pref.gst_rate_percent !== "") {
        const gst = tr.querySelector(".mgb-line-gst");
        if (gst) gst.value = String(pref.gst_rate_percent);
      }
      if (pref.qty != null && pref.qty !== "") {
        const qty = tr.querySelector(".mgb-line-qty");
        if (qty) qty.value = String(pref.qty);
      }
      recalcDscLine(tr);
    }
  }

  function enableDscMode() {
    dscMode = true;
    document.body.classList.add("mgb-dsc");
    document.querySelectorAll(".mgb-single").forEach(function (node) {
      node.classList.add("d-none");
    });
    if (els.item) els.item.required = false;
    if (els.rate) els.rate.required = false;
    els.linesWrap?.classList.remove("d-none");
    if (els.customerName) {
      els.customerName.readOnly = true;
    }
    els.customerMode?.classList.remove("d-none");
    els.saveBtn?.classList.remove("d-none");
    document.getElementById("mgbInvHead")?.classList.remove("d-none");
    document.getElementById("mgbInvTitle")?.classList.remove("d-none");
    document.querySelector(".mgb-old-title")?.classList.add("d-none");
    document.getElementById("mgbParty")?.classList.remove("d-none");
    document.getElementById("mgbTotals")?.classList.remove("d-none");
    document.querySelectorAll(".mgb-tax-field").forEach(function (node) {
      node.classList.add("d-none");
    });
    const stateEl = document.getElementById("mgbState");
    const placeSlot = document.getElementById("mgbPartyPlaceSlot");
    if (stateEl && placeSlot && !placeSlot.contains(stateEl)) placeSlot.appendChild(stateEl);
    document.getElementById("mgbStateWrap")?.classList.add("d-none");
    const addressEl = document.getElementById("mgbAddress");
    const addressSlot = document.getElementById("mgbPartyAddressSlot");
    if (addressEl && addressSlot && !addressSlot.contains(addressEl)) addressSlot.appendChild(addressEl);
    document.getElementById("mgbAddressWrap")?.classList.add("d-none");
    if (els.billSame) els.billSame.checked = true;
    if (els.billAnother) els.billAnother.checked = false;
    billAnotherCustomer = false;
    const amountLabel = document.querySelector('label[for="mgbAmount"]');
    if (amountLabel) amountLabel.textContent = "Total incl. GST (₹)";
    if (!lineRows().length) addDscLine();
  }

  function fillPartyPanel(record) {
    record = record || {};
    const name = record.customer_name || els.customerName?.value || "";
    const mobile = record.contact_mobile || els.mobile?.value || "";
    const code = record.place_of_supply_code || els.placeCode?.value || "";
    const set = function (id, value) {
      const node = document.getElementById(id);
      if (node) node.value = value || "";
    };
    set("mgbPartyName", name);
    set("mgbPartyContact", record.contact_person || "");
    set("mgbPartyGstin", record.customer_gstin || "");
    set("mgbPartyMobile", mobile);
    set("mgbPartyEmail", record.contact_email || "");
    set("mgbPartyStateCode", code);
  }

  function hideCustomerList() {
    els.customerList?.classList.add("d-none");
    if (els.customerList) els.customerList.innerHTML = "";
  }

  function rememberEntryCustomer() {
    const id = (els.customerId?.value || "").trim();
    const name = (els.customerName?.value || "").trim();
    if (!entryCustomer.id && id) entryCustomer.id = id;
    if (!entryCustomer.name && name) entryCustomer.name = name;
  }

  function applyCustomerMode() {
    rememberEntryCustomer();
    billAnotherCustomer = !!els.billAnother?.checked;
    if (!billAnotherCustomer) {
      if (els.customerId) els.customerId.value = entryCustomer.id || "";
      if (els.customerName) {
        els.customerName.value = entryCustomer.name || "";
        els.customerName.readOnly = true;
      }
      customerPickName = (els.customerName?.value || "").trim();
      hideCustomerList();
      if (entryCustomer.id) loadCustomerAddress(entryCustomer.id);
      return;
    }
    if (els.customerId) els.customerId.value = "";
    customerPickName = "";
    if (els.customerName) {
      els.customerName.value = "";
      els.customerName.readOnly = false;
      els.customerName.placeholder = "Customer Master se naam select karein";
      els.customerName.focus();
    }
    searchCustomers("", false).catch(function () {
      hideCustomerList();
    });
  }

  async function searchCustomers(query, silent) {
    const q = String(query || "").trim();
    const listUrl = cfg.customerListUrl || cfg.customerSearchUrl;
    if (!dscMode || !listUrl || (!billAnotherCustomer && q.length < 1)) {
      hideCustomerList();
      return [];
    }
    const url = new URL(listUrl, window.location.origin);
    if (q) url.searchParams.set("q", q);
    const res = await fetch(url.toString(), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    const data = await res.json().catch(function () {
      return {};
    });
    const rows = data.ok && Array.isArray(data.rows) ? data.rows : [];
    if (silent || !els.customerList) return rows;
    if (!rows.length) {
      hideCustomerList();
      return rows;
    }
    els.customerList.innerHTML = rows
      .map(function (row, index) {
        const extra = row.mobile ? " · " + row.mobile : "";
        return (
          "<button type=\"button\" data-index=\"" +
          index +
          "\">" +
          escapeHtml((row.customer_name || "") + extra) +
          "</button>"
        );
      })
      .join("");
    els.customerList.classList.remove("d-none");
    els.customerList.querySelectorAll("button").forEach(function (btn) {
      btn.addEventListener("mousedown", function (event) {
        event.preventDefault();
        const row = rows[Number(btn.getAttribute("data-index"))];
        if (row) selectCustomer(row);
      });
    });
    return rows;
  }

  function selectCustomer(row) {
    if (!row) return;
    if (els.customerId) els.customerId.value = String(row.customer_id || "");
    if (els.customerName) els.customerName.value = row.customer_name || "";
    customerPickName = (els.customerName?.value || "").trim();
    if (els.mobile && row.mobile) els.mobile.value = row.mobile;
    const partyName = document.getElementById("mgbPartyName");
    if (partyName) partyName.value = row.customer_name || "";
    const partyMobile = document.getElementById("mgbPartyMobile");
    if (partyMobile && row.mobile) partyMobile.value = row.mobile;
    hideCustomerList();
    if (row.customer_id) loadCustomerAddress(row.customer_id);
  }

  async function ensureCustomerFromMaster() {
    const currentId = (els.customerId?.value || "").trim();
    const name = (els.customerName?.value || "").trim();
    if (currentId) {
      customerPickName = name;
      rememberEntryCustomer();
      if (!billAnotherCustomer && els.customerName) els.customerName.readOnly = true;
      loadCustomerAddress(currentId);
      return;
    }
    if (name.length < 2) return;
    const rows = await searchCustomers(name, true);
    const exact = rows.filter(function (row) {
      return String(row.customer_name || "").trim().toLowerCase() === name.toLowerCase();
    });
    if (exact.length === 1) {
      selectCustomer(exact[0]);
      rememberEntryCustomer();
      if (!billAnotherCustomer && els.customerName) els.customerName.readOnly = true;
    } else hideCustomerList();
  }

  function buildParticulars() {
    const item = (els.item?.value || "").trim();
    const desc = (els.itemDesc?.value || "").trim();
    if (item && desc) return item + " (" + desc + ")";
    return item || desc;
  }

  function computeTaxes() {
    if (dscMode) return computeDscTaxes();
    // Category amount is GST-inclusive. ₹400 stays ₹400; tax is taken out of it.
    const gross = money(els.rate?.value);
    const gstPct = money(els.gstRate?.value);
    const placeCode = selectedStateCode();
    const seller = String(cfg.companyStateCode || "05").trim();
    const intra = !!(placeCode && placeCode === seller);
    let taxable = gross;
    let cgstRate = 0;
    let sgstRate = 0;
    let igstRate = 0;
    let cgstAmt = 0;
    let sgstAmt = 0;
    let igstAmt = 0;
    let taxType = intra ? "CGST_SGST" : "IGST";

    if (gross > 0 && gstPct > 0) {
      taxable = money((gross * 100) / (100 + gstPct));
      if (intra) {
        taxType = "CGST_SGST";
        cgstRate = money(gstPct / 2);
        sgstRate = cgstRate;
        cgstAmt = money((taxable * cgstRate) / 100);
        sgstAmt = money((taxable * sgstRate) / 100);
      } else {
        taxType = "IGST";
        igstRate = gstPct;
        igstAmt = money((taxable * igstRate) / 100);
      }
    }

    const invoiceValue = gross;

    if (els.placeCode) els.placeCode.value = placeCode;
    if (els.cgst) els.cgst.value = cgstAmt ? fmt(cgstAmt) + " (" + fmt(cgstRate) + "%)" : "0.00";
    if (els.sgst) els.sgst.value = sgstAmt ? fmt(sgstAmt) + " (" + fmt(sgstRate) + "%)" : "0.00";
    if (els.igst) els.igst.value = igstAmt ? fmt(igstAmt) + " (" + fmt(igstRate) + "%)" : "0.00";
    if (els.amount) els.amount.value = fmt(invoiceValue);
    if (els.taxHint) {
      els.taxHint.textContent =
        taxType === "CGST_SGST"
          ? "Amount includes GST. Taxable ₹" +
            fmt(taxable) +
            " · CGST + SGST stay inside this total."
          : "Amount includes GST. Taxable ₹" +
            fmt(taxable) +
            " · IGST stays inside this total.";
    }

    return {
      taxable,
      gstPct,
      taxType,
      cgstRate,
      sgstRate,
      igstRate,
      cgstAmt,
      sgstAmt,
      igstAmt,
      invoiceValue,
      placeCode,
    };
  }

  function computeDscTaxes() {
    const placeCode = selectedStateCode();
    const seller = String(cfg.companyStateCode || "05").trim();
    const intra = !!(placeCode && placeCode === seller);
    let taxable = 0;
    let gstAmt = 0;
    let cgstAmt = 0;
    let sgstAmt = 0;
    let igstAmt = 0;
    let gstPct = 0;
    let mixedGst = false;
    lineRows().forEach(function (tr) {
      recalcDscLine(tr);
      const lineTaxable = money(tr.dataset.taxable);
      const lineGst = money(tr.dataset.gstAmt);
      const linePct = money(tr.querySelector(".mgb-line-gst")?.value);
      taxable = money(taxable + lineTaxable);
      gstAmt = money(gstAmt + lineGst);
      if (intra) {
        const half = money(lineGst / 2);
        cgstAmt = money(cgstAmt + half);
        sgstAmt = money(sgstAmt + (lineGst - half));
      } else {
        igstAmt = money(igstAmt + lineGst);
      }
      if (lineTaxable > 0) {
        if (!gstPct) gstPct = linePct;
        else if (linePct !== gstPct) mixedGst = true;
      }
    });
    const roundOff = roundOffSigned();
    const invoiceValue = money(Math.max(0, taxable + gstAmt + roundOff));
    if (els.placeCode) els.placeCode.value = placeCode;
    if (els.gstRate) els.gstRate.value = mixedGst ? "" : gstPct ? String(gstPct) : "0";
    if (els.cgst) els.cgst.value = cgstAmt ? fmt(cgstAmt) : "0.00";
    if (els.sgst) els.sgst.value = sgstAmt ? fmt(sgstAmt) : "0.00";
    if (els.igst) els.igst.value = igstAmt ? fmt(igstAmt) : "0.00";
    if (els.amount) els.amount.value = fmt(invoiceValue);
    const totTaxable = document.getElementById("mgbTotTaxable");
    const totCgst = document.getElementById("mgbTotCgst");
    const totSgst = document.getElementById("mgbTotSgst");
    const totIgst = document.getElementById("mgbTotIgst");
    const totValue = document.getElementById("mgbTotValue");
    if (totTaxable) totTaxable.textContent = fmt(taxable);
    if (totCgst) totCgst.textContent = els.cgst?.value || "0.00";
    if (totSgst) totSgst.textContent = els.sgst?.value || "0.00";
    if (totIgst) totIgst.textContent = els.igst?.value || "0.00";
    if (totValue) totValue.textContent = fmt(invoiceValue);
    const partyCode = document.getElementById("mgbPartyStateCode");
    if (partyCode) partyCode.value = placeCode || "";
    if (els.taxHint) {
      els.taxHint.textContent =
        "Qty × Rate = taxable ₹" +
        fmt(taxable) +
        " + GST ₹" +
        fmt(gstAmt) +
        " = ₹" +
        fmt(invoiceValue) +
        (intra ? " (CGST + SGST)" : " (IGST)") +
        (roundOff ? " · Round off " + (roundOff > 0 ? "+" : "") + fmt(roundOff) + "." : ".");
    }
    return {
      taxable,
      gstPct,
      taxType: intra ? "CGST_SGST" : "IGST",
      cgstAmt,
      sgstAmt,
      igstAmt,
      roundOff,
      invoiceValue,
      placeCode,
    };
  }

  function collectPayload(forPdf) {
    if (dscMode) return collectDscPayload(forPdf);
    const taxes = computeTaxes();
    const gstPct = taxes.gstPct;
    const invoiceKind = gstPct > 0 ? "GST" : "NON_GST";
    const particulars = buildParticulars();
    const line = {
      item_id: (els.itemId?.value || "").trim(),
      particulars: particulars,
      hsn_sac: (els.hsn?.value || "").trim(),
      unit: (els.unit?.value || "NOS").trim() || "NOS",
      qty: "1",
      rate: String(els.rate?.value || "0"),
      discount_amount: "0",
      gst_rate_percent: String(els.gstRate?.value || "0"),
    };
    // Tax year is stored on the invoice for Sale form, but never sent into PDF extras.
    if (!forPdf) {
      line.tax_period = (els.taxYear?.value || "").trim();
    }
    return {
      invoice_no: (els.invoiceNo?.value || "").trim(),
      invoice_date: (els.date?.value || "").trim(),
      invoice_kind: invoiceKind,
      voucher_type: "SALE",
      customer_id: (els.customerId?.value || "").trim(),
      customer_name: (els.customerName?.value || "").trim(),
      contact_mobile: (els.mobile?.value || "").trim(),
      billing_address: (els.address?.value || "").trim(),
      place_of_supply: (els.state?.value || "").trim(),
      place_of_supply_code: taxes.placeCode,
      reverse_charge: "0",
      notes: "",
      tally_bill_no: (els.tallyBillNo?.value || els.invoiceNo?.value || "").trim(),
      bill_source: "Miscellaneous",
      payment_bank_account_ids: selectedBankIds(),
      lines: [line],
    };
  }

  function collectDscPayload(forPdf) {
    const taxes = computeDscTaxes();
    const lines = [];
    lineRows().forEach(function (tr) {
      const id = tr.querySelector(".mgb-line-item")?.value || "";
      const it = itemById(id);
      if (!it) return;
      const name = String(it.item_name || "").trim();
      const desc = itemDesc(it);
      let particulars = name;
      if (name && desc && desc.toLowerCase() !== name.toLowerCase()) {
        particulars = name + " (" + desc + ")";
      }
      const line = {
        item_id: String(it.item_id),
        particulars: particulars || desc,
        hsn_sac: tr.dataset.hsn || it.hsn_sac || "",
        unit: tr.dataset.unit || it.unit || "NOS",
        qty: tr.querySelector(".mgb-line-qty")?.value || "1",
        rate: tr.querySelector(".mgb-line-rate")?.value || "0",
        discount_amount: "0",
        gst_rate_percent: tr.querySelector(".mgb-line-gst")?.value || "0",
      };
      if (!forPdf) line.tax_period = (els.taxYear?.value || "").trim();
      lines.push(line);
    });
    const gstPct = taxes.gstPct;
    return {
      invoice_no: (els.invoiceNo?.value || "").trim(),
      invoice_date: (els.date?.value || "").trim(),
      invoice_kind: gstPct > 0 ? "GST" : "NON_GST",
      voucher_type: "SALE",
      customer_id: (els.customerId?.value || "").trim(),
      customer_name: (els.customerName?.value || "").trim(),
      contact_mobile: (els.mobile?.value || "").trim(),
      billing_address: (els.address?.value || "").trim(),
      place_of_supply: (els.state?.value || "").trim(),
      place_of_supply_code: taxes.placeCode,
      reverse_charge: "0",
      notes: "",
      tally_bill_no: (els.tallyBillNo?.value || els.invoiceNo?.value || "").trim(),
      bill_source: "Miscellaneous",
      gst_inclusive: false,
      round_off_amount: String(roundOffMagnitude()),
      round_off_sign: (els.roundOffSign?.value || "").trim(),
      payment_bank_account_ids: selectedBankIds(),
      lines: lines,
    };
  }

  const bankOrder = [];

  function selectedBankIds() {
    return bankOrder.slice();
  }

  function setSelectedBanks(ids) {
    bankOrder.length = 0;
    (ids || []).forEach(function (id) {
      const key = String(id);
      if (bankOrder.indexOf(key) < 0 && bankOrder.length < 2) bankOrder.push(key);
    });
    els.banks?.querySelectorAll(".mgb-bank").forEach(function (box) {
      box.checked = bankOrder.indexOf(box.value) >= 0;
    });
  }

  function validateForm() {
    if (dscMode) return validateDscForm();
    if (!(els.date?.value || "").trim()) return "Date is required.";
    if (!(els.taxYear?.value || "").trim()) return "Tax Year is required.";
    if (!(els.invoiceNo?.value || "").trim()) return "Invoice Number is required.";
    if (!(els.customerName?.value || "").trim()) return "Customer is required.";
    if (!(els.item?.value || "").trim()) return "Item is required.";
    if (!(els.state?.value || "").trim()) return "State is required.";
    const rate = Number(els.rate?.value);
    if (!Number.isFinite(rate) || rate < 0) return "Valid rate is required.";
    if (!selectedBankIds().length) return "Select a bank account.";
    return "";
  }

  function validateDscForm() {
    if (!(els.date?.value || "").trim()) return "Date is required.";
    if (!(els.taxYear?.value || "").trim()) return "Tax Year is required.";
    if (!(els.invoiceNo?.value || "").trim()) return "Invoice Number is required.";
    if (!(els.customerId?.value || "").trim()) {
      return "Customer Master se customer name select karein.";
    }
    if (!(els.state?.value || "").trim()) return "State is required.";
    const filled = lineRows().filter(function (tr) {
      return !!(tr.querySelector(".mgb-line-item")?.value || "").trim();
    });
    if (!filled.length) return "Item Master se kam se kam ek item select karein.";
    for (let i = 0; i < filled.length; i++) {
      const qty = Number(filled[i].querySelector(".mgb-line-qty")?.value);
      const rate = Number(filled[i].querySelector(".mgb-line-rate")?.value);
      if (!Number.isFinite(qty) || qty <= 0) return "Har item ki Qty 0 se zyada honi chahiye.";
      if (!Number.isFinite(rate) || rate < 0) return "Har item ka Rate Item Master se aana chahiye.";
    }
    if (!selectedBankIds().length) return "Select a bank account.";
    return "";
  }

  function apiUrl(template, id) {
    return String(template || "").replace(/\/0(\/|$)/, "/" + id + "$1");
  }

  async function saveInvoice() {
    const payload = collectPayload(false);
    payload.from_source = true;
    const existingId = (els.invoiceId?.value || "").trim();
    const url = existingId ? apiUrl(cfg.updateUrl, existingId) : cfg.createUrl;
    const res = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": cfg.csrf || "",
      },
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok || !data.ok) {
      throw new Error(data.error || "Unable to save invoice to Sale / Service grid.");
    }
    const record = data.record || {};
    if (els.invoiceId && record.invoice_id) {
      els.invoiceId.value = String(record.invoice_id);
    }
    return record;
  }

  async function requestPdf(disposition) {
    showError("");
    showOk("");
    const err = validateForm();
    if (err) {
      showError(err);
      return;
    }
    const btn = disposition === "attachment" ? els.downloadBtn : els.previewBtn;
    if (btn) btn.disabled = true;
    try {
      const saved = await saveInvoice();
      showOk(
        "Saved to Sale / Service Invoice grid (Source: Miscellaneous)" +
          (saved.invoice_no ? " — " + saved.invoice_no : "") +
          "."
      );

      // PDF preview must not include tax year in particulars extras.
      const payload = collectPayload(true);
      const res = await fetch(cfg.previewPdfUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/pdf",
          "X-CSRFToken": cfg.csrf || "",
        },
        body: JSON.stringify(payload),
      });
      const contentType = res.headers.get("content-type") || "";
      if (!res.ok) {
        let message = "Unable to build PDF.";
        if (contentType.includes("application/json")) {
          const data = await res.json();
          message = data.error || message;
        }
        throw new Error(message);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      if (disposition === "attachment") {
        const a = document.createElement("a");
        a.href = url;
        const inv = (els.invoiceNo?.value || "Invoice").replace(/[^\w.-]+/g, "_");
        a.download = "Invoice-" + inv + ".pdf";
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(function () {
          URL.revokeObjectURL(url);
        }, 1500);
      } else {
        window.open(url, "_blank");
        setTimeout(function () {
          URL.revokeObjectURL(url);
        }, 60000);
      }
    } catch (e) {
      showError(e.message || "Unable to save / build PDF.");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function loadCustomerAddress(customerId) {
    if (!customerId || !cfg.customerUrl) return;
    try {
      const res = await fetch(apiUrl(cfg.customerUrl, customerId), {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      const data = await res.json();
      if (!data.ok || !data.record) return;
      if (els.address) els.address.value = data.record.billing_address || "";
      if (!els.mobile?.value && data.record.contact_mobile) {
        els.mobile.value = data.record.contact_mobile;
      }
      fillPartyPanel(data.record);
      if (data.record.place_of_supply_code && els.state) {
        const match = Array.from(els.state.options).find(function (opt) {
          return opt.getAttribute("data-code") === String(data.record.place_of_supply_code);
        });
        if (match) {
          els.state.value = match.value;
          computeTaxes();
        }
      }
    } catch (_err) {
      /* ignore */
    }
  }

  function applySeed(seed) {
    if (!seed || typeof seed !== "object") return;
    if (els.date) els.date.value = (seed.date || "").slice(0, 10);
    if (els.taxYear) {
      const want = seed.tax_year || cfg.defaultTaxPeriod || "";
      if (want && Array.from(els.taxYear.options).some(function (o) { return o.value === want; })) {
        els.taxYear.value = want;
      }
    }
    if (els.invoiceNo) els.invoiceNo.value = seed.invoice_no || seed.bill_no || "";
    if (els.customerId) els.customerId.value = seed.customer_id ? String(seed.customer_id) : "";
    if (els.customerName) els.customerName.value = seed.customer_name || "";
    if (els.mobile) els.mobile.value = seed.mobile || "";
    if (els.item) els.item.value = seed.item || seed.sub_work || "";
    if (els.itemDesc) els.itemDesc.value = seed.item_description || "";
    if (els.itemId) els.itemId.value = seed.item_id ? String(seed.item_id) : "";
    if (els.hsn) els.hsn.value = seed.hsn_sac || "";
    if (els.unit) els.unit.value = seed.unit || "NOS";
    if (els.rate) els.rate.value = seed.rate != null && seed.rate !== "" ? String(seed.rate) : "";
    if (els.gstRate) {
      els.gstRate.value =
        seed.gst_rate_percent != null && seed.gst_rate_percent !== ""
          ? String(seed.gst_rate_percent)
          : "18";
    }
    if (els.tallyBillNo) els.tallyBillNo.value = seed.tally_bill_no || seed.invoice_no || "";
    if (els.address) els.address.value = seed.billing_address || "";
    if (seed.state_code && els.state) {
      const match = Array.from(els.state.options).find(function (opt) {
        return opt.getAttribute("data-code") === String(seed.state_code);
      });
      if (match) els.state.value = match.value;
    }
    if (String(seed.source || "") === "DSC") {
      enableDscMode();
      rememberEntryCustomer();
      computeTaxes();
      ensureCustomerFromMaster().catch(function () {
        /* customer list is optional until the user types */
      });
      return;
    }
    computeTaxes();
    if (seed.customer_id) loadCustomerAddress(seed.customer_id);
  }

  function loadSeed() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      applySeed(JSON.parse(raw));
    } catch (_err) {
      /* ignore */
    }
  }

  function closeWindow() {
    try {
      if (window.frameElement && window.top && window.top !== window) {
        const host = window.frameElement.closest(".jtcs-page-win");
        if (host && typeof window.top.jtcsClosePageWindow === "function") {
          window.top.jtcsClosePageWindow(host);
          return;
        }
      }
    } catch (_err) {
      /* fall through to the browser window */
    }
    window.close();
  }

  function notifyInvoiceStatus() {
    const seen = [];
    function ping(win) {
      if (!win || seen.indexOf(win) !== -1) return;
      seen.push(win);
      try {
        if (typeof win.jtcsRefreshInvoiceStatus === "function") win.jtcsRefreshInvoiceStatus();
      } catch (_err) {
        /* frame may be gone */
      }
    }
    try {
      ping(window.opener);
    } catch (_err) {
      /* opener may be closed */
    }
    try {
      if (window.top && window.top.document) {
        window.top.document.querySelectorAll("iframe").forEach(function (frame) {
          try {
            ping(frame.contentWindow);
          } catch (_err) {
            /* cross-frame */
          }
        });
      }
    } catch (_err) {
      /* top document unavailable */
    }
  }

  els.roundOffAmt?.addEventListener("input", function () {
    if (!roundOffMagnitude()) setRoundOffSign("");
    computeTaxes();
  });
  els.roundOffAdd?.addEventListener("click", function () {
    applyRoundOff("add");
  });
  els.roundOffSub?.addEventListener("click", function () {
    applyRoundOff("sub");
  });
  els.rate?.addEventListener("input", computeTaxes);
  els.gstRate?.addEventListener("input", computeTaxes);
  els.state?.addEventListener("change", computeTaxes);
  els.addLineBtn?.addEventListener("click", function () {
    addDscLine();
    computeTaxes();
  });
  els.customerName?.addEventListener("input", function () {
    if (!dscMode || !billAnotherCustomer) return;
    if ((els.customerName.value || "").trim() !== customerPickName) {
      if (els.customerId) els.customerId.value = "";
    }
    clearTimeout(window.__mgbCustTimer);
    window.__mgbCustTimer = setTimeout(function () {
      searchCustomers(els.customerName.value).catch(function () {
        hideCustomerList();
      });
    }, 180);
  });
  els.customerName?.addEventListener("blur", function () {
    setTimeout(hideCustomerList, 160);
  });
  els.customerMode?.addEventListener("change", function () {
    if (!dscMode) return;
    applyCustomerMode();
  });
  els.saveBtn?.addEventListener("click", function () {
    saveBillOnly();
  });
  els.previewBtn?.addEventListener("click", function () {
    requestPdf("inline");
  });
  els.downloadBtn?.addEventListener("click", function () {
    requestPdf("attachment");
  });
  els.banks?.addEventListener("change", function (event) {
    const box = event.target.closest(".mgb-bank");
    if (!box) return;
    const id = box.value;
    const idx = bankOrder.indexOf(id);
    if (box.checked) {
      if (bankOrder.length >= 2) {
        box.checked = false;
        showError("Select at most 2 bank accounts.");
        return;
      }
      if (idx < 0) bankOrder.push(id);
      showError("");
      return;
    }
    if (idx >= 0) bankOrder.splice(idx, 1);
  });

  async function editInvoice() {
    showError("");
    const billNo = (els.tallyBillNo?.value || els.invoiceNo?.value || "").trim();
    if (!billNo || !cfg.lookupUrl) {
      showError("Invoice number is required before edit.");
      return;
    }
    const url = new URL(cfg.lookupUrl, window.location.origin);
    url.searchParams.set("bill_no", billNo);
    const res = await fetch(url.toString(), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok || !data.ok || !data.found || !data.record) {
      if (dscMode && res.ok && data.ok && !data.found) {
        showError("");
        showOk("Abhi saved bill nahi hai. Pehle Save karein, uske baad Edit usi bill ko kholega.");
        return;
      }
      showError(data.error || "No saved bill found to edit.");
      return;
    }
    const rec = data.record;
    if (els.invoiceId) els.invoiceId.value = rec.invoice_id ? String(rec.invoice_id) : "";
    if (els.invoiceNo && rec.invoice_no) els.invoiceNo.value = rec.invoice_no;
    if (els.date && rec.invoice_date) els.date.value = String(rec.invoice_date).slice(0, 10);
    if (els.customerName && rec.customer_name) els.customerName.value = rec.customer_name;
    if (els.rate && rec.invoice_value != null) els.rate.value = String(rec.invoice_value);
    const savedLines = rec.lines || [];
    const line = savedLines[0] || {};
    if (dscMode) {
      if (els.lineBody) els.lineBody.innerHTML = "";
      if (savedLines.length) {
        savedLines.forEach(function (row) {
          addDscLine({
            item_id: row.item_id,
            qty: row.qty,
            rate: row.rate,
            gst_rate_percent: row.gst_rate_percent,
          });
        });
      } else {
        addDscLine();
      }
      if (els.customerId && rec.customer_id) {
        els.customerId.value = String(rec.customer_id);
        customerPickName = (els.customerName?.value || "").trim();
      }
      const billedId = String(rec.customer_id || "");
      const another = !!(entryCustomer.id && billedId && billedId !== String(entryCustomer.id));
      billAnotherCustomer = another;
      if (els.billAnother) els.billAnother.checked = another;
      if (els.billSame) els.billSame.checked = !another;
      if (els.customerName) els.customerName.readOnly = !another;
    } else {
      if (els.gstRate && line.gst_rate_percent != null) {
        els.gstRate.value = String(line.gst_rate_percent);
      }
      if (els.item && (line.particulars || line.item_name)) {
        els.item.value = line.item_name || line.particulars;
      }
    }
    setSelectedBanks(rec.payment_bank_account_ids || []);
    if (dscMode) {
      const signed = Number(rec.round_off != null ? rec.round_off : 0) || 0;
      const mag = Math.abs(
        Number(rec.round_off_amount != null ? rec.round_off_amount : signed) || 0
      );
      let sign = (rec.round_off_sign || "").toLowerCase();
      if (!sign) {
        if (signed > 0) sign = "add";
        else if (signed < 0) sign = "sub";
      }
      if (els.roundOffAmt) els.roundOffAmt.value = mag ? mag.toFixed(2) : "";
      setRoundOffSign(sign);
    }
    computeTaxes();
    showOk("Bill loaded for edit. Preview or Download saves the changes.");
  }

  async function deleteInvoice() {
    showError("");
    const invoiceId = (els.invoiceId?.value || "").trim();
    if (!invoiceId) {
      showError("Save or Edit the bill before delete.");
      return;
    }
    if (!window.confirm("Delete this generated bill?")) return;
    const userId = window.prompt("User ID");
    if (!userId) return;
    const password = window.prompt("Password");
    if (!password) return;
    const res = await fetch(apiUrl(cfg.deleteUrl, invoiceId), {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": cfg.csrf || "",
      },
      body: JSON.stringify({ user_id: userId, password: password, from_source: true }),
    });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok || !data.ok) {
      showError(data.error || data.message || "Unable to delete bill.");
      return;
    }
    if (els.invoiceId) els.invoiceId.value = "";
    setSelectedBanks([]);
    showOk(data.message || "Bill deleted.");
  }

  async function saveBillOnly() {
    showError("");
    showOk("");
    const err = validateForm();
    if (err) {
      showError(err);
      return;
    }
    if (els.saveBtn) els.saveBtn.disabled = true;
    try {
      const saved = await saveInvoice();
      showOk(
        "Bill saved" + (saved.invoice_no ? " — " + saved.invoice_no : "") + ". Edit ab isi bill ko kholega."
      );
    } catch (err) {
      showError(err.message || "Unable to save bill.");
    } finally {
      if (els.saveBtn) els.saveBtn.disabled = false;
    }
  }

  async function confirmConvertUser() {
    if (!dscMode) return true;
    let creds = null;
    if (window.JTCSDeleteConfirm?.ask) {
      creds = await window.JTCSDeleteConfirm.ask({
        message: "Invoice banane ke liye apna User ID aur password darj karein.",
        title: "Confirm",
        confirmLabel: "Convert to Invoice",
        confirmIcon: "bi-receipt",
        variant: "success",
      });
    }
    if (!creds || !creds.user_id || !creds.password) return false;
    const res = await fetch(cfg.confirmUserUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": cfg.csrf || "",
      },
      body: JSON.stringify({ user_id: creds.user_id, password: creds.password }),
    });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok || !data.ok) {
      showError(data.error || "User ID ya password galat hai.");
      return false;
    }
    return true;
  }

  async function convertToInvoice() {
    showError("");
    showOk("");
    const err = validateForm();
    if (err) {
      showError(err);
      return;
    }
    if (els.convertBtn) els.convertBtn.disabled = true;
    try {
      const allowed = await confirmConvertUser();
      if (!allowed) return;
      const saved = await saveInvoice();
      const message =
        "Converted to Sale / Service Invoice" +
        (saved.invoice_no ? " — " + saved.invoice_no : "") +
        ". Open that invoice for Bill Status and Payment Received.";
      if (window.JTCSDialog?.alert) {
        await window.JTCSDialog.alert(message, "success", {
          title: "Converted to invoice",
          okLabel: "OK",
        });
      } else {
        window.alert(message);
      }
      notifyInvoiceStatus();
      closeWindow();
      return;
    } catch (err) {
      showError(err.message || "Unable to convert to invoice.");
    } finally {
      if (els.convertBtn) els.convertBtn.disabled = false;
    }
  }

  els.convertBtn?.addEventListener("click", function () {
    convertToInvoice();
  });

  els.closeBtn?.addEventListener("click", closeWindow);
  els.closeBtn2?.addEventListener("click", closeWindow);
  els.editBtn?.addEventListener("click", function () {
    editInvoice().catch(function (err) {
      showError(err.message || "Unable to edit bill.");
    });
  });
  els.deleteBtn?.addEventListener("click", function () {
    deleteInvoice().catch(function (err) {
      showError(err.message || "Unable to delete bill.");
    });
  });

  function fitWindowToInvoice() {
    if (window.top && window.top !== window) return;
    const shell = document.querySelector(".mgb-shell");
    if (!shell || !window.resizeTo) return;
    const chromeX = Math.max(0, window.outerWidth - window.innerWidth);
    const chromeY = Math.max(0, window.outerHeight - window.innerHeight);
    const width = Math.ceil(shell.offsetWidth + chromeX);
    let height = Math.ceil(shell.offsetHeight + chromeY);
    if (dscMode) {
      const maxH = (screen.availHeight || height) - 24;
      if (height > maxH) height = maxH;
    }
    if (Math.abs(window.outerWidth - width) < 12 && Math.abs(window.outerHeight - height) < 12) {
      return;
    }
    const left = Math.max(0, Math.round(((screen.availWidth || width) - width) / 2));
    const top = Math.max(0, Math.round(((screen.availHeight || height) - height) / 2));
    window.resizeTo(width, height);
    window.moveTo(left, top);
  }

  loadSeed();
  computeTaxes();
  requestAnimationFrame(function () {
    fitWindowToInvoice();
    setTimeout(fitWindowToInvoice, 80);
  });
  window.addEventListener("resize", function () {
    clearTimeout(window.__mgbFitTimer);
    window.__mgbFitTimer = setTimeout(fitWindowToInvoice, 60);
  });
})();
