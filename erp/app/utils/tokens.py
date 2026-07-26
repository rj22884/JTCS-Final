from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from flask import current_app


def _serializer(purpose: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=purpose)


def create_signed_token(user_id: int, email: str, purpose: str) -> str:
    return _serializer(purpose).dumps({"uid": user_id, "email": email.lower()})


def load_signed_token(token: str, purpose: str, max_age: int | None = None) -> dict | None:
    if max_age is None:
        max_age = current_app.config.get("AUTH_TOKEN_EXPIRY_SECONDS", 1800)
    try:
        data = _serializer(purpose).loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict):
        return None
    return data
