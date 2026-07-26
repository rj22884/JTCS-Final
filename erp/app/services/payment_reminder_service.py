from __future__ import annotations

import io
import urllib.parse
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

try:
    import qrcode
except ImportError:  # pragma: no cover
    qrcode = None  # type: ignore

STATIC_IMG = Path(__file__).resolve().parent.parent / "static" / "img"

NAVY = (12, 28, 68)
NAVY_DEEP = (8, 20, 52)
NAVY_CARD = (20, 40, 92)
GOLD = (212, 175, 55)
GOLD_SOFT = (232, 205, 120)
WHITE = (255, 255, 255)
MUTED = (190, 205, 230)
ROW_LINE = (45, 70, 120)


class PaymentReminderService:
    """Generate a professional English payment-reminder PNG for ITR followup."""

    @staticmethod
    def _load_font(size: int, *, bold: bool = False):
        candidates: list[str] = []
        if bold:
            candidates.extend(
                [
                    "C:/Windows/Fonts/arialbd.ttf",
                    "C:/Windows/Fonts/segoeuib.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                ]
            )
        candidates.extend(
            [
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/segoeui.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]
        )
        for path in candidates:
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
        return ImageFont.load_default()

    @staticmethod
    def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]

    @classmethod
    def _center_text(
        cls,
        draw: ImageDraw.ImageDraw,
        *,
        y: int,
        text: str,
        font,
        fill,
        width: int,
    ) -> None:
        draw.text((width // 2, y), text, fill=fill, font=font, anchor="mm")

    @classmethod
    def _draw_ornament_line(cls, draw: ImageDraw.ImageDraw, *, y: int, width: int) -> None:
        margin = 80
        draw.line((margin, y, width - margin, y), fill=GOLD, width=2)
        draw.ellipse((margin - 4, y - 4, margin + 4, y + 4), fill=GOLD)
        draw.ellipse((width - margin - 4, y - 4, width - margin + 4, y + 4), fill=GOLD)

    @classmethod
    def _dash(cls, value: str | None, fallback: str = "—") -> str:
        text = (value or "").strip()
        return text if text else fallback

    @classmethod
    def _format_amount(cls, amount) -> str:
        try:
            value = float(amount or 0)
        except (TypeError, ValueError):
            value = 0.0
        if abs(value - round(value)) < 0.001:
            return f"₹ {int(round(value)):,}"
        return f"₹ {value:,.2f}"

    @classmethod
    def _format_date(cls, value: date | str | None) -> str:
        if value is None:
            return "—"
        if isinstance(value, date):
            return value.strftime("%d/%m/%Y")
        text = str(value).strip()
        if not text:
            return "—"
        try:
            return date.fromisoformat(text[:10]).strftime("%d/%m/%Y")
        except ValueError:
            return text

    @classmethod
    def _upi_payload(
        cls,
        *,
        upi_id: str,
        payee_name: str,
        amount,
        bill_no: str,
    ) -> str:
        upi = (upi_id or "").strip()
        if upi:
            try:
                am = f"{float(amount or 0):.2f}"
            except (TypeError, ValueError):
                am = "0.00"
            params = {
                "pa": upi,
                "pn": (payee_name or "JTCS").strip() or "JTCS",
                "am": am,
                "cu": "INR",
                "tn": (bill_no or "JTCS Bill").strip() or "JTCS Bill",
            }
            return "upi://pay?" + urllib.parse.urlencode(params)
        return (
            f"JTCS Payment Reminder | Bill: {(bill_no or '—').strip()} | "
            f"Amount: {cls._format_amount(amount)}"
        )

    @classmethod
    def _make_qr(cls, payload: str, box_size: int = 6) -> Image.Image | None:
        if not payload or qrcode is None:
            return None
        qr = qrcode.QRCode(version=None, box_size=box_size, border=2)
        qr.add_data(payload)
        qr.make(fit=True)
        return qr.make_image(fill_color="black", back_color="white").convert("RGBA")

    @classmethod
    def resolve_upi_payee(cls) -> tuple[str, str]:
        """Pick first active non-cash bank account that has a UPI ID."""
        from app.repositories.transaction_repository import MasterRepository

        for account in MasterRepository().list_active_bank_accounts():
            upi = (getattr(account, "UpiId", None) or "").strip()
            bank = (getattr(account, "BankName", None) or "").strip()
            if not upi:
                continue
            if bank.lower() == "cash":
                continue
            return upi, bank or "JTCS"
        return "", "JTCS"

    @classmethod
    def _draw_detail_rows(
        cls,
        draw: ImageDraw.ImageDraw,
        *,
        rows: list[tuple[str, str]],
        left: int,
        top: int,
        right: int,
        label_font,
        value_font,
        row_h: int = 52,
    ) -> int:
        y = top
        for index, (label, value) in enumerate(rows):
            draw.text((left, y + 14), label, fill=GOLD_SOFT, font=label_font)
            draw.text((left + 210, y + 12), value, fill=WHITE, font=value_font)
            y += row_h
            if index < len(rows) - 1:
                draw.line((left, y, right, y), fill=ROW_LINE, width=1)
        return y

    @classmethod
    def generate_png(
        cls,
        *,
        customer_name: str,
        bill_no: str,
        bill_date: date | str | None,
        work_date: date | str | None = None,
        period: str = "",
        work_type: str = "ITR",
        return_type: str = "",
        amount,
        upi_id: str = "",
        payee_name: str = "JTCS",
        # legacy alias kept for older callers
        work: str = "",
    ) -> bytes:
        width, height = 760, 1320
        canvas = Image.new("RGB", (width, height), NAVY)
        draw = ImageDraw.Draw(canvas)

        # Header / footer bands
        draw.rectangle((0, 0, width, 175), fill=NAVY_DEEP)
        draw.rectangle((0, height - 78, width, height), fill=GOLD)

        brand_font = cls._load_font(50, bold=True)
        title_font = cls._load_font(36, bold=True)
        body_font = cls._load_font(25)
        small_font = cls._load_font(20)
        label_font = cls._load_font(20, bold=True)
        value_font = cls._load_font(24, bold=True)
        amount_font = cls._load_font(32, bold=True)
        section_font = cls._load_font(18, bold=True)

        # Brand header
        cls._center_text(draw, y=42, text="JTCS", font=brand_font, fill=GOLD, width=width)
        cls._draw_ornament_line(draw, y=82, width=width)
        cls._center_text(
            draw,
            y=120,
            text="Payment Reminder",
            font=title_font,
            fill=GOLD,
            width=width,
        )
        cls._center_text(
            draw,
            y=155,
            text="Kindly clear the outstanding bill at the earliest",
            font=small_font,
            fill=MUTED,
            width=width,
        )

        name = cls._dash(customer_name, "Customer")
        y = 210
        draw.text((70, y), f"Dear {name},", fill=WHITE, font=body_font)
        y = 250
        draw.text(
            (70, y),
            "This is a polite reminder that payment for the details below is pending.",
            fill=MUTED,
            font=small_font,
        )

        # Resolve display fields
        work_type_text = cls._dash(work_type or "ITR")
        if return_type and return_type.strip():
            work_type_text = f"{work_type_text} ({return_type.strip()})"
        if work and not period and not work_type:
            # fallback if only combined work string was passed
            work_type_text = cls._dash(work)

        detail_rows = [
            ("Work Type:", work_type_text),
            ("Period:", cls._dash(period)),
            ("Work Date:", cls._format_date(work_date)),
            ("Bill Number:", cls._dash(bill_no)),
            ("Bill Date:", cls._format_date(bill_date)),
        ]

        # Details card
        card_top, card_bottom = 300, 720
        card = (50, card_top, width - 50, card_bottom)
        draw.rounded_rectangle(card, radius=20, outline=GOLD, width=2, fill=NAVY_CARD)
        draw.rounded_rectangle(
            (50, card_top, width - 50, card_top + 48),
            radius=20,
            fill=(28, 55, 118),
        )
        # flatten bottom corners of header strip
        draw.rectangle((50, card_top + 28, width - 50, card_top + 48), fill=(28, 55, 118))
        cls._center_text(
            draw,
            y=card_top + 24,
            text="BILL DETAILS",
            font=section_font,
            fill=GOLD_SOFT,
            width=width,
        )

        rows_end = cls._draw_detail_rows(
            draw,
            rows=detail_rows,
            left=80,
            top=card_top + 70,
            right=width - 80,
            label_font=label_font,
            value_font=value_font,
            row_h=54,
        )

        # Amount highlight
        amount_y = rows_end + 18
        draw.text((80, amount_y + 10), "Amount Due:", fill=GOLD_SOFT, font=label_font)
        amount_text = cls._format_amount(amount)
        pill_w = max(200, cls._text_width(draw, amount_text, amount_font) + 56)
        pill = (300, amount_y, 300 + pill_w, amount_y + 54)
        draw.rounded_rectangle(pill, radius=27, fill=GOLD)
        draw.text(
            ((pill[0] + pill[2]) // 2, (pill[1] + pill[3]) // 2),
            amount_text,
            fill=NAVY_DEEP,
            font=amount_font,
            anchor="mm",
        )

        # QR section
        qr_payload = cls._upi_payload(
            upi_id=upi_id,
            payee_name=payee_name,
            amount=amount,
            bill_no=bill_no,
        )
        qr_img = cls._make_qr(qr_payload, box_size=7)
        qr_top = 760
        if qr_img is not None:
            qr_size = 230
            qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.NEAREST)
            qr_x = (width - qr_size) // 2
            pad = 16
            draw.rounded_rectangle(
                (qr_x - pad, qr_top - pad, qr_x + qr_size + pad, qr_top + qr_size + pad),
                radius=18,
                fill=WHITE,
                outline=GOLD,
                width=2,
            )
            canvas.paste(qr_img, (qr_x, qr_top), qr_img)
            scan_y = qr_top + qr_size + 40
        else:
            scan_y = qr_top + 40
            cls._center_text(
                draw,
                y=scan_y,
                text="QR unavailable — please contact JTCS for payment details",
                font=small_font,
                fill=MUTED,
                width=width,
            )
            scan_y += 36

        cls._center_text(
            draw,
            y=scan_y,
            text="Scan QR to pay instantly",
            font=small_font,
            fill=GOLD_SOFT,
            width=width,
        )

        ask_y = scan_y + 48
        cls._center_text(
            draw,
            y=ask_y,
            text="Please make the payment at your earliest convenience.",
            font=body_font,
            fill=WHITE,
            width=width,
        )

        thanks_y = min(height - 120, ask_y + 58)
        cls._center_text(
            draw,
            y=thanks_y,
            text="Thank You",
            font=title_font,
            fill=GOLD,
            width=width,
        )
        cls._center_text(
            draw,
            y=height - 40,
            text="Joshi Tax Consultancy & Services",
            font=cls._load_font(18, bold=True),
            fill=NAVY_DEEP,
            width=width,
        )

        buf = io.BytesIO()
        canvas.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
