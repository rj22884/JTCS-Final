"""Sale-amount UPI QR only. Isolated from stamp save/OCR/calculation."""

from __future__ import annotations

import io
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

try:
    import qrcode
except Exception:  # pragma: no cover
    qrcode = None  # type: ignore

STAMP_UPI_ID = "rajn8755396@barodampay"
STAMP_UPI_PN = "JTCS"


def parse_sale_amount(raw) -> Decimal:
    try:
        amount = Decimal(str(raw or "").strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Enter a valid Sale Amount.") from exc
    if amount <= 0:
        raise ValueError("Sale Amount must be greater than zero.")
    return amount.quantize(Decimal("0.01"))


def sale_amount_upi_uri(amount: Decimal) -> str:
    params = {
        "pa": STAMP_UPI_ID,
        "pn": STAMP_UPI_PN,
        "am": f"{amount:.2f}",
        "cu": "INR",
        "tn": "Stamp Sale",
    }
    return "upi://pay?" + urlencode(params)


def sale_amount_upi_qr_png(amount: Decimal) -> bytes:
    if qrcode is None:
        raise RuntimeError("QR library is not available.")
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=14, border=2)
    qr.add_data(sale_amount_upi_uri(amount))
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    return bio.getvalue()
