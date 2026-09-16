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
  };

  function money(n) {
    const v = Number(n);
    if (!Number.isFinite(v)) return 0;
    return Math.round((v + Number.EPSILON) * 100) / 100;
  }

  function fmt(n) {
    return money(n).toFixed(2);
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

  function buildParticulars() {
    const item = (els.item?.value || "").trim();
    const desc = (els.itemDesc?.value || "").trim();
    if (item && desc) return item + " (" + desc + ")";
    return item || desc;
  }

  function computeTaxes() {
    const rate = money(els.rate?.value);
    const gstPct = money(els.gstRate?.value);
    const placeCode = selectedStateCode();
    const seller = String(cfg.companyStateCode || "05").trim();
    const taxable = rate;
    let cgstRate = 0;
    let sgstRate = 0;
    let igstRate = 0;
    let cgstAmt = 0;
    let sgstAmt = 0;
    let igstAmt = 0;
    let taxType = "IGST";

    if (placeCode && placeCode === seller) {
      taxType = "CGST_SGST";
      cgstRate = money(gstPct / 2);
      sgstRate = cgstRate;
      cgstAmt = money((taxable * cgstRate) / 100);
      sgstAmt = money((taxable * sgstRate) / 100);
    } else {
      igstRate = gstPct;
      igstAmt = money((taxable * igstRate) / 100);
    }

    const invoiceValue = money(taxable + cgstAmt + sgstAmt + igstAmt);

    if (els.placeCode) els.placeCode.value = placeCode;
    if (els.cgst) els.cgst.value = cgstAmt ? fmt(cgstAmt) + " (" + fmt(cgstRate) + "%)" : "0.00";
    if (els.sgst) els.sgst.value = sgstAmt ? fmt(sgstAmt) + " (" + fmt(sgstRate) + "%)" : "0.00";
    if (els.igst) els.igst.value = igstAmt ? fmt(igstAmt) + " (" + fmt(igstRate) + "%)" : "0.00";
    if (els.amount) els.amount.value = fmt(invoiceValue);
    if (els.taxHint) {
      els.taxHint.textContent =
        taxType === "CGST_SGST"
          ? "Intra-state: CGST + SGST (from item GST%)."
          : "Inter-state: IGST (from item GST%).";
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

  function collectPayload(forPdf) {
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
      lines: [line],
    };
  }

  function validateForm() {
    if (!(els.date?.value || "").trim()) return "Date is required.";
    if (!(els.taxYear?.value || "").trim()) return "Tax Year is required.";
    if (!(els.invoiceNo?.value || "").trim()) return "Invoice Number is required.";
    if (!(els.customerName?.value || "").trim()) return "Customer is required.";
    if (!(els.item?.value || "").trim()) return "Item is required.";
    if (!(els.state?.value || "").trim()) return "State is required.";
    const rate = Number(els.rate?.value);
    if (!Number.isFinite(rate) || rate < 0) return "Valid rate is required.";
    return "";
  }

  function apiUrl(template, id) {
    return String(template || "").replace(/\/0(\/|$)/, "/" + id + "$1");
  }

  async function saveInvoice() {
    const payload = collectPayload(false);
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
    window.close();
  }

  els.rate?.addEventListener("input", computeTaxes);
  els.gstRate?.addEventListener("input", computeTaxes);
  els.state?.addEventListener("change", computeTaxes);
  els.previewBtn?.addEventListener("click", function () {
    requestPdf("inline");
  });
  els.downloadBtn?.addEventListener("click", function () {
    requestPdf("attachment");
  });
  els.closeBtn?.addEventListener("click", closeWindow);
  els.closeBtn2?.addEventListener("click", closeWindow);

  loadSeed();
  computeTaxes();
})();
