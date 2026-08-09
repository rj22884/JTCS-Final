"""Admin Role → Import/Export (legacy Ledger Export APIs).

Ledger Preview / PDF / Excel lives under Reports and Analysis → Ledger Report.
Duplicate Admin menu entries are deactivated and the page redirects there.
"""

from __future__ import annotations

import io
from datetime import date

from flask import Blueprint, jsonify, redirect, render_template, request, send_file, url_for
from sqlalchemy import text

from app.decorators import admin_required, login_required
from app.extensions import db
from app.services.ledger_export_service import LedgerExportService
from app.utils.db_session import map_db_exception

bp = Blueprint("admin_import_export", __name__, url_prefix="/admin/import-export")

_MENU_ENSURED = False
MENU_PATH = "/admin/import-export/ledger"


def _ensure_import_export_menus() -> None:
    """Retire duplicate Admin Ledger Export menus (merged into Reports and Analysis)."""
    global _MENU_ENSURED
    if _MENU_ENSURED:
        return
    db.session.execute(
        text(
            """
            DECLARE @AdminRoleID INT;
            DECLARE @ImportExportID INT;
            DECLARE @ExportID INT;
            DECLARE @ReportsID INT;

            SELECT TOP 1 @AdminRoleID = MenuID
            FROM dbo.MenuMaster
            WHERE MenuName = N'Admin Role'
              AND ParentMenuID IS NULL
            ORDER BY MenuID;

            SELECT TOP 1 @ReportsID = MenuID
            FROM dbo.MenuMaster
            WHERE ParentMenuID IS NULL
              AND MenuName IN (N'Reports and Analysis', N'Reports & Analysis', N'Reports')
            ORDER BY
                CASE MenuName
                    WHEN N'Reports and Analysis' THEN 0
                    WHEN N'Reports & Analysis' THEN 1
                    ELSE 2
                END,
                MenuID;

            -- Keep / restore the canonical Ledger Report under Reports and Analysis.
            IF @ReportsID IS NOT NULL
            BEGIN
                UPDATE dbo.MenuMaster
                SET MenuName = N'Reports and Analysis',
                    IsActive = 1,
                    MenuURL = NULL
                WHERE MenuID = @ReportsID;

                IF EXISTS (
                    SELECT 1 FROM dbo.MenuMaster
                    WHERE ParentMenuID = @ReportsID AND MenuName = N'Ledger Report'
                )
                    UPDATE dbo.MenuMaster
                    SET MenuURL = N'/Reports_and_analysis/ledger_report',
                        MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-journal-text'),
                        Description = N'Search and preview bank, customer, work/category and item ledgers',
                        IsActive = 1
                    WHERE ParentMenuID = @ReportsID AND MenuName = N'Ledger Report';
                ELSE
                    INSERT INTO dbo.MenuMaster (
                        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                        Description, IsActive, RoleName
                    )
                    VALUES (
                        @ReportsID,
                        N'Ledger Report',
                        N'bi-journal-text',
                        N'/Reports_and_analysis/ledger_report',
                        1,
                        N'Search and preview bank, customer, work/category and item ledgers',
                        1,
                        NULL
                    );
            END;

            SELECT TOP 1 @ImportExportID = MenuID
            FROM dbo.MenuMaster
            WHERE @AdminRoleID IS NOT NULL
              AND ParentMenuID = @AdminRoleID
              AND MenuName = N'Import/Export'
            ORDER BY MenuID;

            SELECT TOP 1 @ExportID = MenuID
            FROM dbo.MenuMaster
            WHERE @ImportExportID IS NOT NULL
              AND ParentMenuID = @ImportExportID
              AND MenuName = N'Export'
            ORDER BY MenuID;

            -- Hide duplicate Admin → Import/Export → Export → Ledger Export tree.
            UPDATE dbo.MenuMaster
            SET IsActive = 0,
                Description = N'Merged into Reports and Analysis → Ledger Report'
            WHERE MenuURL = N'/admin/import-export/ledger'
               OR (
                    @ExportID IS NOT NULL
                    AND ParentMenuID = @ExportID
                    AND MenuName = N'Ledger Export'
               );

            IF @ExportID IS NOT NULL
               AND NOT EXISTS (
                    SELECT 1 FROM dbo.MenuMaster
                    WHERE ParentMenuID = @ExportID
                      AND ISNULL(IsActive, 0) = 1
                      AND MenuName <> N'Ledger Export'
               )
                UPDATE dbo.MenuMaster
                SET IsActive = 0,
                    Description = N'Merged into Reports and Analysis → Ledger Report'
                WHERE MenuID = @ExportID;

            IF @ImportExportID IS NOT NULL
               AND NOT EXISTS (
                    SELECT 1 FROM dbo.MenuMaster
                    WHERE ParentMenuID = @ImportExportID
                      AND ISNULL(IsActive, 0) = 1
               )
                UPDATE dbo.MenuMaster
                SET IsActive = 0,
                    Description = N'Merged into Reports and Analysis → Ledger Report'
                WHERE MenuID = @ImportExportID;
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
    """Legacy URL — redirect to Reports and Analysis → Ledger Report."""
    try:
        _ensure_import_export_menus()
    except Exception:
        db.session.rollback()
    return redirect(url_for("ledger_report.index"))


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
