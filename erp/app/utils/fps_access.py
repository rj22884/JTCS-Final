"""FPS_USER session helpers and route/API allow-lists."""

from __future__ import annotations

import re

from flask import flash, jsonify, redirect, request, session, url_for

from app.utils.roles import FPS_USER_ROLE, has_fps_user_role

FPS_HOME_PATH = "/public-report/ration-card/fps-detail"
FPS_FORBIDDEN_MESSAGE = "You do not have permission to perform this action."
FPS_ACCESS_DENIED = "Access Denied."
FPS_SESSION_EXPIRED = "Your session has expired. Please login again."
FPS_INACTIVE_MESSAGE = "Your FPS account is inactive. Please contact JTCS Administrator."
FPS_LOGIN_ERROR = "Unable to login. Please try again."

FPS_ENABLED_PDS_SLUGS = frozenset({"fps", "ration-card"})
FPS_DISABLED_PDS_SLUGS = frozenset({"state", "district", "dso", "aro", "si"})
FPS_ENABLED_MASTER_PATHS = frozenset(
    {f"/public-report/ration-card/{slug}-master" for slug in FPS_ENABLED_PDS_SLUGS}
)
FPS_DISABLED_MASTER_PATHS = frozenset(
    {f"/public-report/ration-card/{slug}-master" for slug in FPS_DISABLED_PDS_SLUGS}
)
FPS_NAV_MASTER_PATHS = FPS_ENABLED_MASTER_PATHS | FPS_DISABLED_MASTER_PATHS

_DEALER_GET_RE = re.compile(r"^/public-report/api/dealers(?:/\d+)?$")
_PDS_ENABLED_GET_RE = re.compile(r"^/public-report/api/pds/(fps|ration-card)(?:/\d+)?$")


def wants_json_response() -> bool:
    return (
        request.is_json
        or (request.mimetype or "").startswith("application/json")
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in (request.headers.get("Accept") or "")
    )


def is_fps_session() -> bool:
    if not session.get("user_id"):
        return False
    if session.get("auth_mode") != "fps":
        return False
    if not has_fps_user_role(session.get("role")):
        return False
    return session_fps_row_id() is not None


def session_fps_row_id() -> int | None:
    raw = session.get("fps_row_id")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def fps_home_url() -> str:
    return url_for("public_report.fps_detail")


def fps_write_forbidden_response():
    return jsonify({"ok": False, "error": FPS_FORBIDDEN_MESSAGE}), 403


def fps_page_denied_response():
    if wants_json_response():
        return fps_write_forbidden_response()
    flash(FPS_ACCESS_DENIED, "danger")
    return redirect(fps_home_url())


def fps_session_expired_response():
    if wants_json_response():
        return jsonify({"ok": False, "error": FPS_SESSION_EXPIRED}), 401
    flash(FPS_SESSION_EXPIRED, "warning")
    return redirect(url_for("auth.login"))


def _normalize_path(path: str | None) -> str:
    cleaned = (path or "").split("?", 1)[0].strip().lower()
    if not cleaned:
        return "/"
    if not cleaned.startswith("/"):
        cleaned = "/" + cleaned
    if len(cleaned) > 1:
        cleaned = cleaned.rstrip("/")
    return cleaned


def fps_nav_menu_disabled(url: str | None, name: str | None = None) -> bool:
    target = _normalize_path(url)
    if target in FPS_DISABLED_MASTER_PATHS:
        return True
    label = (name or "").strip().lower()
    return label in {
        "state master",
        "district master",
        "dso master",
        "aro master",
        "si master",
    }


def fps_pds_slug_allowed(slug: str | None) -> bool:
    return (slug or "").strip().lower() in FPS_ENABLED_PDS_SLUGS


def fps_user_request_allowed(path: str | None, method: str | None) -> bool:
    """True when an authenticated FPS_USER may hit this path."""
    verb = (method or "GET").upper()
    if verb == "HEAD":
        verb = "GET"
    target = _normalize_path(path)
    if target in {
        "/logout",
        "/login",
        "/other-login",
        "/fps-login",
        "/server-auth",
        "/sw.js",
        "/manifest.webmanifest",
        "/api/runtime",
    }:
        return verb == "GET"
    if target == FPS_HOME_PATH or target in FPS_ENABLED_MASTER_PATHS:
        return verb == "GET"
    if target in {
        "/public-report/api/ration-card/fps-detail/latest",
        "/public-report/api/ration-card/fps-detail/pdf",
    }:
        return verb == "GET"
    if target == "/api/notifications/unread" or target.startswith("/api/notifications/unread"):
        return verb == "GET"
    if target.startswith("/api/market/"):
        return verb == "GET"
    if _DEALER_GET_RE.fullmatch(target):
        return verb == "GET"
    if _PDS_ENABLED_GET_RE.fullmatch(target):
        return verb == "GET"
    return False


def establish_fps_session(data: dict) -> None:
    session.clear()
    session["user_id"] = data["user_id"]
    session["user_name"] = data["user_name"]
    session["role"] = data.get("role") or FPS_USER_ROLE
    session["fps_row_id"] = int(data["fps_row_id"])
    session["fps_id"] = data.get("fps_id") or ""
    session["auth_mode"] = "fps"
    if data.get("login_session_id"):
        session["login_session_id"] = data["login_session_id"]
    session.permanent = False
    session.pop("server_user_id", None)
    session.pop("server_login_id", None)
    session.pop("server_auth_at", None)
