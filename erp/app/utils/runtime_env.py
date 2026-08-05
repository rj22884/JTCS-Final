"""Detect local Windows PC vs Linux VPS runtime for Utility sync labels."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from flask import current_app, has_app_context, has_request_context, request


def is_vps_runtime() -> bool:
    """True when this process is the Linux production host (not the Windows PC)."""
    if os.name == "nt":
        return False

    base = ""
    if has_app_context():
        base = (current_app.config.get("APP_BASE_URL") or "").strip()
    host = (urlparse(base).hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return False

    if has_request_context() and request.host:
        req_host = (request.host.split(":")[0] or "").lower()
        if req_host in {"localhost", "127.0.0.1", "::1"}:
            return False

    return True


def sync_menu_label(*, vps: bool | None = None) -> str:
    if vps is None:
        vps = is_vps_runtime()
    return "Download Local" if vps else "Upload VPS"


def sync_menu_description(*, vps: bool | None = None) -> str:
    if vps is None:
        vps = is_vps_runtime()
    if vps:
        return "Download full application + database ZIP for restore on local PC"
    return "Push code to GitHub and deploy this app to the VPS"
