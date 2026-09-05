from __future__ import annotations

import logging
import re
import secrets
import smtplib
from datetime import datetime
from pathlib import Path

from flask import current_app
from sqlalchemy.exc import IntegrityError, InvalidRequestError, OperationalError
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.auth import AuthToken
from app.repositories.user_repository import AuthTokenRepository, CompanyRepository, UserRepository
from app.services.auth_result import AuthResult
from app.services.email_service import EmailService, SMTP_NOT_CONFIGURED, SMTP_USER_MESSAGE
from app.services.login_activity_service import (
    EVENT_FIRST_SET,
    EVENT_RESET,
    LoginActivityService,
    STATUS_FAILED,
    STATUS_SUCCESS,
)
from app.utils.date_format import format_display_date
from app.utils.db_session import map_db_exception, persist, reset_session
from app.utils.smtp_health import mask_email, mask_mobile
from app.utils.url_helpers import external_url_for
from app.utils.security import (
    hash_password,
    hash_token,
    token_expiry,
    verify_password,
)
from app.utils.tokens import create_signed_token, load_signed_token

logger = logging.getLogger(__name__)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MOBILE_PATTERN = re.compile(r"^\d{10}$")


class AuthService:
    TOKEN_TYPES = {
        "email_verify_link": "EMAIL_VERIFY_LINK",
        "password_reset_link": "PASSWORD_RESET_LINK",
    }

    def __init__(self):
        self.users = UserRepository()
        self.company = CompanyRepository()
        self.tokens = AuthTokenRepository()
        self.email = EmailService()
        self.login_activity = LoginActivityService()

    def _token_expiry_minutes(self) -> int:
        return int(current_app.config.get("AUTH_TOKEN_EXPIRY_MINUTES", 30))

    def _handle_db_error(self, exc: Exception, context: str) -> AuthResult:
        detail = getattr(exc, "orig", exc)
        logger.error("%s failed: %s — %s", context, exc.__class__.__name__, detail)
        return AuthResult.fail(map_db_exception(exc))

    def _handle_unknown_error(self, exc: Exception, context: str) -> AuthResult:
        logger.exception("%s failed unexpectedly", context)
        return AuthResult.fail("An unexpected error occurred. Please try again.")

    def _registration_conflict(self, email: str) -> str | None:
        user = self.users.get_by_email(email)
        if user is None:
            return None

        created = format_display_date(user.CreatedDate, empty="an earlier date")
        masked_mobile = mask_mobile(user.MobileNumber)

        if user.UserStatus == "Rejected":
            return (
                f"This email was previously registered and rejected "
                f"(mobile {masked_mobile}, {created}). Contact the administrator."
            )

        from app.utils.roles import has_admin_role

        if has_admin_role(user.Role):
            return (
                f"This email is already registered as the Administrator account "
                f"(mobile {masked_mobile}, created {created}). "
                f"Use Login or Forgot Password — do not register again."
            )

        if user.UserStatus == "Pending":
            if user.EmailVerified:
                return (
                    f"This email already has a pending registration "
                    f"(mobile {masked_mobile}, submitted {created}). "
                    f"Await administrator approval or contact support."
                )
            return (
                f"This email already has a pending registration "
                f"(mobile {masked_mobile}, submitted {created}). "
                f"Check your inbox for the password setup link."
            )

        return (
            f"This email is already registered "
            f"(mobile {masked_mobile}, {user.UserStatus}, created {created}). Use Login instead."
        )

    def _mobile_conflict(self, mobile: str, *, exclude_user_id: int | None = None) -> str | None:
        users = self.users.get_by_mobile(mobile)
        if exclude_user_id is not None:
            users = [user for user in users if user.UserID != exclude_user_id]
        if not users:
            return None
        user = users[0]
        masked = mask_email(user.EmailID)
        if user.UserStatus == "Rejected":
            return (
                f"This mobile number was previously registered and rejected "
                f"({masked}). Contact the administrator."
            )
        return (
            f"This mobile number is already registered to an account "
            f"({masked}). Use Login or Forgot User ID."
        )

    def administrator_exists(self) -> bool:
        return self.users.administrator_exists()

    def get_company(self):
        return self.company.get_profile()

    def validate_email(self, email: str) -> str | None:
        email = (email or "").strip().lower()
        if not email or not EMAIL_PATTERN.match(email):
            return "Enter a valid email address."
        return None

    def validate_mobile(self, mobile: str) -> str | None:
        mobile = (mobile or "").strip()
        if not MOBILE_PATTERN.match(mobile):
            return "Enter a valid 10-digit mobile number."
        return None

    def validate_password(self, password: str, confirm: str) -> str | None:
        password = password or ""
        if len(password) < 8:
            return "Password must be at least 8 characters."
        if not re.search(r"[A-Z]", password):
            return "Password must include at least one uppercase letter."
        if not re.search(r"[a-z]", password):
            return "Password must include at least one lowercase letter."
        if not re.search(r"\d", password):
            return "Password must include at least one number."
        if password != confirm:
            return "Passwords do not match."
        return None

    def complete_setup(self, form, logo_file=None) -> tuple[bool, str | None, dict]:
        if self.administrator_exists():
            return AuthResult.fail("Setup has already been completed.").as_tuple()

        company_name = (form.get("company_name") or "").strip()
        owner_name = (form.get("owner_name") or "").strip()
        admin_name = (form.get("administrator_name") or "").strip()
        email = (form.get("email") or "").strip().lower()
        mobile = (form.get("mobile") or "").strip()
        password = form.get("password") or ""
        confirm = form.get("confirm_password") or ""

        if not all([company_name, owner_name, admin_name, email, mobile]):
            return AuthResult.fail("All setup fields are required.").as_tuple()

        for validator, value in (
            (self.validate_email, email),
            (self.validate_mobile, mobile),
        ):
            error = validator(value)
            if error:
                return AuthResult.fail(error).as_tuple()

        error = self.validate_password(password, confirm)
        if error:
            return AuthResult.fail(error).as_tuple()

        conflict = self._registration_conflict(email)
        if conflict:
            return AuthResult.fail(conflict).as_tuple()

        mobile_conflict = self._mobile_conflict(mobile)
        if mobile_conflict:
            return AuthResult.fail(mobile_conflict).as_tuple()

        logo_path = self._save_logo(logo_file) if logo_file and logo_file.filename else None

        try:
            def _write():
                self.company.create(
                    {
                        "CompanyName": company_name,
                        "OwnerName": owner_name,
                        "LogoPath": logo_path,
                        "SetupCompleted": True,
                        "CreatedDate": datetime.utcnow(),
                    }
                )
                user = self.users.create(
                    {
                        "FullName": admin_name,
                        "EmailID": email,
                        "MobileNumber": mobile,
                        "PasswordHash": hash_password(password),
                        "IsPasswordSet": True,
                        "Role": "Administrator",
                        "IsActive": True,
                        "UserStatus": "Active",
                        "EmailVerified": True,
                        "AdminApproved": True,
                        "VerificationDate": datetime.utcnow(),
                        "CreatedDate": datetime.utcnow(),
                    }
                )
                return user

            user = persist(_write)
            try:
                self.login_activity.log_password_event(
                    email, EVENT_FIRST_SET, user_pk=user.UserID
                )
            except Exception:
                logger.exception("Password event log skipped after setup")
            return AuthResult.ok({"user_id": user.UserID, "email": email}, "Setup completed successfully.").as_tuple()
        except (IntegrityError, OperationalError, InvalidRequestError) as exc:
            return self._handle_db_error(exc, "complete_setup").as_tuple()
        except Exception as exc:
            reset_session()
            return self._handle_unknown_error(exc, "complete_setup").as_tuple()

    def login(self, email: str, password: str, remember: bool = False) -> tuple[bool, str | None, dict]:
        email = (email or "").strip().lower()
        user = self.users.get_by_email(email)

        def _fail(message: str, data: dict | None = None) -> tuple[bool, str | None, dict]:
            try:
                self.login_activity.log_login_activity(
                    email or "unknown",
                    STATUS_FAILED,
                    user_pk=getattr(user, "UserID", None) if user is not None else None,
                )
            except Exception:
                logger.exception("Failed login activity log skipped")
            return AuthResult.fail(message, data or {}).as_tuple()

        if user is None:
            return _fail("Invalid email or password.")

        # First-time password not set yet — force emailed set-password flow.
        if not bool(getattr(user, "IsPasswordSet", True)):
            return _fail(
                "Please set your password using the link emailed to you, then sign in.",
                {"reason": "password_not_set", "email": email},
            )

        if not verify_password(user.PasswordHash, password):
            return _fail("Invalid email or password.")

        from app.utils.roles import has_admin_role

        if not has_admin_role(user.Role):
            if not user.EmailVerified:
                return _fail(
                    "Your email is not verified.",
                    {"reason": "email_not_verified", "email": email},
                )
            if not user.AdminApproved or user.UserStatus == "Pending":
                return _fail(
                    "Your registration is pending administrator approval.",
                    {"reason": "pending_approval", "email": email},
                )
            if not user.IsActive or user.UserStatus != "Active":
                return _fail(
                    "Your account is not active. Contact the administrator.",
                    {"reason": "inactive", "email": email},
                )
        elif not user.IsActive or user.UserStatus != "Active":
            return _fail("Your account is not active. Contact the administrator.")

        user_id = user.UserID
        user_name = user.FullName
        role = user.Role

        try:
            def _write():
                user.LastLoginDate = datetime.utcnow()
                user.ModifiedDate = datetime.utcnow()
                return True

            persist(_write)
            session_id = None
            try:
                session_id = self.login_activity.log_login_activity(
                    email, STATUS_SUCCESS, user_pk=user_id
                )
            except Exception:
                logger.exception("Success login activity log skipped")
            return AuthResult.ok(
                {
                    "user_id": user_id,
                    "user_name": user_name,
                    "role": role,
                    "remember": remember,
                    "login_session_id": session_id,
                }
            ).as_tuple()
        except (IntegrityError, OperationalError, InvalidRequestError) as exc:
            return self._handle_db_error(exc, "login").as_tuple()
        except Exception as exc:
            reset_session()
            return self._handle_unknown_error(exc, "login").as_tuple()

    def register(self, form) -> tuple[bool, str | None, dict]:
        full_name = (form.get("full_name") or "").strip()
        email = (form.get("email") or "").strip().lower()
        mobile = (form.get("mobile") or "").strip()

        if not all([full_name, email, mobile]):
            return AuthResult.fail("Full name, email, and mobile are required.").as_tuple()

        for validator, value in (
            (self.validate_email, email),
            (self.validate_mobile, mobile),
        ):
            error = validator(value)
            if error:
                return AuthResult.fail(error).as_tuple()

        conflict = self._registration_conflict(email)
        if conflict:
            return AuthResult.fail(conflict).as_tuple()

        mobile_conflict = self._mobile_conflict(mobile)
        if mobile_conflict:
            return AuthResult.fail(mobile_conflict).as_tuple()

        reset_token = ""
        try:
            def _create_user():
                new_user = self.users.create(
                    {
                        "FullName": full_name,
                        "EmailID": email,
                        "MobileNumber": mobile,
                        # Placeholder until the user sets a password via emailed link.
                        "PasswordHash": hash_password(secrets.token_urlsafe(32)),
                        "IsPasswordSet": False,
                        "Role": "Operator",
                        "IsActive": False,
                        "UserStatus": "Pending",
                        "EmailVerified": False,
                        "AdminApproved": False,
                        "CreatedDate": datetime.utcnow(),
                    }
                )
                return new_user.UserID

            user_id = persist(_create_user)
            reset_token = create_signed_token(user_id, email, "password_reset")

            def _create_token():
                self.tokens.invalidate_active(
                    self.TOKEN_TYPES["password_reset_link"],
                    user_id=user_id,
                    email=email,
                )
                self.tokens.create(
                    {
                        "UserID": user_id,
                        "Email": email,
                        "TokenType": self.TOKEN_TYPES["password_reset_link"],
                        "TokenHash": hash_token(reset_token),
                        "ExpiresAt": token_expiry(self._token_expiry_minutes()),
                        "CreatedDate": datetime.utcnow(),
                    }
                )

            persist(_create_token)
        except (IntegrityError, OperationalError, InvalidRequestError) as exc:
            return self._handle_db_error(exc, "register").as_tuple()
        except Exception as exc:
            reset_session()
            return self._handle_unknown_error(exc, "register").as_tuple()

        reset_url = external_url_for("auth.reset_password", token=reset_token)
        logger.info("[REGISTER] User registered user_id=%s email=%s", user_id, email)
        logger.info("[REGISTER] Password setup URL generated: %s", reset_url)
        if "localhost" in reset_url.lower() or "127.0.0.1" in reset_url:
            logger.error(
                "[REGISTER] APP_BASE_URL looks local on a public host — "
                "set APP_BASE_URL in erp/.env to the VPS public URL before users can set a password."
            )
        try:
            sent, mail_error = self.email.send_set_password_email(email, full_name, reset_url)
        except Exception as exc:
            logger.error(
                "[REGISTER] Password setup email failed for %s: %s",
                email,
                exc,
                exc_info=True,
            )
            return AuthResult.ok(
                {"email": email, "user_id": user_id, "email_sent": False},
                f"Registration saved, but {SMTP_USER_MESSAGE} "
                "Open the next page and click Resend. "
                "On VPS also confirm MAIL_PASSWORD and APP_BASE_URL in erp/.env.",
            ).as_tuple()

        if not sent:
            logger.error(
                "[REGISTER] Password setup email not sent for %s: %s",
                email,
                mail_error or SMTP_USER_MESSAGE,
            )
            detail = mail_error or SMTP_USER_MESSAGE
            if detail == SMTP_NOT_CONFIGURED:
                detail = (
                    "SMTP mail is not configured on the server. "
                    "Set MAIL_USERNAME / MAIL_PASSWORD / APP_BASE_URL in erp/.env, then Resend."
                )
            return AuthResult.ok(
                {"email": email, "user_id": user_id, "email_sent": False},
                f"Registration saved, but {detail}",
            ).as_tuple()

        logger.info("[REGISTER] Password setup email sent successfully to %s", email)

        return AuthResult.ok(
            {"email": email, "user_id": user_id, "email_sent": True},
            "Registration submitted. Check your email (and Spam/Junk) for the password setup link.",
        ).as_tuple()

    def verify_email_link(self, token: str, client_ip: str | None = None) -> tuple[bool, str | None, dict]:
        payload = load_signed_token(token, "email_verify")
        if payload is None:
            return AuthResult.fail("Invalid or expired verification link.").as_tuple()

        user_id = payload.get("uid")
        email = (payload.get("email") or "").strip().lower()
        user = self.users.get_by_id(int(user_id)) if user_id else None
        if user is None or user.EmailID.lower() != email:
            return AuthResult.fail("Invalid verification link.").as_tuple()

        if user.EmailVerified:
            return AuthResult.ok(
                {"email": email},
                "Email is already verified. Await administrator approval.",
            ).as_tuple()

        token_row = self._find_token(self.TOKEN_TYPES["email_verify_link"], hash_token(token))
        if token_row is None:
            return AuthResult.fail("Invalid or expired verification link.").as_tuple()

        user_full_name = user.FullName
        user_email = user.EmailID

        try:
            def _write():
                user.EmailVerified = True
                user.VerificationDate = datetime.utcnow()
                user.VerificationIP = (client_ip or "").strip()[:45] or None
                user.ModifiedDate = datetime.utcnow()
                self.tokens.mark_used(token_row)
                return True

            persist(_write)
        except (IntegrityError, OperationalError, InvalidRequestError) as exc:
            return self._handle_db_error(exc, "verify_email_link").as_tuple()
        except Exception as exc:
            reset_session()
            return self._handle_unknown_error(exc, "verify_email_link").as_tuple()

        admin = self.users.get_primary_administrator()
        if admin and admin.EmailID.lower() != email:
            pending_url = external_url_for("auth.users_index")
            try:
                self.email.send_admin_new_user_notification(
                    admin.EmailID,
                    user_full_name,
                    user_email,
                    pending_url,
                )
            except smtplib.SMTPException as exc:
                logger.error("Admin notification SMTP failure: %s", exc, exc_info=True)

        return AuthResult.ok(
            {"email": email},
            "Email verified successfully. Await administrator approval.",
        ).as_tuple()

    def resend_verification_email(self, email: str) -> tuple[bool, str | None, dict]:
        """Resend the registration password-setup link for pending unverified users."""
        email = (email or "").strip().lower()
        user = self.users.get_by_email(email)
        if user is None or user.UserStatus != "Pending" or user.EmailVerified:
            return AuthResult.ok(
                {},
                "If the account is pending setup, a new password link has been sent.",
            ).as_tuple()

        user_id = user.UserID
        user_full_name = user.FullName
        reset_token = ""

        try:
            def _write():
                nonlocal reset_token
                reset_token = create_signed_token(user_id, email, "password_reset")
                self.tokens.invalidate_active(
                    self.TOKEN_TYPES["password_reset_link"],
                    user_id=user_id,
                    email=email,
                )
                self.tokens.create(
                    {
                        "UserID": user_id,
                        "Email": email,
                        "TokenType": self.TOKEN_TYPES["password_reset_link"],
                        "TokenHash": hash_token(reset_token),
                        "ExpiresAt": token_expiry(self._token_expiry_minutes()),
                        "CreatedDate": datetime.utcnow(),
                    }
                )
                return reset_token

            persist(_write)
        except (IntegrityError, OperationalError, InvalidRequestError) as exc:
            return self._handle_db_error(exc, "resend_verification_email").as_tuple()
        except Exception as exc:
            reset_session()
            return self._handle_unknown_error(exc, "resend_verification_email").as_tuple()

        reset_url = external_url_for("auth.reset_password", token=reset_token)
        try:
            sent, mail_error = self.email.send_set_password_email(email, user_full_name, reset_url)
        except smtplib.SMTPException as exc:
            logger.error("Resend password-setup SMTP failure for %s: %s", email, exc, exc_info=True)
            return AuthResult.fail(SMTP_USER_MESSAGE).as_tuple()

        if not sent:
            return AuthResult.fail(mail_error or SMTP_USER_MESSAGE).as_tuple()

        return AuthResult.ok({"email": email}, "Password setup email sent.").as_tuple()

    def request_password_reset(self, email: str) -> tuple[bool, str | None, dict]:
        email = (email or "").strip().lower()
        error = self.validate_email(email)
        if error:
            return AuthResult.fail(error).as_tuple()

        user = self.users.get_by_email(email)
        if user is None:
            return AuthResult.ok({}, "If the email exists, a password reset link has been sent.").as_tuple()

        user_id = user.UserID
        user_full_name = user.FullName
        reset_token = ""
        try:
            def _write():
                nonlocal reset_token
                reset_token = create_signed_token(user_id, email, "password_reset")
                self.tokens.invalidate_active(
                    self.TOKEN_TYPES["password_reset_link"],
                    user_id=user_id,
                    email=email,
                )
                self.tokens.create(
                    {
                        "UserID": user_id,
                        "Email": email,
                        "TokenType": self.TOKEN_TYPES["password_reset_link"],
                        "TokenHash": hash_token(reset_token),
                        "ExpiresAt": token_expiry(self._token_expiry_minutes()),
                        "CreatedDate": datetime.utcnow(),
                    }
                )
                return reset_token

            persist(_write)
        except (IntegrityError, OperationalError, InvalidRequestError) as exc:
            return self._handle_db_error(exc, "request_password_reset").as_tuple()
        except Exception as exc:
            reset_session()
            return self._handle_unknown_error(exc, "request_password_reset").as_tuple()

        reset_url = external_url_for("auth.reset_password", token=reset_token)
        try:
            sent, mail_error = self.email.send_password_reset_email(email, user_full_name, reset_url)
        except smtplib.SMTPException as exc:
            logger.error("Password reset SMTP failure for %s: %s", email, exc, exc_info=True)
            return AuthResult.ok(
                {"email": email},
                f"Password reset was saved, but {SMTP_USER_MESSAGE}",
            ).as_tuple()

        if not sent:
            if mail_error == SMTP_NOT_CONFIGURED:
                return AuthResult.fail(SMTP_NOT_CONFIGURED).as_tuple()
            return AuthResult.ok(
                {"email": email},
                mail_error or SMTP_USER_MESSAGE,
            ).as_tuple()

        return AuthResult.ok(
            {"email": email},
            "If the email exists, a password reset link has been sent.",
        ).as_tuple()

    def reset_password_with_token(self, token: str, password: str, confirm: str) -> tuple[bool, str | None, dict]:
        error = self.validate_password(password, confirm)
        if error:
            return AuthResult.fail(error).as_tuple()

        payload = load_signed_token(token, "password_reset")
        if payload is None:
            return AuthResult.fail("Invalid or expired password reset link.").as_tuple()

        user_id = payload.get("uid")
        email = (payload.get("email") or "").strip().lower()
        user = self.users.get_by_id(int(user_id)) if user_id else None
        if user is None or user.EmailID.lower() != email:
            return AuthResult.fail("Invalid password reset link.").as_tuple()

        token_row = self._find_token(self.TOKEN_TYPES["password_reset_link"], hash_token(token))
        if token_row is None:
            return AuthResult.fail("Invalid or expired password reset link.").as_tuple()

        was_unverified = not user.EmailVerified
        was_first_password = not bool(getattr(user, "IsPasswordSet", False))
        user_full_name = user.FullName
        user_email = user.EmailID
        user_pk = user.UserID

        try:
            def _write():
                user.PasswordHash = hash_password(password)
                user.IsPasswordSet = True
                user.ModifiedDate = datetime.utcnow()
                if was_unverified:
                    user.EmailVerified = True
                    user.VerificationDate = datetime.utcnow()
                self.tokens.mark_used(token_row)
                return user

            persist(_write)
        except (IntegrityError, OperationalError, InvalidRequestError) as exc:
            return self._handle_db_error(exc, "reset_password_with_token").as_tuple()
        except Exception as exc:
            reset_session()
            return self._handle_unknown_error(exc, "reset_password_with_token").as_tuple()

        try:
            self.login_activity.log_password_event(
                user_email,
                EVENT_FIRST_SET if was_first_password else EVENT_RESET,
                user_pk=user_pk,
            )
        except Exception:
            logger.exception("Password event log skipped after reset")

        if was_unverified:
            admin = self.users.get_primary_administrator()
            if admin and admin.EmailID.lower() != email:
                pending_url = external_url_for("auth.users_index")
                try:
                    self.email.send_admin_new_user_notification(
                        admin.EmailID,
                        user_full_name,
                        user_email,
                        pending_url,
                    )
                except smtplib.SMTPException as exc:
                    logger.error("Admin notification SMTP failure: %s", exc, exc_info=True)
            return AuthResult.ok(
                {"email": email},
                "Password set and email verified. Await administrator approval before login.",
            ).as_tuple()

        return AuthResult.ok({"email": email}, "Password updated successfully. Please sign in.").as_tuple()

    def request_forgot_user_id(self, email: str = "", mobile: str = "") -> tuple[bool, str | None, dict]:
        email = (email or "").strip().lower()
        mobile = (mobile or "").strip()
        generic_message = (
            "If a matching account exists, your User ID has been sent to the registered email address."
        )

        if not email and not mobile:
            return AuthResult.fail("Enter your registered email or mobile number.").as_tuple()

        users = []
        if email:
            error = self.validate_email(email)
            if error:
                return AuthResult.fail(error).as_tuple()
            user = self.users.get_by_email(email)
            if user is not None:
                users = [user]
        else:
            error = self.validate_mobile(mobile)
            if error:
                return AuthResult.fail(error).as_tuple()
            users = self.users.get_active_by_mobile(mobile)

        if not users:
            return AuthResult.ok({}, generic_message).as_tuple()

        delivery_email = users[0].EmailID
        user_ids = list(dict.fromkeys(user.EmailID for user in users))

        try:
            sent, mail_error = self.email.send_user_id_recovery_email(delivery_email, user_ids)
        except smtplib.SMTPException as exc:
            logger.error("Forgot user ID SMTP failure for %s: %s", delivery_email, exc, exc_info=True)
            return AuthResult.fail(SMTP_USER_MESSAGE).as_tuple()

        if not sent:
            if mail_error == SMTP_NOT_CONFIGURED:
                return AuthResult.fail(SMTP_NOT_CONFIGURED).as_tuple()
            return AuthResult.fail(mail_error or SMTP_USER_MESSAGE).as_tuple()

        return AuthResult.ok({"email": delivery_email}, generic_message).as_tuple()

    ASSIGNABLE_ROLES = (
        "Operator",
        "Viewer",
        "Manager",
        "Admin",
        "CA",
        "Accountant",
        "DataEntry",
        "Reception",
        "Client",
    )

    def approve_user(self, user_id: int, role=None, roles=None) -> tuple[bool, str | None, dict]:
        from app.utils.roles import ASSIGNABLE_ROLES, join_roles, parse_roles

        user = self.users.get_by_id(user_id)
        if user is None:
            return AuthResult.fail("User not found.").as_tuple()
        if not user.EmailVerified:
            return AuthResult.fail("User must verify email before approval.").as_tuple()

        selected: list[str] = []
        if roles is not None:
            if isinstance(roles, (list, tuple, set)):
                selected = [str(r).strip() for r in roles if str(r).strip()]
            elif roles:
                selected = list(parse_roles(str(roles)))
        elif role:
            selected = list(parse_roles(str(role)))

        selected = [r for r in selected if r in ASSIGNABLE_ROLES]
        role_value = join_roles(selected)
        if not role_value:
            return AuthResult.fail("Please select at least one user role before approval.").as_tuple()

        try:
            def _write():
                user.Role = role_value
                user.AdminApproved = True
                user.UserStatus = "Active"
                user.IsActive = True
                user.ModifiedDate = datetime.utcnow()
                return user

            persist(_write)
            return AuthResult.ok(
                {"user_id": user_id, "role": role_value},
                f"User approved with role(s): {role_value.replace(',', ', ')}.",
            ).as_tuple()
        except (IntegrityError, OperationalError, InvalidRequestError) as exc:
            return self._handle_db_error(exc, "approve_user").as_tuple()
        except Exception as exc:
            reset_session()
            return self._handle_unknown_error(exc, "approve_user").as_tuple()

    def change_user_roles(self, user_id: int, roles=None) -> tuple[bool, str | None, dict]:
        """Update roles for an already-approved (Active) non-admin user."""
        from app.utils.roles import ASSIGNABLE_ROLES, has_admin_role, join_roles, parse_roles

        user = self.users.get_by_id(user_id)
        if user is None:
            return AuthResult.fail("User not found.").as_tuple()
        if has_admin_role(user.Role):
            return AuthResult.fail("Administrator roles cannot be changed from this screen.").as_tuple()
        if user.UserStatus != "Active" or not user.IsActive:
            return AuthResult.fail("Role can only be changed for approved active users.").as_tuple()

        selected: list[str] = []
        if roles is not None:
            if isinstance(roles, (list, tuple, set)):
                selected = [str(r).strip() for r in roles if str(r).strip()]
            elif roles:
                selected = list(parse_roles(str(roles)))

        selected = [r for r in selected if r in ASSIGNABLE_ROLES]
        role_value = join_roles(selected)
        if not role_value:
            return AuthResult.fail("Please select at least one user role.").as_tuple()

        try:
            def _write():
                user.Role = role_value
                user.ModifiedDate = datetime.utcnow()
                return user

            persist(_write)
            return AuthResult.ok(
                {"user_id": user_id, "role": role_value},
                f"Role updated to: {role_value.replace(',', ', ')}.",
            ).as_tuple()
        except (IntegrityError, OperationalError, InvalidRequestError) as exc:
            return self._handle_db_error(exc, "change_user_roles").as_tuple()
        except Exception as exc:
            reset_session()
            return self._handle_unknown_error(exc, "change_user_roles").as_tuple()

    def reject_user(self, user_id: int) -> tuple[bool, str | None, dict]:
        user = self.users.get_by_id(user_id)
        if user is None:
            return AuthResult.fail("User not found.").as_tuple()

        try:
            def _write():
                user.UserStatus = "Rejected"
                user.IsActive = False
                user.ModifiedDate = datetime.utcnow()
                return user

            persist(_write)
            return AuthResult.ok({"user_id": user_id}, "User rejected.").as_tuple()
        except (IntegrityError, OperationalError, InvalidRequestError) as exc:
            return self._handle_db_error(exc, "reject_user").as_tuple()
        except Exception as exc:
            reset_session()
            return self._handle_unknown_error(exc, "reject_user").as_tuple()

    def list_pending_users(self):
        return self.users.list_pending_users()

    def list_active_users(self):
        return self.users.list_active_non_admin_users()

    def list_all_users_for_admin(self):
        return self.users.list_all_for_admin()

    def deactivate_user(self, user_id: int) -> tuple[bool, str | None, dict]:
        user = self.users.get_by_id(user_id)
        if user is None:
            return AuthResult.fail("User not found.").as_tuple()
        from app.utils.roles import has_admin_role

        if has_admin_role(user.Role):
            return AuthResult.fail("Administrator accounts cannot be deactivated.").as_tuple()

        try:
            def _write():
                user.IsActive = False
                user.UserStatus = "Inactive"
                user.AdminApproved = False
                user.ModifiedDate = datetime.utcnow()
                return True

            persist(_write)
            return AuthResult.ok({"user_id": user_id}, "User deactivated successfully.").as_tuple()
        except (IntegrityError, OperationalError, InvalidRequestError) as exc:
            return self._handle_db_error(exc, "deactivate_user").as_tuple()
        except Exception as exc:
            reset_session()
            return self._handle_unknown_error(exc, "deactivate_user").as_tuple()

    def delete_user(self, user_id: int, *, actor_role: str | None = None) -> tuple[bool, str | None, dict]:
        from app.utils.roles import has_admin_role

        if not has_admin_role(actor_role):
            return AuthResult.fail("Only the Administrator can delete users.").as_tuple()

        user = self.users.get_by_id(user_id)
        if user is None:
            return AuthResult.fail("User not found.").as_tuple()
        if has_admin_role(user.Role):
            return AuthResult.fail("Administrator accounts cannot be deleted.").as_tuple()

        try:
            def _write():
                from sqlalchemy import select

                from app.models.auth import AuthToken

                tokens = list(
                    self.users.session.scalars(
                        select(AuthToken).where(AuthToken.UserID == user.UserID)
                    ).all()
                )
                for token in tokens:
                    self.users.session.delete(token)
                self.users.session.delete(user)
                return True

            persist(_write)
            return AuthResult.ok({"user_id": user_id}, "User deleted successfully.").as_tuple()
        except (IntegrityError, OperationalError, InvalidRequestError) as exc:
            return self._handle_db_error(exc, "delete_user").as_tuple()
        except Exception as exc:
            reset_session()
            return self._handle_unknown_error(exc, "delete_user").as_tuple()

    def _find_token(self, token_type: str, token_hash: str) -> AuthToken | None:
        from sqlalchemy import select

        stmt = select(AuthToken).where(
            AuthToken.TokenType == token_type,
            AuthToken.TokenHash == token_hash,
            AuthToken.IsUsed == False,  # noqa: E712
            AuthToken.ExpiresAt > datetime.utcnow(),
        )
        return db.session.scalars(stmt).first()

    def _save_logo(self, logo_file) -> str | None:
        filename = secure_filename(logo_file.filename)
        if not filename:
            return None

        ext = Path(filename).suffix.lower()
        if ext not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
            return None

        upload_dir = Path(current_app.root_path) / "static" / "uploads" / "company"
        upload_dir.mkdir(parents=True, exist_ok=True)
        target = upload_dir / f"logo{ext}"
        logo_file.save(target)
        return f"uploads/company/logo{ext}"
