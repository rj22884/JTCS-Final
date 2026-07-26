from datetime import date
from decimal import Decimal

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required, require_delete_reauth
from app.repositories.transaction_repository import MasterRepository
from app.repositories.user_repository import UserRepository
from app.services.ecourt_service import ECourtService
from app.services.menu_service import MenuService

bp = Blueprint("ecourt", __name__, url_prefix="/shcil")

# Import window only — show every PDF amount in this range (does not change main e-Court).
ECOURT_IMPORT_MIN_AMOUNT = Decimal("1")
ECOURT_IMPORT_MAX_AMOUNT = Decimal("999999999")
ECOURT_IMPORT_SMALL_AMOUNT_MAX = Decimal("10")
ECOURT_IMPORT_AUTO_STN_MIN = Decimal("11")


@bp.route("/ecourt-activity", strict_slashes=False)
@login_required
def ecourt_activity():
    menu_service = MenuService()
    master_repo = MasterRepository()
    latest = ECourtService().repo.latest_batch()
    current_user = UserRepository().get_by_id(int(session.get("user_id") or 0))
    return render_template(
        "ecourt/activity.html",
        page_title="e-Court Activity",
        breadcrumb=menu_service.get_breadcrumb("/shcil/ecourt-activity", session.get("role")),
        latest_import_id=latest.ImportID if latest else None,
        latest_import_name=latest.FileName if latest else "",
        latest_import_count=latest.RecordCount if latest else 0,
        payment_modes=master_repo.list_stamp_bank_payment_modes(),
        default_date=date.today().isoformat(),
        current_login_id=(current_user.EmailID if current_user else "") or "",
    )


@bp.route("/ecourt-activity/parse-pdf", methods=["POST"])
@login_required
def parse_pdf():
    upload = request.files.get("receipt_pdf")
    if upload is None or not upload.filename:
        return jsonify({"ok": False, "error": "Select a PDF file to read."}), 400
    if not upload.filename.lower().endswith(".pdf"):
        return jsonify({"ok": False, "error": "Only PDF files are supported."}), 400

    try:
        result = ECourtService().parse_pdf_preview(upload.read(), file_name=upload.filename)
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unable to read PDF: {exc}"}), 500


@bp.route("/ecourt-activity/import", methods=["POST"])
@login_required
def import_rows():
    payload = request.get_json(silent=True) or {}
    try:
        result = ECourtService().import_rows(payload, imported_by=session.get("user_name", "System"))
        from app.extensions import db

        db.session.commit()
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        from app.extensions import db

        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        from app.extensions import db

        db.session.rollback()
        return jsonify({"ok": False, "error": f"Unable to import rows: {exc}"}), 500


@bp.route("/ecourt-activity/import-lines")
@login_required
def import_lines():
    import_id = request.args.get("import_id", type=int)
    try:
        result = ECourtService().list_import_tree(import_id)
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unable to load imported data: {exc}"}), 500


@bp.route("/ecourt-activity/summary")
@login_required
def ecourt_activity_summary():
    try:
        summary = ECourtService().activity_summary()
        return jsonify({"ok": True, "summary": summary})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/ecourt-activity/search")
@login_required
def search_stationery():
    stationery = (request.args.get("stationery") or request.args.get("stationery_no") or "").strip()
    import_id = request.args.get("import_id", type=int)
    try:
        result = ECourtService().search_stationery(stationery, import_id=import_id)
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unable to search stationery: {exc}"}), 500


@bp.route("/ecourt-activity/sell", methods=["POST"])
@login_required
def sell_receipts():
    receipt_numbers = []
    if hasattr(request.form, "getlist"):
        receipt_numbers = list(request.form.getlist("ReceiptNo[]") or request.form.getlist("receipt_no[]") or [])
    if not receipt_numbers:
        payload = request.get_json(silent=True) or {}
        receipt_numbers = payload.get("receipt_numbers") or payload.get("receipt_nos") or []

    try:
        result = ECourtService().save_receipt_sales(
            request.form,
            receipt_numbers,
            created_by=session.get("user_name", "System"),
        )
        from app.extensions import db

        db.session.commit()
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        from app.extensions import db

        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        from app.extensions import db

        db.session.rollback()
        return jsonify({"ok": False, "error": f"Unable to save sale: {exc}"}), 500


