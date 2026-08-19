"""Server User gate after JTCS application login."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.decorators import login_required, server_auth_exempt
from app.services.server_auth_service import ServerAuthService
from app.repositories.user_repository import UserRepository

bp = Blueprint("server_auth", __name__, url_prefix="/server-auth")


def _next_url() -> str:
    target = (request.args.get("next") or request.form.get("next") or "").strip()
    if target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("dashboard.index")


def _signed_in_user():
    user_id = int(session["user_id"])
    user = UserRepository().get_by_id(user_id)
    email = (user.EmailID if user else "") or ""
    return user_id, user, email


def _dialog_type(message: str) -> str:
    text = (message or "").lower()
    if "invalid" in text or "cannot" in text or "not allowed" in text or "must" in text or "please enter" in text:
        return "invalid"
    return "error"


def _render_login(*, service: ServerAuthService, email: str, dialog_error: str | None = None):
    user_id = int(session["user_id"])
    defaults = service.default_login_fields(user_id)
    return render_template(
        "auth/server_login.html",
        next_url=_next_url(),
        email=email,
        user_name=session.get("user_name") or "",
        login_id=request.form.get("login_id") or defaults.get("login_id") or "",
        password=defaults.get("password") or "",
        dialog_error=dialog_error or "",
        dialog_type=_dialog_type(dialog_error) if dialog_error else "invalid",
    )


def _render_create(*, email: str, dialog_error: str | None = None, login_id: str = ""):
    return render_template(
        "auth/server_create.html",
        next_url=_next_url(),
        email=email,
        user_name=session.get("user_name") or "",
        login_id=login_id,
        dialog_error=dialog_error or "",
        dialog_type=_dialog_type(dialog_error) if dialog_error else "invalid",
    )


@bp.route("", methods=["GET"], strict_slashes=False)
@login_required
@server_auth_exempt
def gate():
    service = ServerAuthService()
    # Never auto-login from the remember cookie — always show Server User ID / password.
    if service.is_authenticated():
        return redirect(_next_url())
    user_id, _user, email = _signed_in_user()
    existing = service.get_by_user_id(user_id)
    if existing:
        return _render_login(service=service, email=email)
    return _render_create(email=email)


@bp.route("/create", methods=["POST"], strict_slashes=False)
@login_required
@server_auth_exempt
def create():
    service = ServerAuthService()
    user_id, _user, email = _signed_in_user()
    login_id = request.form.get("login_id", "")
    ok, message = service.create_server_user(
        user_id=user_id,
        login_id=login_id,
        password=request.form.get("password", ""),
        confirm=request.form.get("confirm_password", ""),
    )
    if not ok:
        return _render_create(email=email, dialog_error=message, login_id=login_id.strip())
    flash(message, "success")
    return redirect(url_for("server_auth.gate", next=_next_url()))


@bp.route("/login", methods=["POST"], strict_slashes=False)
@login_required
@server_auth_exempt
def login():
    service = ServerAuthService()
    user_id, _user, email = _signed_in_user()
    ok, message, row = service.authenticate(
        user_id=user_id,
        login_id=request.form.get("login_id", ""),
        password=request.form.get("password", ""),
    )
    if not ok:
        return _render_login(service=service, email=email, dialog_error=message)
    service.establish_session(row)
    response = redirect(_next_url())
    return service.attach_remember_cookie(
        response,
        user_id=user_id,
        login_id=request.form.get("login_id", ""),
        password=request.form.get("password", ""),
    )


@bp.route("/forgot", methods=["GET", "POST"], strict_slashes=False)
@login_required
@server_auth_exempt
def forgot():
    service = ServerAuthService()
    user_id, _user, email = _signed_in_user()
    if request.method == "POST":
        ok, message = service.request_reset(
            user_id=user_id,
            email=request.form.get("email", email),
        )
        if ok:
            flash(message, "info")
            return redirect(url_for("server_auth.gate"))
        return render_template(
            "auth/server_forgot.html",
            email=request.form.get("email", email),
            dialog_error=message,
            dialog_type=_dialog_type(message),
        )
    return render_template("auth/server_forgot.html", email=email)


@bp.route("/reset-password", methods=["GET", "POST"], strict_slashes=False)
@bp.route("/reset-password/<token>", methods=["GET", "POST"], strict_slashes=False)
def reset_password(token: str | None = None):
    service = ServerAuthService()
    token = token or request.args.get("token") or request.form.get("token") or ""
    if request.method == "POST":
        ok, message = service.reset_password(
            token,
            request.form.get("password", ""),
            request.form.get("confirm_password", ""),
        )
        if ok:
            flash(message, "success")
            response = (
                redirect(url_for("server_auth.gate"))
                if session.get("user_id")
                else redirect(url_for("auth.login"))
            )
            return service.clear_remember_cookie(response)
        peek_ok, peek_msg, data = service.peek_reset_token(token)
        return render_template(
            "auth/server_reset.html",
            token=token,
            login_id=data.get("login_id") if peek_ok else "",
            dialog_error=message,
            dialog_type=_dialog_type(message),
            error=None if peek_ok else peek_msg,
        )
    ok, message, data = service.peek_reset_token(token)
    if not ok:
        flash(message, "danger")
        if session.get("user_id"):
            return redirect(url_for("server_auth.forgot"))
        return redirect(url_for("auth.login"))
    return render_template(
        "auth/server_reset.html",
        token=token,
        login_id=data.get("login_id") or "",
    )
