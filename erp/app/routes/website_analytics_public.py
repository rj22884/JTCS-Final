"""Public visitor ingest for the JTCS marketing website. No login. CSRF exempt."""

from __future__ import annotations

import ipaddress
import json
from urllib.parse import urlparse

from flask import Blueprint, current_app, request

from app.extensions import db
from app.services.website_analytics_service import WebsiteAnalyticsService

bp = Blueprint("website_analytics_public", __name__, url_prefix="/api/public/analytics")

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
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Accept, Content-Type"
    response.headers["Cache-Control"] = "no-store"
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


def _payload() -> dict:
    data = request.get_json(silent=True)
    if isinstance(data, dict):
        return data
    try:
        parsed = json.loads(request.get_data(as_text=True) or "{}")
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


@bp.after_request
def analytics_public_cors(response):
    return _cors(response)


@bp.route("/visit", methods=["POST", "OPTIONS"], strict_slashes=False)
def visit():
    if request.method == "OPTIONS":
        return ("", 204)
    if request.content_length and request.content_length > 4096:
        return ("", 204)
    if not _origin_allowed():
        return ("", 204)
    payload = _payload()
    ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()
    user_agent = (request.headers.get("User-Agent") or "")[:300]
    try:
        WebsiteAnalyticsService().ingest(
            payload,
            ip=ip,
            user_agent=user_agent,
            secret=str(current_app.config.get("SECRET_KEY") or ""),
        )
    except Exception as exc:
        db.session.rollback()
        current_app.logger.warning("Website analytics ingest failed: %s", exc)
    return ("", 204)
