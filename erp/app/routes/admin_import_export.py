"""Admin Role → Import/Export (Ledger Export — bank & customer transaction ledgers)."""

from __future__ import annotations

import io
from datetime import date

from flask import Blueprint, jsonify, render_template, request, send_file, session, url_for
from sqlalchemy import text

from app.decorators import admin_required, login_required
from app.extensions import db
from app.services.ledger_export_service import LedgerExportService
from app.services.menu_service import MenuService
from app.utils.db_session import map_db_exception

bp = Blueprint("admin_import_export", __name__, url_prefix="/admin/import-export")

_MENU_ENSURED = False
MENU_PATH = "/admin/import-export/ledger"


def _ensure_import_export_menus() -> None:
    """Admin Role → Import/Export → Export → Ledger Export (idempotent)."""
    global _MENU_ENSURED
    if _MENU_ENSURED:
        return
    db.session.execute(
        text(
            """
            DECLARE @AdminRoleID INT;
            DECLARE @ImportExportID INT;
            DECLARE @AdminRoles NVARCHAR(50) = N'Administrator,Admin';

            SELECT TOP 1 @AdminRoleID = MenuID
            FROM dbo.MenuMaster
            WHERE MenuName = N'Admin Role'
              AND ParentMenuID IS NULL
            ORDER BY MenuID;

            IF @AdminRoleID IS NULL
            BEGIN
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    NULL,
                    N'Admin Role',
                    N'bi-archive',
                    NULL,
                    1,
                    N'Administrator tools',
                    1,
                    @AdminRoles
                );
                SET @AdminRoleID = SCOPE_IDENTITY();
            END;

            IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster
                WHERE ParentMenuID = @AdminRoleID AND MenuName = N'Import/Export'
            )
                UPDATE dbo.MenuMaster
                SET MenuURL = NULL,
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-arrow-left-right'),
                    DisplayOrder = 40,
                    Description = N'Import and Export tools',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE ParentMenuID = @AdminRoleID AND MenuName = N'Import/Export';
            ELSE
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    @AdminRoleID,
                    N'Import/Export',
                    N'bi-arrow-left-right',
                    NULL,
                    40,
                    N'Import and Export tools',
                    1,
                    @AdminRoles
                );

            SELECT TOP 1 @ImportExportID = MenuID
            FROM dbo.MenuMaster
            WHERE ParentMenuID = @AdminRoleID AND MenuName = N'Import/Export'
            ORDER BY MenuID;

            IF @ImportExportID IS NOT NULL
               AND NOT EXISTS (
                    SELECT 1 FROM dbo.MenuMaster
                    WHERE ParentMenuID = @ImportExportID AND MenuName = N'Export'
               )
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    @ImportExportID,
                    N'Export',
                    N'bi-upload',
                    NULL,
                    1,
                    N'Export transaction ledgers to Excel',
                    1,
                    @AdminRoles
                );
            ELSE IF @ImportExportID IS NOT NULL
                UPDATE dbo.MenuMaster
                SET MenuURL = NULL,
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-upload'),
                    DisplayOrder = 1,
                    Description = N'Export transaction ledgers to Excel',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE ParentMenuID = @ImportExportID AND MenuName = N'Export';

            DECLARE @ExportID INT;
            SELECT TOP 1 @ExportID = MenuID
            FROM dbo.MenuMaster
            WHERE ParentMenuID = @ImportExportID AND MenuName = N'Export'
            ORDER BY MenuID;

            IF @ExportID IS NOT NULL
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM dbo.MenuMaster
                    WHERE ParentMenuID = @ExportID AND MenuName = N'Ledger Export'
                )
                    UPDATE dbo.MenuMaster
                    SET MenuURL = N'/admin/import-export/ledger',
                        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-file-earmark-excel'),
                        DisplayOrder = 1,
                        Description = N'Export bank account and customer transaction ledgers to Excel',
                        IsActive = 1,
                        RoleName = @AdminRoles
                    WHERE ParentMenuID = @ExportID AND MenuName = N'Ledger Export';
                ELSE IF EXISTS (
                    SELECT 1 FROM dbo.MenuMaster
                    WHERE MenuURL = N'/admin/import-export/ledger'
                )
                    UPDATE dbo.MenuMaster
                    SET ParentMenuID = @ExportID,
                        MenuName = N'Ledger Export',
                        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-file-earmark-excel'),
                        DisplayOrder = 1,
                        Description = N'Export bank account and customer transaction ledgers to Excel',
                        IsActive = 1,
                        RoleName = @AdminRoles
                    WHERE MenuURL = N'/admin/import-export/ledger';
                ELSE
                    INSERT INTO dbo.MenuMaster (
                        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                        Description, IsActive, RoleName
                    )
                    VALUES (
                        @ExportID,
                        N'Ledger Export',
                        N'bi-file-earmark-excel',
                        N'/admin/import-export/ledger',
                        1,
                        N'Export bank account and customer transaction ledgers to Excel',
                        1,
                        @AdminRoles
                    );
            END;
            """
        )
    )
    db.session.commit()
    _MENU_ENSURED = True


