from datetime import date

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from app.decorators import admin_required, login_required, require_delete_reauth
from app.exceptions.stamp_exceptions import OcrUserError, StampDuplicateError
from app.repositories.transaction_repository import MasterRepository
from app.services.menu_service import MenuService
from app.services.ocr_provider_service import OcrProviderService
from app.services.stamp_ocr_service import StampOcrService
from app.services.shcil_open_login_service import SHCIL_LOGIN_URL
from app.services.stamp_service import StampService
from app.utils.roles import has_admin_role
from app.utils.runtime_env import is_vps_runtime

bp = Blueprint("stamp", __name__, url_prefix="/shcil")


@bp.route("/stamp-activity", methods=["GET", "POST"])
@login_required
def stamp_activity():
    stamp_service = StampService()
    master_repo = MasterRepository()
    menu_service = MenuService()
    duplicate_existing = None
    repost_stamp_id = None
    repost_mobile = None
    ocr_status = OcrProviderService.get_status().to_dict()

    if request.method == "POST":
        repost_stamp_id = request.form.get("StampID") or request.form.get("EditStampID")
        repost_mobile = (request.form.get("MobileNumber") or "").strip() or None
        try:
            result = stamp_service.save_stamp_activity(
                request.form,
                created_by=session.get("user_name", "System"),
            )
            flash(result.message, "success")
            mobile_digits = "".join(
                ch for ch in (request.form.get("MobileNumber") or "") if ch.isdigit()
            )[-10:]
            if len(mobile_digits) == 10:
                return redirect(
                    url_for("stamp.stamp_activity", continue_mobile=mobile_digits)
                )
            return redirect(url_for("stamp.stamp_activity", load_stamp=result.stamp_id))
        except StampDuplicateError as exc:
            duplicate_existing = exc.existing
            flash(str(exc), "danger")
        except ValueError as exc:
            flash(str(exc), "danger")
        except Exception as exc:
            flash(f"Unable to save stamp activity: {exc}", "danger")

    load_stamp_id = request.args.get("load_stamp", type=int)
    continue_mobile = (request.args.get("continue_mobile") or "").strip() or None
    if load_stamp_id is None and repost_stamp_id:
        try:
            load_stamp_id = int(repost_stamp_id)
        except (TypeError, ValueError):
            load_stamp_id = None

    return render_template(
        "stamp/activity.html",
        page_title="Stamp Activity",
        breadcrumb=menu_service.get_breadcrumb("/shcil/stamp-activity", session.get("role")),
        default_date=date.today().isoformat(),
        default_date_from="",
        default_date_to=date.today().isoformat(),
        payment_modes=master_repo.list_stamp_bank_payment_modes(),
        duplicate_existing=duplicate_existing,
        repost_stamp_id=repost_stamp_id,
        repost_mobile=repost_mobile,
        ocr_status=ocr_status,
        is_admin=has_admin_role(session.get("role")),
        is_vps=is_vps_runtime(),
        shcil_login_url=SHCIL_LOGIN_URL,
        load_stamp_id=load_stamp_id,
        continue_mobile=continue_mobile,
        website_prefill={
            "mobile": (request.args.get("mobile") or "").strip(),
            "first_party": (request.args.get("first_party") or "").strip(),
            "second_party": (request.args.get("second_party") or "").strip(),
            "amount": (request.args.get("amount") or "").strip(),
            "sale_amount": (request.args.get("sale_amount") or "").strip(),
            "description": (request.args.get("description") or "").strip(),
            "website_ref": (request.args.get("website_ref") or "").strip(),
        },
    )


@bp.route("/stamp-activity/open-login", methods=["POST"])
@login_required
def stamp_open_login():
    data = request.get_json(silent=True) or {}
    role = (data.get("role") or request.form.get("role") or "deo").strip().lower()
    try:
        from app.services.shcil_open_login_service import ShcilOpenLoginService

        return jsonify(ShcilOpenLoginService().open_login(role))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": f"Unable to open SHCIL login: {exc}"}), 500


