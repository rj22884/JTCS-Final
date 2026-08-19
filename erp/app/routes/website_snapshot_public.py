"""Business Snapshot API for the JTCS website. Requires existing ERP session."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.decorators import login_required
from app.extensions import db
from app.services.website_snapshot_service import WebsiteSnapshotService

bp = Blueprint("website_snapshot_public", __name__, url_prefix="/api/public/snapshot")

# Exact trusted origins only. Never "*". CORS is not authentication.
_ALLOWED_ORIGINS = {
    "https://jtcsxpert.com",
    "https://www.jtcsxpert.com",
    "https://app.jtcsxpert.com",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
}


def _cors(response):
    origin = (request.headers.get("Origin") or "").strip()
    if origin in _ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Accept, Content-Type"
        response.headers["Vary"] = "Origin"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@bp.after_request
def snapshot_cors(response):
    return _cors(response)


@bp.route("", methods=["OPTIONS"], strict_slashes=False)
def snapshot_options():
    return ("", 204)


@bp.route("", methods=["GET"], strict_slashes=False)
@login_required
def snapshot():
    try:
        payload = WebsiteSnapshotService().get_snapshot()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.warning("Business snapshot failed: %s", exc)
        return jsonify({"ok": False}), 500
    return jsonify(payload)
