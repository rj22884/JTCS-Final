from __future__ import annotations

import base64
import hashlib
import hmac
import io
import urllib.parse
from pathlib import Path

from flask import current_app, has_request_context, request, url_for
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


class _LinkedImage(Image):
    """QR / image that opens a URI when tapped in a PDF viewer."""

    def __init__(self, *args, link_url: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._link_url = link_url

    def draw(self):
        super().draw()
        if self._link_url:
            self.canv.linkURL(
                self._link_url,
                (0, 0, self.drawWidth, self.drawHeight),
                relative=1,
                thickness=0,
            )


class GstInvoicePdfService:
    def __init__(self, invoice_service: GstInvoiceService | None = None):
        self.invoice_service = invoice_service or GstInvoiceService()

    @staticmethod
    def _fmt(amount) -> str:
        try:
            return f"{float(amount):,.2f}"
        except (TypeError, ValueError):
            return "0.00"

    def _static_img_path(self, filename: str) -> Path | None:
        static = Path(current_app.static_folder or "")
        candidate = static / "img" / filename
        return candidate if candidate.is_file() else None

    def _logo_path(self) -> Path | None:
        return self._static_img_path("jtcs_invoice_logo.png")

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
            "round_off": float(header.get("RoundOffAmount") or 0),
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
                self._pdf_line_from_build(ln) for ln in lines
            ],
        }
        return self._render_pdf(data), f"Invoice-Preview.pdf"

    def _pdf_line_from_build(self, ln: dict) -> dict:
        item_id = ln.get("ItemID")
        item_name = ""
        if item_id:
            item = self.invoice_service.item_repo.get_by_id(item_id)
            if item:
                item_name = item.ItemName or ""
        return {
            "sr_no": ln["SrNo"],
            "item_id": item_id,
            "item_name": item_name,
            "tax_period": ln.get("TaxPeriod") or "",
            "quarter": ln.get("Quarter") or "",
            "month": ln.get("Month") or "",
            "particulars": ln["Particulars"],
            "hsn_sac": ln.get("HsnSac") or "",
            "unit": ln.get("Unit") or "",
            "qty": float(ln.get("Qty") or 0),
            "rate": float(ln.get("Rate") or 0),
            "discount_amount": float(ln.get("DiscountAmount") or 0),
            "taxable_value": float(ln.get("TaxableValue") or 0),
            "gst_rate_percent": float(ln.get("GstRatePercent") or 0),
        }

    @staticmethod
    def _pdf_escape(value: str) -> str:
        return (
            (value or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def _particulars_paragraph(self, line: dict, cell: ParagraphStyle) -> Paragraph:
        main, extra = GstInvoiceService.line_particulars_parts(line)
        html = self._pdf_escape(main or "—")
        if extra:
            html += f"<br/>({self._pdf_escape(extra)})"
        return Paragraph(html, cell)

    def upi_intent_url(self, data: dict) -> str | None:
        upi = (data.get("pay_upi_id") or "").strip()
        if not upi:
            return None
        amount = self._fmt(data.get("invoice_value")).replace(",", "")
        pn = (data.get("pay_account_holder") or data.get("pay_bank_name") or "JTCS").strip() or "JTCS"
        tn = (data.get("invoice_no") or "Invoice").strip() or "Invoice"
        params = {
            "pa": upi,
            "pn": pn,
            "am": amount,
            "cu": "INR",
            "tn": tn,
        }
        return "upi://pay?" + urllib.parse.urlencode(params)

    def pay_token(self, data: dict) -> str:
        secret = current_app.secret_key
        if isinstance(secret, str):
            secret = secret.encode("utf-8")
        raw = (
            f"{data.get('invoice_id')}|{data.get('invoice_no') or ''}|"
            f"{self._fmt(data.get('invoice_value')).replace(',', '')}"
        )
        return hmac.new(secret, raw.encode("utf-8"), hashlib.sha256).hexdigest()[:20]

    def verify_pay_token(self, data: dict, token: str) -> bool:
        expected = self.pay_token(data)
        given = (token or "").strip()
        if len(given) != len(expected):
            return False
        return hmac.compare_digest(expected, given)

    def public_pay_url(self, data: dict) -> str | None:
        if not self.upi_intent_url(data) or not data.get("invoice_id"):
            return None
        path = url_for(
            "invoice_pay_public.public_upi_pay",
            invoice_id=int(data["invoice_id"]),
            t=self.pay_token(data),
        )
        base = (current_app.config.get("APP_BASE_URL") or "").strip().rstrip("/")
        if not base and has_request_context():
            base = (request.url_root or "").rstrip("/")
        return (base + path) if base else path

    def _upi_qr_png_bytes(self, data: dict) -> bytes | None:
        payload = self.upi_intent_url(data)
        if not payload or qrcode is None:
            return None
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
        return _LinkedImage(
            io.BytesIO(png),
            width=32 * mm,
            height=32 * mm,
            link_url=self.upi_intent_url(data),
        )

    def build_pdf(self, invoice_id: int) -> tuple[bytes, str]:
        data = self.invoice_service.get_record(invoice_id)
        safe_no = data["invoice_no"].replace("/", "-")
        return self._render_pdf(data), f"Invoice-{safe_no}.pdf"

    @staticmethod
    def _pdf_to_png(pdf_bytes: bytes) -> bytes:
        errors: list[str] = []
        try:
            import pypdfium2 as pdfium

            pdf = pdfium.PdfDocument(pdf_bytes)
            page = pdf[0]
            bitmap = page.render(scale=2)
            image = bitmap.to_pil()
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as exc:
            errors.append(f"pypdfium2: {exc}")
        try:
            import fitz

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            page = doc[0]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            return pix.tobytes("png")
        except Exception as exc:
            errors.append(f"pymupdf: {exc}")
        try:
            from pdf2image import convert_from_bytes

            pages = convert_from_bytes(pdf_bytes, dpi=150)
            if not pages:
                raise RuntimeError("no pages")
            buf = io.BytesIO()
            pages[0].save(buf, format="PNG")
            return buf.getvalue()
        except Exception as exc:
            errors.append(f"pdf2image: {exc}")
        raise RuntimeError(
            "Unable to create PNG from invoice. " + " | ".join(errors)
        )

    def build_png(self, invoice_id: int) -> tuple[bytes, str]:
        pdf_bytes, pdf_name = self.build_pdf(invoice_id)
        png_bytes = self._pdf_to_png(pdf_bytes)
        return png_bytes, pdf_name.replace(".pdf", ".png")

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
            textColor=colors.HexColor("#0B2545"),
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
            textColor=colors.HexColor("#0B2545"),
            spaceBefore=6,
            spaceAfter=8,
        )
        cell = ParagraphStyle(
            "Cell",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
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
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF4EB")),
                    ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#D7E0EA")),
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
                    self._particulars_paragraph(line, cell),
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
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B2545")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#5D6D7E")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
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

        header_cell = ParagraphStyle(
            "TotHead",
            parent=cell,
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9,
            alignment=TA_CENTER,
            textColor=colors.white,
        )
        value_cell = ParagraphStyle(
            "TotVal",
            parent=cell,
            fontSize=8,
            leading=10,
            alignment=TA_CENTER,
        )
        value_cell_b = ParagraphStyle("TotValB", parent=value_cell, fontName="Helvetica-Bold")
        round_off = float(data.get("round_off") or 0)
        show_round = abs(round_off) >= 0.005
        round_txt = f"{'+' if round_off > 0 else '-'}{self._fmt(abs(round_off))}"
        if data.get("tax_type") == "CGST_SGST":
            tot_headers = [
                Paragraph("List Price", header_cell),
                Paragraph("Discount", header_cell),
                Paragraph("Taxable Value", header_cell),
                Paragraph(f"CGST @ {self._fmt(data['cgst_rate'])}%", header_cell),
                Paragraph(f"SGST @ {self._fmt(data['sgst_rate'])}%", header_cell),
            ]
            tot_values = [
                Paragraph(self._fmt(data["list_price"]), value_cell),
                Paragraph(self._fmt(data["discount_amount"]), value_cell),
                Paragraph(self._fmt(data["taxable_value"]), value_cell),
                Paragraph(self._fmt(data["cgst_amount"]), value_cell),
                Paragraph(self._fmt(data["sgst_amount"]), value_cell),
            ]
        else:
            tot_headers = [
                Paragraph("List Price", header_cell),
                Paragraph("Discount", header_cell),
                Paragraph("Taxable Value", header_cell),
                Paragraph(f"IGST @ {self._fmt(data['igst_rate'])}%", header_cell),
            ]
            tot_values = [
                Paragraph(self._fmt(data["list_price"]), value_cell),
                Paragraph(self._fmt(data["discount_amount"]), value_cell),
                Paragraph(self._fmt(data["taxable_value"]), value_cell),
                Paragraph(self._fmt(data["igst_amount"]), value_cell),
            ]
        if show_round:
            tot_headers.append(Paragraph("Round off", header_cell))
            tot_values.append(Paragraph(round_txt, value_cell))
        tot_headers.append(Paragraph("Invoice Value", header_cell))
        tot_values.append(Paragraph(self._fmt(data["invoice_value"]), value_cell_b))
        n_tot = len(tot_headers)
        tot_widths = [content_w / n_tot] * n_tot
        totals = Table([tot_headers, tot_values], colWidths=tot_widths)
        totals.hAlign = "LEFT"
        last_col = n_tot - 1
        totals.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B2545")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("BACKGROUND", (last_col, 1), (last_col, 1), colors.HexColor("#FFF4EB")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#5D6D7E")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
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
            qr_col: list = []
            if qr_img is not None:
                qr_col.append(qr_img)
                qr_col.append(Spacer(1, 2))
                qr_col.append(
                    Paragraph(
                        f"Tap / scan to pay Rs. {self._fmt(data.get('invoice_value'))}",
                        ParagraphStyle(
                            "QrCap",
                            parent=small,
                            alignment=TA_CENTER,
                            fontSize=7,
                        ),
                    )
                )
            else:
                qr_col.append(
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
                [[bank_lines, qr_col]],
                colWidths=[content_w * 0.70, content_w * 0.30],
            )
            pay_table.hAlign = "LEFT"
            pay_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E8F3FC")),
                        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#D7E0EA")),
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

        story.append(Paragraph(f"for {company['name']}", ParagraphStyle("SignFor", parent=small, alignment=TA_RIGHT)))
        stamp_path = self._static_img_path("jtcs_invoice_stamp.png")
        sign_path = self._static_img_path("jtcs_invoice_sign.png")
        stamp_flow = ""
        if stamp_path:
            stamp_flow = Image(str(stamp_path), width=28 * mm, height=28 * mm, mask="auto")
        sign_bits: list = []
        if sign_path:
            sign_bits.append(Image(str(sign_path), width=38 * mm, height=16 * mm, mask="auto"))
            sign_bits.append(Spacer(1, 2))
        sign_bits.append(
            Paragraph(
                "<b>Authorised Signatory</b>",
                ParagraphStyle("SignLab", parent=small, alignment=TA_RIGHT),
            )
        )
        sign_table = Table(
            [[stamp_flow, sign_bits]],
            colWidths=[32 * mm, 48 * mm],
        )
        sign_table.hAlign = "RIGHT"
        sign_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (0, 0), "CENTER"),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(Spacer(1, 4))
        story.append(sign_table)
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
