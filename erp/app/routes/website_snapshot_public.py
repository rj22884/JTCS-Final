"""Public Business Snapshot for the JTCS marketing login page. No login. CSRF exempt."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from flask import Blueprint, current_app, jsonify, request

from app.extensions import db
from app.services.website_snapshot_service import WebsiteSnapshotService

bp = Blueprint("website_snapshot_public", __name__, url_prefix="/api/public/snapshot")

_ALLOWED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "jtcsxpert.com",
    "www.jtcsxpert.com",
    "app.jtcsxpert.com",
    "::1",
}


def _cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = (
        "Accept, Content-Type, Cache-Control, Pragma, X-Requested-With"
    )
    response.headers["Access-Control-Max-Age"] = "86400"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


def _origin_allowed() -> bool:
    raw = (request.headers.get("Origin") or request.headers.get("Referer") or "").strip()
    if not raw or raw.lower() == "null":
        return True
    try:
        host = (urlparse(raw).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return True
    if host in _ALLOWED_HOSTS:
        return True
    if host.endswith(".jtcsxpert.com") or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback or ip.is_private:
            return True
    except ValueError:
        pass
    return False


@bp.after_request
def snapshot_public_cors(response):
    return _cors(response)


@bp.route("", methods=["GET", "OPTIONS"], strict_slashes=False)
def snapshot():
    if request.method == "OPTIONS":
        return ("", 204)
    if not _origin_allowed():
        return jsonify({"ok": False}), 403
    try:
        payload = WebsiteSnapshotService().get_snapshot()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.warning("Public business snapshot failed: %s", exc)
        return jsonify({"ok": False}), 200
    return jsonify(payload)
