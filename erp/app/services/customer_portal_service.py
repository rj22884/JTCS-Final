"""Customer Portal authentication: login, reset, force password change."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from app.extensions import db
from app.repositories.customer_repository import CustomerRepository
from app.utils.db_session import persist
from app.utils.security import hash_password, verify_password

logger = logging.getLogger(__name__)

DEFAULT_PORTAL_PASSWORD = "Admin@123"
MAX_FAILED_LOGINS = 5

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


@dataclass
class PortalLookupResult:
    ok: bool
    error: str | None = None
    error_code: str | None = None
    status_code: int = 400
    detected_type: str | None = None
    customer: dict | None = None
    duplicates: list[dict] | None = None


class CustomerPortalService:
    def __init__(self, repository: CustomerRepository | None = None):
        self.repo = repository or CustomerRepository()

    @staticmethod
    def mask_pan(pan: str | None) -> str:
        """Mask PAN: ABCDE1234F → ABCDEXXX4F. Never return full PAN."""
        value = (pan or "").strip().upper()
        if len(value) < 10:
            return "XXXXXXXXXX"
        return f"{value[:5]}XXX{value[8:]}"

    @staticmethod
    def detect_user_id_type(user_id: str) -> str | None:
        raw = (user_id or "").strip()
        if not raw:
            return None
        if "@" in raw:
            return "EMAIL" if EMAIL_RE.match(raw.lower()) else None
        digits = re.sub(r"\D", "", raw)
        if digits.isdigit() and len(digits) == 12:
            return "AADHAAR"
        if digits.isdigit() and len(digits) == 10:
            return "MOBILE"
        # Allow +91XXXXXXXXXX
        if digits.isdigit() and 10 <= len(digits) <= 12:
            return "MOBILE"
        pan = raw.upper().replace(" ", "")
        if PAN_RE.match(pan):
            return "PAN"
        return None

    def _safe_duplicate_rows(self, rows: list[dict]) -> list[dict]:
        return [
            {
                "customer_name": (row.get("customer_name") or "").strip() or "Customer",
                "masked_pan": self.mask_pan(row.get("pan_number")),
            }
            for row in rows
        ]

    def find_customers_by_user_id(self, user_id: str) -> PortalLookupResult:
        """Resolve User ID to customer(s). Duplicate checks only for Email/Mobile."""
        self.repo.ensure_schema()
        raw = (user_id or "").strip()
        detected = self.detect_user_id_type(raw)
        if not detected:
            return PortalLookupResult(
                ok=False,
                error="Enter a valid PAN, Aadhaar Number, Mobile Number or Email Address.",
                error_code="invalid_user_id",
                status_code=400,
            )

        if detected == "PAN":
            match = self.repo.find_by_pan(raw.upper().replace(" ", ""))
            rows = [match] if match else []
        elif detected == "AADHAAR":
            match = self.repo.find_by_aadhaar(raw)
            rows = [match] if match else []
        elif detected == "EMAIL":
            rows = self.repo.find_by_email(raw)
        else:  # MOBILE
            rows = self.repo.find_by_mobile(raw)

        if not rows:
            return PortalLookupResult(
                ok=False,
                error="Customer not found.\nPlease contact JTCS.",
                error_code="not_found",
                status_code=404,
                detected_type=detected,
            )

        if detected in {"EMAIL", "MOBILE"} and len(rows) > 1:
            return PortalLookupResult(
                ok=False,
                error=(
                    "This Mobile Number or Email Address is registered with multiple "
                    "customer records.\nPlease contact JTCS."
                ),
                error_code="duplicate",
                status_code=409,
                detected_type=detected,
                duplicates=self._safe_duplicate_rows(rows),
            )

        customer_id = int(rows[0]["customer_id"])
        auth = self.repo.get_portal_auth(customer_id)
        if not auth or (auth.get("customer_status") or "").strip().lower() == "inactive":
            return PortalLookupResult(
                ok=False,
                error="Customer not found.\nPlease contact JTCS.",
                error_code="not_found",
                status_code=404,
                detected_type=detected,
            )
        return PortalLookupResult(
            ok=True,
            detected_type=detected,
            customer=auth,
        )

    def _log_write(
        self,
        *,
        customer_id: int | None,
        user_id_input: str,
        detected_type: str | None,
        attempt_result: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.repo.log_portal_login_attempt(
            customer_id=customer_id,
            user_id_input=user_id_input,
            detected_type=detected_type,
            attempt_result=attempt_result,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def _commit_log(
        self,
        *,
        customer_id: int | None,
        user_id_input: str,
        detected_type: str | None,
        attempt_result: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        try:
            def _write() -> None:
                self._log_write(
                    customer_id=customer_id,
                    user_id_input=user_id_input,
                    detected_type=detected_type,
                    attempt_result=attempt_result,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )

            persist(_write)
        except Exception:  # noqa: BLE001
            db.session.rollback()
            logger.exception("Failed to write customer portal login log")

    def login(
        self,
        user_id: str,
        password: str,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        lookup = self.find_customers_by_user_id(user_id)
        if not lookup.ok:
            self._commit_log(
                customer_id=None,
                user_id_input=user_id,
                detected_type=lookup.detected_type,
                attempt_result=lookup.error_code or "failed",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            return {
                "ok": False,
                "error": lookup.error,
                "error_code": lookup.error_code,
                "status_code": lookup.status_code,
                "duplicates": lookup.duplicates,
                "detected_type": lookup.detected_type,
            }

        customer = lookup.customer or {}
        customer_id = int(customer["customer_id"])

        if customer.get("account_locked"):
            self._commit_log(
                customer_id=customer_id,
                user_id_input=user_id,
                detected_type=lookup.detected_type,
                attempt_result="locked",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            return {
                "ok": False,
                "error": "Your account is locked.\nPlease contact JTCS.",
                "error_code": "locked",
                "status_code": 403,
                "detected_type": lookup.detected_type,
            }

        stored = customer.get("portal_password") or ""
        if stored == DEFAULT_PORTAL_PASSWORD:
            password_ok = password == DEFAULT_PORTAL_PASSWORD
        else:
            password_ok = verify_password(stored, password)

        if not password_ok:
            failed = int(customer.get("failed_login_count") or 0) + 1
            lock = failed >= MAX_FAILED_LOGINS
            try:
                def _fail() -> None:
                    self.repo.update_portal_login_failure(customer_id, lock=lock)
                    self._log_write(
                        customer_id=customer_id,
                        user_id_input=user_id,
                        detected_type=lookup.detected_type,
                        attempt_result="locked" if lock else "bad_password",
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )

                persist(_fail)
            except Exception:  # noqa: BLE001
                db.session.rollback()
                logger.exception("Failed to update portal login failure for %s", customer_id)

            if lock:
                return {
                    "ok": False,
                    "error": "Your account is locked.\nPlease contact JTCS.",
                    "error_code": "locked",
                    "status_code": 403,
                    "detected_type": lookup.detected_type,
                }
            return {
                "ok": False,
                "error": "Invalid User ID or Password.",
                "error_code": "bad_credentials",
                "status_code": 401,
                "detected_type": lookup.detected_type,
            }

        must_change = (not customer.get("password_changed")) or password == DEFAULT_PORTAL_PASSWORD
        try:
            def _success() -> None:
                # Migrate legacy plaintext default to bcrypt hash.
                if stored == DEFAULT_PORTAL_PASSWORD:
                    self.repo.reset_portal_password(
                        customer_id, hash_password(DEFAULT_PORTAL_PASSWORD)
                    )
                self.repo.update_portal_login_success(customer_id)
                self._log_write(
                    customer_id=customer_id,
                    user_id_input=user_id,
                    detected_type=lookup.detected_type,
                    attempt_result="must_change_password" if must_change else "success",
                    ip_address=ip_address,
                    user_agent=user_agent,
                )

            persist(_success)
        except Exception:  # noqa: BLE001
            db.session.rollback()
            logger.exception("Failed to update portal login success for %s", customer_id)
            return {
                "ok": False,
                "error": "Unable to complete login. Please try again.",
                "error_code": "server_error",
                "status_code": 500,
            }

        return {
            "ok": True,
            "customer_id": customer_id,
            "customer_name": customer.get("customer_name") or "",
            "password_changed": not must_change,
            "must_change_password": must_change,
            "detected_type": lookup.detected_type,
            "redirect": (
                "/customer/change-password" if must_change else "/customer/dashboard"
            ),
        }

    def reset_password(
        self,
        user_id: str,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        lookup = self.find_customers_by_user_id(user_id)
        if not lookup.ok:
            self._commit_log(
                customer_id=None,
                user_id_input=user_id,
                detected_type=lookup.detected_type,
                attempt_result=f"reset_{lookup.error_code or 'failed'}",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            return {
                "ok": False,
                "error": lookup.error,
                "error_code": lookup.error_code,
                "status_code": lookup.status_code,
                "duplicates": lookup.duplicates,
                "detected_type": lookup.detected_type,
            }

        customer = lookup.customer or {}
        customer_id = int(customer["customer_id"])
        try:
            def _reset() -> None:
                self.repo.reset_portal_password(
                    customer_id, hash_password(DEFAULT_PORTAL_PASSWORD)
                )
                self._log_write(
                    customer_id=customer_id,
                    user_id_input=user_id,
                    detected_type=lookup.detected_type,
                    attempt_result="reset_success",
                    ip_address=ip_address,
                    user_agent=user_agent,
                )

            persist(_reset)
        except Exception:  # noqa: BLE001
            db.session.rollback()
            logger.exception("Portal password reset failed for customer %s", customer_id)
            return {
                "ok": False,
                "error": "Unable to reset password. Please try again.",
                "error_code": "server_error",
                "status_code": 500,
            }

        return {
            "ok": True,
            "message": (
                "Default password reset successfully.\n"
                f"Your temporary password is\n{DEFAULT_PORTAL_PASSWORD}\n"
                "Please login and change your password immediately."
            ),
            "temporary_password": DEFAULT_PORTAL_PASSWORD,
            "detected_type": lookup.detected_type,
        }

    def admin_reset_password(self, customer_id: int) -> dict[str, Any]:
        self.repo.ensure_schema()
        auth = self.repo.get_portal_auth(int(customer_id))
        if not auth:
            return {
                "ok": False,
                "error": "Customer not found.",
                "error_code": "not_found",
                "status_code": 404,
            }
        try:
            def _reset() -> None:
                self.repo.reset_portal_password(
                    int(customer_id), hash_password(DEFAULT_PORTAL_PASSWORD)
                )

            persist(_reset)
        except Exception:  # noqa: BLE001
            db.session.rollback()
            logger.exception("Admin portal password reset failed for %s", customer_id)
            return {
                "ok": False,
                "error": "Unable to reset portal password.",
                "error_code": "server_error",
                "status_code": 500,
            }
        return {
            "ok": True,
            "message": "Default password reset successfully.",
            "temporary_password": DEFAULT_PORTAL_PASSWORD,
        }

    def change_password(
        self,
        customer_id: int,
        old_password: str,
        new_password: str,
        confirm_password: str,
    ) -> dict[str, Any]:
        self.repo.ensure_schema()
        auth = self.repo.get_portal_auth(int(customer_id))
        if not auth:
            return {
                "ok": False,
                "error": "Customer not found.\nPlease contact JTCS.",
                "error_code": "not_found",
                "status_code": 404,
            }

        stored = auth.get("portal_password") or ""
        if stored == DEFAULT_PORTAL_PASSWORD:
            old_ok = old_password == DEFAULT_PORTAL_PASSWORD
        else:
            old_ok = verify_password(stored, old_password)
        if not old_ok:
            return {
                "ok": False,
                "error": "Old Password does not match.",
                "error_code": "bad_old_password",
                "status_code": 400,
            }

        if len(new_password or "") < 8:
            return {
                "ok": False,
                "error": "New Password must be at least 8 characters.",
                "error_code": "weak_password",
                "status_code": 400,
            }
        if new_password != confirm_password:
            return {
                "ok": False,
                "error": "New Password and Confirm Password must match.",
                "error_code": "confirm_mismatch",
                "status_code": 400,
            }
        if new_password == DEFAULT_PORTAL_PASSWORD:
            return {
                "ok": False,
                "error": "Please choose a password different from the default password.",
                "error_code": "default_password",
                "status_code": 400,
            }

        try:
            def _change() -> None:
                self.repo.change_portal_password(int(customer_id), hash_password(new_password))

            persist(_change)
        except Exception:  # noqa: BLE001
            db.session.rollback()
            logger.exception("Portal password change failed for %s", customer_id)
            return {
                "ok": False,
                "error": "Unable to save password. Please try again.",
                "error_code": "server_error",
                "status_code": 500,
            }

        return {
            "ok": True,
            "message": "Password changed successfully.",
            "redirect": "/customer/dashboard",
        }

    def get_profile(self, customer_id: int) -> dict[str, Any]:
        self.repo.ensure_schema()
        auth = self.repo.get_portal_auth(int(customer_id))
        if not auth:
            return {
                "ok": False,
                "error": "Customer not found.",
                "error_code": "not_found",
                "status_code": 404,
            }
        detail = {}
        try:
            detail = self.repo.get_detail(int(customer_id)) or {}
        except Exception:  # noqa: BLE001
            detail = {}
        return {
            "ok": True,
            "profile": {
                "customer_id": auth["customer_id"],
                "customer_name": auth.get("customer_name") or "",
                "masked_pan": self.mask_pan(auth.get("pan_number")),
                "customer_group": detail.get("CustomerGroup") or "",
                "city": detail.get("City") or "",
                "state": detail.get("State") or "",
                "last_login": auth.get("last_login").isoformat()
                if auth.get("last_login")
                else None,
                "password_changed": bool(auth.get("password_changed")),
            },
        }
