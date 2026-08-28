import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# Always load erp/.env from the package root (not process CWD) so VPS starts work.
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
    # ODBC Driver 18+ requires this for SQL Server self-signed certs (typical on Linux VPS).
    trust_cert = _env_bool("DB_TRUST_SERVER_CERTIFICATE", "True")
    trust = "TrustServerCertificate=yes;" if trust_cert else ""

    if trusted:
        odbc = (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            "Trusted_Connection=yes;"
            f"{trust}"
        )
    else:
        odbc = (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            f"{trust}"
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

    # SMTP — GoDaddy Titan / Workspace (see .env.example); secrets from environment only
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtpout.secureserver.net")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "465"))
    MAIL_USE_TLS = _env_bool("MAIL_USE_TLS", "False")
    MAIL_USE_SSL = _env_bool("MAIL_USE_SSL", "True")
    # Strip quotes — VPS .env often has MAIL_PASSWORD="secret" which breaks SMTP auth.
    MAIL_USERNAME = (os.getenv("MAIL_USERNAME") or "").strip().strip('"').strip("'")
    MAIL_PASSWORD = (os.getenv("MAIL_PASSWORD") or "").strip().strip('"').strip("'")
    MAIL_DEFAULT_SENDER = (os.getenv("MAIL_DEFAULT_SENDER") or "").strip().strip('"').strip("'")
    SUPPORT_EMAIL = (os.getenv("SUPPORT_EMAIL") or MAIL_USERNAME or "").strip().strip('"').strip("'")
    MAIL_DEBUG = _env_bool("MAIL_DEBUG", "False")
    MAIL_TIMEOUT = int(os.getenv("MAIL_TIMEOUT", "30"))
    SMTP_HEALTH_CHECK_ON_STARTUP = _env_bool("SMTP_HEALTH_CHECK_ON_STARTUP", "True")
    AUTH_TOKEN_EXPIRY_MINUTES = int(os.getenv("AUTH_TOKEN_EXPIRY_MINUTES", "30"))
    AUTH_TOKEN_EXPIRY_SECONDS = AUTH_TOKEN_EXPIRY_MINUTES * 60

    APP_BASE_URL = (os.getenv("APP_BASE_URL") or "http://localhost:8000").strip().strip('"').strip("'")
    SERVER_NAME = os.getenv("SERVER_NAME") or None
    PREFERRED_URL_SCHEME = os.getenv("PREFERRED_URL_SCHEME", "http")

    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH_MB", "10")) * 1024 * 1024
    UPLOAD_FOLDER = BASE_DIR / "app" / "static" / "uploads"
    CRM_DOCUMENT_FOLDER = UPLOAD_FOLDER / "crm_documents"
    CRM_WHATSAPP_MEDIA_FOLDER = UPLOAD_FOLDER / "whatsapp_media"
    CRM_EMAIL_ATTACHMENTS_FOLDER = UPLOAD_FOLDER / "email_attachments"

    # Website Sales Executive applications (SQLite from JTCS Web Page recruitment)
    _rec_db_env = (os.getenv("RECRUITMENT_DB_PATH") or "").strip().strip('"').strip("'")
    _rec_up_env = (os.getenv("RECRUITMENT_UPLOAD_DIR") or "").strip().strip('"').strip("'")
    _rec_db_local = Path(r"D:\JTCS Web Page\recruitment\var\recruitment.db")
    _rec_db_vps = Path("/var/www/jtcsxpert.com/recruitment/var/recruitment.db")
    _rec_up_local = Path(r"D:\JTCS Web Page\recruitment\var\uploads")
    _rec_up_vps = Path("/var/www/jtcsxpert.com/recruitment/var/uploads")
    RECRUITMENT_DB_PATH = Path(_rec_db_env) if _rec_db_env else (
        _rec_db_local if _rec_db_local.is_file() else _rec_db_vps
    )
    RECRUITMENT_UPLOAD_DIR = Path(_rec_up_env) if _rec_up_env else (
        _rec_up_local if _rec_up_local.is_dir() else _rec_up_vps
    )
    RECRUITMENT_ADMIN_URL = (
        os.getenv("RECRUITMENT_ADMIN_URL") or ""
    ).strip().strip('"').strip("'")
    RECRUITMENT_ADMIN_LOGIN_URL = (
        os.getenv("RECRUITMENT_ADMIN_LOGIN_URL") or ""
    ).strip().strip('"').strip("'")
    RECRUITMENT_PUBLIC_URL = (
        os.getenv("RECRUITMENT_PUBLIC_URL") or ""
    ).strip().strip('"').strip("'")
    RECRUITMENT_SSO_SECRET = (
        os.getenv("RECRUITMENT_SSO_SECRET") or "jtcs-xpert-recruitment-sso-v1"
    ).strip().strip('"').strip("'")

    # Website Property marketplace (SQLite from JTCS Web Page property module)
    _prop_db_env = (os.getenv("PROPERTY_DB_PATH") or "").strip().strip('"').strip("'")
    _prop_db_local = Path(r"D:\JTCS Web Page\property\var\property.db")
    _prop_db_vps = Path("/var/www/jtcsxpert.com/property/var/property.db")
    PROPERTY_DB_PATH = Path(_prop_db_env) if _prop_db_env else (
        _prop_db_local if _prop_db_local.is_file() else _prop_db_vps
    )
    PROPERTY_PUBLIC_URL = (
        os.getenv("PROPERTY_PUBLIC_URL") or os.getenv("RECRUITMENT_PUBLIC_URL") or ""
    ).strip().strip('"').strip("'")
    PROPERTY_SSO_SECRET = (
        os.getenv("PROPERTY_SSO_SECRET") or os.getenv("RECRUITMENT_SSO_SECRET") or "jtcs-xpert-recruitment-sso-v1"
    ).strip().strip('"').strip("'")

    # Website → ERP intake (public API key; website posts Contact/Consultation/Service)
    WEBSITE_INTAKE_API_KEY = (os.getenv("WEBSITE_INTAKE_API_KEY") or "").strip().strip('"').strip("'")
    NOTIFICATION_POLL_SECONDS = int(os.getenv("NOTIFICATION_POLL_SECONDS", "15"))

    # IMAP inbound for Communication Center Email channel
    IMAP_SERVER = (os.getenv("IMAP_SERVER") or "").strip().strip('"').strip("'")
    IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
    IMAP_USE_SSL = _env_bool("IMAP_USE_SSL", "True")
    IMAP_USERNAME = (os.getenv("IMAP_USERNAME") or os.getenv("MAIL_USERNAME") or "").strip().strip('"').strip("'")
    IMAP_PASSWORD = (os.getenv("IMAP_PASSWORD") or os.getenv("MAIL_PASSWORD") or "").strip().strip('"').strip("'")
    IMAP_FOLDER = (os.getenv("IMAP_FOLDER") or "INBOX").strip() or "INBOX"

    # Admin Role — database / full backups
    # BACKUP_ROOT = where the app stores downloadable .bak / full zip files.
    # SQL_SERVER_BACKUP_DIR = path SQL Server itself writes to (Linux mssql often
    # cannot write under /root; defaults to /var/opt/mssql/backup or /tmp).
    BACKUP_ROOT = Path(os.getenv("BACKUP_ROOT", str(BASE_DIR / "backups")))
    BACKUP_DATABASE_DIR = BACKUP_ROOT / "database"
    BACKUP_FULL_DIR = BACKUP_ROOT / "full"
    BACKUP_KEEP_COUNT = int(os.getenv("BACKUP_KEEP_COUNT", "20"))
    SQL_SERVER_BACKUP_DIR = (os.getenv("SQL_SERVER_BACKUP_DIR") or "").strip() or None
    DB_SERVER = os.getenv("DB_SERVER", r"JTCS\JTCS")
    DB_NAME = os.getenv("DB_NAME", "JTCSS")
    DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    DB_TRUSTED_CONNECTION = os.getenv("DB_TRUSTED_CONNECTION", "1") == "1"
    DB_TRUST_SERVER_CERTIFICATE = _env_bool("DB_TRUST_SERVER_CERTIFICATE", "True")
    DB_USER = os.getenv("DB_USER", "")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
