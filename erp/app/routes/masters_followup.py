from __future__ import annotations

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required, require_delete_reauth
from app.services.followup_service import MODULE_META, FollowupService
from app.services.menu_service import MenuService
from app.utils.master_delete_guard import MasterInUseError, json_in_use_response

MASTER_MODULES = {
    "itr": "ITR",
    "dsc": "DSC",
    "tds": "TDS",
    "gst": "GST",
}

bp = Blueprint("masters_followup", __name__, url_prefix="/masters/followup")


def _resolve_module(slug: str) -> tuple[str, dict]:
    code = MASTER_MODULES.get((slug or "").strip().lower())
    if not code:
        raise ValueError("Invalid followup master module.")
    return code, MODULE_META[code]


@bp.route("/<slug>", strict_slashes=False)
@bp.route("/<slug>/", strict_slashes=False)
@login_required
def index(slug: str):
    try:
        module_code, meta = _resolve_module(slug)
    except ValueError:
        return redirect(url_for("dashboard.index"))

    service = FollowupService(module_code)
    menu_service = MenuService()
    menu_path = f"/masters/followup/{slug.lower()}"
    return render_template(
        "masters/followup_workflow.html",
        page_title=f"{meta['title']} Followup Master",
        breadcrumb=menu_service.get_breadcrumb(menu_path, session.get("role")),
        module_code=module_code,
        module_slug=slug.lower(),
        module_meta=meta,
        initial_rows=service.list_master_stages(),
    )


@bp.route("/<slug>/api/records", strict_slashes=False)
@login_required
def list_records(slug: str):
    try:
        module_code, _ = _resolve_module(slug)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    search = (request.args.get("search") or "").strip() or None
    rows = FollowupService(module_code).list_master_stages(search=search)
    return jsonify({"ok": True, "rows": rows, "count": len(rows)})


@bp.route("/<slug>/api/records/<int:stage_id>", strict_slashes=False)
@login_required
def get_record(slug: str, stage_id: int):
    try:
        module_code, _ = _resolve_module(slug)
        record = FollowupService(module_code).get_master_stage(stage_id)
        return jsonify({"ok": True, "record": record})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/<slug>/api/records", methods=["POST"], strict_slashes=False)
@login_required
def create_record(slug: str):
    try:
        module_code, _ = _resolve_module(slug)
        payload = request.get_json(silent=True) or request.form.to_dict()
        record = FollowupService(module_code).create_master_stage(payload)
        return jsonify({"ok": True, "record": record, "message": "Workflow stage added successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/<slug>/api/records/<int:stage_id>", methods=["POST"], strict_slashes=False)
@login_required
def update_record(slug: str, stage_id: int):
    try:
        module_code, _ = _resolve_module(slug)
        payload = request.get_json(silent=True) or request.form.to_dict()
        record = FollowupService(module_code).update_master_stage(stage_id, payload)
        return jsonify({"ok": True, "record": record, "message": "Workflow stage updated successfully."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/<slug>/api/records/<int:stage_id>/delete", methods=["POST"], strict_slashes=False)
@login_required
@require_delete_reauth
def delete_record(slug: str, stage_id: int):
    try:
        module_code, _ = _resolve_module(slug)
        message = FollowupService(module_code).delete_master_stage(stage_id)
        return jsonify({"ok": True, "message": message})
    except MasterInUseError as exc:
        return json_in_use_response(exc)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/exit")
@login_required
def exit_module():
    return redirect(url_for("dashboard.index"))
