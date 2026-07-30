import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# Always load erp/.env from the package root (not process CWD) so VPS/systemd starts work.
load_dotenv(BASE_DIR / ".env")


def _env_bool(name: str, default: str = "False") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def build_sqlalchemy_uri() -> str:
    server = os.getenv("DB_SERVER", r"JTCS\JTCS")
    database = os.getenv("DB_NAME", "JTCSS")
    driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    trusted = os.getenv("DB_TRUSTED_CONNECTION", "1") == "1"
    username = os.getenv("DB_USER", "")
    password = os.getenv("DB_PASSWORD", "")

    if trusted:
        odbc = (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            "Trusted_Connection=yes;"
        )
    else:
        odbc = (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
        )

    return f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc)}"


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "jtcs-erp-dev-secret-change-me")
    DEBUG = os.getenv("FLASK_DEBUG", "1") == "1"
    PORT = int(os.getenv("FLASK_RUN_PORT", os.getenv("PORT", "8000")))
    SQLALCHEMY_DATABASE_URI = build_sqlalchemy_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    }
    APP_NAME = os.getenv("APP_NAME", "JTCS ERP")
    APP_VERSION = os.getenv("APP_VERSION", "2026.1")
    COMPANY_DISPLAY_NAME = os.getenv("COMPANY_DISPLAY_NAME", "Joshi Tax Consultancy & Services")
    COMPANY_TAGLINE = os.getenv("COMPANY_TAGLINE", "Income Tax | GST | Compliance Services")
    # Seller details for GST Tax Invoice PDF (override via .env as needed)
    COMPANY_GSTIN = os.getenv("COMPANY_GSTIN", "05AEBPJ1665H2ZR")
    COMPANY_PAN = os.getenv("COMPANY_PAN", "AEBPJ1665H")
    COMPANY_CIN = os.getenv("COMPANY_CIN", "")
    COMPANY_ADDRESS = os.getenv(
        "COMPANY_ADDRESS",
        "Sanjay Colony, Nainital Road, Haldwani, Uttarakhand 263139",
    )
    COMPANY_STATE = os.getenv("COMPANY_STATE", "Uttarakhand")
    COMPANY_STATE_CODE = os.getenv("COMPANY_STATE_CODE", "05")
    COMPANY_PHONE = os.getenv("COMPANY_PHONE", "9412040614")
    COMPANY_EMAIL = os.getenv("COMPANY_EMAIL", "admin@jtcsxpert.com")
    COMPANY_WEBSITE = os.getenv("COMPANY_WEBSITE", "www.jtcsxpert.com")
    DB_SERVER_DISPLAY = os.getenv("DB_SERVER", r"JTCS\JTCS")
    DB_NAME_DISPLAY = os.getenv("DB_NAME", "JTCSS")
    DB_CONNECTION_DISPLAY = f"{DB_SERVER_DISPLAY}\\{DB_NAME_DISPLAY}"

    PERMANENT_SESSION_LIFETIME = timedelta(
        days=int(os.getenv("SESSION_LIFETIME_DAYS", "14"))
    )
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # SMTP - GoDaddy Titan (see .env.example); all secrets from environment only
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtpout.secureserver.net")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "465"))
    MAIL_USE_TLS = _env_bool("MAIL_USE_TLS", "False")
    MAIL_USE_SSL = _env_bool("MAIL_USE_SSL", "True")
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = (os.getenv("MAIL_DEFAULT_SENDER") or "").strip().strip('"').strip("'")
    SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL") or os.getenv("MAIL_USERNAME", "")
    MAIL_DEBUG = _env_bool("MAIL_DEBUG", "False")
    MAIL_TIMEOUT = int(os.getenv("MAIL_TIMEOUT", "30"))
    SMTP_HEALTH_CHECK_ON_STARTUP = _env_bool("SMTP_HEALTH_CHECK_ON_STARTUP", "True")
    AUTH_TOKEN_EXPIRY_MINUTES = int(os.getenv("AUTH_TOKEN_EXPIRY_MINUTES", "30"))
    AUTH_TOKEN_EXPIRY_SECONDS = AUTH_TOKEN_EXPIRY_MINUTES * 60

    APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
    SERVER_NAME = os.getenv("SERVER_NAME") or None
    PREFERRED_URL_SCHEME = os.getenv("PREFERRED_URL_SCHEME", "http")

    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
    UPLOAD_FOLDER = BASE_DIR / "app" / "static" / "uploads"

    # Admin Role - database / full backups (SQL Server must be able to write DB path)
    BACKUP_ROOT = Path(os.getenv("BACKUP_ROOT", str(BASE_DIR / "backups")))
    BACKUP_DATABASE_DIR = BACKUP_ROOT / "database"
    BACKUP_FULL_DIR = BACKUP_ROOT / "full"
    BACKUP_KEEP_COUNT = int(os.getenv("BACKUP_KEEP_COUNT", "20"))
    DB_SERVER = os.getenv("DB_SERVER", r"JTCS\JTCS")
    DB_NAME = os.getenv("DB_NAME", "JTCSS")
    DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    DB_TRUSTED_CONNECTION = os.getenv("DB_TRUSTED_CONNECTION", "1") == "1"
    DB_USER = os.getenv("DB_USER", "")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

