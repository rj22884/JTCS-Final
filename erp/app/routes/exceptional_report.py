from datetime import date

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required
from app.extensions import db
from app.services.exceptional_stamp_report_service import ExceptionalStampReportService
from app.services.menu_service import MenuService
from sqlalchemy import text

bp = Blueprint("exceptional_report", __name__, url_prefix="/exceptional-report")

ALLOWED_EXTENSIONS = {".csv", ".txt"}
_MENU_ENSURED = False


def _ensure_exceptional_report_menus() -> None:
    """Hide Exceptional Report menu tree from navigation (rows kept, IsActive = 0)."""
    global _MENU_ENSURED
    if _MENU_ENSURED:
        return
    db.session.execute(
        text(
            """
            DECLARE @ParentID INT;

            SELECT TOP 1 @ParentID = MenuID
            FROM dbo.MenuMaster
            WHERE MenuName = N'Exceptional Report'
              AND ParentMenuID IS NULL
            ORDER BY MenuID;

            IF @ParentID IS NOT NULL
            BEGIN
                UPDATE dbo.MenuMaster
                SET IsActive = 0,
                    Description = N'Exceptional and special reports (hidden from nav)'
                WHERE MenuID = @ParentID;

                UPDATE dbo.MenuMaster
                SET IsActive = 0
                WHERE ParentMenuID = @ParentID
                   OR MenuURL LIKE N'/exceptional-report/%'
                   OR MenuName IN (N'Stamp Exception', N'e-Court Exception', N'Stamp Certificate Reconciliation');
            END
            ELSE
            BEGIN
                /* No parent row — still hide any orphan exceptional-report links */
                UPDATE dbo.MenuMaster
                SET IsActive = 0
                WHERE MenuURL LIKE N'/exceptional-report/%'
                   OR MenuName IN (N'Stamp Exception', N'e-Court Exception', N'Stamp Certificate Reconciliation');
            END;
            """
        )
    )
    db.session.commit()
    _MENU_ENSURED = True


@bp.before_app_request
def ensure_menus_once_per_process():
    if request.blueprint != bp.name:
        return None
    try:
        _ensure_exceptional_report_menus()
    except Exception:
        db.session.rollback()
    return None


@bp.route("/", strict_slashes=False)
@bp.route("", strict_slashes=False)
@login_required
def index():
    return redirect(url_for("exceptional_report.stamp_certificate"))


@bp.route("/stamp-certificate", strict_slashes=False)
@login_required
def stamp_certificate():
    _ensure_exceptional_report_menus()
    menu_service = MenuService()
    return render_template(
        "exceptional_report/stamp_certificate.html",
        page_title="Stamp Exception",
        breadcrumb=menu_service.get_breadcrumb(
            "/exceptional-report/stamp-certificate",
            session.get("role"),
        ),
        default_date=date.today().isoformat(),
    )


@bp.route("/ecourt-exception", strict_slashes=False)
@login_required
def ecourt_exception():
    """Placeholder — e-Court Exception work will be done later."""
    _ensure_exceptional_report_menus()
    menu_service = MenuService()
    return render_template(
        "exceptional_report/ecourt_exception.html",
        page_title="e-Court Exception",
        breadcrumb=menu_service.get_breadcrumb(
            "/exceptional-report/ecourt-exception",
            session.get("role"),
        ),
    )


@bp.route("/stamp-certificate/state", methods=["GET"])
@login_required
def stamp_certificate_state():
    try:
        result = ExceptionalStampReportService.page_state()
        db.session.commit()
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": f"Unable to load page state: {exc}"}), 500


@bp.route("/stamp-certificate/compare", methods=["POST"])
@login_required
def stamp_certificate_compare():
    """Parse CSV and return preview/compare results. Does not save to SQL."""
    upload = request.files.get("stamp_file")
    if upload is None or not upload.filename:
        return jsonify({"ok": False, "error": "Select a SHCIL CSV file to upload."}), 400

    file_name = upload.filename.strip()
    extension = file_name[file_name.rfind(".") :].lower() if "." in file_name else ""
    if extension not in ALLOWED_EXTENSIONS:
        return jsonify(
            {
                "ok": False,
                "error": "Only CSV files are supported. Export the SHCIL report as CSV and upload it.",
            }
        ), 400

    try:
        result = ExceptionalStampReportService.compare_upload(
            upload.read(),
            file_name=file_name,
            uploaded_by=session.get("user_name") or session.get("user_email") or "System",
        )
        # Commit so ensure_schema DDL is persisted; compare itself does not insert rows.
        db.session.commit()
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": f"Unable to compare file: {exc}"}), 500


@bp.route("/stamp-certificate/import", methods=["POST"])
@login_required
def stamp_certificate_import():
    """Final Import — save reviewed rows into ExceptionalStampImport (+ upload history)."""
    payload = request.get_json(silent=True) or {}
    rows = payload.get("rows") or []
    file_name = (payload.get("file_name") or "").strip()
    date_from_raw = (payload.get("date_from") or "").strip()
    date_to_raw = (payload.get("date_to") or "").strip()

    date_from = None
    date_to = None
    try:
        if date_from_raw:
            date_from = date.fromisoformat(date_from_raw[:10])
        if date_to_raw:
            date_to = date.fromisoformat(date_to_raw[:10])
        result = ExceptionalStampReportService.final_import(
            rows,
            file_name=file_name,
            date_from=date_from,
            date_to=date_to,
            imported_by=session.get("user_name") or session.get("user_email") or "System",
        )
        db.session.commit()
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": f"Unable to import rows: {exc}"}), 500
