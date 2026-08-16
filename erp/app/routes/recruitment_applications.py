"""Admin Role → Sales Executive Applications (website recruitment data)."""

from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from sqlalchemy import text

from app.decorators import admin_required, login_required
from app.extensions import db
from app.repositories.user_repository import UserRepository
from app.services import recruitment_applications_service as rec
from app.services.menu_service import MenuService
from app.services.recruitment_sso import make_sso_token, recruitment_public_base, sso_secret
from app.whats_new import publish_whats_new

bp = Blueprint("recruitment_applications", __name__, url_prefix="/admin/recruitment")

MENU_PATH = "/admin/recruitment"
_MENU_ENSURED = False


def _ensure_recruitment_menu() -> None:
    global _MENU_ENSURED
    if _MENU_ENSURED:
        return
    db.session.execute(
        text(
            """
            DECLARE @ParentID INT;
            DECLARE @AdminRoles NVARCHAR(50) = N'Administrator,Admin';

            SELECT TOP 1 @ParentID = MenuID
            FROM dbo.MenuMaster
            WHERE MenuName = N'Admin Role'
              AND ParentMenuID IS NULL
            ORDER BY MenuID;

            IF @ParentID IS NULL
            BEGIN
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    NULL, N'Admin Role', N'bi-archive', NULL, 1,
                    N'Administrator tools — backups and system maintenance',
                    1, @AdminRoles
                );
                SET @ParentID = SCOPE_IDENTITY();
            END;

            IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster
                WHERE ParentMenuID = @ParentID AND MenuName = N'Sales Executive Applications'
            )
            BEGIN
                UPDATE dbo.MenuMaster
                SET MenuURL = N'/admin/recruitment',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-briefcase'),
                    DisplayOrder = 66,
                    Description = N'Website Sales Executive job applications',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE ParentMenuID = @ParentID AND MenuName = N'Sales Executive Applications';
            END
            ELSE IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/recruitment'
            )
            BEGIN
                UPDATE dbo.MenuMaster
                SET ParentMenuID = @ParentID,
                    MenuName = N'Sales Executive Applications',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-briefcase'),
                    DisplayOrder = 66,
                    Description = N'Website Sales Executive job applications',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE MenuURL = N'/admin/recruitment';
            END
            ELSE
            BEGIN
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    @ParentID,
                    N'Sales Executive Applications',
                    N'bi-briefcase',
                    N'/admin/recruitment',
                    66,
                    N'Website Sales Executive job applications',
                    1,
                    @AdminRoles
                );
            END;

            IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster
                WHERE ParentMenuID = @ParentID AND MenuName = N'Recruitment Admin Login'
            )
            BEGIN
                UPDATE dbo.MenuMaster
                SET MenuURL = N'/admin/recruitment/admin-login',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-box-arrow-up-right'),
                    DisplayOrder = 67,
                    Description = N'Open website recruitment admin login',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE ParentMenuID = @ParentID AND MenuName = N'Recruitment Admin Login';
            END
            ELSE
            BEGIN
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    @ParentID,
                    N'Recruitment Admin Login',
                    N'bi-box-arrow-up-right',
                    N'/admin/recruitment/admin-login',
                    67,
                    N'Open website recruitment admin login',
                    1,
                    @AdminRoles
                );
            END;
            """
        )
    )
    db.session.commit()
    try:
        publish_whats_new(
            "feature:sales_executive_applications",
            "Sales Executive Applications",
            detail="Admin Role → view website Sales Executive job applications.",
            url=MENU_PATH,
            badge="New",
        )
    except Exception:
        db.session.rollback()
    _MENU_ENSURED = True


def ensure_recruitment_menu() -> None:
    _ensure_recruitment_menu()


@bp.route("", methods=["GET"], strict_slashes=False)
@bp.route("/", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def index():
    try:
        _ensure_recruitment_menu()
    except Exception:
        db.session.rollback()

    available, store_message = rec.store_available()
    rows: list[dict] = []
    counts = {"total": 0, "new": 0}
    error = None
    search = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    if available:
        try:
            rows = rec.list_applications(search=search, status=status)
            counts = rec.summary()
        except Exception as exc:
            error = str(exc)
    else:
        error = store_message

    return render_template(
        "recruitment_applications/index.html",
        page_title="Sales Executive Applications",
        breadcrumb=MenuService().get_breadcrumb(MENU_PATH, session.get("role")),
        rows=rows,
        counts=counts,
        error=error,
        search=search,
        status=status,
        admin_url=url_for("recruitment_applications.admin_login"),
    )


@bp.route("/admin-login", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def admin_login():
    try:
        _ensure_recruitment_menu()
    except Exception:
        db.session.rollback()
    user = UserRepository().get_by_id(session.get("user_id"))
    email = ((getattr(user, "EmailID", None) or "") if user else "").strip().lower()
    name = (session.get("user_name") or getattr(user, "FullName", None) or "JTCS Admin").strip()
    if not email:
        flash("Your ERP user has no email, so recruitment admin cannot open automatically.", "danger")
        return redirect(url_for("recruitment_applications.index"))
    from urllib.parse import quote

    token = make_sso_token(email, name, session.get("role") or "admin", sso_secret())
    base = recruitment_public_base()
    return redirect(f"{base}/recruitment/admin/sso?token={quote(token, safe='')}")


@bp.route("/<int:application_id>", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def detail(application_id: int):
    try:
        _ensure_recruitment_menu()
    except Exception:
        db.session.rollback()
    try:
        application = rec.get_application(application_id)
    except rec.RecruitmentStoreError:
        abort(404)
    if application is None:
        abort(404)
    return render_template(
        "recruitment_applications/detail.html",
        page_title=application.get("application_number") or "Application",
        breadcrumb=MenuService().get_breadcrumb(MENU_PATH, session.get("role")),
        app=application,
        admin_url=current_app.config.get("RECRUITMENT_ADMIN_URL") or "",
    )


@bp.route("/<int:application_id>/resume", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def resume(application_id: int):
    try:
        resolved = rec.resolve_resume(application_id)
    except rec.RecruitmentStoreError:
        abort(404)
    if resolved is None:
        abort(404)
    path, download_name, mime = resolved
    return send_file(path, mimetype=mime, as_attachment=True, download_name=download_name)
