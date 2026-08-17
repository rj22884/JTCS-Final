"""Anonymous visitor/session identifiers and user-agent parsing.

IP address is treated as a technical identifier only — never as a unique person.
No browser fingerprinting is performed.
"""

from __future__ import annotations

import uuid
from typing import Any

from flask import Request, current_app
from user_agents import parse as parse_ua


def new_visitor_id() -> str:
    return "V" + uuid.uuid4().hex[:12].upper()


def new_session_id() -> str:
    return "S" + uuid.uuid4().hex[:12].upper()


def normalize_id(value: Any, prefix: str, max_len: int = 64) -> str:
    text = str(value or "").strip()[:max_len]
    if not text:
        return ""
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    if not all(ch in allowed for ch in text):
        return prefix + uuid.uuid4().hex[:12].upper()
    return text


def client_ip(request: Request) -> str | None:
    if not current_app.config.get("STORE_IP_ADDRESS", True):
        return None
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    ip = forwarded or (request.remote_addr or "")
    return ip[:64] or None


def parse_client(request: Request) -> dict[str, str]:
    raw_ua = (request.headers.get("User-Agent") or "")[:500]
    ua = parse_ua(raw_ua)
    if ua.is_mobile:
        device = "Mobile"
    elif ua.is_tablet:
        device = "Tablet"
    elif ua.is_pc:
        device = "Desktop"
    else:
        device = "Other"
    browser = f"{ua.browser.family} {ua.browser.version_string}".strip()
    os_name = f"{ua.os.family} {ua.os.version_string}".strip()
    return {
        "user_agent": raw_ua,
        "device_type": device[:40],
        "browser": browser[:80],
        "operating_system": os_name[:80],
    }


def request_context(request: Request, payload: dict | None = None) -> dict:
    data = payload or {}
    visitor_id = normalize_id(data.get("visitor_id") or request.cookies.get("jtcs_vid"), "V")
    session_id = normalize_id(data.get("session_id") or request.cookies.get("jtcs_sid"), "S")
    if not visitor_id:
        visitor_id = new_visitor_id()
    if not session_id:
        session_id = new_session_id()
    parsed = parse_client(request)
    return {
        "visitor_id": visitor_id,
        "session_id": session_id,
        "ip_address": client_ip(request),
        "referrer": (data.get("referrer") or request.referrer or "")[:500],
        "page_url": (data.get("page_url") or request.url or "")[:500],
        **parsed,
    }
