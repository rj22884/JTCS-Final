from __future__ import annotations

import io
from datetime import date

from flask import Blueprint, jsonify, render_template, request, send_file, session, url_for

from app.customer_master.constants import COUNTRIES
from app.decorators import login_required, require_delete_reauth
from app.repositories.transaction_repository import MasterRepository
from app.services.customer_service import CustomerService
from app.services.followup_billing_service import FollowupBillingService
from app.services.followup_payment_service import FollowupPaymentService
from app.services.followup_service import (
    GST_RETURN_TYPES,
    MODULE_META,
    TDS_FORM_TYPES,
    TDS_QUARTERS,
    FollowupService,
    default_tax_period,
    tax_period_options,
)
from app.services.menu_service import MenuService
from app.services.payment_reminder_service import PaymentReminderService
from app.services.thank_you_letter_service import ThankYouLetterService


def _followup_api_urls(blueprint_name: str, module_code: str, allow_customer_create: bool) -> dict:
    urls = {
        "grid": url_for(f"{blueprint_name}.grid"),
        "save": url_for(f"{blueprint_name}.save_record"),
        "record": url_for(f"{blueprint_name}.record", entry_id=0),
        "delete": url_for(f"{blueprint_name}.delete_record", entry_id=0),
        "customer_search": url_for(f"{blueprint_name}.customer_search"),
        "billing": url_for(f"{blueprint_name}.billing_page"),
        "next_bill_no": url_for(f"{blueprint_name}.next_bill_no"),
        "thank_you_letter": url_for(f"{blueprint_name}.thank_you_letter", entry_id=0),
    }
    if module_code == "DSC":
        urls["sync_status"] = url_for(f"{blueprint_name}.sync_idsign_status", entry_id=0)
    if module_code == "ITR":
        urls["itr_sync_start"] = url_for(f"{blueprint_name}.itr_sync_start")
        urls["itr_sync_job"] = url_for(f"{blueprint_name}.itr_sync_job", job_id="__JOB__")
        urls["payment_reminder"] = url_for(f"{blueprint_name}.payment_reminder", entry_id=0)
        urls["verify_edit_reauth"] = url_for(f"{blueprint_name}.itr_verify_edit_reauth")
    if allow_customer_create:
        urls["customer_create"] = url_for(f"{blueprint_name}.customer_create")
    return urls


