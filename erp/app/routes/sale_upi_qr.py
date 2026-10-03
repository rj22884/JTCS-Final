"""Standalone UPI QR image for stamp Sale Amount. Does not save stamp records."""

from flask import Blueprint, Response, request

from app.decorators import login_required
from app.services.sale_upi_qr_service import parse_sale_amount, sale_amount_upi_qr_png

bp = Blueprint("sale_upi_qr", __name__)


@bp.route("/api/sale-upi-qr", methods=["GET"], strict_slashes=False)
@login_required
def sale_upi_qr():
    try:
        amount = parse_sale_amount(request.args.get("amount"))
        png = sale_amount_upi_qr_png(amount)
    except ValueError as exc:
        return Response(str(exc), status=400, mimetype="text/plain")
    except Exception:
        return Response("Unable to generate QR.", status=500, mimetype="text/plain")
    return Response(png, mimetype="image/png", headers={"Cache-Control": "no-store"})
