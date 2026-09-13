from __future__ import annotations

import io
import logging

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from sqlalchemy import text

from app.decorators import login_required, require_delete_reauth
from app.extensions import db
from app.services.auth_service import AuthService
from app.services.fps_login_service import FpsLoginService
from app.services.menu_service import MenuService
from app.services.pds_master_service import MENU_ITEMS, PdsMasterService
from app.services.ration_card_report_service import RationCardReportService
from app.utils.db_session import map_db_exception
from app.utils.fps_access import (
    FPS_INACTIVE_MESSAGE,
    FPS_SESSION_EXPIRED,
    fps_page_denied_response,
    fps_pds_slug_allowed,
    fps_write_forbidden_response,
    is_fps_session,
    session_fps_row_id,
)
from app.utils.master_delete_guard import MasterInUseError, json_in_use_response
from app.whats_new import publish_whats_new

bp = Blueprint("public_report", __name__, url_prefix="/public-report")

FPS_DETAIL_PATH = "/public-report/ration-card/fps-detail"
ALLOWED_EXTENSIONS = {".csv", ".txt"}
_BOOTSTRAPPED = False
logger = logging.getLogger(__name__)


def _ensure_public_report_bootstrap() -> None:
    """Create tables and place Public Report immediately after CRM."""
    global _BOOTSTRAPPED
    RationCardReportService().repo.ensure_schema()
    if _BOOTSTRAPPED:
        return
    db.session.execute(
        text(
            """
            IF COL_LENGTH(N'dbo.MenuMaster', N'BackgroundColor') IS NULL
                ALTER TABLE dbo.MenuMaster ADD BackgroundColor NVARCHAR(20) NULL;
            """
        )
    )
    db.session.commit()
    db.session.execute(
        text(
            """
            DECLARE @PublicID INT;
            DECLARE @RationID INT;
            DECLARE @CrmOrder INT = (
                SELECT TOP 1 DisplayOrder FROM dbo.MenuMaster
                WHERE MenuName = N'CRM' AND ParentMenuID IS NULL
                ORDER BY MenuID
            );

            SELECT TOP 1 @PublicID = MenuID
            FROM dbo.MenuMaster
            WHERE MenuName = N'Public Report' AND ParentMenuID IS NULL
            ORDER BY MenuID;

            IF @PublicID IS NULL
            BEGIN
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName, BackgroundColor
                )
                VALUES (
                    NULL, N'Public Report', N'bi-postcard', NULL, ISNULL(@CrmOrder, 25) + 1,
                    N'Public distribution and citizen reports', 1, NULL, N'#0E7490'
                );
                SET @PublicID = SCOPE_IDENTITY();
            END
            ELSE
            BEGIN
                UPDATE dbo.MenuMaster
                SET MenuIcon = N'bi-postcard',
                    MenuURL = NULL,
                    DisplayOrder = ISNULL(@CrmOrder, 25) + 1,
                    Description = N'Public distribution and citizen reports',
                    IsActive = 1,
                    BackgroundColor = COALESCE(NULLIF(BackgroundColor, N''), N'#0E7490')
                WHERE MenuID = @PublicID;
            END;

            SELECT TOP 1 @RationID = MenuID
            FROM dbo.MenuMaster
            WHERE ParentMenuID = @PublicID AND MenuName = N'Ration Card Report'
            ORDER BY MenuID;

            IF @RationID IS NULL
            BEGIN
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    @PublicID, N'Ration Card Report', N'bi-card-list', NULL, 1,
                    N'Ration card reports for FPS dealers', 1, NULL
                );
                SET @RationID = SCOPE_IDENTITY();
            END
            ELSE
            BEGIN
                UPDATE dbo.MenuMaster
                SET MenuIcon = N'bi-card-list',
                    MenuURL = NULL,
                    DisplayOrder = 1,
                    Description = N'Ration card reports for FPS dealers',
                    IsActive = 1
                WHERE MenuID = @RationID;
            END;

            IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster
                WHERE MenuURL = N'/public-report/ration-card/fps-detail'
                   OR (ParentMenuID = @RationID AND MenuName = N'Ration Card Detail Report for FPS')
            )
                UPDATE dbo.MenuMaster
                SET ParentMenuID = @RationID,
                    MenuName = N'Ration Card Detail Report for FPS',
                    MenuIcon = N'bi-shop-window',
                    MenuURL = N'/public-report/ration-card/fps-detail',
                    DisplayOrder = 1,
                    Description = N'FPS-wise ration card detail from NFSA CSV',
                    IsActive = 1,
                    RoleName = NULL
                WHERE MenuURL = N'/public-report/ration-card/fps-detail'
                   OR (ParentMenuID = @RationID AND MenuName = N'Ration Card Detail Report for FPS');
            ELSE
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    @RationID,
                    N'Ration Card Detail Report for FPS',
                    N'bi-shop-window',
                    N'/public-report/ration-card/fps-detail',
                    1,
                    N'FPS-wise ration card detail from NFSA CSV',
                    1,
                    NULL
                );
            """
        )
    )
    db.session.commit()
    _ensure_pds_master_menus()
    try:
        PdsMasterService().import_uttarakhand_once()
    except Exception:
        db.session.rollback()
        logger.exception("Uttarakhand PDS geography import skipped")
    try:
        publish_whats_new(
            "feature:public_report_ration_fps",
            "Public Report — Ration Card Detail for FPS",
            detail="After CRM: search or add a ration dealer, then upload the NFSA CSV to print a Tehsil / Scheme / FPS grouped report.",
            url=FPS_DETAIL_PATH,
            badge="New",
        )
        publish_whats_new(
            "feature:pds_ration_masters",
            "Ration Card masters (Uttarakhand)",
            detail="Public Report → Ration Card Report: State, District, DSO, ARO, SI, FPS, and Ration Card masters. Uttarakhand districts import once.",
            url="/public-report/ration-card/state-master",
            badge="New",
        )
    except Exception:
        db.session.rollback()
    _BOOTSTRAPPED = True


