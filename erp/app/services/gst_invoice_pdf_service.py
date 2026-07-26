from __future__ import annotations

import base64
import io
import urllib.parse
from pathlib import Path

from flask import current_app
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.services.gst_invoice_service import GstInvoiceService

try:
    import qrcode
except ImportError:  # pragma: no cover
    qrcode = None  # type: ignore


class GstInvoicePdfService:
    def __init__(self, invoice_service: GstInvoiceService | None = None):
        self.invoice_service = invoice_service or GstInvoiceService()

    @staticmethod
    def _fmt(amount) -> str:
        try:
            return f"{float(amount):,.2f}"
        except (TypeError, ValueError):
            return "0.00"

    def _logo_path(self) -> Path | None:
        static = Path(current_app.static_folder or "")
        candidate = static / "img" / "jtcs_invoice_logo.png"
        return candidate if candidate.is_file() else None

    def build_pdf_from_payload(self, payload: dict) -> tuple[bytes, str]:
        """Build preview PDF from form payload without requiring a saved invoice."""
        header, lines, preview = self.invoice_service._build_header_and_lines(
            payload, persist_no=False
        )
        data = {
            "invoice_id": 0,
            "invoice_no": preview.get("invoice_no") or header.get("InvoiceNo") or "PREVIEW",
            "invoice_date": header["InvoiceDate"].isoformat(),
            "customer_id": header.get("CustomerID"),
            "customer_name": header.get("CustomerName") or "",
            "contact_person": header.get("ContactPerson") or "",
            "billing_address": header.get("BillingAddress") or "",
            "customer_gstin": header.get("CustomerGSTIN") or "",
            "contact_mobile": header.get("ContactMobile") or "",
            "contact_email": header.get("ContactEmail") or "",
            "place_of_supply": header.get("PlaceOfSupply") or "",
            "place_of_supply_code": header.get("PlaceOfSupplyCode") or "",
            "reverse_charge": bool(header.get("ReverseCharge")),
            "invoice_kind": header.get("InvoiceKind") or "NON_GST",
            "tax_type": header.get("TaxType") or "IGST",
            "list_price": float(header.get("ListPrice") or 0),
            "discount_amount": float(header.get("DiscountAmount") or 0),
            "taxable_value": float(header.get("TaxableValue") or 0),
            "cgst_rate": float(header.get("CgstRate") or 0),
            "cgst_amount": float(header.get("CgstAmount") or 0),
            "sgst_rate": float(header.get("SgstRate") or 0),
            "sgst_amount": float(header.get("SgstAmount") or 0),
            "igst_rate": float(header.get("IgstRate") or 0),
            "igst_amount": float(header.get("IgstAmount") or 0),
            "invoice_value": float(header.get("InvoiceValue") or 0),
            "amount_in_words": header.get("AmountInWords") or "",
            "notes": header.get("Notes") or "",
            "payment_bank_account_id": header.get("PaymentBankAccountID"),
            "pay_bank_name": header.get("PayBankName") or "",
            "pay_account_number": header.get("PayAccountNumber") or "",
            "pay_ifsc": header.get("PayIFSC") or "",
            "pay_branch": header.get("PayBranch") or "",
            "pay_account_holder": header.get("PayAccountHolder") or "",
            "pay_account_type": header.get("PayAccountType") or "",
            "pay_upi_id": header.get("PayUpiId") or "",
            "lines": [
                {
                    "sr_no": ln["SrNo"],
                    "item_id": ln.get("ItemID"),
                    "particulars": ln["Particulars"],
                    "hsn_sac": ln.get("HsnSac") or "",
                    "unit": ln.get("Unit") or "",
                    "qty": float(ln.get("Qty") or 0),
                    "rate": float(ln.get("Rate") or 0),
                    "discount_amount": float(ln.get("DiscountAmount") or 0),
                    "taxable_value": float(ln.get("TaxableValue") or 0),
                    "gst_rate_percent": float(ln.get("GstRatePercent") or 0),
                }
                for ln in lines
            ],
        }
        return self._render_pdf(data), f"Invoice-Preview.pdf"

    def _upi_qr_png_bytes(self, data: dict) -> bytes | None:
        upi = (data.get("pay_upi_id") or "").strip()
        if not upi or qrcode is None:
            return None
        amount = self._fmt(data.get("invoice_value")).replace(",", "")
        pn = (data.get("pay_account_holder") or data.get("pay_bank_name") or "JTCS").strip()
        tn = (data.get("invoice_no") or "Invoice").strip()
        params = {
            "pa": upi,
            "pn": pn,
            "am": amount,
            "cu": "INR",
            "tn": tn,
        }
        payload = "upi://pay?" + urllib.parse.urlencode(params)
        qr = qrcode.QRCode(version=None, box_size=4, border=1)
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        bio = io.BytesIO()
        img.save(bio, format="PNG")
        return bio.getvalue()

    def upi_qr_data_uri(self, data: dict) -> str | None:
        png = self._upi_qr_png_bytes(data)
        if not png:
            return None
        return "data:image/png;base64," + base64.b64encode(png).decode("ascii")

    def _upi_qr_image(self, data: dict) -> Image | None:
        png = self._upi_qr_png_bytes(data)
        if not png:
            return None
        return Image(io.BytesIO(png), width=32 * mm, height=32 * mm)

    def build_pdf(self, invoice_id: int) -> tuple[bytes, str]:
        data = self.invoice_service.get_record(invoice_id)
        safe_no = data["invoice_no"].replace("/", "-")
        return self._render_pdf(data), f"Invoice-{safe_no}.pdf"

    def _render_pdf(self, data: dict) -> bytes:
        company = self.invoice_service.company_profile()

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=10 * mm,
            bottomMargin=12 * mm,
        )
        # Single content width so customer box + line-items table share same L/R edges
        content_w = float(doc.width)
        styles = getSampleStyleSheet()
        brand = ParagraphStyle(
            "Brand",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13,
            textColor=colors.HexColor("#154375"),
            leading=16,
        )
        small = ParagraphStyle(
            "Small",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#1C2833"),
        )
        small_r = ParagraphStyle("SmallR", parent=small, alignment=TA_RIGHT)
        title = ParagraphStyle(
            "InvTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=14,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#154375"),
            spaceBefore=6,
            spaceAfter=8,
        )
        cell = ParagraphStyle(
            "Cell",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
        )
        cell_b = ParagraphStyle("CellB", parent=cell, fontName="Helvetica-Bold")

        story: list = []
        story.append(Paragraph("Original for Recipient", small))
        story.append(Spacer(1, 4))

        logo_path = self._logo_path()
        left_bits = [
            Paragraph(company["name"], brand),
            Paragraph(
                f"GSTIN / UIN: <b>{company['gstin']}</b> ({company['state'].upper()})",
                small,
            ),
        ]
        if company.get("cin"):
            left_bits.append(Paragraph(f"CIN: {company['cin']}", small))
        left_bits.append(Paragraph(f"PAN: {company['pan']}", small))
        left_bits.append(Paragraph(company["address"], small))

        left_col: list = []
        if logo_path:
            left_col.append(Image(str(logo_path), width=38 * mm, height=22 * mm))
            left_col.append(Spacer(1, 3))
        left_col.extend(left_bits)

        right_col = [
            Paragraph(
                f"Invoice Value: <b>Rs. {self._fmt(data['invoice_value'])}</b>",
                small_r,
            ),
            Paragraph(f"Invoice No: <b>{data['invoice_no']}</b>", small_r),
            Paragraph(
                f"Invoice Date: <b>{self._display_date(data['invoice_date'])}</b>",
                small_r,
            ),
        ]

        header_table = Table(
            [[left_col, right_col]],
            colWidths=[content_w * 0.62, content_w * 0.38],
        )
        header_table.hAlign = "LEFT"
        header_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(header_table)
        story.append(Paragraph("Tax Invoice", title))

        pos = data.get("place_of_supply") or "—"
        if data.get("place_of_supply_code"):
            pos = f"{pos} ({data['place_of_supply_code']})"

        cust_left = [
            Paragraph(f"<b>Customer Name:</b> {data['customer_name']}", small),
            Paragraph(
                f"<b>Billing / Shipping Address:</b> {data.get('billing_address') or '—'}",
                small,
            ),
            Paragraph(
                f"<b>Contact Mobile No.:</b> {data.get('contact_mobile') or '—'}",
                small,
            ),
            Paragraph(
                f"<b>Customer GSTIN:</b> {data.get('customer_gstin') or '—'}",
                small,
            ),
            Paragraph(f"<b>Place of Supply:</b> {pos}", small),
        ]
        cust_right = [
            Paragraph(
                f"<b>Contact Person:</b> {data.get('contact_person') or '—'}",
                small,
            ),
            Paragraph(
                f"<b>Contact Email:</b> {data.get('contact_email') or '—'}",
                small,
            ),
            Paragraph(
                f"<b>Customer ID:</b> {data.get('customer_id') or '—'}",
                small,
            ),
            Paragraph(
                f"<b>Reverse Charge:</b> {'Yes' if data.get('reverse_charge') else 'No'}",
                small,
            ),
        ]
        # Same outer width / L-R edges as the invoice line-items table below
        cust_table = Table(
            [[cust_left, cust_right]],
            colWidths=[content_w * 0.58, content_w * 0.42],
        )
        cust_table.hAlign = "LEFT"
        cust_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F6F7")),
                    ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#5D6D7E")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(cust_table)
        story.append(Spacer(1, 8))

        table_data = [
            [
                Paragraph("<b>Sr.</b>", cell),
                Paragraph("<b>Particulars</b>", cell),
                Paragraph("<b>HSN / SAC</b>", cell),
                Paragraph("<b>Unit(s)</b>", cell),
                Paragraph("<b>Rate</b>", cell),
                Paragraph("<b>Discount</b>", cell),
                Paragraph("<b>Taxable Value</b>", cell),
            ]
        ]
        for line in data.get("lines") or []:
            hsn = line.get("hsn_sac") or ""
            table_data.append(
                [
                    Paragraph(str(line.get("sr_no") or ""), cell),
                    Paragraph(line.get("particulars") or "—", cell),
                    Paragraph(hsn, cell),
                    Paragraph(f"{self._fmt(line.get('qty'))} {line.get('unit') or ''}", cell),
                    Paragraph(self._fmt(line.get("rate")), cell),
                    Paragraph(self._fmt(line.get("discount_amount")), cell),
                    Paragraph(self._fmt(line.get("taxable_value")), cell),
                ]
            )

        # Column fractions sum to 1.0 → exact same width as customer box
        item_fracs = (0.06, 0.34, 0.12, 0.11, 0.12, 0.12, 0.13)
        item_widths = [content_w * f for f in item_fracs]
        items = Table(table_data, colWidths=item_widths, repeatRows=1)
        items.hAlign = "LEFT"
        items.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#154375")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#5D6D7E")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(items)
        story.append(Spacer(1, 8))

        story.append(
            Paragraph(
                f"<b>Amount (In Words):</b> {data.get('amount_in_words') or '—'}",
                small,
            )
        )
        story.append(Spacer(1, 6))

        totals_rows = [
            ["List Price:", self._fmt(data["list_price"])],
            ["Discount:", self._fmt(data["discount_amount"])],
            ["Taxable Value:", self._fmt(data["taxable_value"])],
        ]
        if data.get("tax_type") == "CGST_SGST":
            totals_rows.append(
                [
                    f"CGST @ {self._fmt(data['cgst_rate'])}%:",
                    self._fmt(data["cgst_amount"]),
                ]
            )
            totals_rows.append(
                [
                    f"SGST @ {self._fmt(data['sgst_rate'])}%:",
                    self._fmt(data["sgst_amount"]),
                ]
            )
        else:
            totals_rows.append(
                [
                    f"IGST @ {self._fmt(data['igst_rate'])}%:",
                    self._fmt(data["igst_amount"]),
                ]
            )
        totals_rows.append(["Invoice Value:", self._fmt(data["invoice_value"])])

        totals = Table(totals_rows, colWidths=[40 * mm, 30 * mm], hAlign="RIGHT")
        totals.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -2), "Helvetica"),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#D6EAF8")),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(totals)
        story.append(Spacer(1, 8))

        # Payment bank details + UPI QR (just below Invoice Value)
        if data.get("pay_account_number") or data.get("pay_bank_name") or data.get("pay_upi_id"):
            bank_lines = [
                Paragraph("<b>Payment / Bank Details</b>", cell_b),
                Paragraph(
                    f"<b>Bank Name:</b> {data.get('pay_bank_name') or '—'}",
                    small,
                ),
                Paragraph(
                    f"<b>Account Holder:</b> {data.get('pay_account_holder') or '—'}",
                    small,
                ),
                Paragraph(
                    f"<b>Account Number:</b> {data.get('pay_account_number') or '—'}",
                    small,
                ),
                Paragraph(
                    f"<b>IFSC Code:</b> {data.get('pay_ifsc') or '—'}",
                    small,
                ),
                Paragraph(
                    f"<b>Branch:</b> {data.get('pay_branch') or '—'}",
                    small,
                ),
                Paragraph(
                    f"<b>Account Type:</b> {data.get('pay_account_type') or '—'}",
                    small,
                ),
                Paragraph(
                    f"<b>UPI ID:</b> {data.get('pay_upi_id') or '—'}",
                    small,
                ),
            ]
            qr_img = self._upi_qr_image(data)
            right_col: list = []
            if qr_img is not None:
                right_col.append(qr_img)
                right_col.append(Spacer(1, 2))
                right_col.append(
                    Paragraph(
                        f"Scan to pay Rs. {self._fmt(data.get('invoice_value'))}",
                        ParagraphStyle(
                            "QrCap",
                            parent=small,
                            alignment=TA_CENTER,
                            fontSize=7,
                        ),
                    )
                )
            else:
                right_col.append(
                    Paragraph(
                        "UPI QR not available<br/>(set UPI ID on bank master).",
                        ParagraphStyle(
                            "QrMiss",
                            parent=small,
                            alignment=TA_CENTER,
                            fontSize=7,
                            textColor=colors.HexColor("#7F8C8D"),
                        ),
                    )
                )
            pay_table = Table(
                [[bank_lines, right_col]],
                colWidths=[content_w * 0.70, content_w * 0.30],
            )
            pay_table.hAlign = "LEFT"
            pay_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EBF5FB")),
                        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#5D6D7E")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 3),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ("ALIGN", (1, 0), (1, 0), "CENTER"),
                    ]
                )
            )
            story.append(pay_table)
            story.append(Spacer(1, 12))
        else:
            story.append(Spacer(1, 8))

        story.append(Paragraph(f"for {company['name']}", small))
        story.append(Spacer(1, 22))
        story.append(Paragraph("<b>Authorised Signatory</b>", small))
        story.append(Spacer(1, 10))
        story.append(Paragraph("<b>Terms &amp; Conditions:</b>", cell_b))
        story.append(
            Paragraph(
                "All disputes are subject to Haldwani / Nainital jurisdiction only.",
                small,
            )
        )
        story.append(Spacer(1, 6))
        story.append(
            Paragraph(
                f"{company['name']}, {company['address']}<br/>"
                f"{company.get('website') or ''} | {company.get('email') or ''} | "
                f"{company.get('phone') or ''}",
                ParagraphStyle("Foot", parent=small, alignment=TA_CENTER, fontSize=7),
            )
        )
        story.append(
            Paragraph(
                "This is a computer-generated invoice and does not require a physical signature.",
                ParagraphStyle("Foot2", parent=small, alignment=TA_CENTER, fontSize=7),
            )
        )

        doc.build(story)
        return buffer.getvalue()

    @staticmethod
    def _display_date(iso_date: str) -> str:
        if not iso_date or len(iso_date) < 10:
            return iso_date or ""
        y, m, d = iso_date[:10].split("-")
        return f"{d}-{m}-{y}"
