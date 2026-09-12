"""Other Login service picker and Uttarakhand FPS Login."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from app.services.fps_login_service import FpsLoginService
from app.services.other_login_catalog import get_other_login_service, list_other_login_services
from app.utils.db_session import map_db_exception
from app.utils.fps_access import (
    FPS_LOGIN_ERROR,
    establish_fps_session,
    is_fps_session,
)

logger = logging.getLogger(__name__)

bp = Blueprint("other_login", __name__)


def _int_arg(name: str, default: int) -> int:
    raw = (request.args.get(name) or request.form.get(name) or "").strip()
    if not raw.isdigit():
        return default
    return int(raw)


@bp.route("/other-login", strict_slashes=False)
def services():
    if is_fps_session():
        return redirect(url_for("public_report.fps_detail"))
    return render_template(
        "other_login/services.html",
        page_title="Other Login",
        services=list_other_login_services(),
    )


@bp.route("/fps-login", strict_slashes=False)
def fps_login_page():
    if is_fps_session():
        return redirect(url_for("public_report.fps_detail"))
    service = get_other_login_service("uttarakhand_fps")
    if service is None or not service.enabled:
        return redirect(url_for("other_login.services"))
    return render_template(
        "other_login/fps_login.html",
        page_title="Uttarakhand FPS Login",
    )


@bp.route("/fps-login/api/options")
def fps_options():
    level = (request.args.get("level") or "").strip().lower()
    parent_id = _int_arg("parent_id", 0) or None
    try:
        rows = FpsLoginService().cascade_options(level, parent_id=parent_id)
        return jsonify({"ok": True, "level": level, "rows": rows, "count": len(rows)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("FPS cascade options failed")
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/fps-login/api/shops")
def fps_shops():
    term = (request.args.get("q") or request.args.get("search") or "").strip()
    page = _int_arg("page", 1)
    per_page = _int_arg("per_page", 40)
    try:
        payload = FpsLoginService().search_active(
            term or None,
            page=page,
            per_page=per_page,
            state_id=_int_arg("state_id", 0) or None,
            district_id=_int_arg("district_id", 0) or None,
            dso_id=_int_arg("dso_id", 0) or None,
            aro_id=_int_arg("aro_id", 0) or None,
        )
        return jsonify({"ok": True, **payload})
    except Exception as exc:
        logger.exception("FPS shop search failed")
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/fps-login/api/login", methods=["POST"])
def fps_login():
    payload = request.get_json(silent=True) or {}
    raw = payload.get("fps_row_id") or request.form.get("fps_row_id") or ""
    try:
        fps_row_id = int(str(raw).strip())
    except (TypeError, ValueError):
        fps_row_id = 0
    if fps_row_id <= 0:
        return jsonify({"ok": False, "error": "Select an FPS from the list."}), 400
    try:
        ok, message, data = FpsLoginService().login(fps_row_id)
    except Exception:
        logger.exception("FPS login failed")
        return jsonify({"ok": False, "error": FPS_LOGIN_ERROR}), 500
    if not ok:
        status = 403 if data.get("reason") == "inactive" else 400
        return jsonify({"ok": False, "error": message, **data}), status
    establish_fps_session(data)
    return jsonify(
        {
            "ok": True,
            "message": message,
            "redirect": url_for("public_report.fps_detail"),
            "shop": data.get("shop"),
        }
    )
