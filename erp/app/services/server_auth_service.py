"""Second-factor Server User on top of existing JTCS Users login."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from flask import current_app, has_request_context, request, session
from sqlalchemy import text

from app.extensions import db
from app.repositories.user_repository import AuthTokenRepository, UserRepository
from app.services.auth_service import AuthService
from app.services.email_service import EmailService, SMTP_USER_MESSAGE
from app.services.server_audit_service import STATUS_FAILED, STATUS_SUCCESS, ServerAuditService
from app.utils.security import hash_password, hash_token, token_expiry, verify_password
from app.utils.tokens import create_signed_token, dump_payload, load_payload, load_signed_token
from app.utils.url_helpers import external_url_for

logger = logging.getLogger(__name__)

LOGIN_ID_RE = re.compile(r"^[A-Za-z0-9]{1,80}$")
TOKEN_TYPE = "SERVER_PASSWORD_RESET"
TOKEN_PURPOSE = "server_password_reset"
SESSION_IDLE_HOURS = 12
REMEMBER_COOKIE = "jtcs_server_remember"
REMEMBER_PURPOSE = "server-remember"
REMEMBER_DAYS = 365

_SCHEMA_READY = False


def utcnow() -> datetime:
    return datetime.utcnow()


class ServerAuthService:
    def __init__(self):
        self.users = UserRepository()
        self.tokens = AuthTokenRepository()
        self.email = EmailService()
        self.auth = AuthService()
        self.audit = ServerAuditService()

    def ensure_schema(self) -> None:
        global _SCHEMA_READY
        if _SCHEMA_READY:
            return
        statements = (
            """
            IF OBJECT_ID(N'dbo.ServerUser', N'U') IS NULL
            BEGIN
                CREATE TABLE dbo.ServerUser (
                    ServerUserID INT IDENTITY(1, 1) NOT NULL
                        CONSTRAINT PK_ServerUser PRIMARY KEY,
                    UserID INT NOT NULL,
                    LoginID NVARCHAR(80) NOT NULL,
                    PasswordHash NVARCHAR(255) NOT NULL,
                    IsActive BIT NOT NULL CONSTRAINT DF_ServerUser_IsActive DEFAULT (1),
                    CreatedDate DATETIME2 NOT NULL CONSTRAINT DF_ServerUser_CreatedDate DEFAULT (SYSUTCDATETIME()),
                    ModifiedDate DATETIME2 NULL,
                    LastLoginDate DATETIME2 NULL,
                    CONSTRAINT UQ_ServerUser_UserID UNIQUE (UserID),
                    CONSTRAINT UQ_ServerUser_LoginID UNIQUE (LoginID)
                );
                CREATE INDEX IX_ServerUser_LoginID ON dbo.ServerUser (LoginID);
            END;
            """,
            """
            IF COL_LENGTH(N'dbo.AuditLog', N'Module') IS NULL
                ALTER TABLE dbo.AuditLog ADD Module NVARCHAR(100) NULL;
            """,
            """
            IF COL_LENGTH(N'dbo.AuditLog', N'Status') IS NULL
                ALTER TABLE dbo.AuditLog ADD Status NVARCHAR(30) NULL;
            """,
        )
        for sql in statements:
            db.session.execute(text(sql))
        db.session.commit()
        _SCHEMA_READY = True

    def get_by_user_id(self, user_id: int) -> dict | None:
        self.ensure_schema()
        row = db.session.execute(
            text(
                """
                SELECT ServerUserID, UserID, LoginID, PasswordHash, IsActive
                FROM dbo.ServerUser
                WHERE UserID = :user_id
                """
            ),
            {"user_id": int(user_id)},
        ).mappings().first()
        return dict(row) if row else None

    def get_by_login_id(self, login_id: str) -> dict | None:
        self.ensure_schema()
        row = db.session.execute(
            text(
                """
                SELECT ServerUserID, UserID, LoginID, PasswordHash, IsActive
                FROM dbo.ServerUser
                WHERE LOWER(LoginID) = LOWER(:login_id)
                """
            ),
            {"login_id": (login_id or "").strip()},
        ).mappings().first()
        return dict(row) if row else None

    @staticmethod
    def app_login_keys(email: str | None) -> set[str]:
        email = (email or "").strip().lower()
        keys: set[str] = set()
        if email:
            keys.add(email)
            keys.add(email.split("@", 1)[0])
        keys.discard("")
        return keys

    def validate_login_id(
        self,
        login_id: str,
        *,
        user_id: int | None = None,
        app_email: str | None = None,
    ) -> str | None:
        value = (login_id or "").strip()
        if not value:
            return "Please enter a Server User ID."
        if not LOGIN_ID_RE.match(value):
            return (
                "Server User ID can contain letters and numbers only. "
                "Special characters are not allowed."
            )
        email = app_email
        if email is None and user_id is not None:
            user = self.users.get_by_id(user_id)
            email = user.EmailID if user else ""
        if value.lower() in self.app_login_keys(email):
            return "Server User ID cannot be the same as the application login ID."
        return None

    def validate_server_password(
        self,
        password: str,
        confirm: str,
        *,
        user_id: int,
    ) -> str | None:
        password = password or ""
        confirm = confirm if confirm is not None else ""
        if not password:
            return "Please enter a Server password."
        if not confirm:
            return "Please confirm the Server password."
        if password != confirm:
            return "Passwords do not match."
        user = self.users.get_by_id(user_id)
        if user and user.PasswordHash and verify_password(user.PasswordHash, password):
            return "Server password cannot be the same as the application password."
        return None

    def create_server_user(self, *, user_id: int, login_id: str, password: str, confirm: str) -> tuple[bool, str]:
        self.ensure_schema()
        if self.get_by_user_id(user_id):
            return False, "A Server User already exists for this account. Please sign in."
        error = self.validate_login_id(login_id, user_id=user_id)
        if error:
            return False, error
        pwd_error = self.validate_server_password(password, confirm, user_id=user_id)
        if pwd_error:
            return False, pwd_error
        existing = self.get_by_login_id(login_id)
        if existing:
            return False, "This Server User ID is already taken. Choose another."
        try:
            db.session.execute(
                text(
                    """
                    INSERT INTO dbo.ServerUser (UserID, LoginID, PasswordHash, IsActive, CreatedDate)
                    VALUES (:user_id, :login_id, :password_hash, 1, :created)
                    """
                ),
                {
                    "user_id": int(user_id),
                    "login_id": login_id.strip(),
                    "password_hash": hash_password(password),
                    "created": utcnow(),
                },
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("Server user create failed")
            return False, "Unable to create Server User. Please try again."
        user = self.users.get_by_id(user_id)
        self.audit.log(
            action="Server User Created",
            module="ServerAuth",
            record_id=user_id,
            status=STATUS_SUCCESS,
            new_value={"login_id": login_id.strip()},
            user_id=user_id,
            user_name=user.FullName if user else None,
        )
        return True, "Server User created. Sign in with your Server User ID and password."

    def authenticate(
        self,
        *,
        user_id: int,
        login_id: str,
        password: str,
        quiet: bool = False,
    ) -> tuple[bool, str, dict]:
        self.ensure_schema()
        row = self.get_by_login_id(login_id)
        user = self.users.get_by_id(user_id)
        display_name = user.FullName if user else None
        if row is None or int(row["UserID"]) != int(user_id) or not row.get("IsActive"):
            if not quiet:
                self.audit.log(
                    action="Login Failed",
                    module="ServerAuth",
                    record_id=user_id,
                    status=STATUS_FAILED,
                    new_value={"login_id": (login_id or "").strip()},
                    user_id=user_id,
                    user_name=display_name,
                )
            return False, "Invalid Server User ID or password.", {}
        if not verify_password(row["PasswordHash"], password):
            if not quiet:
                self.audit.log(
                    action="Login Failed",
                    module="ServerAuth",
                    record_id=user_id,
                    status=STATUS_FAILED,
                    new_value={"login_id": row["LoginID"]},
                    user_id=user_id,
                    user_name=display_name,
                )
            return False, "Invalid Server User ID or password.", {}
        db.session.execute(
            text(
                """
                UPDATE dbo.ServerUser
                SET LastLoginDate = :now
                WHERE ServerUserID = :pk
                """
            ),
            {"now": utcnow(), "pk": int(row["ServerUserID"])},
        )
        db.session.commit()
        self.audit.log(
            action="Login Success",
            module="ServerAuth",
            record_id=int(row["ServerUserID"]),
            status=STATUS_SUCCESS,
            new_value={"login_id": row["LoginID"], "remembered": quiet},
            user_id=user_id,
            user_name=display_name,
        )
        return True, "Server authentication successful.", dict(row)

    def remembered_credentials(self, user_id: int) -> dict:
        """Last successful Server User ID + password for this JTCS user (encrypted cookie)."""
        if not has_request_context():
            return {}
        token = request.cookies.get(REMEMBER_COOKIE) or ""
        max_age = REMEMBER_DAYS * 24 * 3600
        data = load_payload(token, REMEMBER_PURPOSE, max_age=max_age)
        if not data or int(data.get("uid") or 0) != int(user_id):
            return {}
        login_id = str(data.get("login_id") or "").strip()
        password = str(data.get("password") or "")
        if not login_id or not password:
            return {}
        return {"login_id": login_id, "password": password}

    def default_login_fields(self, user_id: int) -> dict:
        remembered = self.remembered_credentials(user_id)
        existing = self.get_by_user_id(user_id) or {}
        return {
            "login_id": remembered.get("login_id") or existing.get("LoginID") or "",
            "password": remembered.get("password") or "",
        }

    def attach_remember_cookie(self, response, *, user_id: int, login_id: str, password: str):
        token = dump_payload(
            {
                "uid": int(user_id),
                "login_id": (login_id or "").strip(),
                "password": password or "",
            },
            REMEMBER_PURPOSE,
        )
        response.set_cookie(
            REMEMBER_COOKIE,
            token,
            max_age=REMEMBER_DAYS * 24 * 3600,
            httponly=True,
            samesite="Lax",
            secure=bool(current_app.config.get("SESSION_COOKIE_SECURE")),
            path="/",
        )
        return response

    def clear_remember_cookie(self, response):
        response.delete_cookie(REMEMBER_COOKIE, path="/")
        return response

    def establish_session(self, row: dict) -> None:
        session["server_user_id"] = int(row["ServerUserID"])
        session["server_login_id"] = row["LoginID"]
        session["server_auth_at"] = utcnow().replace(tzinfo=timezone.utc).isoformat()

    def clear_session(self) -> None:
        session.pop("server_user_id", None)
        session.pop("server_login_id", None)
        session.pop("server_auth_at", None)

    def is_authenticated(self) -> bool:
        if not session.get("user_id") or not session.get("server_user_id"):
            return False
        raw = session.get("server_auth_at") or ""
        try:
            stamped = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if stamped.tzinfo is None:
                stamped = stamped.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - stamped).total_seconds() / 3600.0
        except (TypeError, ValueError):
            age_hours = SESSION_IDLE_HOURS + 1
        if age_hours > SESSION_IDLE_HOURS:
            self.audit.log(
                action="Session Expired",
                module="ServerAuth",
                record_id=session.get("server_user_id"),
                status=STATUS_FAILED,
            )
            self.clear_session()
            return False
        session["server_auth_at"] = utcnow().replace(tzinfo=timezone.utc).isoformat()
        return True

    def log_logout(self) -> None:
        if not session.get("user_id"):
            return
        self.audit.log(
            action="Logout",
            module="ServerAuth",
            record_id=session.get("server_user_id"),
            status=STATUS_SUCCESS,
            new_value={"login_id": session.get("server_login_id")},
        )

    def request_reset(self, *, user_id: int, email: str) -> tuple[bool, str]:
        """Send a one-time, time-limited reset link. Never emails the password."""
        self.ensure_schema()
        user = self.users.get_by_id(user_id)
        generic = "If the email matches this account, a reset link has been sent."
        email = (email or "").strip().lower()
        if user is None or (user.EmailID or "").strip().lower() != email:
            return True, generic
        server_user = self.get_by_user_id(user_id)
        if server_user is None:
            return True, generic
        try:
            reset_token = create_signed_token(user_id, email, TOKEN_PURPOSE)
            self.tokens.invalidate_active(TOKEN_TYPE, user_id=user_id, email=email)
            self.tokens.create(
                {
                    "UserID": user_id,
                    "Email": email,
                    "TokenType": TOKEN_TYPE,
                    "TokenHash": hash_token(reset_token),
                    "ExpiresAt": token_expiry(self.auth._token_expiry_minutes()),
                    "CreatedDate": utcnow(),
                }
            )
            db.session.commit()
            reset_url = external_url_for("server_auth.reset_password", token=reset_token)
            sent, mail_error = self.email.send_password_reset_email(
                email, user.FullName, reset_url
            )
            if not sent:
                return False, mail_error or SMTP_USER_MESSAGE
        except Exception:
            db.session.rollback()
            logger.exception("Server user reset request failed")
            return False, "Unable to send reset link right now. Please try again."
        self.audit.log(
            action="Password Reset",
            module="ServerAuth",
            record_id=user_id,
            status=STATUS_SUCCESS,
            new_value={"email_sent": True},
            user_id=user_id,
            user_name=user.FullName,
        )
        return True, generic

    def peek_reset_token(self, token: str) -> tuple[bool, str, dict]:
        data = load_signed_token(token, TOKEN_PURPOSE)
        if not data:
            return False, "This reset link is invalid or has expired.", {}
        token_row = self.auth._find_token(TOKEN_TYPE, hash_token(token))
        if token_row is None:
            return False, "This reset link is invalid, used, or expired.", {}
        user_id = int(data.get("uid") or 0)
        server_user = self.get_by_user_id(user_id)
        if not server_user:
            return False, "No Server User is linked to this account.", {}
        return True, "", {"login_id": server_user["LoginID"], "token": token}

    def reset_password(self, token: str, password: str, confirm: str) -> tuple[bool, str]:
        data = load_signed_token(token, TOKEN_PURPOSE)
        if not data:
            return False, "This reset link is invalid or has expired."
        token_row = self.auth._find_token(TOKEN_TYPE, hash_token(token))
        if token_row is None:
            return False, "This reset link is invalid, used, or expired."
        user_id = int(data.get("uid") or 0)
        server_user = self.get_by_user_id(user_id)
        if not server_user:
            return False, "No Server User is linked to this account."
        pwd_error = self.validate_server_password(password, confirm, user_id=user_id)
        if pwd_error:
            return False, pwd_error
        try:
            db.session.execute(
                text(
                    """
                    UPDATE dbo.ServerUser
                    SET PasswordHash = :password_hash, ModifiedDate = :now
                    WHERE ServerUserID = :pk
                    """
                ),
                {
                    "password_hash": hash_password(password),
                    "now": utcnow(),
                    "pk": int(server_user["ServerUserID"]),
                },
            )
            self.tokens.mark_used(token_row)
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("Server user password reset failed")
            return False, "Unable to update password. Please try again."
        user = self.users.get_by_id(user_id)
        self.audit.log(
            action="Password Changed",
            module="ServerAuth",
            record_id=int(server_user["ServerUserID"]),
            status=STATUS_SUCCESS,
            user_id=user_id,
            user_name=user.FullName if user else None,
        )
        return True, "Password updated. Sign in with your Server User ID and new password."