def _ensure_pds_master_menus() -> None:
    parent = db.session.execute(
        text(
            """
            SELECT TOP 1 MenuID FROM dbo.MenuMaster
            WHERE MenuName = N'Ration Card Report'
            ORDER BY MenuID
            """
        )
    ).first()
    if not parent:
        return
    parent_id = int(parent[0])
    for name, icon, url, order, desc in MENU_ITEMS:
        existing = db.session.execute(
            text(
                """
                SELECT TOP 1 MenuID FROM dbo.MenuMaster
                WHERE MenuURL = :url OR (ParentMenuID = :parent AND MenuName = :name)
                """
            ),
            {"url": url, "parent": parent_id, "name": name},
        ).first()
        if existing:
            db.session.execute(
                text(
                    """
                    UPDATE dbo.MenuMaster
                    SET ParentMenuID = :parent, MenuName = :name, MenuIcon = :icon,
                        MenuURL = :url, DisplayOrder = :ord, Description = :desc,
                        IsActive = 1, RoleName = NULL
                    WHERE MenuID = :id
                    """
                ),
                {
                    "parent": parent_id,
                    "name": name,
                    "icon": icon,
                    "url": url,
                    "ord": order,
                    "desc": desc,
                    "id": int(existing[0]),
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
                    VALUES (:parent, :name, :icon, :url, :ord, :desc, 1, NULL)
                    """
                ),
                {
                    "parent": parent_id,
                    "name": name,
                    "icon": icon,
                    "url": url,
                    "ord": order,
                    "desc": desc,
                },
            )
    db.session.execute(
        text(
            """
            UPDATE dbo.MenuMaster
            SET IsActive = 0
            WHERE MenuURL LIKE N'%/si-master%'
               OR (ParentMenuID = :parent AND MenuName = N'SI Master')
            """
        ),
        {"parent": parent_id},
    )
    db.session.commit()


def ensure_public_report_menus() -> None:
    try:
        _ensure_public_report_bootstrap()
    except Exception:
        db.session.rollback()
        raise


def _actor() -> str:
    return session.get("user_name") or session.get("user_email") or "System"


def _fps_write_blocked():
    if is_fps_session():
        return fps_write_forbidden_response()
    return None


def _resolved_dealer_id(raw: str | None) -> int:
    requested = int(raw) if raw and str(raw).strip().isdigit() else None
    return FpsLoginService().resolve_dealer_id(requested)


@bp.before_app_request
def ensure_menus_once_per_process():
    if request.blueprint != bp.name:
        return None
    try:
        _ensure_public_report_bootstrap()
    except Exception:
        db.session.rollback()
    return None


@bp.route("/ration-card/fps-detail", strict_slashes=False)
@login_required
def fps_detail():
    _ensure_public_report_bootstrap()
    menu_service = MenuService()
    fps_readonly = is_fps_session()
    scoped_dealer = None
    scoped_shop = None
    if fps_readonly:
        fps_service = FpsLoginService()
        scoped_shop = fps_service.scoped_shop()
        if not scoped_shop:
            session.clear()
            flash(FPS_SESSION_EXPIRED, "warning")
            return redirect(url_for("auth.login"))
        if not scoped_shop.get("active_status"):
            session.clear()
            flash(FPS_INACTIVE_MESSAGE, "danger")
            return redirect(url_for("other_login.fps_login_page"))
        try:
            scoped_dealer = fps_service.scoped_dealer()
        except Exception:
            db.session.rollback()
            scoped_dealer = None
    return render_template(
        "public_report/fps_detail.html",
        page_title="Ration Card Detail Report for FPS",
        breadcrumb=menu_service.get_breadcrumb(FPS_DETAIL_PATH, session.get("role")),
        fps_readonly=fps_readonly,
        scoped_dealer=scoped_dealer,
        scoped_shop=scoped_shop,
    )


@bp.route("/api/dealers")
@login_required
def search_dealers():
    if is_fps_session():
        try:
            row = FpsLoginService().scoped_dealer()
            rows = [row] if row else []
            return jsonify({"ok": True, "rows": rows, "count": len(rows), "query": ""})
        except Exception as exc:
            db.session.rollback()
            return jsonify({"ok": False, "error": map_db_exception(exc)}), 500
    term = (request.args.get("q") or request.args.get("search") or "").strip()
    try:
        rows = RationCardReportService().search_dealers(term or None)
        return jsonify({"ok": True, "rows": rows, "count": len(rows), "query": term})
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/dealers/by-fps")
@login_required
def dealer_by_fps():
    blocked = _fps_write_blocked()
    if blocked:
        return blocked
    fps_id = (request.args.get("fps") or request.args.get("fps_id") or "").strip()
    if not fps_id:
        return jsonify({"ok": False, "error": "Enter an FPS ID to search."}), 400
    try:
        service = RationCardReportService()
        record = service.find_dealer_by_fps(fps_id)
        if record:
            return jsonify({"ok": True, "found": True, "record": record})
        matches = [
            row
            for row in service.search_dealers(fps_id)
            if fps_id.lower() in (row.get("fps_id") or "").lower()
            or fps_id.lower() in (row.get("existing_fps_id") or "").lower()
        ]
        if matches:
            return jsonify({"ok": True, "found": True, "record": matches[0], "rows": matches})
        return jsonify({"ok": True, "found": False, "record": None, "rows": []})
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/dealers/<int:dealer_id>")
@login_required
def get_dealer(dealer_id: int):
    try:
        if is_fps_session():
            dealer_id = _resolved_dealer_id(str(dealer_id))
        record = RationCardReportService().get_dealer(dealer_id)
        return jsonify({"ok": True, "record": record})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/dealers", methods=["POST"])
@login_required
def create_dealer():
    blocked = _fps_write_blocked()
    if blocked:
        return blocked
    try:
        record = RationCardReportService().create_dealer(request.form, created_by=_actor())
        return jsonify({"ok": True, "record": record, "message": "Ration dealer added."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/dealers/<int:dealer_id>", methods=["POST"])
@login_required
def update_dealer(dealer_id: int):
    blocked = _fps_write_blocked()
    if blocked:
        return blocked
    try:
        record = RationCardReportService().update_dealer(
            dealer_id, request.form, modified_by=_actor()
        )
        return jsonify({"ok": True, "record": record, "message": "Ration dealer updated."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/dealers/<int:dealer_id>/delete", methods=["POST"])
@login_required
@require_delete_reauth
def delete_dealer(dealer_id: int):
    blocked = _fps_write_blocked()
    if blocked:
        return blocked
    try:
        message = RationCardReportService().delete_dealer(dealer_id)
        return jsonify({"ok": True, "message": message})
    except MasterInUseError as exc:
        return json_in_use_response(exc)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/ration-card/fps-detail/generate", methods=["POST"])
@login_required
def generate_fps_detail():
    blocked = _fps_write_blocked()
    if blocked:
        return blocked
    dealer_id_raw = (request.form.get("dealer_id") or "").strip()
    if not dealer_id_raw.isdigit():
        return jsonify({"ok": False, "error": "Select a ration dealer first."}), 400

    upload = request.files.get("csv_file") or request.files.get("ration_file")
    if upload is None or not upload.filename:
        return jsonify({"ok": False, "error": "Browse and select the ration-card CSV file."}), 400

    file_name = upload.filename.strip()
    extension = file_name[file_name.rfind(".") :].lower() if "." in file_name else ""
    if extension not in ALLOWED_EXTENSIONS:
        return jsonify({"ok": False, "error": "Only CSV files are supported."}), 400

    fps_filter = (request.form.get("fps_id") or "").strip()
    import_mode = (request.form.get("import_mode") or "").strip().lower()
    try:
        result = RationCardReportService().generate_from_csv(
            dealer_id=int(dealer_id_raw),
            file_bytes=upload.read(),
            file_name=file_name,
            fps_filter=fps_filter or None,
            uploaded_by=_actor(),
            import_mode=import_mode or None,
        )
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/ration-card/fps-detail/latest")
@login_required
def latest_fps_detail():
    dealer_id_raw = (request.args.get("dealer_id") or "").strip()
    try:
        dealer_id = _resolved_dealer_id(dealer_id_raw)
        result = RationCardReportService().latest_report(dealer_id)
        if result is None:
            return jsonify({"ok": True, "found": False})
        return jsonify({"ok": True, "found": True, **result})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/ration-card/fps-detail/pdf")
@login_required
def fps_detail_pdf():
    dealer_id_raw = (request.args.get("dealer_id") or "").strip()
    try:
        dealer_id = _resolved_dealer_id(dealer_id_raw)
        result = RationCardReportService().latest_report(dealer_id)
        if result is None:
            return jsonify({"ok": False, "error": "Import the CSV onto the grid first."}), 400
        company = AuthService().get_company()
        company_name = (
            (company.CompanyName if company and company.CompanyName else None)
            or "Joshi Tax Consultancy & Services"
        )
        layout = (request.args.get("layout") or request.args.get("device") or "").strip().lower()
        if layout not in {"mobile", "desktop"}:
            ua = (request.user_agent.string or "").lower()
            layout = "mobile" if (
                "iphone" in ua or "android" in ua or "mobile" in ua or "ipad" in ua
            ) else "desktop"
        pdf_bytes, filename = RationCardReportService.build_pdf(
            result, company_name=company_name, layout=layout
        )
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


def _pds_parent_id() -> int | None:
    raw = (request.args.get("parent_id") or request.form.get("parent_id") or "").strip()
    return int(raw) if raw.isdigit() else None


def _fps_pds_read_blocked(slug: str):
    if not is_fps_session():
        return None
    if fps_pds_slug_allowed(slug):
        return None
    return fps_write_forbidden_response()


def _fps_scoped_rows(slug: str, *, search: str | None = None, parent_id: int | None = None):
    fps_row_id = session_fps_row_id() if is_fps_session() else None
    return PdsMasterService().list_records(
        slug,
        search=search,
        parent_id=None if fps_row_id else parent_id,
        fps_row_id=fps_row_id,
    )


def _fps_owns_record(slug: str, record: dict) -> bool:
    fps_row_id = session_fps_row_id()
    if not fps_row_id:
        return False
    if slug == "fps":
        return int(record.get("fps_row_id") or 0) == fps_row_id
    if slug == "ration-card":
        return int(record.get("FpsRowID") or record.get("fps_row_id") or 0) == fps_row_id
    return False


@bp.route("/ration-card/<slug>-master", strict_slashes=False)
@login_required
def pds_master_page(slug: str):
    fps_readonly = is_fps_session()
    if fps_readonly and not fps_pds_slug_allowed(slug):
        return fps_page_denied_response()
    _ensure_public_report_bootstrap()
    try:
        PdsMasterService().import_uttarakhand_once()
    except Exception:
        db.session.rollback()
    service = PdsMasterService()
    try:
        config = service.page_config(slug)
    except ValueError:
        abort(404)
    menu_service = MenuService()
    rows = []
    try:
        rows = _fps_scoped_rows(slug)
    except Exception:
        db.session.rollback()
        rows = []
    if fps_readonly:
        config = {**config, "import_note": "Your FPS shop only. This master is read-only."}
    return render_template(
        "public_report/pds_master.html",
        page_title=config["title"],
        breadcrumb=menu_service.get_breadcrumb(config["url"], session.get("role")),
        pds_config=config,
        initial_rows=rows,
        pds_readonly=fps_readonly,
    )


@bp.route("/api/pds/<slug>")
@login_required
def pds_list(slug: str):
    blocked = _fps_pds_read_blocked(slug)
    if blocked:
        return blocked
    search = (request.args.get("search") or request.args.get("q") or "").strip() or None
    try:
        rows = _fps_scoped_rows(slug, search=search, parent_id=_pds_parent_id())
        return jsonify({"ok": True, "rows": rows, "count": len(rows)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/pds/<slug>/options")
@login_required
def pds_options(slug: str):
    blocked = _fps_write_blocked()
    if blocked:
        return blocked
    try:
        rows = PdsMasterService().options(slug, parent_id=_pds_parent_id())
        return jsonify({"ok": True, "rows": rows})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/pds/<slug>/<int:row_id>")
@login_required
def pds_get(slug: str, row_id: int):
    blocked = _fps_pds_read_blocked(slug)
    if blocked:
        return blocked
    try:
        record = PdsMasterService().get_record(slug, row_id)
        if is_fps_session() and not _fps_owns_record(slug, record):
            return fps_write_forbidden_response()
        return jsonify({"ok": True, "record": record})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/pds/<slug>", methods=["POST"])
@login_required
def pds_create(slug: str):
    blocked = _fps_write_blocked()
    if blocked:
        return blocked
    try:
        record = PdsMasterService().create_record(slug, request.form, created_by=_actor())
        return jsonify({"ok": True, "record": record, "message": "Saved."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/pds/<slug>/<int:row_id>", methods=["POST"])
@login_required
def pds_update(slug: str, row_id: int):
    blocked = _fps_write_blocked()
    if blocked:
        return blocked
    try:
        record = PdsMasterService().update_record(slug, row_id, request.form, modified_by=_actor())
        return jsonify({"ok": True, "record": record, "message": "Updated."})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500


@bp.route("/api/pds/<slug>/<int:row_id>/delete", methods=["POST"])
@login_required
@require_delete_reauth
def pds_delete(slug: str, row_id: int):
    blocked = _fps_write_blocked()
    if blocked:
        return blocked
    try:
        message = PdsMasterService().delete_record(slug, row_id)
        return jsonify({"ok": True, "message": message})
    except MasterInUseError as exc:
        return json_in_use_response(exc)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "error": map_db_exception(exc)}), 500

