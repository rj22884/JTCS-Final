"""Signed SSO token so ERP admins open recruitment without a second login."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

DEFAULT_SSO_SECRET = "jtcs-xpert-recruitment-sso-v1"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


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


def read_sso_token(token: str, secret: str) -> dict:
    if not token or "." not in token:
        raise ValueError("Invalid sign-in token.")
    raw_b64, sig_b64 = token.split(".", 1)
    raw = _unb64(raw_b64)
    expected = hmac.new((secret or DEFAULT_SSO_SECRET).encode("utf-8"), raw, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, _unb64(sig_b64)):
        raise ValueError("Invalid sign-in token.")
    payload = json.loads(raw.decode("utf-8"))
    if int(payload.get("exp") or 0) < int(time.time()):
        raise ValueError("Sign-in link expired. Open it again from ERP Admin Role.")
    email = (payload.get("e") or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("Sign-in token is missing the ERP email.")
    return {
        "email": email,
        "name": (payload.get("n") or "JTCS Admin").strip() or "JTCS Admin",
        "role": "admin" if str(payload.get("r") or "").lower() in {"admin", "administrator"} else "recruiter",
    }
