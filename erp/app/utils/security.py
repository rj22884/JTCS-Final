import hashlib
import secrets
from datetime import datetime, timedelta

import bcrypt
from werkzeug.security import check_password_hash


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password_hash: str, password: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return check_password_hash(password_hash, password)


def generate_otp(length: int = 6) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))


def generate_secure_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def token_expiry(minutes: int | None = None) -> datetime:
    if minutes is None:
        minutes = 30
    return datetime.utcnow() + timedelta(minutes=minutes)
