"""Reports & Analysis → Ledger Report."""

from __future__ import annotations

import io
from datetime import date

from flask import Blueprint, jsonify, render_template, request, send_file, session, url_for
from sqlalchemy import text

from app.decorators import login_required
from app.extensions import db
from app.services.ledger_report_service import LedgerReportService
from app.services.menu_service import MenuService
from app.utils.db_session import map_db_exception

bp = Blueprint(
    "ledger_report",
    __name__,
    url_prefix="/Reports_and_analysis/ledger_report",
)

MENU_PATH = "/Reports_and_analysis/ledger_report"
_MENU_ENSURED = False


def _ensure_ledger_report_menu() -> None:
    """Ensure Reports and Analysis → Ledger Report menu exists (idempotent)."""
    global _MENU_ENSURED
    if _MENU_ENSURED:
        return
    db.session.execute(
        text(
            """
            DECLARE @ParentID INT;
            DECLARE @ReportsOrder INT = (
                SELECT TOP 1 DisplayOrder FROM dbo.MenuMaster
                WHERE MenuName IN (N'Reports', N'Reports and Analysis', N'Reports & Analysis')
                  AND ParentMenuID IS NULL
                ORDER BY MenuID
            );

            SELECT TOP 1 @ParentID = MenuID
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

            IF @ParentID IS NULL
            BEGIN
                SELECT TOP 1 @ParentID = MenuID
                FROM dbo.MenuMaster
                WHERE MenuURL = N'/Reports_and_analysis/ledger_report'
                ORDER BY MenuID;
                IF @ParentID IS NOT NULL
                    SELECT @ParentID = ParentMenuID FROM dbo.MenuMaster WHERE MenuID = @ParentID;
            END;

            IF @ParentID IS NULL
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
                SET @ParentID = SCOPE_IDENTITY();
            END;

            IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster
                WHERE MenuURL = N'/Reports_and_analysis/ledger_report'
            )
                UPDATE dbo.MenuMaster
                SET ParentMenuID = @ParentID,
                    MenuName = N'Ledger Report',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-journal-text'),
                    MenuURL = N'/Reports_and_analysis/ledger_report',
                    Description = N'Search and preview bank, customer, work/category and item ledgers',
                    IsActive = 1
                WHERE MenuURL = N'/Reports_and_analysis/ledger_report';
            ELSE IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster
                WHERE ParentMenuID = @ParentID AND MenuName = N'Ledger Report'
            )
                UPDATE dbo.MenuMaster
                SET MenuURL = N'/Reports_and_analysis/ledger_report',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-journal-text'),
                    Description = N'Search and preview bank, customer, work/category and item ledgers',
                    IsActive = 1
                WHERE ParentMenuID = @ParentID AND MenuName = N'Ledger Report';
            ELSE
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    @ParentID,
                    N'Ledger Report',
                    N'bi-journal-text',
                    N'/Reports_and_analysis/ledger_report',
                    10,
                    N'Search and preview bank, customer, work/category and item ledgers',
                    1,
                    NULL
                );
            """
        )
    )
    db.session.commit()
    _MENU_ENSURED = True


def ensure_ledger_report_menu() -> None:
    _ensure_ledger_report_menu()


def _parse_date_arg(name: str) -> date | None:
    raw = (request.args.get(name) or "").strip()
    if not raw:
        return None
    return LedgerReportService._parse_date(raw, date.today())


@bp.route("", methods=["GET"], strict_slashes=False)
@bp.route("/", methods=["GET"], strict_slashes=False)
@login_required
def index():
    try:
        _ensure_ledger_report_menu()
    except Exception:
        db.session.rollback()

    today = date.today()
    fy_start = LedgerReportService._fy_start(today)
    return render_template(
        "ledger_report/index.html",
        page_title="Ledger Report",
        breadcrumb=MenuService().get_breadcrumb(MENU_PATH, session.get("role")),
        today=today.isoformat(),
        fy_start=fy_start.isoformat(),
    )


@bp.route("/api/search", methods=["GET"], strict_slashes=False)
@login_required
def search():
    kind = (request.args.get("kind") or "all").strip().lower()
    search_q = (request.args.get("search") or "").strip() or None
    try:
        rows = LedgerReportService().search_ledgers(kind=kind, search=search_q)
        return jsonify({"ok": True, "rows": rows})
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": map_db_exception(exc) or str(exc)}), 500


@bp.route("/preview/<string:kind>/<int:entity_id>", methods=["GET"], strict_slashes=False)
@login_required
def preview(kind: str, entity_id: int):
    service = LedgerReportService()
    date_from = _parse_date_arg("date_from")
    date_to = _parse_date_arg("date_to")
    try:
        ledger = service.preview_ledger(
            kind, entity_id, date_from=date_from, date_to=date_to
        )
        html = render_template(
            "ledger_report/_preview_html.html",
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
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route(
    "/export/<string:kind>/<int:entity_id>/<string:fmt>",
    methods=["GET"],
    strict_slashes=False,
)
@login_required
def export(kind: str, entity_id: int, fmt: str):
    service = LedgerReportService()
    date_from = _parse_date_arg("date_from")
    date_to = _parse_date_arg("date_to")
    try:
        content, filename, mimetype = service.export_ledger(
            kind,
            entity_id,
            fmt=fmt,
            date_from=date_from,
            date_to=date_to,
        )
        return send_file(
            io.BytesIO(content),
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500
