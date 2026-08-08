"""Link inbound contacts to Customer Master or auto-create a Lead."""

from __future__ import annotations

import re

from sqlalchemy import text

from app.extensions import db
from app.modules.crm.lead_service import CrmLeadService
from app.modules.shared.schema import ensure_crm_schema


def normalize_phone(raw: str | None) -> str:
    """Return digits only; strip leading 00; keep last 10–15 for matching."""
    if not raw:
        return ""
    digits = re.sub(r"\D", "", str(raw))
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def phones_match(a: str | None, b: str | None) -> bool:
    da, db_ = normalize_phone(a), normalize_phone(b)
    if not da or not db_:
        return False
    if da == db_:
        return True
    # India: compare last 10 digits
    return len(da) >= 10 and len(db_) >= 10 and da[-10:] == db_[-10:]


class CustomerLinkService:
    """Resolve WhatsApp/Email contact → CustomerID or LeadID."""

    def find_customer_by_mobile(self, mobile: str | None) -> dict | None:
        ensure_crm_schema()
        digits = normalize_phone(mobile)
        if not digits:
            return None
        last10 = digits[-10:] if len(digits) >= 10 else digits
        row = db.session.execute(
            text(
                """
                SELECT TOP 1 CustomerID, CustomerName, MobileNumber, WhatsAppNumber,
                       AlternateMobile, EmailID, PANNumber, GSTNumber
                FROM dbo.CustomerMaster
                WHERE ISNULL(CustomerStatus, N'Active') <> N'Inactive'
                  AND (
                        REPLACE(REPLACE(REPLACE(ISNULL(WhatsAppNumber, N''), N' ', N''), N'-', N''), N'+', N'')
                            LIKE N'%' + :last10
                     OR REPLACE(REPLACE(REPLACE(ISNULL(MobileNumber, N''), N' ', N''), N'-', N''), N'+', N'')
                            LIKE N'%' + :last10
                     OR REPLACE(REPLACE(REPLACE(ISNULL(AlternateMobile, N''), N' ', N''), N'-', N''), N'+', N'')
                            LIKE N'%' + :last10
                  )
                ORDER BY CustomerID
                """
            ),
            {"last10": last10},
        ).mappings().first()
        return dict(row) if row else None

    def find_customer_by_email(self, email: str | None) -> dict | None:
        ensure_crm_schema()
        addr = (email or "").strip().lower()
        if not addr or "@" not in addr:
            return None
        row = db.session.execute(
            text(
                """
                SELECT TOP 1 CustomerID, CustomerName, MobileNumber, WhatsAppNumber,
                       AlternateMobile, EmailID, PANNumber, GSTNumber
                FROM dbo.CustomerMaster
                WHERE ISNULL(CustomerStatus, N'Active') <> N'Inactive'
                  AND LOWER(LTRIM(RTRIM(ISNULL(EmailID, N'')))) = :email
                ORDER BY CustomerID
                """
            ),
            {"email": addr},
        ).mappings().first()
        return dict(row) if row else None

    def find_open_lead_by_mobile(self, mobile: str | None) -> dict | None:
        ensure_crm_schema()
        digits = normalize_phone(mobile)
        if not digits:
            return None
        last10 = digits[-10:] if len(digits) >= 10 else digits
        row = db.session.execute(
            text(
                """
                SELECT TOP 1 LeadID, FullName, Mobile, Email, Status, CustomerID
                FROM dbo.CrmLead
                WHERE IsActive = 1
                  AND Status NOT IN (N'Converted', N'Closed', N'Lost')
                  AND REPLACE(REPLACE(REPLACE(ISNULL(Mobile, N''), N' ', N''), N'-', N''), N'+', N'')
                        LIKE N'%' + :last10
                ORDER BY LeadID DESC
                """
            ),
            {"last10": last10},
        ).mappings().first()
        return dict(row) if row else None

    def find_open_lead_by_email(self, email: str | None) -> dict | None:
        ensure_crm_schema()
        addr = (email or "").strip().lower()
        if not addr:
            return None
        row = db.session.execute(
            text(
                """
                SELECT TOP 1 LeadID, FullName, Mobile, Email, Status, CustomerID
                FROM dbo.CrmLead
                WHERE IsActive = 1
                  AND Status NOT IN (N'Converted', N'Closed', N'Lost')
                  AND LOWER(LTRIM(RTRIM(ISNULL(Email, N'')))) = :email
                ORDER BY LeadID DESC
                """
            ),
            {"email": addr},
        ).mappings().first()
        return dict(row) if row else None

    def resolve_mobile(
        self,
        mobile: str | None,
        *,
        display_name: str | None = None,
        source: str = "WhatsApp",
        message: str | None = None,
        user_id: int | None = None,
        user_name: str | None = None,
        create_lead_if_missing: bool = True,
    ) -> dict:
        """
        Returns {customer_id, lead_id, created_lead, contact_name, mobile}.
        """
        customer = self.find_customer_by_mobile(mobile)
        if customer:
            return {
                "customer_id": int(customer["CustomerID"]),
                "lead_id": None,
                "created_lead": False,
                "contact_name": customer.get("CustomerName"),
                "mobile": normalize_phone(mobile),
            }

        lead = self.find_open_lead_by_mobile(mobile)
        if lead:
            return {
                "customer_id": int(lead["CustomerID"]) if lead.get("CustomerID") else None,
                "lead_id": int(lead["LeadID"]),
                "created_lead": False,
                "contact_name": lead.get("FullName"),
                "mobile": normalize_phone(mobile),
            }

        if not create_lead_if_missing:
            return {
                "customer_id": None,
                "lead_id": None,
                "created_lead": False,
                "contact_name": display_name,
                "mobile": normalize_phone(mobile),
            }

        name = (display_name or "").strip() or f"WhatsApp {normalize_phone(mobile)[-10:]}"
        result = CrmLeadService().create_lead(
            source=source,
            request_type="WhatsApp",
            full_name=name,
            mobile=normalize_phone(mobile) or None,
            message=message,
            priority="Normal",
            user_id=user_id,
            user_name=user_name,
        )
        lead_id = int(result.get("lead_id") or result.get("LeadID") or 0)
        return {
            "customer_id": None,
            "lead_id": lead_id or None,
            "created_lead": True,
            "contact_name": name,
            "mobile": normalize_phone(mobile),
        }

    def resolve_email(
        self,
        email: str | None,
        *,
        display_name: str | None = None,
        source: str = "Email",
        message: str | None = None,
        user_id: int | None = None,
        user_name: str | None = None,
        create_lead_if_missing: bool = True,
        mobile: str | None = None,
    ) -> dict:
        customer = self.find_customer_by_email(email)
        if customer:
            return {
                "customer_id": int(customer["CustomerID"]),
                "lead_id": None,
                "created_lead": False,
                "contact_name": customer.get("CustomerName"),
                "email": (email or "").strip().lower(),
            }

        lead = self.find_open_lead_by_email(email)
        if lead:
            return {
                "customer_id": int(lead["CustomerID"]) if lead.get("CustomerID") else None,
                "lead_id": int(lead["LeadID"]),
                "created_lead": False,
                "contact_name": lead.get("FullName"),
                "email": (email or "").strip().lower(),
            }

        if not create_lead_if_missing:
            return {
                "customer_id": None,
                "lead_id": None,
                "created_lead": False,
                "contact_name": display_name,
                "email": (email or "").strip().lower(),
            }

        name = (display_name or "").strip() or (email or "Email Lead")
        result = CrmLeadService().create_lead(
            source=source,
            request_type="Email",
            full_name=name,
            mobile=mobile,
            email=(email or "").strip() or None,
            message=message,
            priority="Normal",
            user_id=user_id,
            user_name=user_name,
        )
        lead_id = int(result.get("lead_id") or result.get("LeadID") or 0)
        return {
            "customer_id": None,
            "lead_id": lead_id or None,
            "created_lead": True,
            "contact_name": name,
            "email": (email or "").strip().lower(),
        }
