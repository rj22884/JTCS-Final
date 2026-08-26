"""Public UPI pay page for invoice WhatsApp / QR links. No login."""

from __future__ import annotations

from flask import Blueprint, abort, render_template, request

from app.services.gst_invoice_pdf_service import GstInvoicePdfService
from app.services.gst_invoice_service import GstInvoiceService

bp = Blueprint("invoice_pay_public", __name__)


@bp.route("/pay/invoice/<int:invoice_id>", methods=["GET"], strict_slashes=False)
def public_upi_pay(invoice_id: int):
    token = (request.args.get("t") or "").strip()
    try:
        invoice = GstInvoiceService().get_record(invoice_id)
    except ValueError:
        abort(404)
    pdf_svc = GstInvoicePdfService()
    if not pdf_svc.verify_pay_token(invoice, token):
        abort(404)
    upi_uri = pdf_svc.upi_intent_url(invoice)
    if not upi_uri:
        abort(404)
    company = GstInvoiceService().company_profile()
    return render_template(
        "accounting/upi_pay.html",
        invoice=invoice,
        company=company,
        upi_uri=upi_uri,
        qr_data_uri=pdf_svc.upi_qr_data_uri(invoice),
        page_title="Pay Invoice",
    )
