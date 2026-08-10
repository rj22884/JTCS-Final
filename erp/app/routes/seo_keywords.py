"""Admin SEO Keyword Management — /admin/seo."""

from __future__ import annotations

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from app.decorators import admin_required, login_required
from app.extensions import db
from app.services.menu_service import MenuService
from app.services.seo_keyword_service import SeoKeywordService
from app.utils.db_session import map_db_exception
from app.whats_new import publish_whats_new

bp = Blueprint("seo_keywords", __name__, url_prefix="/admin/seo")

MENU_PATH = "/admin/seo"
_BOOTSTRAPPED = False


def ensure_seo_keywords_bootstrap() -> None:
    """Create table, seed preload keywords, and register Admin menu (idempotent)."""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    SeoKeywordService().ensure_schema()
    try:
        publish_whats_new(
            "feature:seo_keywords",
            "SEO Keyword Management",
            detail="Admin Role → manage keywords used in footer, meta tags, and schema markup.",
            url=MENU_PATH,
            badge="New",
        )
    except Exception:
        db.session.rollback()
    _BOOTSTRAPPED = True


def _wants_json() -> bool:
    return (
        request.is_json
        or (request.mimetype or "").startswith("application/json")
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in (request.headers.get("Accept") or "")
    )


def _parse_bool(raw) -> bool | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "active"}


@bp.route("", methods=["GET"], strict_slashes=False)
@bp.route("/", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def index():
    try:
        ensure_seo_keywords_bootstrap()
    except Exception:
        db.session.rollback()

    service = SeoKeywordService()
    try:
        rows = service.list_all()
    except Exception:
        db.session.rollback()
        rows = []

    menu_service = MenuService()
    return render_template(
        "seo_keywords/index.html",
        page_title="SEO Keywords",
        breadcrumb=menu_service.get_breadcrumb(MENU_PATH, session.get("role")),
        keywords=rows,
    )


@bp.route("/add", methods=["POST"], strict_slashes=False)
@login_required
@admin_required
def add():
    payload = request.get_json(silent=True) or {}
    keyword = payload.get("keyword") if payload else request.form.get("keyword")
    try:
        ensure_seo_keywords_bootstrap()
        row = SeoKeywordService().add_keyword(keyword)
        if _wants_json():
            return jsonify(
                {
                    "ok": True,
                    "message": "Keyword added.",
                    "keyword": SeoKeywordService().to_dict(row),
                }
            )
        flash(f'Keyword "{row.keyword}" added.', "success")
    except ValueError as exc:
        if _wants_json():
            return jsonify({"ok": False, "error": str(exc)}), 400
        flash(str(exc), "danger")
    except Exception as exc:
        db.session.rollback()
        err = map_db_exception(exc)
        if _wants_json():
            return jsonify({"ok": False, "error": err}), 500
        flash(err, "danger")
    return redirect(url_for("seo_keywords.index"))


@bp.route("/bulk-add", methods=["POST"], strict_slashes=False)
@login_required
@admin_required
def bulk_add():
    payload = request.get_json(silent=True) or {}
    raw = payload.get("keywords") if payload else (
        request.form.get("keywords") or request.form.get("bulk_keywords")
    )
    try:
        ensure_seo_keywords_bootstrap()
        result = SeoKeywordService().bulk_add(raw)
        message = (
            f"Bulk add complete: {result['added']} added, "
            f"{result['skipped']} skipped (duplicates)."
        )
        if _wants_json():
            return jsonify({"ok": True, "message": message, **result})
        flash(message, "success" if result["added"] else "warning")
    except ValueError as exc:
        if _wants_json():
            return jsonify({"ok": False, "error": str(exc)}), 400
        flash(str(exc), "danger")
    except Exception as exc:
        db.session.rollback()
        err = map_db_exception(exc)
        if _wants_json():
            return jsonify({"ok": False, "error": err}), 500
        flash(err, "danger")
    return redirect(url_for("seo_keywords.index"))


@bp.route("/toggle", methods=["POST"], strict_slashes=False)
@login_required
@admin_required
def toggle():
    payload = request.get_json(silent=True) or {}
    raw_id = payload.get("id") if payload else request.form.get("id")
    try:
        keyword_id = int(raw_id)
    except (TypeError, ValueError):
        if _wants_json():
            return jsonify({"ok": False, "error": "Valid keyword id is required."}), 400
        flash("Valid keyword id is required.", "danger")
        return redirect(url_for("seo_keywords.index"))

    is_active = _parse_bool(
        payload.get("is_active") if payload else request.form.get("is_active")
    )
    try:
        ensure_seo_keywords_bootstrap()
        row = SeoKeywordService().toggle(keyword_id, is_active=is_active)
        status = "active" if row.is_active else "inactive"
        message = f'Keyword "{row.keyword}" is now {status}.'
        if _wants_json():
            return jsonify(
                {
                    "ok": True,
                    "message": message,
                    "keyword": SeoKeywordService().to_dict(row),
                }
            )
        flash(message, "success")
    except ValueError as exc:
        if _wants_json():
            return jsonify({"ok": False, "error": str(exc)}), 404
        flash(str(exc), "danger")
    except Exception as exc:
        db.session.rollback()
        err = map_db_exception(exc)
        if _wants_json():
            return jsonify({"ok": False, "error": err}), 500
        flash(err, "danger")
    return redirect(url_for("seo_keywords.index"))


@bp.route("/delete/<int:keyword_id>", methods=["DELETE", "POST"], strict_slashes=False)
@login_required
@admin_required
def delete(keyword_id: int):
    try:
        ensure_seo_keywords_bootstrap()
        SeoKeywordService().delete(keyword_id)
        message = "Keyword deleted."
        if _wants_json() or request.method == "DELETE":
            return jsonify({"ok": True, "message": message})
        flash(message, "success")
    except ValueError as exc:
        if _wants_json() or request.method == "DELETE":
            return jsonify({"ok": False, "error": str(exc)}), 404
        flash(str(exc), "danger")
    except Exception as exc:
        db.session.rollback()
        err = map_db_exception(exc)
        if _wants_json() or request.method == "DELETE":
            return jsonify({"ok": False, "error": err}), 500
        flash(err, "danger")
    return redirect(url_for("seo_keywords.index"))
