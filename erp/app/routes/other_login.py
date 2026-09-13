"""Other Login service picker, local E:\\Web-Data vault, and Uttarakhand FPS Login."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from app.extensions import csrf
from app.services.fps_login_service import FpsLoginService
from app.services.other_login_bridge import (
    computer_is_online,
    extract_request_token,
    presence_payload,
    pull_jobs,
    record_heartbeat,
    store_job_result,
    tokens_match,
    workspace_via_bridge,
)
from app.services.other_login_catalog import (
    get_other_login_definition,
    get_other_login_service,
    list_other_login_services,
)
from app.services.other_login_store import ensure_office_layout, is_known_key
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


def _render_services():
    if is_fps_session():
        return redirect(url_for("public_report.fps_detail"))
    ensure_office_layout()
    presence = presence_payload()
    return render_template(
        "other_login/services.html",
        page_title="Other Login",
        services=list_other_login_services(),
        computer_online=presence["online"],
        presence=presence,
    )


@bp.route("/other_login", strict_slashes=False)
def services_alias():
    return _render_services()


@bp.route("/other-login", strict_slashes=False)
def services():
    return _render_services()


@bp.route("/other_login/api/presence", methods=["GET"])
def presence_alias():
    ensure_office_layout()
    return jsonify(presence_payload())


@bp.route("/other-login/api/presence", methods=["GET"])
def presence():
    ensure_office_layout()
    return jsonify(presence_payload())


@bp.route("/other-login/api/local-heartbeat", methods=["POST"])
@csrf.exempt
def local_heartbeat():
    payload = request.get_json(silent=True) or {}
    if not tokens_match(extract_request_token(payload)):
        return jsonify({"ok": False, "error": "Unauthorized Other Login bridge."}), 401
    return jsonify(record_heartbeat(payload))


@bp.route("/other-login/api/local-jobs", methods=["GET"])
@csrf.exempt
def local_jobs():
    if not tokens_match(extract_request_token()):
        return jsonify({"ok": False, "error": "Unauthorized Other Login bridge."}), 401
    return jsonify({"ok": True, "jobs": pull_jobs()})


@bp.route("/other-login/api/local-job-result", methods=["POST"])
@csrf.exempt
def local_job_result():
    payload = request.get_json(silent=True) or {}
    if not tokens_match(extract_request_token(payload)):
        return jsonify({"ok": False, "error": "Unauthorized Other Login bridge."}), 401
    job_id = str(payload.get("id") or payload.get("job_id") or "").strip()
    if not job_id:
        return jsonify({"ok": False, "error": "Missing job id."}), 400
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    store_job_result(job_id, result)
    return jsonify({"ok": True})


@bp.route("/other-login/api/workspace/<key>", methods=["GET", "POST"])
def workspace_api(key: str):
    if not is_known_key(key):
        return jsonify({"ok": False, "error": "Unknown Other Login service."}), 404
    if not computer_is_online():
        return jsonify({"ok": False, "offline": True, "error": "Office computer is off. Other Login is disabled."}), 423
    if request.method == "GET":
        return jsonify(workspace_via_bridge(key, op="read"))
    body = request.get_json(silent=True) or {}
    return jsonify(workspace_via_bridge(key, op="write", payload=body if isinstance(body, dict) else {}))


@bp.route("/other-login/<key>", strict_slashes=False)
def workspace(key: str):
    if is_fps_session():
        return redirect(url_for("public_report.fps_detail"))
    if key in {"api", "_bridge"}:
        return redirect(url_for("other_login.services"))
    definition = get_other_login_definition(key)
    if definition is None:
        return redirect(url_for("other_login.services"))
    service = get_other_login_service(key)
    if service is None or not service.enabled:
        return redirect(url_for("other_login.services"))
    if definition.key == "uttarakhand_fps":
        return redirect(url_for("other_login.fps_login_page"))
    ensure_office_layout()
    return render_template(
        "other_login/workspace.html",
        page_title=definition.name,
        service=definition,
        presence=presence_payload(),
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
    if not computer_is_online():
        return jsonify({"ok": False, "error": "Office computer is off. Other Login is disabled."}), 423
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
    if not computer_is_online():
        return jsonify({"ok": False, "error": "Office computer is off. Other Login is disabled."}), 423
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
    if not computer_is_online():
        return jsonify({"ok": False, "error": "Office computer is off. Other Login is disabled."}), 423
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