@bp.route("/ecourt-activity/unsell", methods=["POST"])
@login_required
def unsell_receipts():
    payload = request.get_json(silent=True) or {}
    receipt_numbers = payload.get("receipt_numbers") or payload.get("receipt_nos") or []
    if not receipt_numbers and hasattr(request.form, "getlist"):
        receipt_numbers = list(
            request.form.getlist("ReceiptNo[]") or request.form.getlist("receipt_no[]") or []
        )

    try:
        result = ECourtService().unsell_receipts(receipt_numbers)
        from app.extensions import db

        db.session.commit()
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        from app.extensions import db

        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        from app.extensions import db

        db.session.rollback()
        return jsonify({"ok": False, "error": f"Unable to unsell receipts: {exc}"}), 500


@bp.route("/ecourt-activity/manual", methods=["POST"])
@login_required
def manual_sale():
    try:
        result = ECourtService().save_manual_sale(
            request.form,
            created_by=session.get("user_name", "System"),
        )
        from app.extensions import db

        db.session.commit()
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        from app.extensions import db

        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/ecourt-activity/sales")
@login_required
def recent_sales():
    rows = ECourtService().list_recent_sales()
    return jsonify({"ok": True, "rows": rows, "count": len(rows)})


@bp.route("/ecourt-activity/delete-stationery", methods=["POST"])
@login_required
@require_delete_reauth
def delete_stationery():
    """Permanently delete a fully Not Sold stationery (hard delete from SQL).

    Requires logged-in user's User ID + password confirmation.
    """
    payload = request.get_json(silent=True) or {}
    stationery = (payload.get("stationerynumber") or payload.get("stationery_no") or "").strip()
    try:
        result = ECourtService().delete_unsold_stationery(stationery)
        from app.extensions import db

        db.session.commit()
        result["message"] = (
            f"Permanently deleted stationery '{stationery}' "
            f"({result.get('record_count') or 0} receipt(s)) from database. "
            "This cannot be rolled back."
        )
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        from app.extensions import db

        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        from app.extensions import db

        db.session.rollback()
        return jsonify({"ok": False, "error": f"Unable to delete stationery: {exc}"}), 500


@bp.route("/ecourt-activity/import", strict_slashes=False)
@login_required
def ecourt_activity_import():
    """PDF import UI (former ecourt-import-test), under e-Court Activity."""
    menu_service = MenuService()
    return render_template(
        "ecourt/import_test.html",
        page_title="e-Court Activity",
        breadcrumb=menu_service.get_breadcrumb("/shcil/ecourt-activity", session.get("role")),
    )


@bp.route("/ecourt-import-test", strict_slashes=False)
@login_required
def ecourt_import_test():
    """Legacy URL → renamed import under e-Court Activity."""
    return redirect(url_for("ecourt.ecourt_activity_import"))


def _ecourt_test_existing_receipt_details(service: ECourtService, receipt_numbers: list[str]) -> dict[str, dict]:
    """Chunked DB lookup so large PDFs do not hit SQL Server IN-parameter limits."""
    normalized = sorted(
        {(value or "").strip().upper() for value in receipt_numbers if (value or "").strip()}
    )
    details: dict[str, dict] = {}
    chunk_size = 400
    for start in range(0, len(normalized), chunk_size):
        chunk = normalized[start : start + chunk_size]
        details.update(service.repo.existing_imported_receipt_details(chunk))
    return details


def _ecourt_test_sold_stationery_numbers(service: ECourtService, stationery_numbers: list[str]) -> list[str]:
    """Return stationery numbers that are fully Sold (all receipts sold)."""
    return sorted(service.repo.fully_sold_stationery_numbers(stationery_numbers))


def _ecourt_test_amount_band(amount_dec) -> tuple[str, int, bool]:
    """Return (band, page_size, auto_stationery) for import window only.

    - small (≤10): 20 receipts / page, manual stationery
    - mid (11–999999999): 1 receipt / page, system stationery (disabled)
    """
    if amount_dec <= ECOURT_IMPORT_SMALL_AMOUNT_MAX:
        return "small", 20, False
    if amount_dec <= ECOURT_IMPORT_MAX_AMOUNT:
        return "mid", 1, True
    return "over", 1, False