def _make_activity_blueprint(
    module_code: str,
    url_prefix: str,
    blueprint_name: str,
    *,
    allow_customer_create: bool = False,
) -> Blueprint:
    bp = Blueprint(blueprint_name, __name__, url_prefix=url_prefix)
    meta = MODULE_META[module_code]
    menu_path = meta["menu_path"]

    @bp.route("", methods=["GET"], strict_slashes=False)
    @bp.route("/", methods=["GET"], strict_slashes=False)
    @login_required
    def index():
        service = FollowupService(module_code)
        menu_service = MenuService()
        master_repo = MasterRepository()
        return render_template(
            "followup/activity.html",
            page_title=f"{meta['title']} Followup",
            breadcrumb=menu_service.get_breadcrumb(menu_path, session.get("role")),
            module_code=module_code,
            module_meta=meta,
            default_date=date.today().isoformat(),
            default_tax_period=default_tax_period(),
            tax_periods=tax_period_options(),
            tds_form_types=TDS_FORM_TYPES,
            tds_quarters=TDS_QUARTERS,
            gst_return_types=GST_RETURN_TYPES,
            workflow_stages=service.list_stages(),
            allow_customer_add=allow_customer_create,
            countries=COUNTRIES,
            payment_modes=master_repo.list_stamp_bank_payment_modes(),
            api_urls=_followup_api_urls(blueprint_name, module_code, allow_customer_create),
            pincode_lookup_url=url_for("masters_customer.lookup_pincode"),
            load_entry_id=request.args.get("load_entry", type=int),
        )

    @bp.route("/grid", methods=["GET"], strict_slashes=False)
    @login_required
    def grid():
        service = FollowupService(module_code)
        search = (request.args.get("search") or "").strip() or None
        status_filter = (request.args.get("status") or "").strip() or None
        tax_period = (request.args.get("tax_period") or "").strip() or None
        return_type = (request.args.get("return_type") or "").strip() or None
        date_from = (request.args.get("date_from") or "").strip() or None
        date_to = (request.args.get("date_to") or "").strip() or None
        filter_kwargs = {
            "search": search,
            "tax_period": tax_period,
            "return_type": return_type,
            "date_from": date_from,
            "date_to": date_to,
        }
        rows = service.list_entries(status_filter=status_filter, **filter_kwargs)
        # Cards ignore status so totals stay visible while browsing a status slice.
        stats = service.stats(**filter_kwargs)
        return jsonify({"ok": True, "rows": rows, "stats": stats, "count": len(rows)})

    @bp.route("/stats", methods=["GET"], strict_slashes=False)
    @login_required
    def stats():
        service = FollowupService(module_code)
        return jsonify(
            {
                "ok": True,
                "stats": service.stats(
                    search=(request.args.get("search") or "").strip() or None,
                    tax_period=(request.args.get("tax_period") or "").strip() or None,
                    return_type=(request.args.get("return_type") or "").strip() or None,
                    date_from=(request.args.get("date_from") or "").strip() or None,
                    date_to=(request.args.get("date_to") or "").strip() or None,
                ),
            }
        )

    @bp.route("/records/<int:entry_id>", methods=["GET"], strict_slashes=False)
    @login_required
    def record(entry_id: int):
        service = FollowupService(module_code)
        try:
            return jsonify({"ok": True, "record": service.get_entry(entry_id)})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404

    @bp.route("/records", methods=["POST"], strict_slashes=False)
    @login_required
    def save_record():
        service = FollowupService(module_code)
        payload = request.get_json(silent=True) or request.form.to_dict()
        if hasattr(request, "form") and request.form.getlist("stage_ids"):
            payload["stage_ids"] = request.form.getlist("stage_ids")
        try:
            record = service.save_entry(payload, created_by=session.get("user_name", "System"))
            return jsonify({"ok": True, "record": record, "message": "Followup entry saved successfully."})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc) or "Unable to save followup entry."}), 500

    @bp.route("/records/<int:entry_id>/delete", methods=["POST"], strict_slashes=False)
    @login_required
    @require_delete_reauth
    def delete_record(entry_id: int):
        service = FollowupService(module_code)
        try:
            message = service.delete_entry(entry_id)
            return jsonify({"ok": True, "message": message})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404

    if module_code == "DSC":

        @bp.route("/records/<int:entry_id>/sync-idsign-status", methods=["POST"], strict_slashes=False)
        @login_required
        def sync_idsign_status(entry_id: int):
            service = FollowupService(module_code)
            try:
                result = service.sync_idsign_status(entry_id)
                return jsonify({"ok": True, **result})
            except ValueError as exc:
                return jsonify({"ok": False, "error": str(exc)}), 400
            except Exception as exc:
                return jsonify({"ok": False, "error": f"Unable to sync ID Sign status: {exc}"}), 500

    if module_code == "ITR":

        @bp.route("/api/verify-edit-reauth", methods=["POST"], strict_slashes=False)
        @login_required
        @require_delete_reauth
        def itr_verify_edit_reauth():
            """ITR only: confirm User ID + password before editing a Payment Received row."""
            return jsonify({"ok": True, "message": "Edit authorised."})

        @bp.route("/api/sync-status", methods=["POST"], strict_slashes=False)
        @login_required
        def itr_sync_start():
            from flask import current_app

            from app.services.itr_kdk_sync_service import ItrKdkSyncService

            payload = request.get_json(silent=True) or request.form.to_dict()
            user_id = (payload.get("user_id") or payload.get("userid") or "").strip()
            password = payload.get("password") or ""
            headless_raw = str(payload.get("headless") or "1").strip().lower()
            headless = headless_raw not in {"0", "false", "no", "off"}
            entry_raw = payload.get("entry_id")
            entry_id = None
            if entry_raw not in (None, ""):
                try:
                    entry_id = int(entry_raw)
                except (TypeError, ValueError):
                    return jsonify({"ok": False, "error": "Invalid entry_id."}), 400
            try:
                result = ItrKdkSyncService().start_sync(
                    user_id=user_id,
                    password=password,
                    app=current_app._get_current_object(),
                    headless=headless,
                    entry_id=entry_id,
                )
                return jsonify({"ok": True, **result})
            except ValueError as exc:
                return jsonify({"ok": False, "error": str(exc)}), 400
            except Exception as exc:
                return jsonify({"ok": False, "error": str(exc) or "Unable to start sync."}), 500

        @bp.route("/api/sync-status/<job_id>", methods=["GET"], strict_slashes=False)
        @login_required
        def itr_sync_job(job_id: str):
            from app.services.itr_kdk_sync_service import ItrKdkSyncService

            job = ItrKdkSyncService().get_job(job_id)
            if not job:
                return jsonify({"ok": False, "error": "Sync job not found."}), 404
            return jsonify({"ok": True, "job": job})

    @bp.route("/billing", methods=["GET"], strict_slashes=False)
    @login_required
    def billing_page():
        menu_service = MenuService()
        work_date_raw = (request.args.get("work_date") or "").strip() or date.today().isoformat()
        try:
            work_date = date.fromisoformat(work_date_raw[:10])
        except ValueError:
            work_date = date.today()
        return render_template(
            "followup/billing.html",
            page_title=f"{meta['title']} Automated Billing",
            breadcrumb=menu_service.get_breadcrumb(menu_path, session.get("role")),
            module_code=module_code,
            module_meta=meta,
            default_date=work_date.isoformat(),
            default_tax_period=(request.args.get("tax_period") or "").strip() or default_tax_period(),
            customer_id=(request.args.get("customer_id") or "").strip(),
            customer_name=(request.args.get("customer_name") or "").strip(),
            bill_amount=(request.args.get("bill_amount") or "").strip(),
            next_bill_no=FollowupBillingService.next_bill_no(module_code, work_date),
            api_next_bill=url_for(f"{blueprint_name}.next_bill_no"),
        )

    @bp.route("/billing/next-bill-no", methods=["GET"], strict_slashes=False)
    @login_required
    def next_bill_no():
        work_date_raw = (request.args.get("work_date") or "").strip()
        try:
            work_date = date.fromisoformat(work_date_raw[:10]) if work_date_raw else date.today()
        except ValueError:
            work_date = date.today()
        bill_no = FollowupBillingService.next_bill_no(module_code, work_date)
        return jsonify({"ok": True, "bill_no": bill_no})

    @bp.route("/records/<int:entry_id>/thank-you-letter", methods=["GET"], strict_slashes=False)
    @login_required
    def thank_you_letter(entry_id: int):
        service = FollowupService(module_code)
        try:
            record = service.get_entry(entry_id)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404
        stage_codes = {
            (s.get("StageCode") or "").lower()
            for s in record.get("completed_stages", [])
        }
        # ITR: thank-you letter only after Payment Received; other modules keep tally-bill rule.
        if module_code == "ITR":
            has_payment = (
                "payment_received" in stage_codes
                or record.get("workflow_status") == "Payment Received"
            )
            if not has_payment:
                return jsonify(
                    {
                        "ok": False,
                        "error": "Thank You letter is available only after Payment Received.",
                    }
                ), 400
        else:
            has_tally = (
                "tally_bill_generated" in stage_codes
                or bool(record.get("bill_no"))
                or record.get("workflow_status") == "Tally Bill Generated"
            )
            if not has_tally:
                return jsonify({"ok": False, "error": "Tally bill is not generated for this entry."}), 400
        fmt = (request.args.get("format") or "jpg").strip().lower()
        letter_amount = (
            FollowupService.received_amount_for_letter(record)
            if module_code == "ITR"
            else (record.get("bill_amount") or 0)
        )
        kwargs = {
            "customer_name": record.get("customer_name") or "",
            "amount": letter_amount,
            "bill_date": None,
            "invoice_no": record.get("bill_no") or "",
        }
        if module_code == "ITR":
            pay_svc = FollowupPaymentService(module_code)
            account = pay_svc.payment_account_for_letter(record.get("bill_no") or "")
            if not (account or "").strip():
                labels = []
                for payment in record.get("payments") or []:
                    label = (
                        payment.get("label")
                        or payment.get("masked_account_number")
                        or payment.get("account_number")
                        or payment.get("bank_name")
                        or ""
                    ).strip()
                    if label and label != "Udhaar" and label not in labels:
                        labels.append(label)
                account = ", ".join(labels)
            kwargs["payment_account"] = ThankYouLetterService.format_payment_account(account)
            udhaar_amt = FollowupService.udhaar_amount_for_record(record)
            if udhaar_amt > 0.001:
                try:
                    udhaar_disp = (
                        f"{int(round(udhaar_amt)):,}"
                        if abs(udhaar_amt - round(udhaar_amt)) < 0.001
                        else f"{udhaar_amt:,.2f}"
                    )
                except (TypeError, ValueError):
                    udhaar_disp = str(udhaar_amt)
                kwargs["payment_note"] = (
                    f"Partial payment received. Balance: Rs. {udhaar_disp}"
                )
        raw_date = record.get("bill_date")
        if raw_date:
            try:
                kwargs["bill_date"] = date.fromisoformat(str(raw_date)[:10])
            except ValueError:
                kwargs["bill_date"] = date.today()
        if fmt == "png":
            data = ThankYouLetterService.generate_png(**kwargs)
            mime = "image/png"
            ext = "png"
        else:
            data = ThankYouLetterService.generate_jpg(**kwargs)
            mime = "image/jpeg"
            ext = "jpg"
        safe_name = (record.get("customer_name") or "Customer").replace(" ", "_")[:40]
        filename = f"Thanking_Letter_{safe_name}_{record.get('tax_period') or 'FY'}.{ext}"
        return send_file(
            io.BytesIO(data),
            mimetype=mime,
            as_attachment=True,
            download_name=filename,
        )

    if module_code == "ITR":

        @bp.route("/records/<int:entry_id>/payment-reminder", methods=["GET"], strict_slashes=False)
        @login_required
        def payment_reminder(entry_id: int):
            """PNG payment reminder — available after Tally Bill Generated (payment pending)."""
            service = FollowupService(module_code)
            try:
                record = service.get_entry(entry_id)
            except ValueError as exc:
                return jsonify({"ok": False, "error": str(exc)}), 404

            stage_codes = {
                (s.get("StageCode") or "").lower()
                for s in record.get("completed_stages", [])
            }
            has_tally = (
                "tally_bill_generated" in stage_codes
                or bool(record.get("bill_no"))
                or record.get("workflow_status") == "Tally Bill Generated"
            )
            has_payment = (
                "payment_received" in stage_codes
                or record.get("workflow_status") == "Payment Received"
            )
            if not has_tally:
                return jsonify(
                    {"ok": False, "error": "Payment reminder is available after Tally Bill Generated."}
                ), 400
            if has_payment:
                return jsonify(
                    {"ok": False, "error": "Payment already received. Use Thank You letter instead."}
                ), 400

            amount = record.get("bill_amount") or 0

            def _parse_iso(raw):
                if not raw:
                    return None
                try:
                    return date.fromisoformat(str(raw)[:10])
                except ValueError:
                    return None

            bill_date = _parse_iso(record.get("bill_date"))
            work_date = _parse_iso(record.get("work_date"))
            work_type = (meta.get("work_type_label") or "ITR").strip() or "ITR"

            upi_id, payee_name = PaymentReminderService.resolve_upi_payee()
            data = PaymentReminderService.generate_png(
                customer_name=record.get("customer_name") or "",
                bill_no=record.get("bill_no") or "",
                bill_date=bill_date,
                work_date=work_date,
                period=str(record.get("tax_period") or "").strip(),
                work_type=work_type,
                return_type=str(record.get("return_type") or "").strip(),
                amount=amount,
                upi_id=upi_id,
                payee_name=payee_name or "JTCS",
            )
            safe_name = (record.get("customer_name") or "Customer").replace(" ", "_")[:40]
            filename = f"Payment_Reminder_{safe_name}_{record.get('bill_no') or entry_id}.png"
            return send_file(
                io.BytesIO(data),
                mimetype="image/png",
                as_attachment=True,
                download_name=filename,
            )

    @bp.route("/customers/search", methods=["GET"], strict_slashes=False)
    @login_required
    def customer_search():
        query = (request.args.get("q") or request.args.get("query") or "").strip()
        rows = CustomerService().search(query)
        return jsonify({"ok": True, "rows": rows})

    if allow_customer_create:

        @bp.route("/customers", methods=["POST"], strict_slashes=False)
        @login_required
        def customer_create():
            payload = request.get_json(silent=True) or request.form.to_dict()
            try:
                customer = CustomerService().create(payload)
                return jsonify({"ok": True, "customer": customer, "message": "Customer added successfully."})
            except ValueError as exc:
                return jsonify({"ok": False, "error": str(exc)}), 400

    return bp


