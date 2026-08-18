"""Link inbound contacts to Customer Master without assuming unique mobiles."""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import text

from app.extensions import db
from app.modules.crm.lead_service import CrmLeadService
from app.modules.shared.schema import ensure_crm_schema


def normalize_phone(raw: str | None) -> str:
    """Return digits only; strip leading 00."""
    if not raw:
        return ""
    digits = re.sub(r"\D", "", str(raw))
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def last10_digits(raw: str | None) -> str:
    digits = normalize_phone(raw)
    if len(digits) >= 10:
        return digits[-10:]
    return digits


def phones_match(a: str | None, b: str | None) -> bool:
    da, db_ = last10_digits(a), last10_digits(b)
    if not da or not db_:
        return False
    return da == db_


_PHONE_DIGITS = (
    "REPLACE(REPLACE(REPLACE(ISNULL({col}, N''), N' ', N''), N'-', N''), N'+', N'')"
)


class CustomerLinkService:
    """Resolve WhatsApp/Email contact → CustomerID or LeadID.

    Customer Master mobile is not unique. Confirmed WhatsApp mappings are
    conversation-level. A number-level hint is never applied automatically
    when more than one customer shares the mobile.
    """

    def find_customers_by_mobile(self, mobile: str | None) -> list[dict]:
        ensure_crm_schema()
        last10 = last10_digits(mobile)
        if not last10:
            return []
        wa = _PHONE_DIGITS.format(col="WhatsAppNumber")
        mo = _PHONE_DIGITS.format(col="MobileNumber")
        alt = _PHONE_DIGITS.format(col="AlternateMobile")
        rows = db.session.execute(
            text(
                f"""
                SELECT CustomerID, CustomerName, MobileNumber, WhatsAppNumber,
                       AlternateMobile, EmailID, CustomerGroup, CustomerStatus, City
                FROM dbo.CustomerMaster
                WHERE ISNULL(CustomerStatus, N'Active') <> N'Inactive'
                  AND (
                        {wa} LIKE N'%' + :last10
                     OR {mo} LIKE N'%' + :last10
                     OR {alt} LIKE N'%' + :last10
                  )
                ORDER BY CustomerID
                """
            ),
            {"last10": last10},
        ).mappings().all()
        out = []
        for row in rows:
            rec = dict(row)
            rec["customer_id"] = int(rec["CustomerID"])
            out.append(rec)
        return out

    def find_customer_by_mobile(self, mobile: str | None) -> dict | None:
        """Return the customer only when exactly one active match exists."""
        matches = self.find_customers_by_mobile(mobile)
        if len(matches) == 1:
            return matches[0]
        return None

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
        last10 = last10_digits(mobile)
        if not last10:
            return None
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

    def find_whatsapp_mapping(
        self,
        mobile: str | None,
        *,
        conversation_id: int | None = None,
        confirmed_only: bool = False,
    ) -> dict | None:
        """Return a mapping hint. Conversation-level rows win over number-level hints."""
        ensure_crm_schema()
        last10 = last10_digits(mobile)
        if not last10 and not conversation_id:
            return None
        clauses = [
            """(
                RIGHT(REPLACE(REPLACE(REPLACE(ISNULL(m.WhatsAppNumber, N''), N' ', N''), N'-', N''), N'+', N''), 10)
                    = :last10
                OR m.WhatsAppNumber = :num
            )"""
        ]
        params: dict = {"last10": last10 or "", "num": normalize_phone(mobile)[:30]}
        if conversation_id:
            clauses.append("(m.ConversationID = :cid OR m.ConversationID IS NULL)")
            params["cid"] = int(conversation_id)
        if confirmed_only:
            clauses.append("ISNULL(m.IsConfirmed, 0) = 1")
        where = " AND ".join(clauses)
        row = db.session.execute(
            text(
                f"""
                SELECT TOP 1 m.MappingID, m.WhatsAppNumber, m.CustomerID, m.LeadID,
                       m.ConversationID, ISNULL(m.IsConfirmed, 0) AS IsConfirmed,
                       c.CustomerName, l.FullName AS LeadName
                FROM dbo.CrmWhatsAppContact m
                LEFT JOIN dbo.CustomerMaster c ON c.CustomerID = m.CustomerID
                LEFT JOIN dbo.CrmLead l ON l.LeadID = m.LeadID
                WHERE {where}
                ORDER BY CASE WHEN m.ConversationID IS NOT NULL THEN 0 ELSE 1 END,
                         CASE WHEN ISNULL(m.IsConfirmed, 0) = 1 THEN 0 ELSE 1 END,
                         m.MappingID DESC
                """
            ),
            params,
        ).mappings().first()
        if not row:
            return None
        return {
            "mapping_id": int(row["MappingID"]),
            "customer_id": int(row["CustomerID"]) if row.get("CustomerID") else None,
            "lead_id": int(row["LeadID"]) if row.get("LeadID") else None,
            "conversation_id": int(row["ConversationID"]) if row.get("ConversationID") else None,
            "is_confirmed": bool(row.get("IsConfirmed")),
            "contact_name": row.get("CustomerName") or row.get("LeadName"),
        }

    def upsert_whatsapp_mapping(
        self,
        mobile: str | None,
        *,
        customer_id: int | None = None,
        lead_id: int | None = None,
        conversation_id: int | None = None,
        confirmed: bool = False,
        user_id: int | None = None,
        overwrite: bool = False,
    ) -> None:
        """Store a conversation-level mapping. Never silently overwrite another conversation."""
        ensure_crm_schema()
        digits = normalize_phone(mobile)
        last10 = last10_digits(mobile)
        if not last10:
            return
        stored_number = last10
        now = datetime.utcnow()

        existing = None
        if conversation_id:
            existing = db.session.execute(
                text(
                    """
                    SELECT TOP 1 MappingID, CustomerID, ISNULL(IsConfirmed, 0) AS IsConfirmed
                    FROM dbo.CrmWhatsAppContact
                    WHERE ConversationID = :cid
                    """
                ),
                {"cid": int(conversation_id)},
            ).mappings().first()
        if existing is None and conversation_id is None:
            existing = db.session.execute(
                text(
                    """
                    SELECT TOP 1 MappingID, CustomerID, ISNULL(IsConfirmed, 0) AS IsConfirmed
                    FROM dbo.CrmWhatsAppContact
                    WHERE ConversationID IS NULL
                      AND RIGHT(REPLACE(REPLACE(REPLACE(ISNULL(WhatsAppNumber, N''), N' ', N''), N'-', N''), N'+', N''), 10)
                          = :last10
                    ORDER BY MappingID DESC
                    """
                ),
                {"last10": last10},
            ).mappings().first()

        if existing:
            same_customer = (
                customer_id
                and existing.get("CustomerID")
                and int(existing["CustomerID"]) == int(customer_id)
            )
            if existing.get("IsConfirmed") and not overwrite and not same_customer:
                if conversation_id and existing:
                    # Conversation-level explicit remap is handled by overwrite=True from the link API.
                    return
                return
            db.session.execute(
                text(
                    """
                    UPDATE dbo.CrmWhatsAppContact
                    SET WhatsAppNumber = :num,
                        CustomerID = COALESCE(:cid, CustomerID),
                        LeadID = COALESCE(:lid, LeadID),
                        ConversationID = COALESCE(:conv, ConversationID),
                        IsConfirmed = CASE WHEN :confirmed = 1 THEN 1 ELSE ISNULL(IsConfirmed, 0) END,
                        ConfirmedByUserID = CASE WHEN :confirmed = 1 THEN :uid ELSE ConfirmedByUserID END,
                        ConfirmedDate = CASE WHEN :confirmed = 1 THEN :now ELSE ConfirmedDate END,
                        ModifiedDate = :now
                    WHERE MappingID = :id
                    """
                ),
                {
                    "num": stored_number,
                    "cid": customer_id,
                    "lid": lead_id,
                    "conv": conversation_id,
                    "confirmed": 1 if confirmed else 0,
                    "uid": user_id,
                    "now": now,
                    "id": int(existing["MappingID"]),
                },
            )
        else:
            db.session.execute(
                text(
                    """
                    INSERT INTO dbo.CrmWhatsAppContact
                        (WhatsAppNumber, CustomerID, LeadID, ConversationID, IsConfirmed,
                         ConfirmedByUserID, ConfirmedDate, ModifiedDate)
                    VALUES
                        (:num, :cid, :lid, :conv, :confirmed, :uid, :cdate, :now)
                    """
                ),
                {
                    "num": stored_number,
                    "cid": customer_id,
                    "lid": lead_id,
                    "conv": conversation_id,
                    "confirmed": 1 if confirmed else 0,
                    "uid": user_id if confirmed else None,
                    "cdate": now if confirmed else None,
                    "now": now,
                },
            )
        db.session.commit()

    def resolve_mobile(
        self,
        mobile: str | None,
        *,
        display_name: str | None = None,
        source: str = "WhatsApp",
        message: str | None = None,
        user_id: int | None = None,
        user_name: str | None = None,
        create_lead_if_missing: bool = False,
        existing_customer_id: int | None = None,
        existing_lead_id: int | None = None,
        conversation_id: int | None = None,
    ) -> dict:
        """Match Customer Master without assuming unique mobiles.

        Returns customer_id only when:
        - the conversation is already linked, or
        - exactly one active customer matches the normalized mobile.

        Multiple matches → ambiguous (no automatic CustomerID).
        Confirmed mappings are suggestions only when more than one customer exists.
        """
        last10 = last10_digits(mobile)
        digits = normalize_phone(mobile)
        candidates = self.find_customers_by_mobile(mobile)
        hint = self.find_whatsapp_mapping(mobile, conversation_id=conversation_id)
        suggested = None
        if hint and hint.get("customer_id"):
            if any(int(c["CustomerID"]) == int(hint["customer_id"]) for c in candidates):
                suggested = int(hint["customer_id"])

        if existing_customer_id:
            name = next(
                (c.get("CustomerName") for c in candidates if int(c["CustomerID"]) == int(existing_customer_id)),
                display_name,
            )
            return {
                "customer_id": int(existing_customer_id),
                "lead_id": int(existing_lead_id) if existing_lead_id else None,
                "created_lead": False,
                "contact_name": name,
                "mobile": digits,
                "last10": last10,
                "unknown": False,
                "ambiguous": False,
                "match_status": "Linked",
                "match_count": len(candidates),
                "candidates": candidates,
                "suggested_customer_id": int(existing_customer_id),
            }

        if existing_lead_id and not candidates:
            lead = self.find_open_lead_by_mobile(mobile)
            return {
                "customer_id": None,
                "lead_id": int(existing_lead_id),
                "created_lead": False,
                "contact_name": (lead or {}).get("FullName") or display_name,
                "mobile": digits,
                "last10": last10,
                "unknown": False,
                "ambiguous": False,
                "match_status": "Linked",
                "match_count": 0,
                "candidates": [],
                "suggested_customer_id": None,
            }

        if len(candidates) == 1:
            customer = candidates[0]
            cid = int(customer["CustomerID"])
            return {
                "customer_id": cid,
                "lead_id": None,
                "created_lead": False,
                "contact_name": customer.get("CustomerName"),
                "mobile": digits,
                "last10": last10,
                "unknown": False,
                "ambiguous": False,
                "match_status": "Linked",
                "match_count": 1,
                "candidates": candidates,
                "suggested_customer_id": cid,
            }

        if len(candidates) > 1:
            return {
                "customer_id": None,
                "lead_id": None,
                "created_lead": False,
                "contact_name": display_name,
                "mobile": digits,
                "last10": last10,
                "unknown": False,
                "ambiguous": True,
                "match_status": "Ambiguous",
                "match_count": len(candidates),
                "candidates": candidates,
                "suggested_customer_id": suggested,
            }

        lead = self.find_open_lead_by_mobile(mobile)
        if lead:
            return {
                "customer_id": int(lead["CustomerID"]) if lead.get("CustomerID") else None,
                "lead_id": int(lead["LeadID"]),
                "created_lead": False,
                "contact_name": lead.get("FullName"),
                "mobile": digits,
                "last10": last10,
                "unknown": False,
                "ambiguous": False,
                "match_status": "Linked",
                "match_count": 0,
                "candidates": [],
                "suggested_customer_id": None,
            }

        if not create_lead_if_missing:
            return {
                "customer_id": None,
                "lead_id": None,
                "created_lead": False,
                "contact_name": display_name,
                "mobile": digits,
                "last10": last10,
                "unknown": True,
                "ambiguous": False,
                "match_status": "Unknown",
                "match_count": 0,
                "candidates": [],
                "suggested_customer_id": None,
            }

        name = (display_name or "").strip() or f"WhatsApp {last10 or digits}"
        result = CrmLeadService().create_lead(
            source=source,
            request_type="WhatsApp",
            full_name=name,
            mobile=digits or None,
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
            "mobile": digits,
            "last10": last10,
            "unknown": False,
            "ambiguous": False,
            "match_status": "Linked",
            "match_count": 0,
            "candidates": [],
            "suggested_customer_id": None,
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
