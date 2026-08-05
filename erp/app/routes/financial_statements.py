"""Reports and Analysis → Financial Statements (Tally-style)."""

from __future__ import annotations

from io import BytesIO

from flask import Blueprint, jsonify, render_template, request, send_file, session
from sqlalchemy import text

from app.decorators import login_required
from app.extensions import db
from app.services.financial_statements.export import FinancialStatementsExport
from app.services.financial_statements.reports import FinancialStatementsService
from app.services.menu_service import MenuService

bp = Blueprint(
    "financial_statements",
    __name__,
    url_prefix="/Reports_and_analysis/financial-statements",
)

CHILD_MENUS = (
    ("Balance Sheet", "balance-sheet", 1, "bi-layout-split"),
    ("Profit & Loss", "profit-loss", 2, "bi-graph-up"),
    ("Trial Balance", "trial-balance", 3, "bi-scales"),
    ("Trading Account", "trading-account", 4, "bi-cart"),
    ("Cash Flow", "cash-flow", 5, "bi-cash-stack"),
    ("Fund Flow", "fund-flow", 6, "bi-arrow-left-right"),
    ("Depreciation Chart", "depreciation-chart", 7, "bi-percent"),
    ("Schedule of Fixed Assets", "fixed-assets-schedule", 8, "bi-building"),
    ("Ratio Analysis", "ratio-analysis", 9, "bi-pie-chart"),
)


def ensure_financial_statements_menus() -> None:
    parent_id = db.session.execute(
        text(
            """
            SELECT TOP 1 MenuID
            FROM dbo.MenuMaster
            WHERE ParentMenuID IS NULL
              AND (
                    MenuName = N'Reports and Analysis'
                 OR MenuURL LIKE N'/Reports_and_analysis%'
              )
            ORDER BY MenuID
            """
        )
    ).scalar()
    if not parent_id:
        return

    fs_id = db.session.execute(
        text(
            """
            SELECT TOP 1 MenuID
            FROM dbo.MenuMaster
            WHERE ParentMenuID = :pid
              AND (
                    MenuName = N'Financial Statements'
                 OR MenuURL = N'/Reports_and_analysis/financial-statements'
              )
            ORDER BY MenuID
            """
        ),
        {"pid": parent_id},
    ).scalar()

    if fs_id:
        db.session.execute(
            text(
                """
                UPDATE dbo.MenuMaster
                SET MenuName = N'Financial Statements',
                    MenuIcon = N'bi-journal-richtext',
                    MenuURL = N'/Reports_and_analysis/financial-statements',
                    DisplayOrder = 10,
                    IsActive = 1,
                    Description = N'Tally-style Balance Sheet, P&L, Trial Balance and related reports'
                WHERE MenuID = :id
                """
            ),
            {"id": fs_id},
        )
    else:
        db.session.execute(
            text(
                """
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    :pid, N'Financial Statements', N'bi-journal-richtext',
                    N'/Reports_and_analysis/financial-statements', 10,
                    N'Tally-style Balance Sheet, P&L, Trial Balance and related reports',
                    1, NULL
                )
                """
            ),
            {"pid": parent_id},
        )
        db.session.flush()
        fs_id = db.session.execute(
            text(
                """
                SELECT TOP 1 MenuID FROM dbo.MenuMaster
                WHERE ParentMenuID = :pid
                  AND MenuURL = N'/Reports_and_analysis/financial-statements'
                ORDER BY MenuID DESC
                """
            ),
            {"pid": parent_id},
        ).scalar()

    for name, slug, order, icon in CHILD_MENUS:
        url = f"/Reports_and_analysis/financial-statements/{slug}"
        existing = db.session.execute(
            text(
                """
                SELECT TOP 1 MenuID FROM dbo.MenuMaster
                WHERE ParentMenuID = :pid AND (MenuURL = :url OR MenuName = :name)
                ORDER BY MenuID
                """
            ),
            {"pid": fs_id, "url": url, "name": name},
        ).scalar()
        if existing:
            db.session.execute(
                text(
                    """
                    UPDATE dbo.MenuMaster
                    SET MenuName = :name, MenuURL = :url, DisplayOrder = :ord,
                        MenuIcon = :icon, IsActive = 1, ParentMenuID = :pid
                    WHERE MenuID = :id
                    """
                ),
                {
                    "name": name,
                    "url": url,
                    "ord": order,
                    "icon": icon,
                    "pid": fs_id,
                    "id": existing,
                },
            )
        else:
            db.session.execute(
                text(
                    """
                    INSERT INTO dbo.MenuMaster (
                        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                        Description, IsActive, RoleName
                    )
                    VALUES (:pid, :name, :icon, :url, :ord, :name, 1, NULL)
                    """
                ),
                {
                    "pid": fs_id,
                    "name": name,
                    "icon": icon,
                    "url": url,
                    "ord": order,
                },
            )
    db.session.commit()


