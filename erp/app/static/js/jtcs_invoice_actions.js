/* Shared invoice actions for a known invoice id. */
(function () {
  "use strict";

  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return (meta && meta.getAttribute("content")) || "";
  }

  function apiUrl(template, id) {
    return String(template || "").replace(/\/0(\/|$)/, "/" + id + "$1");
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function plainAmount(value) {
    return Number(value || 0).toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function money(value) {
    return "₹" + plainAmount(value);
  }

  function formatDate(iso) {
    const text = String(iso || "").slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return text || "—";
    const parts = text.split("-");
    return parts[2] + "/" + parts[1] + "/" + parts[0];
  }

  function digitsOnly(value) {
    return String(value || "").replace(/\D/g, "");
  }

  function invoiceIdOf(invoice) {
    const id = parseInt(invoice && invoice.invoice_id, 10);
    return id > 0 ? id : 0;
  }

  function button(act, icon, title, invoiceId, extraClass) {
    return (
      '<button type="button" class="btn btn-sm jtcs-inv-act ' + (extraClass || "btn-outline-secondary") + '" ' +
      'data-inv-act="' + act + '" data-invoice-id="' + invoiceId + '" title="' + title + '">' +
      '<i class="bi ' + icon + '"></i></button>'
    );
  }

  function buttonsHtml(invoice) {
    const id = invoiceIdOf(invoice);
    if (!id) return "";
    return (
      '<span class="jtcs-inv-actions">' +
      button("edit", "bi-pencil", "Edit Invoice", id) +
      button("preview", "bi-eye", "Preview Invoice", id) +
      button("print", "bi-printer", "Print Invoice", id) +
      button("pdf", "bi-file-earmark-pdf", "Download Invoice PDF", id) +
      button("png", "bi-image", "Download Invoice PNG", id) +
      button("whatsapp", "bi-whatsapp", "Send Invoice on WhatsApp", id, "btn-outline-success") +
      button("delete", "bi-trash", "Delete Invoice", id, "btn-outline-danger") +
      "</span>"
    );
  }

  function summaryHtml(invoice) {
    const id = invoiceIdOf(invoice);
    if (!id) return "";
    const packed = escapeHtml(JSON.stringify({
      invoice_id: id,
      invoice_no: invoice.invoice_no || "",
      invoice_date: invoice.invoice_date || "",
      invoice_value: invoice.invoice_value || 0,
      customer_id: invoice.customer_id || null,
      customer_name: invoice.customer_name || "",
      contact_mobile: invoice.contact_mobile || "",
      pay_url: invoice.pay_url || "",
    }));
    return (
      '<div class="jtcs-inv-meta" data-invoice-json="' + packed + '">' +
      "<div><strong>" + escapeHtml(invoice.invoice_no || "—") + "</strong></div>" +
      "<div>" + escapeHtml(formatDate(invoice.invoice_date)) + "</div>" +
      "<div>" + escapeHtml(money(invoice.invoice_value)) + "</div>" +
      buttonsHtml(invoice) +
      "</div>"
    );
  }

  function cssHref() {
    return "/static/css/gst_invoice.css?v=20261006invact";
  }

  function ensurePreviewModal() {
    let modal = document.getElementById("jtcsInvPreviewModal");
    if (modal) return modal;
    if (!document.querySelector("link[data-jtcs-inv-css]")) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = cssHref();
      link.setAttribute("data-jtcs-inv-css", "1");
      document.head.appendChild(link);
    }
    modal = document.createElement("div");
    modal.id = "jtcsInvPreviewModal";
    modal.className = "modal fade";
    modal.tabIndex = -1;
    modal.innerHTML =
      '<div class="modal-dialog modal-xl modal-dialog-scrollable">' +
      '<div class="modal-content">' +
      '<div class="modal-header py-2">' +
      '<h5 class="modal-title" id="jtcsInvPreviewTitle">Invoice Preview</h5>' +
      '<button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>' +
      "</div>" +
      '<div class="modal-body" id="jtcsInvPreviewBody"></div>' +
      "</div></div>";
    document.body.appendChild(modal);
    return modal;
  }

  async function loadPreviewHtml(invoiceId) {
    const res = await fetch("/accounting/invoice/" + invoiceId + "/preview-html", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    const data = await res.json().catch(function () { return {}; });
    if (!res.ok || !data.ok) throw new Error(data.error || "Preview failed");
    return data;
  }

  function previewDocument(html) {
    return (
      "<!DOCTYPE html><html><head><meta charset=\"utf-8\">" +
      '<link rel="stylesheet" href="' + cssHref() + '">' +
      "</head><body>" + html + "</body></html>"
    );
  }

  async function preview(invoice) {
    const id = invoiceIdOf(invoice);
    if (!id) return;
    const modalEl = ensurePreviewModal();
    const title = document.getElementById("jtcsInvPreviewTitle");
    const body = document.getElementById("jtcsInvPreviewBody");
    if (title) title.textContent = "Invoice Preview";
    if (body) body.innerHTML = '<div class="text-muted small py-4 text-center">Loading preview…</div>';
    if (window.bootstrap && bootstrap.Modal) {
      bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }
    const data = await loadPreviewHtml(id);
    if (title && data.invoice_no) title.textContent = "Invoice Preview — " + data.invoice_no;
    if (body) body.innerHTML = data.html || "";
  }

  async function printInvoice(invoice) {
    const id = invoiceIdOf(invoice);
    if (!id) return;
    const data = await loadPreviewHtml(id);
    let frame = document.getElementById("jtcsInvPrintFrame");
    if (!frame) {
      frame = document.createElement("iframe");
      frame.id = "jtcsInvPrintFrame";
      frame.setAttribute("title", "Print Invoice");
      frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;";
      document.body.appendChild(frame);
    }
    const doc = frame.contentDocument;
    doc.open();
    doc.write(previewDocument(data.html || ""));
    doc.close();
    const win = frame.contentWindow;
    if (!win) return;
    setTimeout(function () {
      win.focus();
      win.print();
    }, 250);
  }

  async function downloadFile(invoice, kind) {
    const id = invoiceIdOf(invoice);
    if (!id) return;
    const path = kind === "png" ? "/png" : "/pdf";
    const res = await fetch("/accounting/invoice/" + id + path, { credentials: "same-origin" });
    if (!res.ok) {
      const data = await res.json().catch(function () { return {}; });
      throw new Error(data.error || "Unable to download the invoice.");
    }
    const blob = await res.blob();
    const header = res.headers.get("Content-Disposition") || "";
    const match = /filename="?([^"]+)"?/.exec(header);
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = (match && match[1]) || (kind === "png" ? "invoice.png" : "invoice.pdf");
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
  }

  async function invoiceRecord(invoiceId) {
    const res = await fetch("/accounting/api/invoices/" + invoiceId, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    const data = await res.json().catch(function () { return {}; });
    if (!res.ok || data.ok === false) throw new Error(data.error || "Invoice not found.");
    return data.record || data;
  }

  async function whatsapp(invoice) {
    const id = invoiceIdOf(invoice);
    if (!id) return;
    const record = await invoiceRecord(id);
    const mobile = digitsOnly(record.contact_mobile || "");
    let phone = mobile;
    if (phone.length === 10) phone = "91" + phone;
    if (!phone) {
      window.alert("This invoice customer does not have a mobile number.");
      return;
    }
    let msg =
      "Dear " + (record.customer_name || "Customer") + ",\n\n" +
      "Your tax invoice from JTCS:\n" +
      "Invoice No: " + (record.invoice_no || "") + "\n" +
      "Date: " + formatDate(record.invoice_date) + "\n" +
      "Amount: Rs. " + plainAmount(record.invoice_value);
    const payUrl = (invoice && invoice.pay_url) || record.pay_url || "";
    if (payUrl) {
      msg += "\n\nPay now (Google Pay / PhonePe / Paytm):\n" + payUrl;
    }
    msg += "\n\nThank you.";
    window.open(
      "https://wa.me/" + phone + "?text=" + encodeURIComponent(msg),
      "_blank",
      "noopener"
    );
  }

  function confirmDelete() {
    const message = "Are you sure you want to delete this invoice?";
    if (window.JTCSDialog && JTCSDialog.confirm) {
      return JTCSDialog.confirm(message, {
        title: "Delete Invoice",
        okLabel: "Yes",
        cancelLabel: "No",
        type: "warning",
      });
    }
    return Promise.resolve(window.confirm(message));
  }

  async function remove(invoice, options) {
    const id = invoiceIdOf(invoice);
    if (!id) {
      window.alert("Unable to delete invoice: Invoice ID is missing or invalid.");
      return false;
    }
    const yes = await confirmDelete();
    if (!yes) return false;
    let creds = null;
    if (window.JTCSDeleteConfirm && JTCSDeleteConfirm.ask) {
      creds = await JTCSDeleteConfirm.ask({
        message: "Enter your User ID and password to delete this invoice.",
        title: "Delete invoice",
        confirmLabel: "Yes",
        cancelLabel: "No",
      });
      if (!creds) return false;
    }
    const body = { from_source: true };
    const followupId = parseInt(options && options.followupEntryId, 10);
    if (followupId > 0) body.followup_entry_id = followupId;
    const miscId = parseInt(options && options.miscEntryId, 10);
    if (miscId > 0) body.misc_entry_id = miscId;
    if (creds && JTCSDeleteConfirm.withCreds) {
      Object.assign(body, JTCSDeleteConfirm.withCreds({}, creds));
    }
    const res = await fetch("/accounting/api/invoices/" + id + "/delete", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(function () { return {}; });
    if (!res.ok || data.ok === false) {
      throw new Error(data.error || "Unable to delete the invoice.");
    }
    if (options && typeof options.onDeleted === "function") options.onDeleted(id);
    return true;
  }

  function edit(invoice, options) {
    const id = invoiceIdOf(invoice);
    if (!id) return;
    const params = new URLSearchParams();
    params.set("edit", String(id));
    const followupId = parseInt(options && options.followupEntryId, 10);
    if (followupId > 0) params.set("followup_entry_id", String(followupId));
    const miscId = parseInt(options && options.miscEntryId, 10);
    if (miscId > 0) params.set("misc_entry_id", String(miscId));
    const host = window.top || window;
    if (typeof host.jtcsOpenPageWindow !== "function") {
      window.alert("Invoice window could not be opened in this page. Refresh and try again.");
      return;
    }
    host.jtcsOpenPageWindow("/accounting/invoice/sale?" + params.toString(), "Edit Sale / Service Invoice");
  }

  function run(act, invoice, options) {
    const action = String(act || "");
    const task = action === "edit" ? Promise.resolve(edit(invoice, options))
      : action === "preview" ? preview(invoice)
      : action === "print" ? printInvoice(invoice)
      : action === "pdf" ? downloadFile(invoice, "pdf")
      : action === "png" ? downloadFile(invoice, "png")
      : action === "whatsapp" ? whatsapp(invoice)
      : action === "delete" ? remove(invoice, options)
      : Promise.resolve();
    return Promise.resolve(task).catch(function (err) {
      window.alert(err.message || "Unable to open this invoice.");
    });
  }

  function invoiceFromButton(btn) {
    const id = parseInt(btn.getAttribute("data-invoice-id") || "", 10);
    if (!id) return null;
    const holder = btn.closest("[data-invoice-json]");
    if (holder) {
      try {
        const parsed = JSON.parse(holder.getAttribute("data-invoice-json") || "{}");
        if (parseInt(parsed.invoice_id, 10) === id) return parsed;
      } catch (_err) {
        /* use the id alone */
      }
    }
    return { invoice_id: id };
  }

  function bind(root, options) {
    if (!root || root.dataset.jtcsInvBound === "1") return;
    root.dataset.jtcsInvBound = "1";
    root.addEventListener("click", function (event) {
      const btn = event.target.closest(".jtcs-inv-act");
      if (!btn || !root.contains(btn)) return;
      event.preventDefault();
      const invoice = invoiceFromButton(btn);
      if (!invoice) return;
      const followupEntryId = btn.closest("[data-followup-entry-id]")
        ? btn.closest("[data-followup-entry-id]").getAttribute("data-followup-entry-id")
        : (options && options.followupEntryId);
      const miscEntryId = btn.closest("[data-misc-entry-id]")
        ? btn.closest("[data-misc-entry-id]").getAttribute("data-misc-entry-id")
        : (options && options.miscEntryId);
      run(btn.getAttribute("data-inv-act"), invoice, {
        followupEntryId: followupEntryId,
        miscEntryId: miscEntryId,
        onDeleted: options && options.onDeleted,
      });
    });
  }

  window.JtcsInvoiceActions = {
    buttonsHtml: buttonsHtml,
    summaryHtml: summaryHtml,
    run: run,
    bind: bind,
    money: money,
    formatDate: formatDate,
    apiUrl: apiUrl,
  };
})();