@bp.route("/stamp-activity/extract", methods=["POST"])
@login_required
def stamp_extract():
    upload = request.files.get("certificate_file")
    ocr = StampOcrService()
    try:
        result = ocr.extract_from_upload(
            upload,
            created_by=session.get("user_name", "System"),
        )
        return jsonify(
            {
                "ok": True,
                "fields": result.fields,
                "provider": result.provider,
                "confidence": result.confidence,
                "ocr_text": result.ocr_text,
                "ocr_image_id": result.ocr_image_id,
            }
        )
    except OcrUserError as exc:
        status = OcrProviderService.get_status().to_dict()
        return jsonify(
            {
                "ok": False,
                "error": str(exc),
                "reason": str(exc),
                "engine_missing": True,
                "status": status,
                "install_guide": status.get("install_guide", []),
            }
        ), 400
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc), "reason": str(exc), "fields": {}}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc), "reason": str(exc), "fields": {}}), 500


@bp.route("/stamp-activity/ocr-status", methods=["GET"])
@login_required
def stamp_ocr_status():
    return jsonify(OcrProviderService.get_status().to_dict())


@bp.route("/stamp-activity/ocr-install", methods=["POST"])
@login_required
@admin_required
def stamp_ocr_install():
    result = OcrProviderService.install_easyocr_stack()
    if result.get("ok"):
        return jsonify(result)
    return jsonify(result), 500


@bp.route("/stamp-activity/grid-data", methods=["GET"])
@login_required
def stamp_grid_data():
    filters = StampService.filters_from_request(request.args)
    data = StampService().grid_data(filters)
    return jsonify({"ok": True, **data})


@bp.route("/stamp-activity/duty-grouping", methods=["GET"])
@login_required
def stamp_duty_grouping():
    def _parse_date(name: str):
        raw = (request.args.get(name) or "").strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None

    data = StampService().duty_grouping(
        date_from=_parse_date("date_from"),
        date_to=_parse_date("date_to"),
    )
    return jsonify({"ok": True, **data})


@bp.route("/stamp-activity/card-detail", methods=["GET"])
@login_required
def stamp_card_detail():
    filters = StampService.filters_from_request(request.args)
    card = (request.args.get("card") or "").strip()
    try:
        data = StampService().card_detail(card, filters)
        return jsonify({"ok": True, **data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/stamp-activity/bank-accounts", methods=["GET"])
@login_required
def stamp_bank_accounts():
    master_repo = MasterRepository()
    return jsonify(master_repo.list_stamp_bank_payment_modes())


@bp.route("/stamp-activity/search")
@login_required
def stamp_search():
    query = (request.args.get("q") or request.args.get("certificate") or "").strip()
    if not query:
        return jsonify({"ok": False, "error": "Enter certificate number to search.", "rows": []}), 400
    rows = StampService().search_records(query)
    return jsonify({"ok": True, "rows": rows, "count": len(rows)})


@bp.route("/stamp-activity/record/<int:stamp_id>")
@login_required
def stamp_record(stamp_id: int):
    try:
        record = StampService().get_record(stamp_id)
        return jsonify({"ok": True, "record": record})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@bp.route("/stamp-activity/delete/<int:stamp_id>", methods=["POST"])
@login_required
@require_delete_reauth
def stamp_delete(stamp_id: int):
    try:
        message = StampService().delete_stamp(
            stamp_id,
            deleted_by=session.get("user_name", "System"),
        )
        return jsonify({"ok": True, "message": message})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/stamp-activity/check-certificate")
@login_required
def check_certificate():
    number = (request.args.get("number") or "").strip()
    if not number:
        return jsonify({"exists": False})
    return jsonify(StampService().check_certificate(number))


@bp.route("/stamp-activity/view/<int:stamp_id>")
@login_required
def view_stamp(stamp_id: int):
    from app.repositories.stamp_repository import StampRepository

    stamp = StampRepository().get_by_id(stamp_id)
    if stamp is None:
        flash("Stamp record not found.", "warning")
        return redirect(url_for("stamp.stamp_activity"))

    existing = StampService().check_certificate(stamp.CertificateNumber)
    flash(
        f"Certificate {stamp.CertificateNumber} — Transaction #{existing.get('transaction_id', '—')}",
        "info",
    )
    return redirect(url_for("stamp.stamp_activity", load_stamp=stamp_id))