itr_followup_bp = _make_activity_blueprint("ITR", "/itr/followup", "itr_followup", allow_customer_create=True)
dsc_followup_bp = _make_activity_blueprint("DSC", "/dsc/followup", "dsc_followup", allow_customer_create=True)
tds_followup_bp = _make_activity_blueprint("TDS", "/tds/followup", "tds_followup", allow_customer_create=False)
gst_followup_bp = _make_activity_blueprint("GST", "/gst/followup", "gst_followup", allow_customer_create=True)

# Spec alias: POST /api/itr/sync-status (same handler as ITR Followup Sync)
api_itr_bp = Blueprint("api_itr", __name__, url_prefix="/api/itr")


@api_itr_bp.route("/sync-status", methods=["POST"], strict_slashes=False)
@login_required
def api_itr_sync_status():
    from flask import current_app

    from app.services.itr_kdk_sync_service import ItrKdkSyncService

    payload = request.get_json(silent=True) or request.form.to_dict()
    user_id = (payload.get("user_id") or payload.get("userid") or "").strip()
    password = payload.get("password") or ""
    headless_raw = str(payload.get("headless") or "1").strip().lower()
    headless = headless_raw not in {"0", "false", "no", "off"}
    entry_raw = payload.get("entry_id")
    entry_id = None
    if entry_raw not in (None, ""):
        try:
            entry_id = int(entry_raw)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Invalid entry_id."}), 400
    try:
        result = ItrKdkSyncService().start_sync(
            user_id=user_id,
            password=password,
            app=current_app._get_current_object(),
            headless=headless,
            entry_id=entry_id,
        )
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc) or "Unable to start sync."}), 500


@api_itr_bp.route("/sync-status/<job_id>", methods=["GET"], strict_slashes=False)
@login_required
def api_itr_sync_job(job_id: str):
    from app.services.itr_kdk_sync_service import ItrKdkSyncService

    job = ItrKdkSyncService().get_job(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Sync job not found."}), 404
    return jsonify({"ok": True, "job": job})
