from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app.customer_master.constants import (
    COUNTRIES,
    CUSTOMER_STATUSES,
    CUSTOMER_TYPES,
    GENDERS,
    GST_FILING_FREQUENCIES,
    TAB_LABELS,
)
from app.decorators import login_required, require_delete_reauth
from app.utils.roles import has_admin_role
from app.services.chart_group_service import ChartGroupService
from app.services.customer_group_service import CustomerGroupService
from app.services.customer_master_service import (
    CustomerMasterService,
    CustomerInUseError,
    DuplicateFieldError,
    DuplicateMobileWarning,
)
from app.services.menu_service import MenuService
from app.services.work_master_service import WorkMasterService

bp = Blueprint("masters_customer", __name__, url_prefix="/masters/customer")
MENU_PATH = "/masters/customer"


def _in_use_response(exc: CustomerInUseError):
    return jsonify(
        {
            "ok": False,
            "error": str(exc),
            "in_use": True,
            "usage": exc.usage,
        }
    ), 409


@bp.route("", strict_slashes=False)
@bp.route("/", strict_slashes=False)
@login_required
def index():
    service = CustomerMasterService()
    group_service = CustomerGroupService()
    menu_service = MenuService()
    ui = service.ui_config()
    cm_api = {
        "list": url_for("masters_customer.list_records"),
        "get": url_for("masters_customer.get_record", customer_id=0),
        "save": url_for("masters_customer.save_record"),
        "delete": url_for("masters_customer.delete_record", customer_id=0),
        "restore": url_for("masters_customer.restore_record", customer_id=0),
        "checkDuplicates": url_for("masters_customer.check_duplicates"),
        "pincodeLookup": url_for("masters_customer.lookup_pincode"),
        "incomeTaxPortalLogin": url_for("masters_customer.income_tax_portal_login"),
        "incomeTaxPortalStatus": url_for("masters_customer.income_tax_portal_status"),
        "aadhaarEkycStart": url_for("masters_customer.aadhaar_ekyc_start"),
        "aadhaarEkycStatus": url_for("masters_customer.aadhaar_ekyc_status"),
        "aadhaarEkycUnlock": url_for("masters_customer.aadhaar_ekyc_unlock"),
        "resetPortalPassword": url_for("masters_customer.reset_portal_password", customer_id=0),
    }
    is_admin = has_admin_role(session.get("role"))
    try:
        chart_of_groups = ChartGroupService().list_active_for_dropdown()
    except Exception:
        chart_of_groups = []
    default_chart_group_id = None
    for g in chart_of_groups:
        if (g.get("group_name") or "").strip().casefold() == "individual client":
            default_chart_group_id = g.get("group_id")
            break
    try:
        customer_group_filter = group_service.customer_form_filter_payload()
    except Exception:
        customer_group_filter = {
            "groups": ui["groups"],
            "usage": {},
            "chart_natures": {},
        }
    try:
        income_expense_works = WorkMasterService().list_records()
    except Exception:
        income_expense_works = []

    return render_template(
        "masters/customer_master.html",
        page_title="Customer Master",
        breadcrumb=menu_service.get_breadcrumb(MENU_PATH, session.get("role")),
        initial_rows=service.list_records(),
        customer_groups=ui["groups"],
        customer_group_filter=customer_group_filter,
        chart_of_groups=chart_of_groups,
        default_chart_group_id=default_chart_group_id,
        income_expense_works=income_expense_works,
        customer_types=CUSTOMER_TYPES,
        customer_statuses=CUSTOMER_STATUSES,
        genders=GENDERS,
        countries=COUNTRIES,
        gst_filing_frequencies=GST_FILING_FREQUENCIES,
        group_tabs=ui["group_tabs"],
        tab_labels=TAB_LABELS,
        ui_config=ui,
        cm_api=cm_api,
        is_admin=is_admin,
    )


@bp.route("/api/records", strict_slashes=False)
@login_required
def list_records():
    search = (request.args.get("search") or "").strip() or None
    customer_group = (request.args.get("customer_group") or "").strip() or None
    status = (request.args.get("status") or "").strip() or None
    rows = CustomerMasterService().list_records(
        search=search,
        customer_group=customer_group,
        status=status,
    )
    return jsonify({"ok": True, "rows": rows, "count": len(rows)})


@bp.route("/api/records/<int:customer_id>", strict_slashes=False)
@login_required
def get_record(customer_id: int):
    try:
        record = CustomerMasterService().get_record(customer_id)
        return jsonify({"ok": True, "record": record})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/api/pincode-lookup", strict_slashes=False)
@login_required
def lookup_pincode():
    """Address tab: resolve pincode → country, state, district."""
    pin = (request.args.get("pincode") or request.args.get("pin") or "").strip()
    try:
        return jsonify(CustomerMasterService.lookup_pincode(pin))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/check-duplicates", strict_slashes=False)
@login_required
def check_duplicates():
    customer_id = None
    raw_id = request.args.get("customer_id")
    if raw_id not in (None, "", "0"):
        try:
            customer_id = int(raw_id)
        except (TypeError, ValueError):
            customer_id = None
    result = CustomerMasterService().check_duplicates(
        pan=(request.args.get("pan") or "").strip() or None,
        aadhaar=(request.args.get("aadhaar") or "").strip() or None,
        mobile=(request.args.get("mobile") or "").strip() or None,
        customer_id=customer_id,
    )
    return jsonify({"ok": True, **result})


