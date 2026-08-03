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
    """Move Stamp / e-Court Exception under Reports and Analysis (after Ledger Report).

    Keeps existing module URLs. Hides only the old Exceptional Report parent.
    Does not change or remove any other menus.
    """
    global _MENU_ENSURED
    if _MENU_ENSURED:
        return
    db.session.execute(
        text(
            """
            DECLARE @ReportsID INT;
            DECLARE @LedgerOrder INT;
            DECLARE @StampOrder INT;
            DECLARE @EcourtOrder INT;
            DECLARE @ReportsOrder INT = (
                SELECT TOP 1 DisplayOrder FROM dbo.MenuMaster
                WHERE MenuName IN (N'Reports', N'Reports and Analysis', N'Reports & Analysis')
                  AND ParentMenuID IS NULL
                ORDER BY MenuID
            );

            /* Hide old Exceptional Report parent only (children are relocated below) */
            UPDATE dbo.MenuMaster
            SET IsActive = 0,
                Description = N'Exceptional and special reports (hidden from nav; children under Reports and Analysis)'
            WHERE MenuName = N'Exceptional Report'
              AND ParentMenuID IS NULL;

            SELECT TOP 1 @ReportsID = MenuID
            FROM dbo.MenuMaster
            WHERE ParentMenuID IS NULL
              AND (
                    MenuURL = N'/Reports_and_analysis'
                 OR MenuName IN (
                        N'Reports and Analysis',
                        N'Reports & Analysis',
                        N'Reports_and_analysis'
                    )
              )
            ORDER BY MenuID;

            IF @ReportsID IS NULL
            BEGIN
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    NULL,
                    N'Reports and Analysis',
                    N'bi-graph-up',
                    NULL,
                    ISNULL(@ReportsOrder, 50),
                    N'Reports and analysis',
                    1,
                    NULL
                );
                SET @ReportsID = SCOPE_IDENTITY();
            END
            ELSE
                UPDATE dbo.MenuMaster SET IsActive = 1 WHERE MenuID = @ReportsID;

            SELECT @LedgerOrder = MAX(DisplayOrder)
            FROM dbo.MenuMaster
            WHERE ParentMenuID = @ReportsID
              AND (
                    MenuURL = N'/Reports_and_analysis/ledger_report'
                 OR MenuName = N'Ledger Report'
              );

            SET @StampOrder = ISNULL(@LedgerOrder, 10) + 10;
            SET @EcourtOrder = @StampOrder + 10;

            /* Stamp Exception → Reports and Analysis (after Ledger Report) */
            IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster
                WHERE MenuURL = N'/exceptional-report/stamp-certificate'
                   OR MenuName IN (N'Stamp Exception', N'Stamp Certificate Reconciliation')
            )
                UPDATE dbo.MenuMaster
                SET ParentMenuID = @ReportsID,
                    MenuName = N'Stamp Exception',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-file-earmark-spreadsheet'),
                    MenuURL = N'/exceptional-report/stamp-certificate',
                    DisplayOrder = @StampOrder,
                    Description = N'SHCIL stamp certificate reconciliation',
                    IsActive = 1,
                    RoleName = NULL
                WHERE MenuURL = N'/exceptional-report/stamp-certificate'
                   OR MenuName IN (N'Stamp Exception', N'Stamp Certificate Reconciliation');
            ELSE
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    @ReportsID,
                    N'Stamp Exception',
                    N'bi-file-earmark-spreadsheet',
                    N'/exceptional-report/stamp-certificate',
                    @StampOrder,
                    N'SHCIL stamp certificate reconciliation',
                    1,
                    NULL
                );

            /* e-Court Exception → Reports and Analysis (after Stamp Exception) */
            IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster
                WHERE MenuURL = N'/exceptional-report/ecourt-exception'
                   OR MenuName IN (N'e-Court Exception', N'E-Court Exception')
            )
                UPDATE dbo.MenuMaster
                SET ParentMenuID = @ReportsID,
                    MenuName = N'e-Court Exception',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-journal-check'),
                    MenuURL = N'/exceptional-report/ecourt-exception',
                    DisplayOrder = @EcourtOrder,
                    Description = N'e-Court exceptional report',
                    IsActive = 1,
                    RoleName = NULL
                WHERE MenuURL = N'/exceptional-report/ecourt-exception'
                   OR MenuName IN (N'e-Court Exception', N'E-Court Exception');
            ELSE
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    @ReportsID,
                    N'e-Court Exception',
                    N'bi-journal-check',
                    N'/exceptional-report/ecourt-exception',
                    @EcourtOrder,
                    N'e-Court exceptional report',
                    1,
                    NULL
                );

            /* Hide leftover exceptional-report URLs other than stamp and ecourt */
            UPDATE dbo.MenuMaster
            SET IsActive = 0
            WHERE MenuURL LIKE N'/exceptional-report/%'
              AND MenuURL NOT IN (
                    N'/exceptional-report/stamp-certificate',
                    N'/exceptional-report/ecourt-exception'
              );

            /* Keep a single active row per exception URL (dedupe legacy seeds) */
            ;WITH d AS (
                SELECT MenuID,
                       ROW_NUMBER() OVER (
                           PARTITION BY MenuURL
                           ORDER BY MenuID
                       ) AS rn
                FROM dbo.MenuMaster
                WHERE MenuURL IN (
                    N'/exceptional-report/stamp-certificate',
                    N'/exceptional-report/ecourt-exception'
                )
            )
            UPDATE m
            SET IsActive = 0
            FROM dbo.MenuMaster m
            INNER JOIN d ON d.MenuID = m.MenuID
            WHERE d.rn > 1;
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
