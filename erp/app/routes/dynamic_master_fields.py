from datetime import date

from flask import Blueprint, jsonify, request

from app.decorators import login_required
from app.services.dynamic_master_fields import DynamicMasterFieldService

bp = Blueprint("dynamic_master_fields", __name__, url_prefix="/api/dynamic-master-fields")


@bp.route("/config", methods=["GET"], strict_slashes=False)
@login_required
def config():
    try:
        svc = DynamicMasterFieldService()
        svc.reset_cache()
        return jsonify({"ok": True, **svc.client_config()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/catalog", methods=["GET"], strict_slashes=False)
@login_required
def catalog():
    try:
        svc = DynamicMasterFieldService()
        return jsonify({"ok": True, **svc.catalog_for_editor(), **svc.client_config()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/catalog", methods=["POST"], strict_slashes=False)
@login_required
def create_catalog_field():
    payload = request.get_json(silent=True) or request.form.to_dict()
    try:
        record = DynamicMasterFieldService().create_custom_field(payload)
        return jsonify({"ok": True, "record": record, "message": "Field added."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/catalog/<field_key>", methods=["POST"], strict_slashes=False)
@login_required
def update_catalog_field(field_key: str):
    payload = request.get_json(silent=True) or request.form.to_dict()
    try:
        record = DynamicMasterFieldService().update_custom_field(field_key, payload)
        return jsonify({"ok": True, "record": record, "message": "Field updated."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/catalog/<field_key>/delete", methods=["POST"], strict_slashes=False)
@login_required
def delete_catalog_field(field_key: str):
    try:
        message = DynamicMasterFieldService().delete_custom_field(field_key)
        return jsonify({"ok": True, "message": message})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/group/<int:group_id>", methods=["GET"], strict_slashes=False)
@login_required
def group_fields(group_id: int):
    try:
        return jsonify({"ok": True, **DynamicMasterFieldService().fields_for_group_editor(group_id)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/india-locations", methods=["GET"], strict_slashes=False)
@login_required
def india_locations():
    from app.services.india_location_service import IndiaLocationService

    level = (request.args.get("level") or "").strip()
    try:
        rows = IndiaLocationService().list_options(
            level,
            state=request.args.get("state") or "",
            district=request.args.get("district") or "",
            taluka=request.args.get("taluka") or request.args.get("tehsil") or "",
            village=request.args.get("village")
            or request.args.get("town")
            or request.args.get("locality")
            or "",
            pincode=request.args.get("pincode") or "",
        )
        return jsonify({"ok": True, "rows": rows})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/land-value-sync", methods=["GET"], strict_slashes=False)
@login_required
def land_value_sync():
    from app.services.land_value_service import LandValueService

    try:
        result = LandValueService().lookup(
            state=request.args.get("state") or "",
            district=request.args.get("district") or "",
            tehsil=request.args.get("tehsil") or request.args.get("taluka") or "",
            village=request.args.get("village") or "",
            town=request.args.get("town") or "",
            locality=request.args.get("locality") or "",
            area_class=request.args.get("area_class") or "",
            land_area=request.args.get("land_area") or request.args.get("area") or "",
            land_unit=request.args.get("land_unit") or request.args.get("unit") or "",
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/depreciation-rate-sync", methods=["GET"], strict_slashes=False)
@login_required
def depreciation_rate_sync():
    from app.services.depreciation_service import DepreciationService

    purchase_raw = (request.args.get("purchase_date") or request.args.get("date") or "").strip()
    purchase = None
    if purchase_raw:
        try:
            purchase = date.fromisoformat(purchase_raw[:10])
        except ValueError:
            return jsonify({"ok": False, "error": "Purchase date is invalid."}), 400
    try:
        result = DepreciationService().lookup_public_rate(
            purchase_date=purchase,
            item_code=(request.args.get("item_code") or "").strip(),
            item_name=(request.args.get("item_name") or "").strip(),
            hsn_sac=(request.args.get("hsn") or request.args.get("hsn_sac") or "").strip(),
        )
        return jsonify(result)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