@bp.route("/api/records", methods=["POST"], strict_slashes=False)
@login_required
def save_record():
    payload = request.get_json(silent=True) or request.form.to_dict()
    customer_id = None
    raw_id = payload.get("customer_id")
    if raw_id not in (None, "", "0"):
        try:
            customer_id = int(raw_id)
        except (TypeError, ValueError):
            customer_id = None
    allow_duplicate_mobile = str(
        payload.get("allow_duplicate_mobile") or payload.get("confirm_duplicate_mobile") or ""
    ).lower() in {"1", "true", "yes", "on"}
    try:
        record = CustomerMasterService().save_record(
            payload,
            customer_id=customer_id,
            allow_duplicate_mobile=allow_duplicate_mobile,
        )
        message = "Customer updated successfully." if customer_id else "Customer added successfully."
        return jsonify({"ok": True, "record": record, "message": message})
    except CustomerInUseError as exc:
        return _in_use_response(exc)
    except DuplicateFieldError as exc:
        return jsonify(
            {
                "ok": False,
                "error": str(exc),
                "duplicate_type": exc.field,
                "duplicate": exc.duplicate,
                "can_edit": True,
            }
        ), 409
    except DuplicateMobileWarning as exc:
        return jsonify(
            {
                "ok": False,
                "error": str(exc),
                "duplicate_type": "mobile_number",
                "mobile_duplicates": exc.duplicates,
                "can_confirm": True,
            }
        ), 409
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/records/<int:customer_id>/delete", methods=["POST"], strict_slashes=False)
@login_required
@require_delete_reauth
def delete_record(customer_id: int):
    try:
        message = CustomerMasterService().delete_record(customer_id)
        return jsonify({"ok": True, "message": message})
    except CustomerInUseError as exc:
        return _in_use_response(exc)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/api/records/<int:customer_id>/restore", methods=["POST"], strict_slashes=False)
@login_required
def restore_record(customer_id: int):
    try:
        message = CustomerMasterService().restore_record(customer_id)
        return jsonify({"ok": True, "message": message})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/portal/income-tax-login", methods=["POST"], strict_slashes=False)
@login_required
def income_tax_portal_login():
    """Open Income Tax e-Filing login, fill credentials, then sync profile into job result."""
    from app.services.customer_portal_sync_service import CustomerPortalSyncService

    payload = request.get_json(silent=True) or request.form.to_dict()
    user_id = (payload.get("user_id") or payload.get("pan") or "").strip()
    password = payload.get("password") or payload.get("income_tax_password") or ""
    try:
        result = CustomerPortalSyncService().launch_income_tax_login(user_id, password)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": f"Unable to open Income Tax portal: {exc}"}), 500


@bp.route("/api/portal/income-tax-status", strict_slashes=False)
@login_required
def income_tax_portal_status():
    from app.services.customer_portal_sync_service import CustomerPortalSyncService

    job_id = (request.args.get("job_id") or "").strip()
    if not job_id:
        return jsonify({"ok": False, "error": "job_id is required."}), 400
    job = CustomerPortalSyncService().get_job(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Sync job not found."}), 404
    return jsonify({"ok": True, "job": job})


@bp.route("/api/aadhaar-ekyc/start", methods=["POST"], strict_slashes=False)
@login_required
def aadhaar_ekyc_start():
    """Start watching Downloads for Offline Aadhaar ZIP (no captcha/OTP automation)."""
    from app.services.aadhaar_offline_ekyc_service import AadhaarOfflineEkycService

    try:
        return jsonify(AadhaarOfflineEkycService().start_watch())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": f"Unable to start Aadhaar import: {exc}"}), 500


@bp.route("/api/aadhaar-ekyc/status", strict_slashes=False)
@login_required
def aadhaar_ekyc_status():
    from app.services.aadhaar_offline_ekyc_service import AadhaarOfflineEkycService

    job_id = (request.args.get("job_id") or "").strip()
    if not job_id:
        return jsonify({"ok": False, "error": "job_id is required."}), 400
    job = AadhaarOfflineEkycService().get_job(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Aadhaar import job not found."}), 404
    return jsonify({"ok": True, "job": job})


@bp.route("/api/aadhaar-ekyc/unlock", methods=["POST"], strict_slashes=False)
@login_required
def aadhaar_ekyc_unlock():
    """Unlock downloaded ZIP with Share Code, parse XML, return form field mapping (no auto-save)."""
    from app.services.aadhaar_offline_ekyc_service import AadhaarOfflineEkycService

    payload = request.get_json(silent=True) or request.form.to_dict()
    job_id = (payload.get("job_id") or "").strip()
    password = payload.get("password") or payload.get("share_code") or ""
    if not job_id:
        return jsonify({"ok": False, "error": "job_id is required."}), 400
    try:
        return jsonify(AadhaarOfflineEkycService().unlock_and_parse(job_id, password))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": f"Unable to process Aadhaar ZIP: {exc}"}), 500


@bp.route("/api/records/<int:customer_id>/reset-portal-password", methods=["POST"], strict_slashes=False)
@login_required
def reset_portal_password(customer_id: int):
    """Admin / Super Admin: clear Customer Portal password (identity verify + new password)."""
    if not has_admin_role(session.get("role")):
        return jsonify({"ok": False, "error": "Administrator access required."}), 403

    from app.services.customer_portal_service import CustomerPortalService

    result = CustomerPortalService().admin_reset_password(customer_id)
    if not result.get("ok"):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": result.get("error"),
                    "error_code": result.get("error_code"),
                }
            ),
            int(result.get("status_code") or 400),
        )
    return jsonify(
        {
            "ok": True,
            "message": result.get("message") or "Default password reset successfully.",
        }
    )


@bp.route("/exit", strict_slashes=False)
@login_required
def exit_module():
    return redirect(url_for("dashboard.index"))
