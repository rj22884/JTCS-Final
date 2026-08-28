"""Signed SSO so ERP admins open website Property Admin without a second login."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from flask import current_app, request

DEFAULT_SSO_SECRET = "jtcs-xpert-recruitment-sso-v1"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def make_sso_token(email: str, name: str, role: str, secret: str, ttl_seconds: int = 180) -> str:
    payload = {
        "e": (email or "").strip().lower(),
        "n": (name or "JTCS Admin").strip() or "JTCS Admin",
        "r": (role or "admin").strip() or "admin",
        "exp": int(time.time()) + max(30, ttl_seconds),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    key = (secret or DEFAULT_SSO_SECRET).encode("utf-8")
    sig = hmac.new(key, raw, hashlib.sha256).digest()
    return f"{_b64(raw)}.{_b64(sig)}"


def property_public_base() -> str:
    explicit = (current_app.config.get("PROPERTY_PUBLIC_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    host = (request.host or "").split(":")[0].lower()
    if host in {"jtcsxpert.com", "www.jtcsxpert.com", "app.jtcsxpert.com"}:
        return "https://jtcsxpert.com"
    return "http://127.0.0.1:5070"


def sso_secret() -> str:
    return (
        current_app.config.get("PROPERTY_SSO_SECRET")
        or current_app.config.get("RECRUITMENT_SSO_SECRET")
        or DEFAULT_SSO_SECRET
    ).strip()