@bp.route("/ecourt-activity/import/parse-pdf", methods=["POST"])
@bp.route("/ecourt-import-test/parse-pdf", methods=["POST"])
@login_required
def ecourt_import_test_parse_pdf():
    """Parse PDF and return Amount+Date groups for the import preview grid.

    Marks receipts already present in main table so Remark shows Already Imported.
    """
    upload = request.files.get("receipt_pdf")
    if upload is None or not upload.filename:
        return jsonify({"ok": False, "error": "Select a PDF file to read."}), 400
    if not upload.filename.lower().endswith(".pdf"):
        return jsonify({"ok": False, "error": "Only PDF files are supported."}), 400

    try:
        service = ECourtService()
        report = service.pdf.parse_pdf_bytes(upload.read())

        groups_map: dict[tuple[str, str], dict] = {}
        record_count = 0
        excluded_rows: list[dict] = []
        all_receipt_nos: list[str] = []
        auto_seq = 0

        def _append_excluded(line, *, amount_text: str, reason: str) -> None:
            excluded_rows.append(
                {
                    "receipt_no": (line.receipt_no or "").strip().upper(),
                    "receipt_date": line.receipt_date.isoformat() if line.receipt_date else "",
                    "amount": amount_text,
                    "payment_mode": (line.payment_mode or "").strip(),
                    "reason": reason,
                }
            )

        def _next_auto_stationery() -> str:
            nonlocal auto_seq
            auto_seq += 1
            return f"{service._generate_high_amount_stationery()}{auto_seq:03d}"

        for line in report.lines:
            amount = line.amount
            date_value = line.receipt_date.isoformat() if line.receipt_date else ""
            if amount is None:
                _append_excluded(
                    line,
                    amount_text="",
                    reason=(
                        f"Amount missing (allowed {ECOURT_IMPORT_MIN_AMOUNT}"
                        f"–{ECOURT_IMPORT_MAX_AMOUNT})."
                    ),
                )
                continue
            try:
                amount_dec = service._decimal(amount)
            except ValueError:
                _append_excluded(
                    line,
                    amount_text=str(amount),
                    reason=(
                        f"Invalid amount (allowed {ECOURT_IMPORT_MIN_AMOUNT}"
                        f"–{ECOURT_IMPORT_MAX_AMOUNT})."
                    ),
                )
                continue
            if amount_dec == amount_dec.to_integral_value():
                amount_text = str(int(amount_dec))
            else:
                amount_text = format(amount_dec.quantize(service._decimal("0.01")), "f")
            if amount_dec < ECOURT_IMPORT_MIN_AMOUNT or amount_dec > ECOURT_IMPORT_MAX_AMOUNT:
                _append_excluded(
                    line,
                    amount_text=amount_text,
                    reason=(
                        f"Outside amount range "
                        f"(allowed {ECOURT_IMPORT_MIN_AMOUNT}–{ECOURT_IMPORT_MAX_AMOUNT})."
                    ),
                )
                continue

            band, page_size, auto_stationery = _ecourt_test_amount_band(amount_dec)
            receipt_no = (line.receipt_no or "").strip().upper()
            key = (amount_text, date_value)
            bucket = groups_map.get(key)
            if bucket is None:
                bucket = {
                    "per_record_amt": amount_text,
                    "date": date_value,
                    "total": 0,
                    "receipts": [],
                    "amount_band": band,
                    "page_size": page_size,
                    "auto_stationery": auto_stationery,
                }
                groups_map[key] = bucket
            bucket["receipts"].append(
                {
                    "receipt_no": receipt_no,
                    "receipt_date": date_value,
                    "amount": amount_text,
                    "payment_mode": (line.payment_mode or "").strip(),
                    "receipt_status": (getattr(line, "receipt_status", None) or "").strip(),
                    "imported": False,
                    "stationerynumber": "",
                    "auto_stationery": auto_stationery,
                    "amount_band": band,
                }
            )
            if receipt_no:
                all_receipt_nos.append(receipt_no)
            bucket["total"] += 1
            record_count += 1

        if record_count <= 0:
            raise ValueError(
                f"No receipts with amount {ECOURT_IMPORT_MIN_AMOUNT}"
                f"–{ECOURT_IMPORT_MAX_AMOUNT} found in PDF."
            )

        # Flag receipts already in main table (chunked IN queries)
        existing_details = _ecourt_test_existing_receipt_details(service, all_receipt_nos)
        already_imported_count = 0
        imported_stationery_nos: list[str] = []
        for bucket in groups_map.values():
            for rec in bucket["receipts"]:
                key = (rec.get("receipt_no") or "").strip().upper()
                detail = existing_details.get(key)
                if detail:
                    rec["imported"] = True
                    stn = detail.get("stationerynumber") or ""
                    rec["stationerynumber"] = stn
                    if stn:
                        imported_stationery_nos.append(stn)
                    already_imported_count += 1

        sold_stationery_numbers = _ecourt_test_sold_stationery_numbers(
            service, imported_stationery_nos
        )
        sold_stationery_set = {value.upper() for value in sold_stationery_numbers}

        groups = []
        for bucket in groups_map.values():
            receipts = bucket["receipts"]
            page_size = int(bucket.get("page_size") or 20)
            auto_stationery = bool(bucket.get("auto_stationery"))
            amount_band = bucket.get("amount_band") or "small"
            pages = []
            for start in range(0, len(receipts), page_size):
                chunk = receipts[start : start + page_size]
                page_no = (start // page_size) + 1
                imported_in_page = sum(1 for rec in chunk if rec.get("imported"))
                page_fully_imported = imported_in_page == len(chunk) and len(chunk) > 0
                page_stationery = ""
                page_auto = auto_stationery
                if page_fully_imported:
                    for rec in chunk:
                        if rec.get("stationerynumber"):
                            page_stationery = rec["stationerynumber"]
                            break
                elif auto_stationery:
                    # Mid band (11–max): system stationery, 1 record / page
                    page_stationery = _next_auto_stationery()
                    for rec in chunk:
                        if not rec.get("imported"):
                            rec["stationerynumber"] = page_stationery
                            rec["auto_stationery"] = True
                pages.append(
                    {
                        "page_no": page_no,
                        "count": len(chunk),
                        "receipts": chunk,
                        "imported": page_fully_imported,
                        "applied": page_fully_imported,
                        "stationerynumber": page_stationery,
                        "auto_stationery": page_auto and not page_fully_imported,
                        "stationery_sold": bool(
                            page_stationery
                            and page_stationery.strip().upper() in sold_stationery_set
                        ),
                        "already_imported_count": imported_in_page,
                        "ready_count": len(chunk) - imported_in_page,
                    }
                )
            groups.append(
                {
                    "per_record_amt": bucket["per_record_amt"],
                    "date": bucket["date"],
                    "total": bucket["total"],
                    "page_count": len(pages),
                    "page_size": page_size,
                    "amount_band": amount_band,
                    "auto_stationery": auto_stationery,
                    "pages": pages,
                }
            )

        groups = sorted(
            groups,
            key=lambda item: (
                item.get("date") or "",
                service._decimal(item.get("per_record_amt") or "0"),
            ),
        )

        message = (
            f"Read {record_count} receipt(s) "
            f"(amount {ECOURT_IMPORT_MIN_AMOUNT}–{ECOURT_IMPORT_MAX_AMOUNT}). "
            f"Grouped into {len(groups)} Amount+Date row(s). "
            f"≤{ECOURT_IMPORT_SMALL_AMOUNT_MAX}: 20/page (manual stationery). "
            f"{ECOURT_IMPORT_AUTO_STN_MIN}–{ECOURT_IMPORT_MAX_AMOUNT}: 1/page (system stationery)."
        )
        if already_imported_count:
            message += f" {already_imported_count} receipt(s) already in main table (Already Imported)."
        if excluded_rows:
            message += f" {len(excluded_rows)} row(s) excluded (see list below)."

        return jsonify(
            {
                "ok": True,
                "file_name": upload.filename,
                "report_from": report.report_from.isoformat() if report.report_from else "",
                "report_to": report.report_to.isoformat() if report.report_to else "",
                "state_name": report.state_name or "",
                "total_amount": str(report.total_amount or ""),
                "message": message,
                "record_count": record_count,
                "already_imported_count": already_imported_count,
                "sold_stationery_numbers": sold_stationery_numbers,
                "excluded_count": len(excluded_rows),
                "excluded_rows": excluded_rows,
                "group_count": len(groups),
                "groups": groups,
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unable to read PDF: {exc}"}), 500


@bp.route("/ecourt-activity/import/import-page", methods=["POST"])
@bp.route("/ecourt-import-test/import-page", methods=["POST"])
@login_required
def ecourt_import_test_import_page():
    """Import one page with a unique stationery number.

    ≤10: up to 20 receipts / page (manual stationery).
    11–999999999: 1 receipt / page (system stationery).
    """
    payload = request.get_json(silent=True) or {}
    stationery = (payload.get("stationerynumber") or payload.get("stationery_no") or "").strip()
    rows = payload.get("rows") or []

    if not stationery:
        return jsonify({"ok": False, "error": "Stationery Number is required."}), 400
    if not rows:
        return jsonify({"ok": False, "error": "No receipt rows to import."}), 400

    try:
        service = ECourtService()

        sample_amount = service._decimal(
            (rows[0].get("amount") or rows[0].get("Amount") or "0")
        )
        if sample_amount < ECOURT_IMPORT_MIN_AMOUNT or sample_amount > ECOURT_IMPORT_MAX_AMOUNT:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": (
                            f"Amount must be between {ECOURT_IMPORT_MIN_AMOUNT} "
                            f"and {ECOURT_IMPORT_MAX_AMOUNT}."
                        ),
                    }
                ),
                400,
            )
        _band, max_rows, _auto = _ecourt_test_amount_band(sample_amount)
        if len(rows) > max_rows:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": (
                            f"This amount band allows at most {max_rows} receipt(s) per page "
                            f"(got {len(rows)})."
                        ),
                    }
                ),
                400,
            )

        existing_stn = service.repo.list_lines_for_stationery(stationery, exact=True)
        if existing_stn:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": (
                            f"Stationery number '{stationery}' already exists in main table "
                            f"({len(existing_stn)} receipt(s)). Choose another."
                        ),
                    }
                ),
                400,
            )

        import_rows = []
        seen_receipts: set[str] = set()
        for row in rows:
            receipt_no = (row.get("receipt_no") or row.get("ReceiptNo") or "").strip().upper()
            if not receipt_no:
                continue
            if receipt_no in seen_receipts:
                return (
                    jsonify({"ok": False, "error": f"Duplicate Receipt No. in page: {receipt_no}."}),
                    400,
                )
            seen_receipts.add(receipt_no)
            import_rows.append(
                {
                    "receipt_no": receipt_no,
                    "receipt_date": row.get("receipt_date") or row.get("ReceiptDate") or "",
                    "amount": row.get("amount") or row.get("Amount") or "",
                    "payment_mode": row.get("payment_mode") or "",
                    "receipt_status": row.get("receipt_status") or "",
                    "remarks": row.get("remarks") or "",
                    "stationerynumber": stationery,
                }
            )

        if not import_rows:
            return jsonify({"ok": False, "error": "No valid receipt rows to import."}), 400

        existing_receipts = service.repo.existing_receipt_numbers_in_db(
            [row["receipt_no"] for row in import_rows]
        )
        if existing_receipts:
            sample = ", ".join(sorted(existing_receipts)[:5])
            more = "" if len(existing_receipts) <= 5 else f" (+{len(existing_receipts) - 5} more)"
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": (
                            f"{len(existing_receipts)} receipt number(s) already imported "
                            f"(unique). Examples: {sample}{more}"
                        ),
                    }
                ),
                400,
            )

        result = service.import_rows(
            {
                "file_name": payload.get("file_name") or "ecourt-import.pdf",
                "report_from": payload.get("report_from") or "",
                "report_to": payload.get("report_to") or "",
                "state_name": payload.get("state_name") or "",
                "total_amount": payload.get("total_amount") or "",
                "rows": import_rows,
            },
            imported_by=session.get("user_name", "System"),
            allow_any_positive_amount=True,
        )
        from app.extensions import db

        db.session.commit()
        return jsonify(
            {
                "ok": True,
                "stationerynumber": stationery,
                "record_count": result.get("record_count") or len(import_rows),
                "import_id": result.get("import_id"),
                "message": "Import Successfully",
            }
        )
    except ValueError as exc:
        from app.extensions import db

        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        from app.extensions import db

        db.session.rollback()
        return jsonify({"ok": False, "error": f"Unable to import page: {exc}"}), 500
