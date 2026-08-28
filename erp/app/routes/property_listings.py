"""Admin Role → Property Management (website Property SQLite, same pattern as recruitment)."""

from __future__ import annotations

from urllib.parse import quote

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import text

from app.decorators import admin_required, login_required
from app.extensions import db
from app.repositories.user_repository import UserRepository
from app.services import property_listings_service as prop
from app.services.menu_service import MenuService
from app.services.property_sso import make_sso_token, property_public_base, sso_secret
from app.whats_new import publish_whats_new

bp = Blueprint("property_listings", __name__, url_prefix="/admin/property")

MENU_PATH = "/admin/property"
_MENU_ENSURED = False

SECTIONS = (
    ("listings", "Property Registrations"),
    ("owners", "Owners / Landlords"),
    ("buyers", "Buyers / Tenants"),
    ("leads", "Property Leads"),
    ("visits", "Site Visits"),
    ("requirements", "Requirements"),
    ("deals", "Deals / Brokerage"),
    ("agreements", "Agreements"),
)


def _ensure_property_menu() -> None:
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
                WHERE ParentMenuID = @ParentID AND MenuName = N'Property Management'
            )
            BEGIN
                UPDATE dbo.MenuMaster
                SET MenuURL = N'/admin/property',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-houses'),
                    DisplayOrder = 68,
                    Description = N'Website Haldwani property registrations, owners, leads and deals',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE ParentMenuID = @ParentID AND MenuName = N'Property Management';
            END
            ELSE IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/property'
            )
            BEGIN
                UPDATE dbo.MenuMaster
                SET ParentMenuID = @ParentID,
                    MenuName = N'Property Management',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-houses'),
                    DisplayOrder = 68,
                    Description = N'Website Haldwani property registrations, owners, leads and deals',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE MenuURL = N'/admin/property';
            END
            ELSE
            BEGIN
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    @ParentID,
                    N'Property Management',
                    N'bi-houses',
                    N'/admin/property',
                    68,
                    N'Website Haldwani property registrations, owners, leads and deals',
                    1,
                    @AdminRoles
                );
            END;

            IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster
                WHERE ParentMenuID = @ParentID AND MenuName = N'Property Admin Login'
            )
            BEGIN
                UPDATE dbo.MenuMaster
                SET MenuURL = N'/admin/property/admin-login',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-box-arrow-up-right'),
                    DisplayOrder = 69,
                    Description = N'Open website Property Admin (documents, verification, deals)',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE ParentMenuID = @ParentID AND MenuName = N'Property Admin Login';
            END
            ELSE IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/property/admin-login'
            )
            BEGIN
                UPDATE dbo.MenuMaster
                SET ParentMenuID = @ParentID,
                    MenuName = N'Property Admin Login',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-box-arrow-up-right'),
                    DisplayOrder = 69,
                    Description = N'Open website Property Admin (documents, verification, deals)',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE MenuURL = N'/admin/property/admin-login';
            END
            ELSE
            BEGIN
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    @ParentID,
                    N'Property Admin Login',
                    N'bi-box-arrow-up-right',
                    N'/admin/property/admin-login',
                    69,
                    N'Open website Property Admin (documents, verification, deals)',
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
            "feature:property_management",
            "Property Management",
            detail="Admin Role → view website Haldwani property registrations, owners, leads and deals.",
            url=MENU_PATH,
            badge="New",
        )
    except Exception:
        db.session.rollback()
    _MENU_ENSURED = True


def ensure_property_menu() -> None:
    _ensure_property_menu()


def _safe_ensure() -> None:
    try:
        _ensure_property_menu()
    except Exception:
        db.session.rollback()


@bp.route("", methods=["GET"], strict_slashes=False)
@bp.route("/", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def index():
    _safe_ensure()
    available, store_message = prop.store_available()
    error = None
    counts = {}
    rows: list[dict] = []
    search = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    section = (request.args.get("section") or "listings").strip() or "listings"
    if section not in {s[0] for s in SECTIONS}:
        section = "listings"
    if available:
        try:
            counts = prop.summary()
            if section == "owners":
                rows = prop.list_owners()
            elif section == "buyers":
                rows = prop.list_buyers()
            elif section == "leads":
                rows = prop.list_leads()
            elif section == "visits":
                rows = prop.list_leads(lead_type="site_visit")
            elif section == "requirements":
                rows = prop.list_requirements()
            elif section == "deals":
                rows = prop.list_deals()
            elif section == "agreements":
                rows = prop.list_agreements()
            else:
                rows = prop.list_listings(search=search, status=status)
        except Exception as exc:
            error = str(exc)
    else:
        error = store_message
    return render_template(
        "property_listings/index.html",
        page_title="Property Management",
        breadcrumb=MenuService().get_breadcrumb(MENU_PATH, session.get("role")),
        rows=rows,
        counts=counts,
        error=error,
        search=search,
        status=status,
        section=section,
        sections=SECTIONS,
        admin_url=url_for("property_listings.admin_login"),
    )


@bp.route("/admin-login", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def admin_login():
    _safe_ensure()
    user = UserRepository().get_by_id(session.get("user_id"))
    email = ((getattr(user, "EmailID", None) or "") if user else "").strip().lower()
    name = (session.get("user_name") or getattr(user, "FullName", None) or "JTCS Admin").strip()
    if not email:
        flash("Your ERP user has no email, so Property Admin cannot open automatically.", "danger")
        return redirect(url_for("property_listings.index"))
    token = make_sso_token(email, name, session.get("role") or "admin", sso_secret())
    base = property_public_base()
    return redirect(f"{base}/property/admin/sso?token={quote(token, safe='')}")


@bp.route("/<public_id>", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def detail(public_id: str):
    _safe_ensure()
    if public_id in {"admin-login"}:
        abort(404)
    try:
        listing = prop.get_listing(public_id)
    except prop.PropertyStoreError:
        abort(404)
    if listing is None:
        abort(404)
    return render_template(
        "property_listings/detail.html",
        page_title=listing.get("listing_number") or "Property",
        breadcrumb=MenuService().get_breadcrumb(MENU_PATH, session.get("role")),
        listing=listing,
        admin_url=url_for("property_listings.admin_login"),
    )
