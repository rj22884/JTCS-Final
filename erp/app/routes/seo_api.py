"""Public SEO keywords API for the JTCS website (no login required)."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.extensions import db
from app.services.seo_keyword_service import SeoKeywordService, get_active_keywords

bp = Blueprint("seo_api", __name__, url_prefix="/api/seo")


def _cors(response):
    """Allow the static website (and local preview) to fetch keywords."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Accept, Content-Type"
    # Avoid browsers caching a previous empty/error payload.
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@bp.after_request
def seo_api_cors(response):
    return _cors(response)


@bp.route("/keywords", methods=["GET", "OPTIONS"], strict_slashes=False)
def keywords():
    """
    GET /api/seo/keywords
    { "keywords": ["income tax consultant", "GST services", ...] }
    """
    if request.method == "OPTIONS":
        return ("", 204)

    try:
        SeoKeywordService().ensure_schema()
    except Exception:
        db.session.rollback()

    # Prefer raw SQL so SQL Server BIT / ORM edge cases never blank the public API.
    active: list[str] = []
    try:
        from sqlalchemy import text

        rows = db.session.execute(
            text(
                """
                SELECT keyword
                FROM dbo.seo_keywords
                WHERE ISNULL(is_active, 0) = 1
                ORDER BY id ASC
                """
            )
        ).fetchall()
        active = [
            str(row[0]).strip()
            for row in rows
            if row and row[0] and str(row[0]).strip()
        ]
    except Exception as exc:
        db.session.rollback()
        from flask import current_app

        current_app.logger.warning("SEO keywords raw query failed: %s", exc)
        try:
            active = get_active_keywords()
        except Exception as exc2:
            db.session.rollback()
            current_app.logger.warning("SEO keywords ORM fallback failed: %s", exc2)
            active = []

    return jsonify({"ok": True, "keywords": active, "count": len(active)})
