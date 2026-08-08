"""Customer Portal authentication, profile self-service, and related data."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from flask import current_app
from sqlalchemy import text
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.customer_master.constants import FORM_TO_DB, GENDERS, GST_FILING_FREQUENCIES
from app.customer_portal.constants import (
    PORTAL_BLOCKED_FIELDS,
    PORTAL_EDITABLE_FIELDS,
    PORTAL_MODULES,
    PORTAL_READONLY_FIELDS,
)
from app.extensions import db
from app.modules.shared.audit_service import AuditService
from app.repositories.customer_repository import CustomerRepository
from app.utils.db_session import persist
from app.utils.security import hash_password, verify_password

logger = logging.getLogger(__name__)

DEFAULT_PORTAL_PASSWORD = "Admin@123"
MAX_FAILED_LOGINS = 5

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
MOBILE_RE = re.compile(r"^\d{10}$")
AADHAAR_RE = re.compile(r"^\d{12}$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


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
        """Full Customer Master profile for the logged-in customer only."""
        self.repo.ensure_schema()
        cid = int(customer_id)
        auth = self.repo.get_portal_auth(cid)
        if not auth:
            return {
                "ok": False,
                "error": "Customer not found.",
                "error_code": "not_found",
                "status_code": 404,
            }
        try:
            record = self.repo.get_full(cid)
        except Exception:  # noqa: BLE001
            logger.exception("Unable to load portal profile for %s", cid)
            return {
                "ok": False,
                "error": "Unable to load profile.",
                "error_code": "server_error",
                "status_code": 500,
            }
        # Never expose income-tax portal password to the customer UI.
        record.pop("income_tax_password", None)
        record["customer_id"] = cid
        record["masked_pan"] = self.mask_pan(record.get("pan_number") or auth.get("pan_number"))
        record["last_login"] = (
            auth.get("last_login").isoformat() if auth.get("last_login") else None
        )
        record["password_changed"] = bool(auth.get("password_changed"))
        record["readonly_fields"] = sorted(PORTAL_READONLY_FIELDS)
        record["editable_fields"] = sorted(PORTAL_EDITABLE_FIELDS)
        return {"ok": True, "profile": record}

    def _validate_profile_payload(self, payload: dict, *, customer_id: int) -> dict[str, Any]:
        cleaned: dict[str, Any] = {}
        for key, value in (payload or {}).items():
            if key in PORTAL_BLOCKED_FIELDS or key in PORTAL_READONLY_FIELDS:
                continue
            if key not in PORTAL_EDITABLE_FIELDS or key not in FORM_TO_DB:
                continue
            if isinstance(value, str):
                value = value.strip()
            cleaned[key] = value

        mobile = self.repo._normalize_mobile(cleaned.get("mobile_number"))
        if "mobile_number" in cleaned:
            if mobile and not MOBILE_RE.match(mobile):
                raise ValueError("Mobile Number must be a valid 10-digit number.")
            cleaned["mobile_number"] = mobile or None

        if "alternate_mobile" in cleaned:
            alt = self.repo._normalize_mobile(cleaned.get("alternate_mobile"))
            if alt and not MOBILE_RE.match(alt):
                raise ValueError("Alternate Mobile must be a valid 10-digit number.")
            cleaned["alternate_mobile"] = alt or None

        if "whatsapp_number" in cleaned:
            wa = self.repo._normalize_mobile(cleaned.get("whatsapp_number"))
            if wa and not MOBILE_RE.match(wa):
                raise ValueError("WhatsApp Number must be a valid 10-digit number.")
            cleaned["whatsapp_number"] = wa or None

        if "email_id" in cleaned:
            email = (cleaned.get("email_id") or "").strip().lower()
            if email and not EMAIL_RE.match(email):
                raise ValueError("Email Address is invalid.")
            cleaned["email_id"] = email or None

        if "aadhaar_number" in cleaned:
            aadhaar = re.sub(r"\D", "", cleaned.get("aadhaar_number") or "")
            if aadhaar and not AADHAAR_RE.match(aadhaar):
                raise ValueError("Aadhaar Number must be 12 digits.")
            cleaned["aadhaar_number"] = aadhaar or None

        if "gender" in cleaned and cleaned.get("gender"):
            if cleaned["gender"] not in GENDERS:
                raise ValueError("Gender is invalid.")

        if "filing_frequency" in cleaned and cleaned.get("filing_frequency"):
            if cleaned["filing_frequency"] not in GST_FILING_FREQUENCIES:
                raise ValueError("GST Filing Frequency is invalid.")

        if "ifsc_code" in cleaned and cleaned.get("ifsc_code"):
            ifsc = str(cleaned["ifsc_code"]).upper().replace(" ", "")
            if not IFSC_RE.match(ifsc):
                raise ValueError("IFSC Code is invalid.")
            cleaned["ifsc_code"] = ifsc

        if "pincode" in cleaned and cleaned.get("pincode"):
            pin = re.sub(r"\D", "", str(cleaned["pincode"]))
            if len(pin) != 6:
                raise ValueError("PIN Code must be 6 digits.")
            cleaned["pincode"] = pin

        for date_key in ("date_of_birth", "date_of_incorporation"):
            if date_key in cleaned and cleaned.get(date_key):
                raw = str(cleaned[date_key])[:10]
                try:
                    cleaned[date_key] = date.fromisoformat(raw)
                except ValueError as exc:
                    raise ValueError(f"{date_key.replace('_', ' ').title()} is invalid.") from exc

        # Duplicate checks for identity/contact fields (exclude self).
        if cleaned.get("aadhaar_number"):
            dup = self.repo.find_by_aadhaar(
                cleaned["aadhaar_number"], exclude_customer_id=customer_id
            )
            if dup:
                raise ValueError(
                    "This Aadhaar Number is already registered with another customer. "
                    "Please contact JTCS."
                )
        if cleaned.get("mobile_number"):
            dups = self.repo.find_by_mobile(
                cleaned["mobile_number"], exclude_customer_id=customer_id
            )
            if dups:
                raise ValueError(
                    "This Mobile Number is registered with multiple / other customer records. "
                    "Please contact JTCS."
                )
        if cleaned.get("email_id"):
            dups = self.repo.find_by_email(
                cleaned["email_id"], exclude_customer_id=customer_id
            )
            if len(dups) > 0:
                raise ValueError(
                    "This Email Address is registered with another customer. "
                    "Please contact JTCS."
                )
        return cleaned

    def _save_profile_photo(self, customer_id: int, file_storage: FileStorage) -> str:
        if not file_storage or not file_storage.filename:
            raise ValueError("Photo file is required.")
        filename = secure_filename(file_storage.filename)
        ext = Path(filename).suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValueError("Photo must be JPG, PNG or WEBP.")
        root = Path(current_app.root_path) / "static" / "uploads" / "customer_photos"
        root.mkdir(parents=True, exist_ok=True)
        name = f"portal_{int(customer_id)}_{uuid4().hex[:10]}{ext}"
        dest = root / name
        file_storage.save(dest)
        return f"uploads/customer_photos/{name}"

    def update_profile(
        self,
        customer_id: int,
        payload: dict,
        *,
        photo_file: FileStorage | None = None,
        actor_name: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """Update Customer Master fields for the logged-in customer only."""
        self.repo.ensure_schema()
        cid = int(customer_id)
        auth = self.repo.get_portal_auth(cid)
        if not auth:
            return {
                "ok": False,
                "error": "Customer not found.",
                "error_code": "not_found",
                "status_code": 404,
            }
        try:
            old_record = self.repo.get_full(cid)
        except Exception:  # noqa: BLE001
            return {
                "ok": False,
                "error": "Unable to load profile.",
                "error_code": "server_error",
                "status_code": 500,
            }

        try:
            cleaned = self._validate_profile_payload(payload, customer_id=cid)
            if photo_file and getattr(photo_file, "filename", None):
                cleaned["photo_path"] = self._save_profile_photo(cid, photo_file)
        except ValueError as exc:
            return {
                "ok": False,
                "error": str(exc),
                "error_code": "validation_error",
                "status_code": 400,
            }

        if not cleaned:
            return {
                "ok": False,
                "error": "No editable fields provided.",
                "error_code": "empty_payload",
                "status_code": 400,
            }

        # Force-protect identity fields even if payload tried to smuggle them.
        cleaned.pop("customer_name", None)
        cleaned.pop("pan_number", None)
        # save_full() defaults missing CustomerStatus to Active — preserve admin status.
        cleaned["customer_status"] = old_record.get("customer_status") or "Active"

        try:
            def _write() -> dict:
                return self.repo.save_full(cleaned, customer_id=cid)

            saved = persist(_write)
        except Exception:  # noqa: BLE001
            db.session.rollback()
            logger.exception("Portal profile update failed for %s", cid)
            return {
                "ok": False,
                "error": "Unable to save profile. Please try again.",
                "error_code": "server_error",
                "status_code": 500,
            }

        changed = {
            key: {"old": old_record.get(key), "new": cleaned.get(key)}
            for key in cleaned
            if str(old_record.get(key) or "") != str(cleaned.get(key) or "")
        }
        try:
            AuditService().log(
                action_name="CustomerPortal.ProfileUpdate",
                entity_type="CustomerMaster",
                entity_id=cid,
                old_value={k: v["old"] for k, v in changed.items()},
                new_value={k: v["new"] for k, v in changed.items()},
                user_id=None,
                user_name=(actor_name or f"Customer:{cid}")[:150],
                ip_address=ip_address,
                browser=user_agent,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Audit log failed for portal profile update %s", cid)

        result = self.get_profile(cid)
        result["message"] = "Profile updated successfully."
        result["changed_fields"] = sorted(changed.keys())
        return result

    # ------------------------------------------------------------------
    # Customer-scoped related data (always filtered by CustomerID)
    # ------------------------------------------------------------------

    @staticmethod
    def _table_exists(table_name: str) -> bool:
        value = db.session.execute(
            text(
                """
                SELECT CASE WHEN OBJECT_ID(:obj, N'U') IS NULL THEN 0 ELSE 1 END
                """
            ),
            {"obj": f"dbo.{table_name}"},
        ).scalar()
        return bool(value)

    @staticmethod
    def _serialize_cell(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat(sep=" ", timespec="minutes")
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Decimal):
            return f"{value.quantize(Decimal('0.01')):.2f}"
        return value

    def _rows(self, sql: str, params: dict) -> list[dict]:
        rows = db.session.execute(text(sql), params).mappings().all()
        return [{k: self._serialize_cell(v) for k, v in dict(r).items()} for r in rows]

    def get_module_data(self, customer_id: int, module_key: str) -> dict[str, Any]:
        """Return related JTCS ERP records for this customer only."""
        cid = int(customer_id)
        auth = self.repo.get_portal_auth(cid)
        if not auth:
            return {
                "ok": False,
                "error": "Customer not found.",
                "error_code": "not_found",
                "status_code": 404,
            }
        meta = PORTAL_MODULES.get(module_key)
        if not meta or module_key == "profile":
            return {
                "ok": False,
                "error": "Unknown module.",
                "error_code": "unknown_module",
                "status_code": 404,
            }

        sections: list[dict[str, Any]] = []
        try:
            if module_key == "documents":
                if self._table_exists("CrmDocument"):
                    sections.append(
                        {
                            "title": "Documents",
                            "columns": [
                                ("title", "Title"),
                                ("folder_type", "Folder"),
                                ("file_name", "File"),
                                ("created_date", "Date"),
                            ],
                            "rows": self._rows(
                                """
                                SELECT TOP 200
                                    DocumentID AS id,
                                    Title AS title,
                                    FolderType AS folder_type,
                                    FileName AS file_name,
                                    CreatedDate AS created_date
                                FROM dbo.CrmDocument
                                WHERE CustomerID = :cid AND ISNULL(IsActive, 1) = 1
                                ORDER BY CreatedDate DESC, DocumentID DESC
                                """,
                                {"cid": cid},
                            ),
                        }
                    )
            elif module_key == "itr":
                if self._table_exists("FollowupEntryMaster"):
                    sections.append(
                        {
                            "title": "Income Tax Follow-ups",
                            "columns": [
                                ("entry_id", "Entry"),
                                ("financial_year", "FY"),
                                ("status", "Status"),
                                ("assessment_year", "AY"),
                                ("remarks", "Remarks"),
                                ("created_date", "Created"),
                            ],
                            "rows": self._followup_rows(cid, "ITR"),
                        }
                    )
                if self._table_exists("JTCSDailyTransaction"):
                    sections.append(
                        {
                            "title": "ITR Related Transactions",
                            "columns": [
                                ("transaction_id", "Txn"),
                                ("transaction_date", "Date"),
                                ("description", "Description"),
                                ("total_amount", "Amount"),
                                ("status", "Status"),
                            ],
                            "rows": self._daily_rows(cid, work_like="ITR"),
                        }
                    )
            elif module_key == "gst":
                if self._table_exists("FollowupEntryMaster"):
                    sections.append(
                        {
                            "title": "GST Follow-ups",
                            "columns": [
                                ("entry_id", "Entry"),
                                ("financial_year", "FY"),
                                ("status", "Status"),
                                ("remarks", "Remarks"),
                                ("created_date", "Created"),
                            ],
                            "rows": self._followup_rows(cid, "GST"),
                        }
                    )
                if self._table_exists("GstInvoice"):
                    sections.append(
                        {
                            "title": "GST Invoices",
                            "columns": [
                                ("invoice_id", "Invoice"),
                                ("invoice_no", "Number"),
                                ("invoice_date", "Date"),
                                ("grand_total", "Amount"),
                                ("status", "Status"),
                            ],
                            "rows": self._gst_invoice_rows(cid),
                        }
                    )
            elif module_key == "tds":
                if self._table_exists("FollowupEntryMaster"):
                    sections.append(
                        {
                            "title": "TDS Follow-ups",
                            "columns": [
                                ("entry_id", "Entry"),
                                ("financial_year", "FY"),
                                ("status", "Status"),
                                ("remarks", "Remarks"),
                                ("created_date", "Created"),
                            ],
                            "rows": self._followup_rows(cid, "TDS"),
                        }
                    )
            elif module_key == "notices":
                if self._table_exists("CrmDocument"):
                    sections.append(
                        {
                            "title": "Notices",
                            "columns": [
                                ("title", "Title"),
                                ("folder_type", "Folder"),
                                ("file_name", "File"),
                                ("created_date", "Date"),
                            ],
                            "rows": self._rows(
                                """
                                SELECT TOP 200
                                    DocumentID AS id,
                                    Title AS title,
                                    FolderType AS folder_type,
                                    FileName AS file_name,
                                    CreatedDate AS created_date
                                FROM dbo.CrmDocument
                                WHERE CustomerID = :cid
                                  AND ISNULL(IsActive, 1) = 1
                                  AND (
                                        FolderType LIKE N'%Notice%'
                                     OR Title LIKE N'%Notice%'
                                     OR Title LIKE N'%Demand%'
                                  )
                                ORDER BY CreatedDate DESC, DocumentID DESC
                                """,
                                {"cid": cid},
                            ),
                        }
                    )
            elif module_key == "downloads":
                if self._table_exists("CrmDocument"):
                    sections.append(
                        {
                            "title": "Downloads",
                            "columns": [
                                ("title", "Title"),
                                ("folder_type", "Folder"),
                                ("file_name", "File"),
                                ("created_date", "Date"),
                            ],
                            "rows": self._rows(
                                """
                                SELECT TOP 200
                                    DocumentID AS id,
                                    Title AS title,
                                    FolderType AS folder_type,
                                    FileName AS file_name,
                                    CreatedDate AS created_date
                                FROM dbo.CrmDocument
                                WHERE CustomerID = :cid AND ISNULL(IsActive, 1) = 1
                                ORDER BY CreatedDate DESC, DocumentID DESC
                                """,
                                {"cid": cid},
                            ),
                        }
                    )
            elif module_key == "payments":
                if self._table_exists("JTCSDailyTransaction"):
                    sections.append(
                        {
                            "title": "Payments / Receipts",
                            "columns": [
                                ("transaction_id", "Txn"),
                                ("transaction_date", "Date"),
                                ("work_type", "Work"),
                                ("description", "Description"),
                                ("total_amount", "Amount"),
                                ("status", "Status"),
                            ],
                            "rows": self._daily_rows(cid, work_like=None),
                        }
                    )
                if self._table_exists("GstInvoice"):
                    sections.append(
                        {
                            "title": "GST Invoices",
                            "columns": [
                                ("invoice_id", "Invoice"),
                                ("invoice_no", "Number"),
                                ("invoice_date", "Date"),
                                ("grand_total", "Amount"),
                                ("status", "Status"),
                            ],
                            "rows": self._gst_invoice_rows(cid),
                        }
                    )
            elif module_key == "support":
                if self._table_exists("CrmTask"):
                    sections.append(
                        {
                            "title": "Assigned Tasks",
                            "columns": [
                                ("task_id", "Task"),
                                ("title", "Title"),
                                ("status", "Status"),
                                ("priority", "Priority"),
                                ("deadline", "Deadline"),
                            ],
                            "rows": self._rows(
                                """
                                SELECT TOP 200
                                    TaskID AS task_id,
                                    Title AS title,
                                    Status AS status,
                                    Priority AS priority,
                                    Deadline AS deadline
                                FROM dbo.CrmTask
                                WHERE CustomerID = :cid AND ISNULL(IsActive, 1) = 1
                                ORDER BY CreatedDate DESC, TaskID DESC
                                """,
                                {"cid": cid},
                            ),
                        }
                    )
                if self._table_exists("CrmConversation"):
                    sections.append(
                        {
                            "title": "Communication History",
                            "columns": [
                                ("conversation_id", "ID"),
                                ("subject", "Subject"),
                                ("channel", "Channel"),
                                ("status", "Status"),
                                ("created_date", "Date"),
                            ],
                            "rows": self._conversation_rows(cid),
                        }
                    )
        except Exception:  # noqa: BLE001
            logger.exception("Portal module %s failed for customer %s", module_key, cid)
            return {
                "ok": False,
                "error": "Unable to load module data.",
                "error_code": "server_error",
                "status_code": 500,
            }

        if not sections:
            sections.append(
                {
                    "title": meta["title"],
                    "columns": [("message", "Message")],
                    "rows": [
                        {
                            "message": (
                                "No related records are available for your account yet, "
                                "or this module is not configured in the current database."
                            )
                        }
                    ],
                }
            )

        return {
            "ok": True,
            "module": module_key,
            "title": meta["title"],
            "blurb": meta["blurb"],
            "customer_id": cid,
            "customer_name": auth.get("customer_name") or "",
            "sections": sections,
        }

    def _followup_column_map(self) -> dict[str, str]:
        """Resolve FollowupEntryMaster column names present in this DB."""
        cols = {
            r[0]
            for r in db.session.execute(
                text(
                    """
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = N'FollowupEntryMaster'
                    """
                )
            ).all()
        }
        return {
            "fy": "FinancialYear" if "FinancialYear" in cols else (
                "FY" if "FY" in cols else None
            ),
            "ay": "AssessmentYear" if "AssessmentYear" in cols else None,
            "status": "Status" if "Status" in cols else (
                "CurrentStatus" if "CurrentStatus" in cols else None
            ),
            "remarks": "Remarks" if "Remarks" in cols else None,
            "module": "ModuleCode" if "ModuleCode" in cols else (
                "Module" if "Module" in cols else None
            ),
            "created": "CreatedDate" if "CreatedDate" in cols else None,
        }

    def _followup_rows(self, customer_id: int, module_code: str) -> list[dict]:
        cmap = self._followup_column_map()
        if not cmap.get("module"):
            return []
        select_parts = ["EntryID AS entry_id"]
        if cmap["fy"]:
            select_parts.append(f"{cmap['fy']} AS financial_year")
        else:
            select_parts.append("NULL AS financial_year")
        if cmap["ay"]:
            select_parts.append(f"{cmap['ay']} AS assessment_year")
        else:
            select_parts.append("NULL AS assessment_year")
        if cmap["status"]:
            select_parts.append(f"{cmap['status']} AS status")
        else:
            select_parts.append("NULL AS status")
        if cmap["remarks"]:
            select_parts.append(f"{cmap['remarks']} AS remarks")
        else:
            select_parts.append("NULL AS remarks")
        if cmap["created"]:
            select_parts.append(f"{cmap['created']} AS created_date")
        else:
            select_parts.append("NULL AS created_date")
        sql = f"""
            SELECT TOP 200 {", ".join(select_parts)}
            FROM dbo.FollowupEntryMaster
            WHERE CustomerID = :cid
              AND UPPER(LTRIM(RTRIM({cmap['module']}))) = :module
            ORDER BY EntryID DESC
        """
        return self._rows(sql, {"cid": customer_id, "module": module_code.upper()})

    def _daily_rows(self, customer_id: int, *, work_like: str | None) -> list[dict]:
        sql = """
            SELECT TOP 200
                TransactionID AS transaction_id,
                TransactionDate AS transaction_date,
                WorkType AS work_type,
                Description AS description,
                TotalAmount AS total_amount,
                Status AS status
            FROM dbo.JTCSDailyTransaction
            WHERE CustomerID = :cid
        """
        params: dict[str, Any] = {"cid": customer_id}
        if work_like:
            sql += " AND UPPER(ISNULL(WorkType, N'')) LIKE :work"
            params["work"] = f"%{work_like.upper()}%"
        sql += " ORDER BY TransactionDate DESC, TransactionID DESC"
        return self._rows(sql, params)

    def _gst_invoice_rows(self, customer_id: int) -> list[dict]:
        cols = {
            r[0]
            for r in db.session.execute(
                text(
                    """
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = N'GstInvoice'
                    """
                )
            ).all()
        }
        inv_no = "InvoiceNo" if "InvoiceNo" in cols else (
            "InvoiceNumber" if "InvoiceNumber" in cols else None
        )
        inv_date = "InvoiceDate" if "InvoiceDate" in cols else None
        total = "GrandTotal" if "GrandTotal" in cols else (
            "TotalAmount" if "TotalAmount" in cols else None
        )
        status = "Status" if "Status" in cols else None
        select_parts = ["InvoiceID AS invoice_id"]
        select_parts.append(f"{inv_no} AS invoice_no" if inv_no else "NULL AS invoice_no")
        select_parts.append(f"{inv_date} AS invoice_date" if inv_date else "NULL AS invoice_date")
        select_parts.append(f"{total} AS grand_total" if total else "NULL AS grand_total")
        select_parts.append(f"{status} AS status" if status else "NULL AS status")
        sql = f"""
            SELECT TOP 200 {", ".join(select_parts)}
            FROM dbo.GstInvoice
            WHERE CustomerID = :cid
            ORDER BY InvoiceID DESC
        """
        return self._rows(sql, {"cid": customer_id})

    def _conversation_rows(self, customer_id: int) -> list[dict]:
        cols = {
            r[0]
            for r in db.session.execute(
                text(
                    """
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = N'CrmConversation'
                    """
                )
            ).all()
        }
        subject = "Subject" if "Subject" in cols else ("Title" if "Title" in cols else None)
        channel = "Channel" if "Channel" in cols else None
        status = "Status" if "Status" in cols else None
        created = "CreatedDate" if "CreatedDate" in cols else None
        id_col = "ConversationID" if "ConversationID" in cols else "ID"
        select_parts = [f"{id_col} AS conversation_id"]
        select_parts.append(f"{subject} AS subject" if subject else "NULL AS subject")
        select_parts.append(f"{channel} AS channel" if channel else "NULL AS channel")
        select_parts.append(f"{status} AS status" if status else "NULL AS status")
        select_parts.append(f"{created} AS created_date" if created else "NULL AS created_date")
        order = created or id_col
        sql = f"""
            SELECT TOP 200 {", ".join(select_parts)}
            FROM dbo.CrmConversation
            WHERE CustomerID = :cid
            ORDER BY {order} DESC
        """
        return self._rows(sql, {"cid": customer_id})

