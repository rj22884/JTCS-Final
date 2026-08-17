"""Recruitment module configuration. Credentials come from the environment."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_DIR = Path(__file__).resolve().parent
VAR_DIR = PACKAGE_DIR / "var"

load_dotenv(PACKAGE_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _database_uri() -> str:
    """Resolve sqlite:///var/... against the recruitment package, not the process cwd."""
    raw = (os.environ.get("DATABASE_URL") or "").strip()
    default_path = VAR_DIR / "recruitment.db"
    if not raw:
        VAR_DIR.mkdir(parents=True, exist_ok=True)
        return "sqlite:///" + str(default_path).replace("\\", "/")
    if raw.startswith("sqlite:///"):
        path_part = raw[len("sqlite:///"):]
        if path_part.startswith("/") or (len(path_part) >= 2 and path_part[1] == ":"):
            Path(path_part).parent.mkdir(parents=True, exist_ok=True)
            return raw
        resolved = (PACKAGE_DIR / path_part).resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return "sqlite:///" + str(resolved).replace("\\", "/")
    return raw


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-only-change-me"
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    WTF_CSRF_TIME_LIMIT = 8 * 60 * 60
    WTF_CSRF_SSL_STRICT = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    REMEMBER_COOKIE_HTTPONLY = True

    STORE_IP_ADDRESS = _bool("STORE_IP_ADDRESS", True)
    UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR") or (VAR_DIR / "uploads"))
    if not UPLOAD_DIR.is_absolute():
        UPLOAD_DIR = PACKAGE_DIR / UPLOAD_DIR
    MAX_RESUME_MB = _int("MAX_RESUME_MB", 5)
    APPLICATION_PDF_DIR = Path(os.environ.get("APPLICATION_PDF_DIR") or (VAR_DIR / "application_pdfs"))
    if not APPLICATION_PDF_DIR.is_absolute():
        APPLICATION_PDF_DIR = PACKAGE_DIR / APPLICATION_PDF_DIR
    # Resume limit plus multipart form fields/overhead. A tighter cap returns 413
    # and drops the whole application when a near-5 MB resume is attached.
    MAX_CONTENT_LENGTH = max(8, MAX_RESUME_MB + 3) * 1024 * 1024

    APPLICATION_NUMBER_PREFIX = os.environ.get("APPLICATION_NUMBER_PREFIX") or "JTCS-SE"
    APPLICATION_NUMBER_PADDING = _int("APPLICATION_NUMBER_PADDING", 5)
    EMPLOYEE_CODE_PREFIX = os.environ.get("EMPLOYEE_CODE_PREFIX") or "EMP"
    EMPLOYEE_CODE_PADDING = _int("EMPLOYEE_CODE_PADDING", 5)
    HR_LETTER_DIR = Path(os.environ.get("HR_LETTER_DIR") or (VAR_DIR / "hr_letters"))
    if not HR_LETTER_DIR.is_absolute():
        HR_LETTER_DIR = PACKAGE_DIR / HR_LETTER_DIR
    EMPLOYEE_DOC_DIR = Path(os.environ.get("EMPLOYEE_DOC_DIR") or (VAR_DIR / "employee_docs"))
    if not EMPLOYEE_DOC_DIR.is_absolute():
        EMPLOYEE_DOC_DIR = PACKAGE_DIR / EMPLOYEE_DOC_DIR

    ADMIN_NAME = os.environ.get("RECRUITMENT_ADMIN_NAME") or "JTCS Admin"
    ADMIN_EMAIL = (os.environ.get("RECRUITMENT_ADMIN_EMAIL") or "admin@jtcsxpert.com").lower()
    ADMIN_PASSWORD = os.environ.get("RECRUITMENT_ADMIN_PASSWORD") or ""

    CORS_ORIGINS = [
        o.strip()
        for o in (os.environ.get("CORS_ORIGINS") or "").split(",")
        if o.strip()
    ] or [
        "https://jtcsxpert.com",
        "https://www.jtcsxpert.com",
        "http://localhost:5000",
        "http://127.0.0.1:5000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5050",
        "http://127.0.0.1:5050",
    ]
    PUBLIC_SITE_URL = (os.environ.get("PUBLIC_SITE_URL") or "").rstrip("/")

    SMTP_HOST = os.environ.get("SMTP_HOST") or ""
    SMTP_PORT = _int("SMTP_PORT", 587)
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME") or ""
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD") or ""
    SMTP_USE_TLS = _bool("SMTP_USE_TLS", True)
    SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL") or "admin@jtcsxpert.com"
    SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME") or "JTCS Xpert Recruitment"
    RECRUITMENT_NOTIFY_EMAIL = os.environ.get("RECRUITMENT_NOTIFY_EMAIL") or "admin@jtcsxpert.com"

    TEMPLATES_AUTO_RELOAD = True
    HOST = os.environ.get("HOST") or "127.0.0.1"
    PORT = _int("PORT", 5050)
    PREFERRED_URL_SCHEME = os.environ.get("PREFERRED_URL_SCHEME") or "http"
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI") or "memory://"
    SSO_SECRET = os.environ.get("RECRUITMENT_SSO_SECRET") or "jtcs-xpert-recruitment-sso-v1"


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret"
    STORE_IP_ADDRESS = True
    ADMIN_EMAIL = "admin@jtcsxpert.com"
    ADMIN_PASSWORD = "TestAdmin!234"
    SMTP_HOST = ""
    RATELIMIT_ENABLED = False