@bp.route("", strict_slashes=False)
@bp.route("/", strict_slashes=False)
@bp.route("/<report_key>", strict_slashes=False)
@login_required
def index(report_key: str = "balance-sheet"):
    try:
        ensure_financial_statements_menus()
    except Exception:
        db.session.rollback()

    service = FinancialStatementsService()
    key = (report_key or "balance-sheet").strip().lower()
    if key not in dict(service.REPORTS):
        key = "balance-sheet"
    d1, d2 = service.resolve_period(None, None)
    menu_service = MenuService()
    return render_template(
        "financial_statements/index.html",
        page_title="Financial Statements",
        breadcrumb=menu_service.get_breadcrumb(
            "/Reports_and_analysis/financial-statements", session.get("role")
        ),
        reports=service.REPORTS,
        active_report=key,
        default_from=d1.isoformat(),
        default_to=d2.isoformat(),
    )


@bp.route("/api/report/<report_key>")
@login_required
def api_report(report_key: str):
    service = FinancialStatementsService()
    try:
        raw = service.build(
            report_key,
            date_from=request.args.get("date_from"),
            date_to=request.args.get("date_to"),
            search=request.args.get("search"),
        )
        return jsonify({"ok": True, "report": service.to_jsonable(raw)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/vouchers")
@login_required
def api_vouchers():
    """Drill-down: full ledger statement (Opening + vouchers + running + Closing)."""
    service = FinancialStatementsService()
    ledger_key = (request.args.get("ledger_key") or "").strip()
    if not ledger_key:
        return jsonify({"ok": False, "error": "ledger_key is required."}), 400
    d1, d2 = service.resolve_period(request.args.get("date_from"), request.args.get("date_to"))
    try:
        stmt = service.engine.get_ledger_statement(
            ledger_key, date_from=d1, date_to=d2
        )
        money = service.engine.money
        lines_out = []
        for line in stmt.get("lines") or []:
            item = dict(line)
            for k in ("debit", "credit", "running_balance"):
                if k in item and item[k] is not None:
                    item[k] = str(money(item[k]))
            lines_out.append(item)
        return jsonify(
            {
                "ok": True,
                "format": stmt.get("format") or "ledger",
                "ledger_kind": stmt.get("ledger_kind") or "generic",
                "title": stmt.get("title") or "Ledger Statement",
                "entity_name": stmt.get("entity_name") or "",
                "meta": stmt.get("meta") or [],
                "headers": stmt.get("headers") or [],
                "opening": str(money(stmt.get("opening"))),
                "closing": str(money(stmt.get("closing"))),
                "date_from": stmt.get("date_from"),
                "date_to": stmt.get("date_to"),
                "lines": lines_out,
                "count": len(lines_out),
                # Back-compat for older clients
                "rows": lines_out,
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/voucher-detail")
@login_required
def api_voucher_detail():
    service = FinancialStatementsService()
    source_table = (request.args.get("source_table") or "").strip()
    try:
        source_id = int(request.args.get("source_id") or 0)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid source_id."}), 400
    try:
        detail = service.engine.get_voucher_detail(source_table, source_id)
        rec = detail.get("record") or {}
        safe = {}
        for k, v in rec.items():
            if hasattr(v, "isoformat"):
                safe[k] = v.isoformat()
            else:
                safe[k] = str(v) if v is not None else ""
        return jsonify({"ok": True, "source": detail.get("source"), "record": safe})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/export/<report_key>")
@login_required
def api_export(report_key: str):
    fmt = (request.args.get("format") or "xlsx").strip().lower()
    service = FinancialStatementsService()
    exporter = FinancialStatementsExport()
    try:
        raw = service.build(
            report_key,
            date_from=request.args.get("date_from"),
            date_to=request.args.get("date_to"),
            search=request.args.get("search"),
        )
        data = service.to_jsonable(raw)
        title = (data.get("meta") or {}).get("report_title") or "report"
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in title)
        if fmt == "pdf":
            content = exporter.to_pdf(data)
            return send_file(
                BytesIO(content),
                mimetype="application/pdf",
                as_attachment=True,
                download_name=f"{safe}.pdf",
            )
        content = exporter.to_excel(data)
        return send_file(
            BytesIO(content),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"{safe}.xlsx",
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
