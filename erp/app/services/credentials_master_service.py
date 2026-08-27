from __future__ import annotations

from datetime import datetime
import re

from app.repositories.credentials_master_repository import CredentialsMasterRepository
from app.utils.db_session import persist
from app.utils.master_delete_guard import assert_master_unused


class CredentialsMasterService:
    def __init__(self, repository: CredentialsMasterRepository | None = None):
        self.repo = repository or CredentialsMasterRepository()

    @staticmethod
    def _clean(value, max_len: int | None = None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if max_len is not None:
            return text[:max_len]
        return text

    def _parse_form(self, form: dict) -> dict:
        activity = self._clean(form.get("Activity"), 200)
        if not activity:
            raise ValueError("Activity is required.")

        email = self._clean(form.get("EmailID"), 200)
        if email and "@" not in email:
            raise ValueError("Enter a valid Email ID.")

        mobile = self._clean(form.get("MobileNumber"), 20)
        if mobile:
            digits = re.sub(r"\D", "", mobile)
            if len(digits) not in (10, 12) and not re.fullmatch(r"[0-9+\-\s]{7,20}", mobile):
                raise ValueError("Enter a valid Mobile Number.")
            mobile = digits[-10:] if len(digits) >= 10 else mobile

        if "ActiveStatus" in form or "active_status" in form:
            active_raw = (form.get("ActiveStatus") or form.get("active_status") or "").strip().lower()
            active = active_raw in {"1", "true", "on", "yes"}
        else:
            active = False

        return {
            "Activity": activity,
            "URL": self._clean(form.get("URL"), 500),
            "UserID": self._clean(form.get("UserID"), 150),
            "Password": self._clean(form.get("Password"), 200),
            "EmailID": email,
            "MobileNumber": mobile,
            "ActiveStatus": active,
        }

    @staticmethod
    def _serialize(row) -> dict:
        return {
            "credential_id": row.CredentialID,
            "activity": row.Activity or "",
            "url": row.URL or "",
            "user_id": row.UserID or "",
            "password": row.Password or "",
            "email_id": row.EmailID or "",
            "mobile_number": row.MobileNumber or "",
            "active_status": bool(row.ActiveStatus),
            "created_date": row.CreatedDate.isoformat() if isinstance(row.CreatedDate, datetime) else "",
            "modified_date": row.ModifiedDate.isoformat() if isinstance(row.ModifiedDate, datetime) else "",
        }

    def list_records(self, *, search: str | None = None, active_only: bool = False) -> list[dict]:
        return [
            self._serialize(row)
            for row in self.repo.list_all(search=search, active_only=active_only)
        ]

    def find_shcil_login(self, role: str = "deo") -> dict | None:
        """Return Stamp DEO or Stamp Admin credentials from Credentials Master."""
        wanted = (role or "deo").strip().lower()
        if wanted not in {"deo", "admin"}:
            wanted = "deo"
        stamp_rows: list[tuple[str, object]] = []
        for row in self.repo.list_all(active_only=True):
            if not (row.UserID and row.Password):
                continue
            blob = f"{row.Activity or ''} {row.URL or ''} {row.UserID or ''}".lower()
            if not any(
                key in blob
                for key in ("shcil", "estamp", "e-stamp", "e stamp", "stamp")
            ):
                continue
            stamp_rows.append((blob, row))
        if not stamp_rows:
            return None

        def is_deo(blob: str) -> bool:
            return bool(re.search(r"\bdeo\b|data\s*entry|stamp\s*deo", blob))

        def is_admin(blob: str) -> bool:
            return bool(re.search(r"\badmin\b|stamp\s*admin", blob)) and not is_deo(blob)

        if wanted == "admin":
            admin_rows = [row for blob, row in stamp_rows if is_admin(blob)]
            return self._serialize(admin_rows[0]) if admin_rows else None

        deo_rows = [row for blob, row in stamp_rows if is_deo(blob)]
        if deo_rows:
            return self._serialize(deo_rows[0])
        other_rows = [row for blob, row in stamp_rows if not is_admin(blob)]
        if other_rows:
            return self._serialize(other_rows[0])
        return None

    def get_record(self, credential_id: int) -> dict:
        row = self.repo.get_by_id(credential_id)
        if row is None:
            raise ValueError("Credential not found.")
        return self._serialize(row)

    def create_record(self, form: dict, *, created_by: str = "System") -> dict:
        data = self._parse_form(form)

        def _write() -> dict:
            row = self.repo.create({**data, "CreatedBy": created_by})
            return self._serialize(row)

        return persist(_write)

    def update_record(self, credential_id: int, form: dict) -> dict:
        data = self._parse_form(form)

        def _write() -> dict:
            row = self.repo.get_by_id(credential_id)
            if row is None:
                raise ValueError("Credential not found.")
            row = self.repo.update(row, data)
            return self._serialize(row)

        return persist(_write)

    def delete_record(self, credential_id: int) -> str:
        def _write() -> str:
            row = self.repo.get_by_id(credential_id)
            if row is None:
                raise ValueError("Credential not found.")
            assert_master_unused(
                table="CredentialsMaster",
                pk_column="CredentialID",
                pk_value=credential_id,
                display_name=row.Activity or "Credential",
            )
            if row.ActiveStatus:
                self.repo.update(row, {"ActiveStatus": False})
                return "Credential marked inactive."
            self.repo.delete(row)
            return "Credential deleted successfully."

        return persist(_write)
