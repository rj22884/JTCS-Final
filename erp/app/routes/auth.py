import logging

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy import text

from app.decorators import admin_required, login_required, require_delete_reauth, server_auth_exempt
from app.extensions import db
from app.services.auth_service import AuthService
from app.utils.roles import has_admin_role

logger = logging.getLogger(__name__)

bp = Blueprint("auth", __name__)

_USERS_MENU_ENSURED = False


def _ensure_admin_users_menu() -> None:
    """Wire Admin Role → Users (after Settings) to pending users page."""
    global _USERS_MENU_ENSURED
    if _USERS_MENU_ENSURED:
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
                    NULL,
                    N'Admin Role',
                    N'bi-archive',
                    NULL,
                    1,
                    N'Administrator tools — backups and system maintenance',
                    1,
                    @AdminRoles
                );
                SET @ParentID = SCOPE_IDENTITY();
            END
            ELSE
            BEGIN
                UPDATE dbo.MenuMaster
                SET RoleName = @AdminRoles,
                    IsActive = 1
                WHERE MenuID = @ParentID;
            END;

            IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster
                WHERE ParentMenuID = @ParentID AND MenuName = N'Users'
            )
            BEGIN
                UPDATE dbo.MenuMaster
                SET MenuURL = N'/admin/users',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-people'),
                    DisplayOrder = 4,
                    Description = N'All users — review status and approve pending registrations',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE ParentMenuID = @ParentID AND MenuName = N'Users';
            END
            ELSE IF EXISTS (
                SELECT 1 FROM dbo.MenuMaster
                WHERE MenuURL IN (N'/admin/users', N'/admin/users/pending')
            )
            BEGIN
                UPDATE dbo.MenuMaster
                SET ParentMenuID = @ParentID,
                    MenuName = N'Users',
                    MenuIcon = COALESCE(NULLIF(MenuIcon, N''), N'bi-people'),
                    MenuURL = N'/admin/users',
                    DisplayOrder = 4,
                    Description = N'All users — review status and approve pending registrations',
                    IsActive = 1,
                    RoleName = @AdminRoles
                WHERE MenuURL IN (N'/admin/users', N'/admin/users/pending');
            END
            ELSE
            BEGIN
                INSERT INTO dbo.MenuMaster (
                    ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                    Description, IsActive, RoleName
                )
                VALUES (
                    @ParentID,
                    N'Users',
                    N'bi-people',
                    N'/admin/users',
                    4,
                    N'All users — review status and approve pending registrations',
                    1,
                    @AdminRoles
                );
            END;

            UPDATE dbo.MenuMaster
            SET RoleName = @AdminRoles
            WHERE ParentMenuID = @ParentID
              AND (RoleName IS NULL OR LTRIM(RTRIM(RoleName)) = N'');
            """
        )
    )
    db.session.commit()
    _USERS_MENU_ENSURED = True


def ensure_admin_users_menu() -> None:
    _ensure_admin_users_menu()


def _client_ip() -> str | None:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr


@bp.route("/login", methods=["GET", "POST"])
def login():
    auth = AuthService()
    if session.get("user_id"):
        if session.get("server_user_id"):
            return redirect(url_for("dashboard.index"))
        return redirect(url_for("server_auth.gate"))

    if not auth.administrator_exists():
        return redirect(url_for("setup.index"))

    email = (request.args.get("email") or request.form.get("email") or "").strip().lower()
    show_unverified = False
    show_pending_approval = request.args.get("verified") == "1" and bool(email)
    verification_sent = False

    if request.method == "POST":
        action = request.form.get("action", "login")

        if action == "resend_verification":
            email = request.form.get("email", "").strip().lower()
            success, message, _ = auth.resend_verification_email(email)
            if success:
                verification_sent = True
                show_unverified = True
            else:
                flash(message, "danger")
                show_unverified = True
            return render_template(
                "auth/login.html",
                email=email,
                show_unverified=show_unverified,
                verification_sent=verification_sent,
                show_pending_approval=show_pending_approval,
            )

        success, message, data = auth.login(
            email,
            request.form.get("password", ""),
            remember=request.form.get("remember") == "on",
        )
        if not success:
            reason = data.get("reason")
            if reason == "password_not_set":
                show_unverified = True
                flash(message, "warning")
                return render_template(
                    "auth/login.html",
                    email=data.get("email", email),
                    show_unverified=True,
                    verification_sent=False,
                    show_pending_approval=False,
                )
            if reason == "email_not_verified":
                show_unverified = True
                return render_template(
                    "auth/login.html",
                    email=data.get("email", email),
                    show_unverified=True,
                    verification_sent=False,
                    show_pending_approval=False,
                )
            if reason == "pending_approval":
                return render_template(
                    "auth/login.html",
                    email=data.get("email", email),
                    show_unverified=False,
                    verification_sent=False,
                    show_pending_approval=True,
                )
            flash(message, "danger")
        else:
            session.clear()
            session["user_id"] = data["user_id"]
            session["user_name"] = data["user_name"]
            session["role"] = data["role"]
            session.pop("server_user_id", None)
            session.pop("server_login_id", None)
            session.pop("server_auth_at", None)
            if data.get("login_session_id"):
                session["login_session_id"] = data["login_session_id"]
            session.permanent = data["remember"]
            flash(f"Welcome, {data['user_name']}!", "success")
            # Admin login: WhatsApp token + Integration Health alerts
            try:
                from app.utils.roles import has_admin_role
                from app.modules.settings.services import IntegrationSettingsService
                from app.modules.settings.integration_health_service import IntegrationHealthService

                if has_admin_role(data.get("role")):
                    alert = IntegrationSettingsService().check_token_on_login()
                    if alert:
                        flash(
                            f"WhatsApp Meta: {alert.get('status') or 'Alert'} — {alert.get('message')}",
                            "warning",
                        )
                    for ha in IntegrationHealthService().login_alerts()[:3]:
                        flash(
                            f"Integration Health [{ha.get('provider')}]: {ha.get('title')} — {ha.get('message')}",
                            "warning",
                        )
            except Exception:
                pass
            next_url = (request.args.get("next") or "").strip()
            if next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(url_for("server_auth.gate", next=next_url))
            return redirect(url_for("server_auth.gate"))

    return render_template(
        "auth/login.html",
        email=email,
        show_unverified=show_unverified,
        verification_sent=verification_sent,
        show_pending_approval=show_pending_approval,
    )


@bp.route("/register", methods=["GET", "POST"])
def register():
    auth = AuthService()
    if session.get("user_id"):
        return redirect(url_for("dashboard.index"))
    if not auth.administrator_exists():
        return redirect(url_for("setup.index"))

    if request.method == "POST":
        success, message, data = auth.register(request.form)
        if not success:
            flash(message, "danger")
        else:
            flash(
                message or "Registration submitted. Check your email for the password setup link.",
                "success" if "saved, but" not in (message or "").lower() else "warning",
            )
            return redirect(url_for("auth.verify_email", email=data.get("email", "")))

    return render_template("auth/register.html")


@bp.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    auth = AuthService()
    email = (request.args.get("email") or request.form.get("email") or "").strip().lower()

    if request.method == "POST" and request.form.get("action") == "resend":
        success, message, _ = auth.resend_verification_email(email)
        flash(message, "danger" if not success else "info")

    return render_template("auth/verify_email.html", email=email)


@bp.route("/verify/<token>")
def verify_token(token: str):
    auth = AuthService()
    success, message, data = auth.verify_email_link(token, client_ip=_client_ip())
    if not success:
        flash(message, "danger")
        return redirect(url_for("auth.verify_email", email=data.get("email", "")))
    flash(message or "Email verified successfully. Await administrator approval.", "success")
    return redirect(url_for("auth.login", email=data.get("email", ""), verified=1))


@bp.route("/verify-email/confirm")
def verify_email_link():
    token = request.args.get("token", "")
    if not token:
        flash("Invalid verification link.", "danger")
        return redirect(url_for("auth.verify_email"))
    return redirect(url_for("auth.verify_token", token=token))


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    auth = AuthService()
    if request.method == "POST":
        try:
            success, message, _ = auth.request_password_reset(request.form.get("email", ""))
        except Exception:
            logger.exception("forgot_password failed")
            flash("Unable to process password reset right now. Please try again.", "danger")
            return render_template("auth/forgot_password.html")

        if not success:
            flash(message, "danger")
        else:
            flash(message or "If the email exists, a password reset link has been sent.", "info")
            return redirect(url_for("auth.login"))
    return render_template("auth/forgot_password.html")


@bp.route("/reset-password", methods=["GET", "POST"])
@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str | None = None):
    auth = AuthService()
    token = token or request.args.get("token", "")

    if request.method == "POST":
        token = request.form.get("token", token)
        try:
            success, message, _ = auth.reset_password_with_token(
                token,
                request.form.get("password", ""),
                request.form.get("confirm_password", ""),
            )
        except Exception:
            logger.exception("reset_password failed")
            flash("Unable to update password right now. Please try again.", "danger")
            return render_template("auth/reset_password.html", token=token)

        if not success:
            flash(message, "danger")
        else:
            flash(message or "Password updated successfully. Please sign in.", "success")
            return redirect(url_for("auth.login"))

    if not token:
        flash("Invalid or expired password reset link.", "danger")
        return redirect(url_for("auth.forgot_password"))

    return render_template("auth/reset_password.html", token=token)


@bp.route("/forgot-user-id", methods=["GET", "POST"])
def forgot_user_id():
    auth = AuthService()

    if request.method == "POST":
        success, message, _ = auth.request_forgot_user_id(
            email=request.form.get("email", ""),
            mobile=request.form.get("mobile", ""),
        )
        if not success:
            flash(message, "danger")
        else:
            flash(message or "If a matching account exists, your User ID has been sent to the registered email.", "info")
            return redirect(url_for("auth.login"))

    return render_template("auth/forgot_user_id.html")


@bp.route("/logout")
@login_required
@server_auth_exempt
def logout():
    login_session_id = session.get("login_session_id")
    try:
        from app.services.server_auth_service import ServerAuthService

        ServerAuthService().log_logout()
    except Exception:
        logger.exception("Server logout audit skipped")
    try:
        from app.services.login_activity_service import LoginActivityService

        LoginActivityService().mark_logout(login_session_id)
    except Exception:
        logger.exception("Logout activity update skipped")
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/admin/users", methods=["GET"], strict_slashes=False)
@bp.route("/admin/users/", methods=["GET"], strict_slashes=False)
@login_required
@admin_required
def users_index():
    try:
        _ensure_admin_users_menu()
    except Exception:
        db.session.rollback()
    auth = AuthService()
    from app.services.menu_service import MenuService

    focus_user_id = request.args.get("user_id", type=int)
    return render_template(
        "auth/users.html",
        page_title="Users",
        breadcrumb=MenuService().get_breadcrumb("/admin/users", session.get("role")),
        users=auth.list_all_users_for_admin(),
        pending_count=len(auth.list_pending_users()),
        focus_user_id=focus_user_id,
        assignable_roles=AuthService.ASSIGNABLE_ROLES,
        can_delete_users=has_admin_role(session.get("role")),
    )


@bp.route("/admin/users/pending")
@login_required
@admin_required
def pending_users():
    """Legacy URL — open Users list focused on pending activity."""
    user_id = request.args.get("user_id", type=int)
    if user_id:
        return redirect(url_for("auth.users_index", user_id=user_id))
    return redirect(url_for("auth.users_index"))


@bp.route("/admin/users/active")
@login_required
@admin_required
def active_users():
    return redirect(url_for("auth.users_index"))


@bp.route("/admin/users/<int:user_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve_user(user_id: int):
    auth = AuthService()
    roles = request.form.getlist("role")
    success, message, _ = auth.approve_user(user_id, roles=roles)
    flash(message or ("User approved successfully." if success else "Approval failed."), "success" if success else "danger")
    return redirect(url_for("auth.users_index"))


@bp.route("/admin/users/<int:user_id>/change-role", methods=["POST"])
@login_required
@admin_required
def change_user_role(user_id: int):
    auth = AuthService()
    roles = request.form.getlist("role")
    success, message, _ = auth.change_user_roles(user_id, roles=roles)
    flash(message or ("Role updated." if success else "Role update failed."), "success" if success else "danger")
    return redirect(url_for("auth.users_index"))


@bp.route("/admin/users/<int:user_id>/reject", methods=["POST"])
@login_required
@admin_required
def reject_user(user_id: int):
    auth = AuthService()
    success, message, _ = auth.reject_user(user_id)
    flash(message or ("User rejected." if success else "Rejection failed."), "info" if success else "danger")
    return redirect(url_for("auth.users_index"))


@bp.route("/admin/users/<int:user_id>/deactivate", methods=["POST"])
@login_required
@admin_required
def deactivate_user(user_id: int):
    auth = AuthService()
    success, message, _ = auth.deactivate_user(user_id)
    flash(message or ("User deactivated." if success else "Deactivation failed."), "info" if success else "danger")
    return redirect(url_for("auth.users_index"))


@bp.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
@require_delete_reauth
def delete_user(user_id: int):
    auth = AuthService()
    success, message, _ = auth.delete_user(user_id, actor_role=session.get("role"))
    flash(message or ("User deleted." if success else "Delete failed."), "info" if success else "danger")
    return redirect(url_for("auth.users_index"))
