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
    global _MENU_ENSURED
    if _MENU_ENSURED:
        return
    db.session.execute(
        text(
            """
            DECLARE @StockOrder INT = (
                SELECT TOP 1 DisplayOrder FROM dbo.MenuMaster
                WHERE MenuName = N'Stock' AND ParentMenuID IS NULL
            );
            DECLARE @TargetOrder INT = ISNULL(@StockOrder, 27) + 1;
            DECLARE @ParentID INT;

            /* Top-level Exceptional Report = dropdown parent (no direct URL) */
            SELECT TOP 1 @ParentID = MenuID
            FROM dbo.MenuMaster
            WHERE MenuName = N'Exceptional Report'
              AND ParentMenuID IS NULL
            ORDER BY MenuID;

            IF @ParentID IS NULL
            BEGIN
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName
                )
                VALUES (
                    NULL,
                    N'Exceptional Report',
                    N'bi-clipboard-data',
                    NULL,
                    @TargetOrder,
                    N'Exceptional and special reports',
                    1,
                    NULL
                );
                SET @ParentID = SCOPE_IDENTITY();
            END
            ELSE
            BEGIN
                UPDATE dbo.MenuMaster
                SET DisplayOrder = @TargetOrder,
                    MenuURL = NULL,
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-clipboard-data'),
                    Description = COALESCE(Description, N'Exceptional and special reports'),
                    IsActive = 1
                WHERE MenuID = @ParentID;
            END;

            UPDATE dbo.MenuMaster
            SET IsActive = 0
            WHERE MenuName = N'Exceptional Report'
              AND ParentMenuID IS NULL
              AND MenuID <> @ParentID;

            /* Move / rename existing stamp page under Stamp Exception */
            UPDATE dbo.MenuMaster
            SET ParentMenuID = @ParentID,
                MenuName = N'Stamp Exception',
                MenuIcon = N'bi-file-earmark-spreadsheet',
                MenuURL = N'/exceptional-report/stamp-certificate',
                DisplayOrder = 1,
                Description = N'SHCIL stamp certificate reconciliation',
                IsActive = 1
            WHERE MenuURL = N'/exceptional-report/stamp-certificate'
               OR (
                    ParentMenuID = @ParentID
                    AND MenuName IN (N'Stamp Certificate Reconciliation', N'Stamp Exception')
               );

            IF NOT EXISTS (
                SELECT 1 FROM dbo.MenuMaster
                WHERE ParentMenuID = @ParentID
                  AND MenuURL = N'/exceptional-report/stamp-certificate'
            )
            BEGIN
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName
                )
                VALUES (
                    @ParentID,
                    N'Stamp Exception',
                    N'bi-file-earmark-spreadsheet',
                    N'/exceptional-report/stamp-certificate',
                    1,
                    N'SHCIL stamp certificate reconciliation',
                    1,
                    NULL
                );
            END;

            /* e-Court Exception submenu (placeholder for later work) */
            IF NOT EXISTS (
                SELECT 1 FROM dbo.MenuMaster
                WHERE ParentMenuID = @ParentID
                  AND (
                      MenuURL = N'/exceptional-report/ecourt-exception'
                      OR MenuName = N'e-Court Exception'
                  )
            )
            BEGIN
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder, Description, IsActive, RoleName
                )
                VALUES (
                    @ParentID,
                    N'e-Court Exception',
                    N'bi-journal-check',
                    N'/exceptional-report/ecourt-exception',
                    2,
                    N'e-Court exceptional report (coming soon)',
                    1,
                    NULL
                );
            END
            ELSE
            BEGIN
                UPDATE dbo.MenuMaster
                SET MenuName = N'e-Court Exception',
                    MenuIcon = N'bi-journal-check',
                    MenuURL = N'/exceptional-report/ecourt-exception',
                    DisplayOrder = 2,
                    Description = N'e-Court exceptional report (coming soon)',
                    IsActive = 1,
                    ParentMenuID = @ParentID
                WHERE ParentMenuID = @ParentID
                  AND (
                      MenuURL = N'/exceptional-report/ecourt-exception'
                      OR MenuName = N'e-Court Exception'
                  );
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
