from __future__ import annotations

import io
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from app.utils.number_words import amount_in_words_rupees

STATIC_IMG = Path(__file__).resolve().parent.parent / "static" / "img"
WATERMARK_PATH = STATIC_IMG / "thank_you_watermark.png"
BLUE = (30, 136, 229)
RED = (200, 30, 30)

CONTACT_SERVICES = [
    "Web Designing",
    "Database Management",
    "Income Tax Return (ITR)",
    "GST Registration & Return",
    "Digital Signature Certificate (DSC)",
    "TDS Return Filing",
    "Accounting & Bookkeeping",
    "Project Reports",
    "MSME Consultancy",
    "E-Stamp / E-Court Fee",
    "CSC Related Services",
    "Uttarakhand Apuni Sarkar Documents",
    "Government Card Printing",
    "Share Market Trading Adviser",
]

BODY_PARAGRAPHS = [
    (
        "We appreciate your timely action and support. Your payment has been successfully "
        "recorded, and everything is now updated from our side. If you have any questions "
        "or need assistance, we are always here to help."
    ),
    "Thank you once again for choosing our services.",
]


class ThankYouLetterService:
    @staticmethod
    def _load_font(size: int, *, bold: bool = False):
        candidates = []
        if bold:
            candidates.extend([
                "C:/Windows/Fonts/arialbd.ttf",
                "C:/Windows/Fonts/segoeuib.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            ])
        candidates.extend([
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ])
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
    def _wrap_text(
        cls,
        draw: ImageDraw.ImageDraw,
        text: str,
        *,
        font,
        max_width: int,
    ) -> list[str]:
        words = text.split()
        if not words:
            return []
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if cls._text_width(draw, candidate, font) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    @staticmethod
    def format_payment_account(payment_account: str | None) -> str:
        text = (payment_account or "").strip()
        if text.lower() == "cash" or text.upper() == "CASH":
            return "Cash"
        if text in {"—", "-", "–"}:
            return "Cash"
        return text or "—"

    @classmethod
    def _draw_header(cls, draw: ImageDraw.ImageDraw, width: int) -> int:
        draw.rectangle((0, 0, width, 110), fill=BLUE)
        title_font = cls._load_font(34, bold=True)
        sub_font = cls._load_font(22, bold=True)
        draw.text((width // 2, 34), "JTCS", fill="white", font=title_font, anchor="mm")
        draw.text((width // 2, 76), "THANK YOU LETTER", fill="white", font=sub_font, anchor="mm")
        return 130

    @classmethod
    def _paste_watermark(cls, canvas: Image.Image) -> None:
        if not WATERMARK_PATH.exists():
            return
        wm = Image.open(WATERMARK_PATH).convert("RGBA")
        wm = ImageOps.fit(
            wm,
            (canvas.width, canvas.height),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.45),
        )
        alpha = wm.split()[3].point(lambda p: int(p * 0.12))
        wm.putalpha(alpha)
        canvas.paste(wm, (0, 0), wm)

    @classmethod
    def _draw_payment_table(
        cls,
        draw: ImageDraw.ImageDraw,
        *,
        left: int,
        width: int,
        y: int,
        payment_account: str,
        amount_text: str,
        invoice_no: str,
        bill_date_text: str,
    ) -> int:
        table_width = width - (left * 2)
        row_height = 46
        header_height = 42
        headers = ["Payment Account no", "Payment amount", "Bill no", "Bill Date"]
        values = [
            cls.format_payment_account(payment_account),
            amount_text,
            invoice_no or "—",
            bill_date_text,
        ]
        col_width = table_width // 4
        header_font = cls._load_font(20, bold=True)
        cell_font = cls._load_font(20)

        draw.rectangle((left, y, left + table_width, y + header_height), fill=BLUE)
        for index, header in enumerate(headers):
            col_left = left + (index * col_width)
            col_center = col_left + (col_width // 2)
            draw.text(
                (col_center, y + (header_height // 2)),
                header,
                fill="white",
                font=header_font,
                anchor="mm",
            )

        row_top = y + header_height
        draw.rectangle((left, row_top, left + table_width, row_top + row_height), outline=BLUE, width=2)
        for index in range(1, 4):
            x = left + (index * col_width)
            draw.line((x, row_top, x, row_top + row_height), fill=BLUE, width=2)

        for index, value in enumerate(values):
            col_left = left + (index * col_width)
            col_center = col_left + (col_width // 2)
            draw.text(
                (col_center, row_top + (row_height // 2)),
                value,
                fill="black",
                font=cell_font,
                anchor="mm",
            )

        return row_top + row_height + 18

    @classmethod
    def _draw_wrapped_paragraph(
        cls,
        draw: ImageDraw.ImageDraw,
        *,
        text: str,
        x: int,
        y: int,
        max_width: int,
        font,
        fill,
        line_gap: int = 34,
    ) -> int:
        for line in cls._wrap_text(draw, text, font=font, max_width=max_width):
            draw.text((x, y), line, fill=fill, font=font)
            y += line_gap
        return y

    @classmethod
    def _draw_contact_footer(
        cls,
        draw: ImageDraw.ImageDraw,
        *,
        width: int,
        left: int,
        content_width: int,
        start_y: int,
    ) -> None:
        blue_font = cls._load_font(24, bold=True)
        small_font = cls._load_font(22)
        bullet_font = cls._load_font(16, bold=True)
        title = "Contact Also For"
        title_width = cls._text_width(draw, title, blue_font)
        title_x = width // 2
        title_y = start_y
        line_gap = 18
        draw.text((title_x, title_y), title, fill=BLUE, font=blue_font, anchor="mm")
        line_y = title_y
        draw.line((left, line_y, title_x - (title_width // 2) - line_gap, line_y), fill=BLUE, width=2)
        draw.line(
            (title_x + (title_width // 2) + line_gap, line_y, width - left, line_y),
            fill=BLUE,
            width=2,
        )

        service_y = title_y + 42
        col_gap = 36
        col_width = (content_width - col_gap) // 2
        left_col_x = left
        right_col_x = left + col_width + col_gap
        split_at = 7

        for index, item in enumerate(CONTACT_SERVICES):
            column_x = left_col_x if index < split_at else right_col_x
            row_index = index if index < split_at else index - split_at
            item_y = service_y + (row_index * 30)
            draw.text((column_x, item_y + 2), "◆", fill=BLUE, font=bullet_font)
            draw.text((column_x + 22, item_y), item, fill="black", font=small_font)

    @classmethod
    def generate_jpg(
        cls,
        *,
        customer_name: str,
        amount,
        bill_date: date | None,
        invoice_no: str,
        payment_account: str | None = None,
        payment_note: str | None = None,
    ) -> bytes:
        width, height = 1240, 1754
        canvas = Image.new("RGB", (width, height), "white")
        cls._paste_watermark(canvas)
        draw = ImageDraw.Draw(canvas)
        y = cls._draw_header(draw, width)

        body_font = cls._load_font(24)
        bold_font = cls._load_font(26, bold=True)
        table_note_font = cls._load_font(22, bold=True)

        left = 70
        content_width = width - (left * 2)
        display_date = (bill_date or date.today()).strftime("%d/%m/%Y")
        try:
            amount_val = float(amount or 0)
        except (TypeError, ValueError):
            amount_val = 0
        amount_display = f"{amount_val:,.0f}"
        words = amount_in_words_rupees(amount_val)

        draw.text((left, y), f"Dear {customer_name or 'Customer'},", fill="black", font=bold_font)
        y += 44
        thanks_line = (
            "Thank you very much for your payment."
            if (payment_note or "").strip()
            else "Thank you very much for completing your payment."
        )
        draw.text(
            (left, y),
            thanks_line,
            fill="black",
            font=body_font,
        )
        y += 40

        y = cls._draw_payment_table(
            draw,
            left=left,
            width=width,
            y=y,
            payment_account=payment_account,
            amount_text=amount_display,
            invoice_no=invoice_no or "—",
            bill_date_text=display_date,
        )

        amount_line = f"({words}) Dated {display_date}"
        draw.text((left, y), amount_line, fill=BLUE, font=table_note_font)
        y += 36
        note = (payment_note or "").strip()
        if note:
            draw.text((left, y), note, fill=RED, font=table_note_font)
            y += 36
        else:
            y += 6

        for paragraph in BODY_PARAGRAPHS:
            y = cls._draw_wrapped_paragraph(
                draw,
                text=paragraph,
                x=left,
                y=y,
                max_width=content_width,
                font=body_font,
                fill="black",
                line_gap=34,
            )
            y += 8

        y += 6
        draw.text((left, y), "Warm Regards,", fill="black", font=body_font)
        y += 34
        draw.text(
            (left, y),
            "Joshi Tax Consultancy & Services (JTCS)",
            fill="black",
            font=bold_font,
        )

        footer_y = max(y + 90, 980)
        cls._draw_contact_footer(
            draw,
            width=width,
            left=left,
            content_width=content_width,
            start_y=footer_y,
        )

        buf = io.BytesIO()
        canvas.save(buf, format="JPEG", quality=92)
        return buf.getvalue()

    @classmethod
    def generate_png(cls, **kwargs) -> bytes:
        jpg_bytes = cls.generate_jpg(**kwargs)
        img = Image.open(io.BytesIO(jpg_bytes)).convert("RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
