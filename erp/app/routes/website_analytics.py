"""Admin Website Analytics — /admin/website-analytics."""

from __future__ import annotations

import io
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, send_file, session, url_for

from app.decorators import admin_required, login_required
from app.extensions import db
from app.services.menu_service import MenuService
from app.services.website_analytics_service import WebsiteAnalyticsService
from app.utils.db_session import map_db_exception
from app.whats_new import publish_whats_new

bp = Blueprint("website_analytics", __name__, url_prefix="/admin/website-analytics")

MENU_PATH = "/admin/website-analytics"
_BOOTSTRAPPED = False


def ensure_website_analytics_bootstrap() -> None:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    WebsiteAnalyticsService().ensure_schema()
    try:
        publish_whats_new(
            "feature:website_analytics",
            "Website Analytics",
            detail="Admin Role → visitor statistics from the public JTCS website.",
            url=MENU_PATH,
            badge="New",
        )
    except Exception:
        db.session.rollback()
    _BOOTSTRAPPED = True


def _parse_date(raw: str | None):
    value = (raw or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _period_from_request():
    return WebsiteAnalyticsService.resolve_period(
        request.args.get("period") or request.args.get("preset"),
        _parse_date(request.args.get("date_from") or request.args.get("from")),
        _parse_date(request.args.get("date_to") or request.args.get("to")),
    )


@bp.route("", methods=["GET"], strict_slashes=False)
@bp.route("/", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def index():
    try:
        ensure_website_analytics_bootstrap()
    except Exception:
        db.session.rollback()
    date_from, date_to, preset = _period_from_request()
    try:
        data = WebsiteAnalyticsService().dashboard(date_from=date_from, date_to=date_to)
    except Exception:
        db.session.rollback()
        data = {
            "cards": {},
            "trend": [],
            "devices": [],
            "browsers": [],
            "operating_systems": [],
            "sources": [],
            "pages": [],
            "recent": [],
            "active_window_minutes": 5,
        }
    return render_template(
        "website_analytics/index.html",
        page_title="Website Analytics",
        breadcrumb=MenuService().get_breadcrumb(MENU_PATH, session.get("role")),
        data=data,
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        period_preset=preset,
        summary_url=url_for("website_analytics.summary"),
        export_url=url_for("website_analytics.export", fmt="csv"),
    )


@bp.route("/api/summary", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def summary():
    try:
        ensure_website_analytics_bootstrap()
        date_from, date_to, preset = _period_from_request()
        data = WebsiteAnalyticsService().dashboard(date_from=date_from, date_to=date_to)
        return jsonify(
            {
                "ok": True,
                "period": preset,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                **data,
            }
        )
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": map_db_exception(exc) or str(exc)}), 500


@bp.route("/api/export/<string:fmt>", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def export(fmt: str):
    try:
        ensure_website_analytics_bootstrap()
        date_from, date_to, _preset = _period_from_request()
        content, filename, mime = WebsiteAnalyticsService().export(
            fmt=fmt, date_from=date_from, date_to=date_to
        )
        return send_file(
            io.BytesIO(content),
            mimetype=mime,
            as_attachment=True,
            download_name=filename,
        )
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": map_db_exception(exc) or str(exc)}), 500
