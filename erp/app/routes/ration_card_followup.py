from __future__ import annotations

from datetime import date

from flask import Blueprint, jsonify, render_template, request, session
from sqlalchemy import text

from app.decorators import login_required, require_delete_reauth
from app.extensions import db
from app.repositories.transaction_repository import MasterRepository
from app.services.menu_service import MenuService
from app.services.ration_card_followup_service import RationCardFollowupService

bp = Blueprint("ration_card_followup", __name__, url_prefix="/public-report/ration-card/followup")

MENU_PATH = "/public-report/ration-card/followup"
FOLLOWUP_MENU_NAME = "Followup"


def ensure_ration_card_followup_menu() -> None:
    """Permanently remove Followup from Public Report → Ration Card Report."""
    db.session.execute(
        text(
            """
            DELETE FROM dbo.MenuMaster
            WHERE MenuURL = :url
               OR (
                    MenuName = :name
                    AND ParentMenuID IN (
                        SELECT MenuID FROM dbo.MenuMaster WHERE MenuName = N'Ration Card Report'
                    )
               )
            """
        ),
        {"url": MENU_PATH, "name": FOLLOWUP_MENU_NAME},
    )
    db.session.commit()


@bp.route("", methods=["GET"], strict_slashes=False)
@bp.route("/", methods=["GET"], strict_slashes=False)
@login_required
def index():
    master_repo = MasterRepository()
    return render_template(
        "public_report/ration_card_followup.html",
        page_title="Ration Card Followup",
        breadcrumb=MenuService().get_breadcrumb(MENU_PATH, session.get("role")),
        default_date=date.today().isoformat(),
        payment_modes=master_repo.list_stamp_bank_payment_modes(),
        load_entry_id=request.args.get("load_entry", type=int),
    )


@bp.route("/ensure-customer", methods=["POST"], strict_slashes=False)
@login_required
def ensure_customer():
    """Work Done → auto-create Customer Master as ``Name - FPS Code`` (no duplicates)."""
    fps_name = ""
    fps_code = ""
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        fps_name = (payload.get("fps_name") or "").strip()
        fps_code = (payload.get("fps_code") or "").strip()
    else:
        fps_name = (request.form.get("fps_name") or "").strip()
        fps_code = (request.form.get("fps_code") or "").strip()
    try:
        result = RationCardFollowupService().ensure_fps_customer(fps_name, fps_code)
        return jsonify(
            {
                "ok": True,
                "created": bool(result.get("created")),
                "customer_id": result.get("customer_id"),
                "customer_name": result.get("customer_name"),
                "message": (
                    f"Customer created: {result.get('customer_name')}"
                    if result.get("created")
                    else f"Customer already exists: {result.get('customer_name')}"
                ),
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unable to create customer: {exc}"}), 500


@bp.route("/save", methods=["POST"], strict_slashes=False)
@login_required
def save_record():
    service = RationCardFollowupService()
    try:
        result = service.save_entry(
            request.form,
            created_by=session.get("user_name", "System"),
        )
        return jsonify(
            {
                "ok": True,
                "message": result.message,
                "entry_id": result.entry_id,
                "bill_no": result.bill_no,
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unable to save entry: {exc}"}), 500


@bp.route("/grid", methods=["GET"], strict_slashes=False)
@login_required
def grid():
    return jsonify({"ok": True, "rows": RationCardFollowupService().list_entries()})


@bp.route("/next-bill-no", methods=["GET"], strict_slashes=False)
@login_required
def next_bill_no():
    work_date_raw = (request.args.get("work_date") or "").strip()
    try:
        work_date = date.fromisoformat(work_date_raw[:10])
    except ValueError:
        return jsonify({"ok": False, "error": "Valid work date is required."}), 400
    return jsonify({"ok": True, "bill_no": RationCardFollowupService().next_bill_no(work_date)})


@bp.route("/records/<int:entry_id>", methods=["GET"], strict_slashes=False)
@login_required
def record(entry_id: int):
    try:
        return jsonify({"ok": True, "record": RationCardFollowupService().get_entry(entry_id)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/records/<int:entry_id>/delete", methods=["POST"], strict_slashes=False)
@login_required
@require_delete_reauth
def delete_record(entry_id: int):
    try:
        message = RationCardFollowupService().delete_entry(entry_id)
        return jsonify({"ok": True, "message": message})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
