from functools import wraps

from flask import flash, jsonify, redirect, request, session, url_for

from app.utils.delete_auth import verify_delete_credentials
from app.utils.roles import ADMIN_ROLES, has_admin_role


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not has_admin_role(session.get("role")):
            flash("Administrator access required.", "danger")
            return redirect(url_for("dashboard.index"))
        return view(*args, **kwargs)

    return wrapped


def require_delete_reauth(view):
    """Require logged-in User ID + password before a delete endpoint runs."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        payload = request.get_json(silent=True) or {}
        user_id = (
            payload.get("user_id")
            or payload.get("userid")
            or request.form.get("user_id")
            or request.args.get("user_id")
            or ""
        )
        password = (
            payload.get("password")
            or request.form.get("password")
            or request.args.get("password")
            or ""
        )
        try:
            verify_delete_credentials(str(user_id), str(password))
        except ValueError as exc:
            wants_json = (
                request.is_json
                or (request.mimetype or "").startswith("application/json")
                or request.headers.get("X-Requested-With") == "XMLHttpRequest"
                or "application/json" in (request.headers.get("Accept") or "")
                or request.method == "DELETE"
            )
            if wants_json:
                return (
                    jsonify(
                        {
                            "ok": False,
                            "success": False,
                            "error": str(exc),
                            "message": str(exc),
                        }
                    ),
                    400,
                )
            flash(str(exc), "danger")
            return redirect(request.referrer or url_for("dashboard.index"))
        return view(*args, **kwargs)

    return wrapped