def ensure_import_export_menus() -> None:
    _ensure_import_export_menus()


def _parse_date_arg(name: str) -> date | None:
    raw = (request.args.get(name) or "").strip()
    if not raw:
        return None
    return LedgerExportService._parse_date(raw, date.today())


@bp.route("/ledger", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def ledger_export_page():
    try:
        _ensure_import_export_menus()
    except Exception:
        db.session.rollback()
    service = LedgerExportService()
    return render_template(
        "admin_import_export/ledger.html",
        page_title="Ledger Export",
        breadcrumb=MenuService().get_breadcrumb(MENU_PATH, session.get("role")),
        bank_accounts=service.list_bank_accounts(),
        today=date.today().isoformat(),
        fy_start=f"{date.today().year if date.today().month >= 4 else date.today().year - 1}-04-01",
    )


@bp.route("/ledger/api/banks", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def list_banks():
    search = (request.args.get("search") or "").strip() or None
    try:
        rows = LedgerExportService().list_bank_accounts(search=search)
        return jsonify({"ok": True, "rows": rows})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/ledger/api/customers", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def list_customers():
    search = (request.args.get("search") or "").strip() or None
    try:
        rows = LedgerExportService().list_customers(search=search)
        return jsonify({"ok": True, "rows": rows})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


def _format_arg(explicit: str | None = None) -> str:
    raw = (explicit or request.args.get("format") or request.args.get("fmt") or "xlsx")
    fmt = str(raw).strip().lower()
    return "pdf" if fmt == "pdf" else "xlsx"


def _send_ledger(data: bytes, filename: str, mimetype: str):
    # Force correct extension so browsers don't treat PDF as Excel.
    if mimetype == "application/pdf" and not filename.lower().endswith(".pdf"):
        filename = f"{filename.rsplit('.', 1)[0]}.pdf"
    if (
        mimetype
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        and not filename.lower().endswith(".xlsx")
    ):
        filename = f"{filename.rsplit('.', 1)[0]}.xlsx"
    return send_file(
        io.BytesIO(data),
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
    )


def _ledger_preview_response(ledger: dict):
    html = render_template(
        "admin_import_export/_ledger_preview_html.html",
        ledger=ledger,
        logo_url=url_for("static", filename="img/jtcs_invoice_logo.png"),
    )
    return jsonify(
        {
            "ok": True,
            "html": html,
            "title": ledger.get("title") or "Ledger Preview",
            "entity_name": ledger.get("entity_name") or "",
        }
    )


@bp.route("/ledger/preview/bank/<int:account_id>", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def preview_bank_ledger(account_id: int):
    """Same-page HTML bank ledger preview (JSON: {ok, html})."""
    service = LedgerExportService()
    date_from = _parse_date_arg("date_from")
    date_to = _parse_date_arg("date_to")
    try:
        ledger = service.bank_ledger_preview_data(
            account_id, date_from=date_from, date_to=date_to
        )
        return _ledger_preview_response(ledger)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/ledger/preview/customer/<int:customer_id>", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def preview_customer_ledger(customer_id: int):
    """Same-page HTML customer ledger preview (JSON: {ok, html})."""
    service = LedgerExportService()
    date_from = _parse_date_arg("date_from")
    date_to = _parse_date_arg("date_to")
    try:
        ledger = service.customer_ledger_preview_data(
            customer_id, date_from=date_from, date_to=date_to
        )
        return _ledger_preview_response(ledger)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/ledger/download/bank/<int:account_id>", methods=["GET"], strict_slashes=False)
@bp.route(
    "/ledger/download/bank/<int:account_id>/<string:file_format>",
    methods=["GET"],
    strict_slashes=False,
)
@login_required
@admin_required
def download_bank_ledger(account_id: int, file_format: str | None = None):
    service = LedgerExportService()
    date_from = _parse_date_arg("date_from")
    date_to = _parse_date_arg("date_to")
    fmt = _format_arg(file_format)
    try:
        data, filename, mimetype = service.build_bank_ledger(
            account_id, date_from=date_from, date_to=date_to, fmt=fmt
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return _send_ledger(data, filename, mimetype)


@bp.route("/ledger/download/customer/<int:customer_id>", methods=["GET"], strict_slashes=False)
@bp.route(
    "/ledger/download/customer/<int:customer_id>/<string:file_format>",
    methods=["GET"],
    strict_slashes=False,
)
@login_required
@admin_required
def download_customer_ledger(customer_id: int, file_format: str | None = None):
    service = LedgerExportService()
    date_from = _parse_date_arg("date_from")
    date_to = _parse_date_arg("date_to")
    fmt = _format_arg(file_format)
    try:
        data, filename, mimetype = service.build_customer_ledger(
            customer_id, date_from=date_from, date_to=date_to, fmt=fmt
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return _send_ledger(data, filename, mimetype)
