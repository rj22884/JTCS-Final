"""Encrypt / decrypt / mask integration secrets (Fernet via existing SECRET_KEY)."""

from __future__ import annotations

import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

logger = logging.getLogger(__name__)

MASK_PLACEHOLDER = "********"
UNCHANGED_SENTINEL = "__UNCHANGED__"


@lru_cache(maxsize=4)
def _fernet_for_secret(secret_key: str) -> Fernet:
    digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def _get_fernet() -> Fernet:
    secret = current_app.config.get("SECRET_KEY") or "jtcs-erp-dev-secret-change-me"
    return _fernet_for_secret(str(secret))


def encrypt_value(plain: str | None) -> str | None:
    if plain is None:
        return None
    text = str(plain)
    if text == "":
        return ""
    token = _get_fernet().encrypt(text.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_value(cipher: str | None) -> str | None:
    if cipher is None:
        return None
    text = str(cipher)
    if text == "":
        return ""
    try:
        return _get_fernet().decrypt(text.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.warning("IntegrationSettings decrypt failed (invalid token or key mismatch)")
        return None
    except Exception:
        logger.exception("IntegrationSettings decrypt error")
        return None


def mask_secret(plain: str | None, *, visible_tail: int = 4) -> str:
    if not plain:
        return ""
    value = str(plain)
    # visible_tail <= 0 => full mask only (required for form fields; value[-0:] is the whole string).
    if visible_tail <= 0 or len(value) <= visible_tail:
        return MASK_PLACEHOLDER
    return f"{MASK_PLACEHOLDER}{value[-visible_tail:]}"


def mask_access_token(plain: str | None) -> str:
    """Display style: EAAG*******************XYZ (never full token)."""
    if not plain:
        return ""
    value = str(plain).strip()
    if len(value) <= 10:
        return MASK_PLACEHOLDER
    head = value[:4]
    tail = value[-3:]
    return f"{head}{'*' * 19}{tail}"


def is_masked_or_unchanged(value: str | None) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    if text == "" or text == UNCHANGED_SENTINEL:
        return True
    if text == MASK_PLACEHOLDER or text.startswith(MASK_PLACEHOLDER):
        return True
    # Browser / UI may show a different number of bullets than MASK_PLACEHOLDER.
    if text and set(text) <= {"*"}:
        return True
    return False
