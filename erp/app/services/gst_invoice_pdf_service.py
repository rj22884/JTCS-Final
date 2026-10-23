from __future__ import annotations

import base64
import hashlib
import hmac
import io
import urllib.parse
from pathlib import Path

from flask import current_app, has_request_context, request, url_for
from reportlab.graphics import renderPDF, renderSVG
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, C6
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
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


class _LinkedQr(Flowable):
    """Vector QR fallback for PDF environments without the optional qrcode package."""

    def __init__(self, drawing: Drawing, size: float, link_url: str | None = None):
        super().__init__()
        self.drawing = drawing
        self.width = size
        self.height = size
        self._link_url = link_url

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        self.canv.saveState()
        scale = min(self.width / self.drawing.width, self.height / self.drawing.height)
        draw_width = self.drawing.width * scale
        draw_height = self.drawing.height * scale
        self.canv.translate((self.width - draw_width) / 2, (self.height - draw_height) / 2)
        self.canv.scale(scale, scale)
        renderPDF.draw(self.drawing, self.canv, 0, 0)
        self.canv.restoreState()
        if self._link_url:
            self.canv.linkURL(
                self._link_url,
                (0, 0, self.width, self.height),
                relative=1,
                thickness=0,
            )


class _StampWithSignature(Flowable):
    """Round stamp with the signature drawn across it."""

    def __init__(self, stamp_path: str, sign_path: str | None, size: float):
        super().__init__()
        self.stamp_path = stamp_path
        self.sign_path = sign_path
        self.size = size

    def wrap(self, availWidth, availHeight):
        return self.size, self.size

    def draw(self):
        self.canv.drawImage(
            self.stamp_path,
            0,
            0,
            width=self.size,
            height=self.size,
            mask="auto",
            preserveAspectRatio=True,
            anchor="c",
        )
        if not self.sign_path:
            return
        sign_w = self.size * 0.92
        sign_h = self.size * 0.42
        x = (self.size - sign_w) / 2
        y = (self.size - sign_h) / 2
        self.canv.drawImage(
            self.sign_path,
            x,
            y,
            width=sign_w,
            height=sign_h,
            mask="auto",
            preserveAspectRatio=True,
            anchor="c",
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
            payload, persist_no=False, require_payment_bank=False
        )
        data = {
            "invoice_id": 0,
            "invoice_no": preview.get("invoice_no") or header.get("InvoiceNo") or "PREVIEW",
            "invoice_date": header["InvoiceDate"].isoformat(),
            "customer_id": header.get("CustomerID"),
            "customer_name": header.get("CustomerName") or "",
            "contact_person": header.get("ContactPerson") or header.get("CustomerName") or "",
            "billing_address": header.get("BillingAddress") or "",
            "customer_gstin": header.get("CustomerGSTIN") or "",
            "contact_mobile": header.get("ContactMobile") or "",
            "contact_email": header.get("ContactEmail") or "",
            "place_of_supply": header.get("PlaceOfSupply") or "",
            "place_of_supply_code": header.get("PlaceOfSupplyCode") or "",
            "reverse_charge": bool(header.get("ReverseCharge")),
            "invoice_kind": header.get("InvoiceKind") or "NON_GST",
            "tax_type": header.get("TaxType") or "IGST",
            "bill_source": self.invoice_service.normalize_bill_source(
                payload.get("bill_source") or header.get("BillSource")
            ),
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
            "payment_received": self.invoice_service._form_flag(
                payload, "payment_received", "PaymentReceived"
            ),
            "payment_date": str(payload.get("payment_date") or ""),
            "pay_bank_name": header.get("PayBankName") or "",
            "pay_account_number": header.get("PayAccountNumber") or "",
            "pay_ifsc": header.get("PayIFSC") or "",
            "pay_branch": header.get("PayBranch") or "",
            "pay_account_holder": header.get("PayAccountHolder") or "",
            "pay_account_type": header.get("PayAccountType") or "",
            "pay_upi_id": header.get("PayUpiId") or "",
            "pay_banks": self._banks_from_header(header),
            "lines": [
                self._pdf_line_from_build(ln) for ln in lines
            ],
        }
        if str(payload.get("preview_page_size") or "").strip().upper() == "C6":
            return self._render_c6_pdf(data), "Invoice-Preview-C6.pdf"
        return self._render_pdf(data), "Invoice-Preview.pdf"

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

    def _particulars_paragraph(self, line: dict, cell: ParagraphStyle, *, bill_source: str = "") -> Paragraph:
        source = (bill_source or "").strip()
        if source == GstInvoiceService.BILL_SOURCE_MISCELLANEOUS:
            # Misc bills: particulars already = Item (description); never print tax year.
            text = (line.get("particulars") or line.get("item_name") or "—").strip() or "—"
            return Paragraph(self._pdf_escape(text), cell)
        main, extra = GstInvoiceService.line_particulars_parts(line)
        html = self._pdf_escape(main or "—")
        if extra:
            html += f"<br/>({self._pdf_escape(extra)})"
        return Paragraph(html, cell)

    def upi_intent_url(self, data: dict) -> str | None:
        bank = {}
        upi = (data.get("pay_upi_id") or "").strip()
        if not upi:
            bank = next(
                (
                    row
                    for row in (data.get("pay_banks") or [])
                    if isinstance(row, dict) and (row.get("upi_id") or "").strip()
                ),
                {},
            )
            upi = (bank.get("upi_id") or "").strip()
        if not upi:
            return None
        amount = self._fmt(data.get("invoice_value")).replace(",", "")
        pn = (
            data.get("pay_account_holder")
            or data.get("pay_bank_name")
            or bank.get("account_holder_name")
            or bank.get("bank_name")
            or "JTCS"
        ).strip() or "JTCS"
        tn = (data.get("invoice_no") or "Invoice").strip() or "Invoice"
        params = {
            "pa": upi,
            "pn": pn,
            "am": amount,
            "cu": "INR",
            "tn": tn,
        }
        return "upi://pay?" + urllib.parse.urlencode(params)

    def _qr_payload(self, data: dict) -> str:
        """Use a UPI payment intent when possible, otherwise encode invoice details."""
        payment_url = self.upi_intent_url(data)
        if payment_url:
            return payment_url

        banks = self._banks_for_pdf(data)
        bank = banks[0] if banks else {}
        account_number = (bank.get("account_number") or data.get("pay_account_number") or "").strip()
        ifsc = (bank.get("ifsc_code") or data.get("pay_ifsc") or "").strip()
        return "\n".join(
            [
                "JTCS INVOICE DETAILS",
                f"Invoice: {(data.get('invoice_no') or 'Invoice').strip()}",
                f"Date: {self._display_date(data.get('invoice_date') or '')}",
                f"Amount: INR {self._fmt(data.get('invoice_value')).replace(',', '')}",
                f"Bank: {(bank.get('bank_name') or data.get('pay_bank_name') or '').strip() or '—'}",
                f"Account: {account_number or '—'}",
                f"IFSC: {ifsc or '—'}",
            ]
        )

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
        payload = self._qr_payload(data)
        if qrcode is None:
            return None
        qr = qrcode.QRCode(version=None, box_size=4, border=4)
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        bio = io.BytesIO()
        img.save(bio, format="PNG")
        return bio.getvalue()

    def upi_qr_data_uri(self, data: dict) -> str | None:
        png = self._upi_qr_png_bytes(data)
        if png:
            return "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        drawing = self._qr_drawing(self._qr_payload(data))
        svg = renderSVG.drawToString(drawing).encode("utf-8")
        return "data:image/svg+xml;base64," + base64.b64encode(svg).decode("ascii")

    @staticmethod
    def _qr_drawing(payload: str) -> Drawing:
        widget = QrCodeWidget(payload, barLevel="M", barBorder=4)
        x1, y1, x2, y2 = widget.getBounds()
        drawing = Drawing(x2 - x1, y2 - y1)
        drawing.add(widget)
        return drawing

    def _banks_for_pdf(self, data: dict) -> list[dict]:
        banks = data.get("pay_banks") or []
        if isinstance(banks, list) and banks:
            return [row for row in banks if isinstance(row, dict)][:2]
        upi = (data.get("pay_upi_id") or "").strip()
        number = (data.get("pay_account_number") or "").strip()
        if not upi and not number:
            return []
        return [
            {
                "bank_name": data.get("pay_bank_name") or "",
                "account_number": number,
                "ifsc_code": data.get("pay_ifsc") or "",
                "branch_name": data.get("pay_branch") or "",
                "account_holder_name": data.get("pay_account_holder") or "",
                "account_type": data.get("pay_account_type") or "",
                "upi_id": upi,
            }
        ]

    def _banks_from_header(self, header: dict) -> list[dict]:
        import json

        raw = header.get("PayBankAccounts") or ""
        if raw:
            try:
                parsed = json.loads(raw)
            except (TypeError, ValueError):
                parsed = []
            if isinstance(parsed, list):
                return [row for row in parsed if isinstance(row, dict)][:2]
        upi = (header.get("PayUpiId") or "").strip()
        number = (header.get("PayAccountNumber") or "").strip()
        if not upi and not number:
            return []
        return [
            {
                "account_id": header.get("PaymentBankAccountID"),
                "bank_name": header.get("PayBankName") or "",
                "account_number": number,
                "ifsc_code": header.get("PayIFSC") or "",
                "branch_name": header.get("PayBranch") or "",
                "account_holder_name": header.get("PayAccountHolder") or "",
                "account_type": header.get("PayAccountType") or "",
                "upi_id": upi,
            }
        ]

    def _upi_qr_image(self, data: dict, size: float | None = None) -> Flowable | None:
        png = self._upi_qr_png_bytes(data)
        side = size if size and size > 0 else 32 * mm
        link_url = self.upi_intent_url(data)
        if png:
            return _LinkedImage(
                io.BytesIO(png),
                width=side,
                height=side,
                link_url=link_url,
            )
        return _LinkedQr(self._qr_drawing(self._qr_payload(data)), side, link_url=link_url)

    def paid_stamp_details(self, data: dict) -> dict[str, str]:
        """Return the payment date and receiving account for the PAID mark."""
        if not self._invoice_is_paid(data):
            return {"date": "", "account": "—"}
        payment_date = (data.get("payment_date") or "").strip()
        accounts: list[str] = []
        invoice_id = data.get("invoice_id")
        try:
            invoice_key = int(invoice_id or 0)
        except (TypeError, ValueError):
            invoice_key = 0

        if invoice_key > 0:
            try:
                from app.extensions import db
                from app.models.bank_cash import OthersBankCashTransaction
                from app.models.transactions import JtcsBankAccountMaster
                from app.services.others_bank_cash_service import OthersBankCashService

                receipt_summary = OthersBankCashService().invoice_payment_adjustment(invoice_key)
                receipt_entries = [
                    row
                    for row in (receipt_summary.get("entries") or [])
                    if float(row.get("allocated_amount") or 0) > 0
                ]
                if receipt_entries:
                    latest = max(
                        receipt_entries,
                        key=lambda row: (row.get("work_date") or "", int(row.get("money_inout_entry_id") or 0)),
                    )
                    payment_date = payment_date or (latest.get("work_date") or "")
                    for row in receipt_entries:
                        txn = db.session.get(
                            OthersBankCashTransaction,
                            int(row.get("money_inout_entry_id") or 0),
                        )
                        if txn is None:
                            continue
                        bank_id = getattr(txn, "DebitBankAccountID", None)
                        ledger_key = (getattr(txn, "DebitLedgerKey", None) or "").strip()
                        if not bank_id and ledger_key.lower().startswith("bank-"):
                            try:
                                bank_id = int(ledger_key.split("-", 1)[1])
                            except (TypeError, ValueError):
                                bank_id = None
                        if bank_id:
                            account = db.session.get(JtcsBankAccountMaster, int(bank_id))
                            raw_number = (
                                getattr(account, "AccountNumber", None)
                                or getattr(account, "MaskedAccountNumber", None)
                                or ""
                            ) if account else ""
                            digits = "".join(char for char in str(raw_number) if char.isdigit())
                            suffix = digits[-4:] if digits else ""
                            if suffix and suffix not in accounts:
                                accounts.append(suffix)
                        elif ledger_key:
                            label = OthersBankCashService()._label_for_ledger_key(ledger_key)
                            if "cash" in f"{ledger_key} {label}".lower() and "Cash" not in accounts:
                                accounts.append("Cash")
            except Exception:
                # Keep the invoice printable if optional receipt/account details cannot be resolved.
                pass

        if not accounts:
            banks = self._banks_for_pdf(data)
            bank = banks[0] if banks else {}
            raw_number = bank.get("account_number") or data.get("pay_account_number") or ""
            digits = "".join(char for char in str(raw_number) if char.isdigit())
            suffix = digits[-4:] if digits else ""
            if suffix:
                accounts.append(suffix)

        return {
            "date": payment_date,
            "account": ", ".join(accounts) if accounts else "—",
        }

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

    def build_preview_pages_from_payload(self, payload: dict) -> tuple[bytes, list[bytes], str]:
        """Return the unsaved preview PDF and raster pages for the interactive viewer."""
        pdf_bytes, filename = self.build_pdf_from_payload(payload)
        return pdf_bytes, self._pdf_to_png_pages(pdf_bytes, dpi=180), filename

    @staticmethod
    def _pdf_to_png_pages(pdf_bytes: bytes, *, dpi: int = 180) -> list[bytes]:
        errors: list[str] = []
        try:
            import pypdfium2 as pdfium

            pdf = pdfium.PdfDocument(pdf_bytes)
            pages: list[bytes] = []
            for index in range(len(pdf)):
                bitmap = pdf[index].render(scale=dpi / 72)
                image = bitmap.to_pil()
                buf = io.BytesIO()
                image.save(buf, format="PNG")
                pages.append(buf.getvalue())
            if pages:
                return pages
            raise RuntimeError("no pages")
        except Exception as exc:
            errors.append(f"pypdfium2: {exc}")
        try:
            import fitz

            pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            pages = [
                page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False).tobytes("png")
                for page in pdf_doc
            ]
            if pages:
                return pages
            raise RuntimeError("no pages")
        except Exception as exc:
            errors.append(f"pymupdf: {exc}")
        try:
            from pdf2image import convert_from_bytes

            images = convert_from_bytes(pdf_bytes, dpi=dpi)
            pages = []
            for image in images:
                buf = io.BytesIO()
                image.save(buf, format="PNG")
                pages.append(buf.getvalue())
            if pages:
                return pages
            raise RuntimeError("no pages")
        except Exception as exc:
            errors.append(f"pdf2image: {exc}")
        raise RuntimeError("Unable to render invoice preview pages. " + " | ".join(errors))

    def build_png(self, invoice_id: int) -> tuple[bytes, str]:
        pdf_bytes, pdf_name = self.build_pdf(invoice_id)
        png_bytes = self._pdf_to_png(pdf_bytes)
        return png_bytes, pdf_name.replace(".pdf", ".png")

    def _render_c6_pdf(self, data: dict) -> bytes:
        """Render a compact portrait invoice preview on C6 envelope paper."""
        company = self.invoice_service.company_profile()
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=C6,
            leftMargin=4 * mm,
            rightMargin=4 * mm,
            topMargin=4 * mm,
            bottomMargin=4 * mm,
        )
        content_w = float(doc.width)
        styles = getSampleStyleSheet()
        tiny = ParagraphStyle(
            "C6Tiny", parent=styles["Normal"], fontName="Helvetica",
            fontSize=5.2, leading=6.1, textColor=colors.HexColor("#1C2833"),
        )
        tiny_b = ParagraphStyle("C6TinyB", parent=tiny, fontName="Helvetica-Bold")
        tiny_r = ParagraphStyle("C6TinyR", parent=tiny, alignment=TA_RIGHT)
        brand = ParagraphStyle(
            "C6Brand", parent=tiny_b, fontSize=7.2, leading=8.2,
            textColor=colors.HexColor("#0B2545"),
        )
        title = ParagraphStyle(
            "C6Title", parent=tiny_b, fontSize=9, leading=10,
            alignment=TA_CENTER, textColor=colors.HexColor("#0B2545"),
            spaceBefore=2, spaceAfter=3,
        )
        table_head = ParagraphStyle(
            "C6Head", parent=tiny_b, fontSize=5.1, leading=5.8,
            textColor=colors.white,
        )
        table_cell = ParagraphStyle("C6Cell", parent=tiny, fontSize=5.1, leading=5.8)
        table_cell_r = ParagraphStyle("C6CellR", parent=table_cell, alignment=TA_RIGHT)

        def text(value) -> str:
            return self._pdf_escape(str(value or "—"))

        banks = self._banks_for_pdf(data)
        qr_bank = next((row for row in banks if (row.get("upi_id") or "").strip()), None)
        if qr_bank:
            data = {
                **data,
                "pay_upi_id": qr_bank.get("upi_id") or "",
                "pay_bank_name": qr_bank.get("bank_name") or "",
                "pay_account_holder": qr_bank.get("account_holder_name") or "",
            }

        story: list = [Paragraph("Original for Recipient", tiny)]
        logo_path = self._logo_path()
        company_bits: list = []
        if logo_path:
            company_bits.append(Image(str(logo_path), width=17 * mm, height=10 * mm))
            company_bits.append(Spacer(1, 1))
        company_bits.extend(
            [
                Paragraph(text(company.get("name")), brand),
                Paragraph(f"GSTIN: <b>{text(company.get('gstin'))}</b>", tiny),
                Paragraph(f"PAN: {text(company.get('pan'))}", tiny),
                Paragraph(text(company.get("address")), tiny),
            ]
        )
        invoice_bits = [
            Paragraph(f"<b>Value:</b> Rs. {self._fmt(data.get('invoice_value'))}", tiny_r),
            Paragraph(f"<b>No:</b> {text(data.get('invoice_no'))}", tiny_r),
            Paragraph(f"<b>Date:</b> {text(self._display_date(data.get('invoice_date') or ''))}", tiny_r),
        ]
        qr_img = self._upi_qr_image(data, 13 * mm)
        if qr_img is not None:
            qr_img.hAlign = "RIGHT"
            invoice_bits.extend([Spacer(1, 1), qr_img])
            invoice_bits.append(Paragraph(
                "Scan to pay" if self.upi_intent_url(data) else "Invoice QR",
                ParagraphStyle("C6QrCaption", parent=tiny_r, fontSize=4.8, leading=5.2),
            ))
        header = Table(
            [[company_bits, invoice_bits]],
            colWidths=[content_w * 0.62, content_w * 0.38],
        )
        header.hAlign = "LEFT"
        header.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.extend([header, Paragraph("Tax Invoice", title)])

        place = data.get("place_of_supply") or "—"
        if data.get("place_of_supply_code"):
            place = f"{place} ({data['place_of_supply_code']})"
        party_heading = (
            "Supplier" if str(data.get("voucher_type") or "").upper() == "PURCHASE"
            else "Customer / Bill To"
        )
        party_lines = [
            f"<b>{party_heading}:</b> {text(data.get('customer_name'))}",
            f"<b>Address:</b> {text(data.get('billing_address'))}",
            f"<b>Mobile:</b> {text(data.get('contact_mobile'))}"
            f" &nbsp; <b>Email:</b> {text(data.get('contact_email'))}",
            f"<b>GSTIN:</b> {text(data.get('customer_gstin'))}"
            f" &nbsp; <b>Place of Supply:</b> {text(place)}",
            f"<b>Contact:</b> {text(data.get('contact_person'))}"
            f" &nbsp; <b>Reverse Charge:</b> {'Yes' if data.get('reverse_charge') else 'No'}",
        ]
        party_box = Table([[Paragraph("<br/>".join(party_lines), tiny)]], colWidths=[content_w])
        party_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF4EB")),
            ("BOX", (0, 0), (-1, -1), 0.35, colors.HexColor("#D7E0EA")),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.extend([party_box, Spacer(1, 3)])

        item_widths = [5 * mm, 34 * mm, 15 * mm, 11 * mm, 13 * mm, content_w - 78 * mm]
        item_rows = [[
            Paragraph("#", table_head), Paragraph("Item / Particulars", table_head),
            Paragraph("HSN / GST", table_head), Paragraph("Qty", table_head),
            Paragraph("Rate", table_head), Paragraph("Taxable / Disc", table_head),
        ]]
        for line in data.get("lines") or []:
            hsn_html = (
                f"<b>HSN</b> {text(line.get('hsn_sac'))}<br/>"
                f"<b>GST</b> {self._fmt(line.get('gst_rate_percent'))}%"
            )
            amount_html = (
                f"<b>{self._fmt(line.get('taxable_value'))}</b><br/>"
                f"Disc: {self._fmt(line.get('discount_amount'))}"
            )
            item_rows.append([
                Paragraph(text(line.get("sr_no")), table_cell),
                self._particulars_paragraph(
                    line, table_cell, bill_source=data.get("bill_source") or ""
                ),
                Paragraph(hsn_html, table_cell),
                Paragraph(
                    f"{self._fmt(line.get('qty'))}<br/>{text(line.get('unit'))}", table_cell
                ),
                Paragraph(self._fmt(line.get("rate")), table_cell_r),
                Paragraph(amount_html, table_cell_r),
            ])
        item_table = Table(item_rows, colWidths=item_widths, repeatRows=1)
        item_table.hAlign = "LEFT"
        item_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B2545")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#7B8794")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 1.5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 1.5),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.extend([item_table, Spacer(1, 3)])

        round_off = float(data.get("round_off") or 0)
        if abs(round_off) < 0.005:
            round_off = 0.0
        single_item = len(data.get("lines") or []) == 1
        show_round_off = abs(round_off) >= 0.005
        totals_rows = []
        if not single_item:
            totals_rows.append(["List Price", self._fmt(data.get("list_price"))])
        totals_rows.extend([
            ["Discount", self._fmt(data.get("discount_amount"))],
            ["Taxable Value", self._fmt(data.get("taxable_value"))],
        ])
        if data.get("tax_type") == "CGST_SGST":
            totals_rows.extend([
                [f"CGST @ {self._fmt(data.get('cgst_rate'))}%", self._fmt(data.get("cgst_amount"))],
                [f"SGST @ {self._fmt(data.get('sgst_rate'))}%", self._fmt(data.get("sgst_amount"))],
            ])
        else:
            totals_rows.append([
                f"IGST @ {self._fmt(data.get('igst_rate'))}%", self._fmt(data.get("igst_amount"))
            ])
        if show_round_off:
            totals_rows.append([
                "Round off", f"{'+' if round_off >= 0 else '-'}{self._fmt(abs(round_off))}"
            ])
        totals_rows.append(["Invoice Value", self._fmt(data.get("invoice_value"))])
        if single_item:
            one_row_style = ParagraphStyle(
                "C6OneItemTotals", parent=tiny, fontSize=4.5, leading=5.2,
                alignment=TA_CENTER,
            )
            one_row = [[
                Paragraph(
                    f"<b>{text(label)}</b><br/>{'<b>' + text(value) + '</b>' if label == 'Invoice Value' else text(value)}",
                    one_row_style,
                )
                for label, value in totals_rows
            ]]
            totals = Table(one_row, colWidths=[content_w / len(totals_rows)] * len(totals_rows))
            totals.hAlign = "LEFT"
            totals.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#AAB7C4")),
                ("BACKGROUND", (-1, 0), (-1, 0), colors.HexColor("#FFF0E5")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 1.2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 1.2),
                ("TOPPADDING", (0, 0), (-1, -1), 1.2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
            ]))
        else:
            totals_data = [
                [Paragraph(text(label), tiny_b), Paragraph(text(value), tiny_r)]
                for label, value in totals_rows
            ]
            totals = Table(totals_data, colWidths=[content_w * 0.64, content_w * 0.36])
            totals.hAlign = "RIGHT"
            totals.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#AAB7C4")),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#FFF0E5")),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 1.2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
            ]))
        story.append(totals)
        story.append(Paragraph(
            f"<b>In Words:</b> {text(data.get('amount_in_words'))}",
            ParagraphStyle("C6Words", parent=tiny, fontSize=5.4, leading=6.2, spaceBefore=2),
        ))

        if banks:
            bank_columns = []
            for bank in banks[:2]:
                bank_columns.append(Paragraph(
                    "<b>Bank:</b> " + text(bank.get("bank_name")) + "<br/>"
                    "<b>A/c:</b> " + text(bank.get("account_number")) + "<br/>"
                    "<b>IFSC:</b> " + text(bank.get("ifsc_code")) + "<br/>"
                    "<b>Branch:</b> " + text(bank.get("branch_name")) + "<br/>"
                    "<b>UPI:</b> " + text(bank.get("upi_id")),
                    tiny,
                ))
            while len(bank_columns) < 2:
                bank_columns.append(Paragraph("", tiny))
            bank_box = Table([[bank_columns[0], bank_columns[1]]], colWidths=[content_w / 2] * 2)
            bank_box.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E8F3FC")),
                ("BOX", (0, 0), (-1, -1), 0.3, colors.HexColor("#D7E0EA")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            story.extend([Spacer(1, 3), bank_box])

        stamp_path = self._static_img_path("jtcs_invoice_stamp.png")
        sign_path = self._static_img_path("jtcs_invoice_sign.png")
        sign_flow: Flowable | str = ""
        if stamp_path:
            sign_flow = _StampWithSignature(
                str(stamp_path), str(sign_path) if sign_path else None, 12 * mm
            )
        elif sign_path:
            sign_flow = Image(str(sign_path), width=16 * mm, height=7 * mm, mask="auto")
        signature = Table(
            [[Paragraph(f"for {text(company.get('name'))}", tiny_r), sign_flow]],
            colWidths=[content_w - 19 * mm, 19 * mm],
        )
        signature.setStyle(TableStyle([
            ("ALIGN", (0, 0), (0, 0), "RIGHT"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.extend([
            Spacer(1, 2), signature,
            Paragraph("<b>Terms:</b> All disputes subject to Haldwani / Nainital jurisdiction.", tiny),
            Paragraph(
                text(company.get("website") or "") + " | " + text(company.get("email") or "")
                + " | " + text(company.get("phone") or ""),
                ParagraphStyle("C6Foot", parent=tiny, alignment=TA_CENTER, fontSize=4.8, leading=5.2),
            ),
        ])

        paid = self._invoice_is_paid(data)
        paid_details = self.paid_stamp_details(data) if paid else {"date": "", "account": ""}

        def draw_paid_stamp(canvas, _document):
            if not paid:
                return
            page_width, page_height = C6
            canvas.saveState()
            canvas.translate(page_width / 2, page_height - 19 * mm)
            canvas.rotate(25)
            canvas.setFillColor(colors.HexColor("#b42318"))
            canvas.setFont("Helvetica-Bold", 12)
            canvas.drawCentredString(0, 0, "PAID")
            canvas.setFont("Helvetica-Bold", 5)
            canvas.drawCentredString(
                0, -7, f"DOP: {self._display_date(paid_details.get('date') or '') or '—'}"
            )
            canvas.drawCentredString(0, -13, f"Account No: {paid_details.get('account') or '—'}")
            canvas.restoreState()

        doc.build(story, onFirstPage=draw_paid_stamp)
        return buffer.getvalue()

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

        banks = self._banks_for_pdf(data)
        right_bank = banks[0] if banks else None
        left_bank = banks[1] if len(banks) > 1 else None
        qr_bank = next(
            (bank for bank in banks if (bank.get("upi_id") or "").strip()),
            None,
        )
        if qr_bank:
            data = {
                **data,
                "pay_upi_id": qr_bank.get("upi_id") or "",
                "pay_bank_name": qr_bank.get("bank_name") or "",
                "pay_account_holder": qr_bank.get("account_holder_name") or "",
            }
        invoice_no = str(data.get("invoice_no") or "")
        qr_side = 25 * mm
        right_w = content_w * 0.38
        right_rows = [
            [
                Paragraph(
                    f"Invoice Value: <b>Rs. {self._fmt(data['invoice_value'])}</b>",
                    small_r,
                )
            ],
            [Paragraph(f"Invoice No: <b>{invoice_no}</b>", small_r)],
            [
                Paragraph(
                    f"Invoice Date: <b>{self._display_date(data['invoice_date'])}</b>",
                    small_r,
                )
            ],
        ]
        qr_img = self._upi_qr_image(data, qr_side)
        if qr_img is not None:
            qr_img.hAlign = "RIGHT"
            right_rows.append([Spacer(1, 1)])
            right_rows.append([qr_img])
            right_rows.append(
                [
                    Paragraph(
                        "Scan to pay" if self.upi_intent_url(data) else "Invoice details QR · not a payment QR",
                        ParagraphStyle("QrCaption", parent=small_r, fontSize=7, leading=9),
                    )
                ]
            )
        right_col = Table(right_rows, colWidths=[right_w])
        right_col.hAlign = "RIGHT"
        right_col.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )

        header_table = Table(
            [[left_col, right_col]],
            colWidths=[content_w * 0.62, right_w],
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

        party_heading = (
            "Supplier"
            if str(data.get("voucher_type") or "").upper() == "PURCHASE"
            else "Customer / Bill To"
        )
        cust_left = [
            Paragraph(f"<b>{party_heading}:</b> {data['customer_name']}", small),
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

        item_head = ParagraphStyle(
            "ItemHead",
            parent=cell,
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9,
            textColor=colors.white,
        )
        table_data = [
            [
                Paragraph("Sr.", item_head),
                Paragraph("Particulars", item_head),
                Paragraph("HSN / SAC", item_head),
                Paragraph("Unit(s)", item_head),
                Paragraph("Rate", item_head),
                Paragraph("Discount", item_head),
                Paragraph("Taxable Value", item_head),
            ]
        ]
        for line in data.get("lines") or []:
            hsn = line.get("hsn_sac") or ""
            table_data.append(
                [
                    Paragraph(str(line.get("sr_no") or ""), cell),
                    self._particulars_paragraph(
                        line, cell, bill_source=data.get("bill_source") or ""
                    ),
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
        if abs(round_off) < 0.005:
            round_off = 0.0
        single_item = len(data.get("lines") or []) == 1
        show_round_off = abs(round_off) >= 0.005
        round_txt = f"{'+' if round_off >= 0 else '-'}{self._fmt(abs(round_off))}"
        if single_item:
            metric_cells = [
                ("Discount", self._fmt(data["discount_amount"])),
                ("Taxable Value", self._fmt(data["taxable_value"])),
            ]
            if data.get("tax_type") == "CGST_SGST":
                metric_cells.extend([
                    (f"CGST @ {self._fmt(data['cgst_rate'])}%", self._fmt(data["cgst_amount"])),
                    (f"SGST @ {self._fmt(data['sgst_rate'])}%", self._fmt(data["sgst_amount"])),
                ])
            else:
                metric_cells.append(
                    (f"IGST @ {self._fmt(data['igst_rate'])}%", self._fmt(data["igst_amount"]))
                )
            if show_round_off:
                metric_cells.append(("Round off", round_txt))
            metric_cells.append(("Invoice Value", self._fmt(data["invoice_value"])))
            single_cell = ParagraphStyle(
                "TotOneRow", parent=cell, fontSize=7, leading=9, alignment=TA_CENTER,
            )
            totals = Table(
                [[
                    Paragraph(
                        f"<b>{label}</b><br/>{'<b>' + value + '</b>' if label == 'Invoice Value' else value}",
                        single_cell,
                    )
                    for label, value in metric_cells
                ]],
                colWidths=[content_w / len(metric_cells)] * len(metric_cells),
            )
            totals.hAlign = "LEFT"
            last_col = len(metric_cells) - 1
            totals.setStyle(TableStyle([
                ("BACKGROUND", (last_col, 0), (last_col, 0), colors.HexColor("#FFF4EB")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#5D6D7E")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ]))
        elif data.get("tax_type") == "CGST_SGST":
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
        if not single_item:
            if show_round_off:
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

        if right_bank:
            small_l = ParagraphStyle("BankL", parent=small, alignment=TA_LEFT)
            small_bank_r = ParagraphStyle("BankR", parent=small, alignment=TA_RIGHT)

            def bank_lines(bank: dict | None, style) -> list:
                if not bank:
                    return [Paragraph("", style)]
                return [
                    Paragraph("<b>Bank Details</b>", style),
                    Paragraph(f"<b>Bank:</b> {bank.get('bank_name') or '—'}", style),
                    Paragraph(
                        f"<b>A/c No:</b> {bank.get('account_number') or '—'}",
                        style,
                    ),
                    Paragraph(f"<b>IFSC:</b> {bank.get('ifsc_code') or '—'}", style),
                    Paragraph(f"<b>Branch:</b> {bank.get('branch_name') or '—'}", style),
                    Paragraph(
                        f"<b>Holder:</b> {bank.get('account_holder_name') or '—'}",
                        style,
                    ),
                    Paragraph(f"<b>UPI:</b> {bank.get('upi_id') or '—'}", style),
                ]

            # One account stays on the right. Two accounts: second on the left, first on the right.
            pay_table = Table(
                [[bank_lines(left_bank, small_l), bank_lines(right_bank, small_bank_r)]],
                colWidths=[content_w * 0.50, content_w * 0.50],
            )
            pay_table.hAlign = "LEFT"
            pay_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E8F3FC")),
                        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#D7E0EA")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("ALIGN", (0, 0), (0, 0), "LEFT"),
                        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ]
                )
            )
            story.append(pay_table)
            story.append(Spacer(1, 8))
        else:
            story.append(Spacer(1, 8))

        story.append(Paragraph(f"for {company['name']}", ParagraphStyle("SignFor", parent=small, alignment=TA_RIGHT)))
        stamp_path = self._static_img_path("jtcs_invoice_stamp.png")
        sign_path = self._static_img_path("jtcs_invoice_sign.png")
        stamp_size = 32 * mm
        sign_flow: Flowable | str = ""
        if stamp_path:
            sign_flow = _StampWithSignature(
                str(stamp_path),
                str(sign_path) if sign_path else None,
                stamp_size,
            )
        elif sign_path:
            sign_flow = Image(str(sign_path), width=38 * mm, height=16 * mm, mask="auto")
        sign_label = Paragraph(
            "<b>Authorised Signatory</b>",
            ParagraphStyle("SignLab", parent=small, alignment=TA_CENTER),
        )
        sign_table = Table(
            [[sign_flow], [sign_label]],
            colWidths=[stamp_size],
        )
        sign_table.hAlign = "RIGHT"
        sign_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (0, 0), 0),
                    ("TOPPADDING", (0, 1), (0, 1), 1),
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

        paid = self._invoice_is_paid(data)
        paid_details = self.paid_stamp_details(data) if paid else {"date": "", "account": ""}

        def draw_paid_stamp(canvas, _document):
            if not paid:
                return
            page_width, page_height = A4
            canvas.saveState()
            canvas.translate(page_width / 2, page_height - 42 * mm)
            canvas.rotate(35)
            canvas.setFillColor(colors.HexColor("#b42318"))
            canvas.setFont("Helvetica-Bold", 24)
            canvas.drawCentredString(0, -8, "PAID")
            canvas.setFont("Helvetica-Bold", 8)
            canvas.drawCentredString(
                0,
                -21,
                f"DOP: {self._display_date(paid_details.get('date') or '') or '—'}",
            )
            canvas.drawCentredString(
                0,
                -32,
                f"Account No: {paid_details.get('account') or '—'}",
            )
            canvas.restoreState()

        doc.build(story, onFirstPage=draw_paid_stamp)
        return buffer.getvalue()

    @staticmethod
    def _invoice_is_paid(data: dict) -> bool:
        received = data.get("payment_received")
        if isinstance(received, str):
            received = received.strip().lower() in {"1", "true", "yes", "on"}
        return (
            bool(received)
            or str(data.get("payment_status") or "").strip().lower() == "paid"
        )

    @staticmethod
    def _display_date(iso_date: str) -> str:
        if not iso_date or len(iso_date) < 10:
            return iso_date or ""
        y, m, d = iso_date[:10].split("-")
        return f"{d}-{m}-{y}"
