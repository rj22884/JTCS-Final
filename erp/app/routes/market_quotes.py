"""Live market index quotes for the header ticker."""

from flask import Blueprint, jsonify, request

from app.decorators import login_required
from app.services.market_quote_service import get_quotes

bp = Blueprint("market_quotes", __name__, url_prefix="/api/market")


@bp.route("/quotes", methods=["GET"], strict_slashes=False)
@login_required
def quotes():
    force = (request.args.get("force") or "").strip() in {"1", "true", "yes"}
    try:
        data = get_quotes(force=force)
    except Exception as exc:
        return jsonify({"ok": False, "live": False, "error": str(exc), "indices": []}), 502
    return jsonify(data)
