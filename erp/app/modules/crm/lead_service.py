"""CRM lead lifecycle — intake, assignment, conversion."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text

from app.extensions import db
from app.modules.communication.services import CommunicationService
from app.modules.notification.services import NotificationService
from app.modules.shared.audit_service import AuditService
from app.modules.shared.schema import ensure_crm_schema
from app.modules.shared.timeline_service import TimelineService
from app.repositories.customer_repository import CustomerRepository
from app.services.customer_group_service import CustomerGroupService
from app.services.customer_master_service import CustomerMasterService


class CrmLeadService:
    PAGE_SIZE = 40

    def __init__(
        self,
        *,
        customer_repo: CustomerRepository | None = None,
        customer_service: CustomerMasterService | None = None,
        communication: CommunicationService | None = None,
        notifications: NotificationService | None = None,
        timeline: TimelineService | None = None,
        audit: AuditService | None = None,
    ):
        self.customer_repo = customer_repo or CustomerRepository()
        self.customer_service = customer_service or CustomerMasterService()
        self.communication = communication or CommunicationService()
        self.notifications = notifications or NotificationService()
        self.timeline = timeline or TimelineService()
        self.audit = audit or AuditService()

    def list_leads(
        self,
        *,
        status: str | None = None,
        search: str | None = None,
        page: int = 1,
    ) -> dict:
        ensure_crm_schema()
        page = max(1, page)
        offset = (page - 1) * self.PAGE_SIZE
        clauses = ["IsActive = 1"]
        params: dict = {"limit": self.PAGE_SIZE, "offset": offset}
        if status:
            clauses.append("Status = :status")
            params["status"] = status.strip()
        if search:
            needle = search.strip()
            clauses.append(
                "(FullName LIKE :like OR Mobile LIKE :like OR Email LIKE :like "
                "OR BusinessName LIKE :like OR CAST(LeadID AS NVARCHAR(20)) = :exact)"
            )
            params["like"] = f"%{needle}%"
            params["exact"] = needle
        where = " AND ".join(clauses)
        total = db.session.execute(
            text(f"SELECT COUNT(1) FROM dbo.CrmLead WHERE {where}"),
            params,
        ).scalar() or 0
        rows = db.session.execute(
            text(
                f"""
                SELECT LeadID, Source, RequestType, FullName, Mobile, Email, BusinessName,
                       Message, Status, Priority, AssignedUserID, CustomerID, IdempotencyKey,
                       CreatedDate, ModifiedDate
                FROM dbo.CrmLead
                WHERE {where}
                ORDER BY CreatedDate DESC, LeadID DESC
                OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
                """
            ),
            params,
        ).mappings().all()
        return {
            "total": int(total),
            "page": page,
            "page_size": self.PAGE_SIZE,
            "rows": [dict(r) for r in rows],
        }

    def get_lead(self, lead_id: int) -> dict | None:
        ensure_crm_schema()
        row = db.session.execute(
            text(
                """
                SELECT LeadID, Source, RequestType, FullName, Mobile, Email, BusinessName,
                       Message, Status, Priority, AssignedUserID, CustomerID, IdempotencyKey,
                       CreatedDate, ModifiedDate
                FROM dbo.CrmLead
                WHERE LeadID = :id AND IsActive = 1
                """
            ),
            {"id": lead_id},
        ).mappings().first()
        return dict(row) if row else None

    def create_lead(
        self,
        *,
        source: str,
        request_type: str,
        full_name: str,
        mobile: str | None = None,
        email: str | None = None,
        business_name: str | None = None,
        message: str | None = None,
        priority: str = "Normal",
        idempotency_key: str | None = None,
        user_id: int | None = None,
        user_name: str | None = None,
    ) -> dict:
        ensure_crm_schema()
        name = (full_name or "").strip()
        if not name:
            raise ValueError("Full name is required.")

        if idempotency_key:
            existing = db.session.execute(
                text(
                    """
                    SELECT TOP 1 LeadID FROM dbo.CrmLead
                    WHERE IdempotencyKey = :key AND IsActive = 1
                    """
                ),
                {"key": idempotency_key[:100]},
            ).scalar()
            if existing:
                lead = self.get_lead(int(existing))
                if lead:
                    return {"lead_id": int(existing), "duplicate": True, "lead": lead}

        now = datetime.utcnow()
        row = db.session.execute(
            text(
                """
                INSERT INTO dbo.CrmLead
                    (Source, RequestType, FullName, Mobile, Email, BusinessName, Message,
                     Status, Priority, IdempotencyKey, CreatedDate)
                OUTPUT INSERTED.LeadID
                VALUES
                    (:source, :request_type, :full_name, :mobile, :email, :business_name, :message,
                     N'New', :priority, :idempotency_key, :now)
                """
            ),
            {
                "source": (source or "Website")[:50],
                "request_type": (request_type or "Contact")[:50],
                "full_name": name[:255],
                "mobile": (mobile or "")[:20] or None,
                "email": (email or "")[:255] or None,
                "business_name": (business_name or "")[:255] or None,
                "message": message,
                "priority": (priority or "Normal")[:20],
                "idempotency_key": (idempotency_key or "")[:100] or None,
                "now": now,
            },
        ).first()
        lead_id = int(row[0])

        self.communication.open_conversation(
            channel=source or "Website",
            subject=f"{request_type}: {name}",
            lead_id=lead_id,
            priority=priority,
            initial_body=message,
            direction="Inbound",
            user_id=user_id,
            user_name=user_name,
        )

        self.notifications.notify_roles_or_all(
            notification_type="Website",
            title=f"New lead: {name}",
            message=message,
            link_url=f"/crm/leads/{lead_id}",
            priority=priority,
            lead_id=lead_id,
            entity_type="CrmLead",
            entity_id=lead_id,
        )

        self.timeline.add_event(
            event_type="LeadCreated",
            title=f"Lead created: {name}",
            description=message,
            lead_id=lead_id,
            entity_type="CrmLead",
            entity_id=lead_id,
            user_id=user_id,
            user_name=user_name,
        )

        self.audit.log(
            action_name="LeadCreated",
            entity_type="CrmLead",
            entity_id=lead_id,
            new_value={"source": source, "request_type": request_type, "full_name": name},
            user_id=user_id,
            user_name=user_name,
        )

        return {"lead_id": lead_id, "duplicate": False, "lead": self.get_lead(lead_id)}

    def update_lead(
        self,
        lead_id: int,
        *,
        status: str | None = None,
        priority: str | None = None,
        full_name: str | None = None,
        mobile: str | None = None,
        email: str | None = None,
        business_name: str | None = None,
        message: str | None = None,
        user_id: int | None = None,
        user_name: str | None = None,
    ) -> dict:
        ensure_crm_schema()
        old = self.get_lead(lead_id)
        if not old:
            raise ValueError("Lead not found.")

        sets = ["ModifiedDate = :now"]
        params: dict = {"id": lead_id, "now": datetime.utcnow()}
        field_map = {
            "status": status,
            "priority": priority,
            "full_name": full_name,
            "mobile": mobile,
            "email": email,
            "business_name": business_name,
            "message": message,
        }
        col_map = {
            "status": "Status",
            "priority": "Priority",
            "full_name": "FullName",
            "mobile": "Mobile",
            "email": "Email",
            "business_name": "BusinessName",
            "message": "Message",
        }
        for key, value in field_map.items():
            if value is not None:
                sets.append(f"{col_map[key]} = :{key}")
                params[key] = value

        db.session.execute(
            text(f"UPDATE dbo.CrmLead SET {', '.join(sets)} WHERE LeadID = :id"),
            params,
        )
        db.session.commit()

        updated = self.get_lead(lead_id)
        self.audit.log(
            action_name="LeadUpdated",
            entity_type="CrmLead",
            entity_id=lead_id,
            old_value=old,
            new_value=updated,
            user_id=user_id,
            user_name=user_name,
        )
        return updated or {}

    def assign_lead(
        self,
        lead_id: int,
        *,
        assigned_user_id: int | None,
        assigned_user_name: str | None = None,
        user_id: int | None = None,
        user_name: str | None = None,
    ) -> dict:
        ensure_crm_schema()
        old = self.get_lead(lead_id)
        if not old:
            raise ValueError("Lead not found.")

        db.session.execute(
            text(
                """
                UPDATE dbo.CrmLead
                SET AssignedUserID = :assigned, ModifiedDate = :now,
                    Status = CASE WHEN Status = N'New' THEN N'Assigned' ELSE Status END
                WHERE LeadID = :id
                """
            ),
            {"id": lead_id, "assigned": assigned_user_id, "now": datetime.utcnow()},
        )
        db.session.commit()

        self.timeline.add_event(
            event_type="LeadAssigned",
            title="Lead assigned",
            description=assigned_user_name,
            lead_id=lead_id,
            entity_type="CrmLead",
            entity_id=lead_id,
            user_id=user_id,
            user_name=user_name,
        )
        self.audit.log(
            action_name="LeadAssigned",
            entity_type="CrmLead",
            entity_id=lead_id,
            old_value={"assigned_user_id": old.get("AssignedUserID")},
            new_value={"assigned_user_id": assigned_user_id},
            user_id=user_id,
            user_name=user_name,
        )
        return self.get_lead(lead_id) or {}

    def _find_by_email(self, email: str) -> dict | None:
        needle = (email or "").strip().lower()
        if not needle or "@" not in needle:
            return None
        row = db.session.execute(
            text(
                """
                SELECT TOP 1 CustomerID, CustomerName, MobileNumber, PANNumber, EmailID, CustomerGroup
                FROM dbo.CustomerMaster
                WHERE LOWER(LTRIM(RTRIM(EmailID))) = :email
                  AND CustomerStatus <> N'Inactive'
                """
            ),
            {"email": needle},
        ).mappings().first()
        if not row:
            return None
        return {
            "customer_id": row["CustomerID"],
            "customer_name": row.get("CustomerName") or "",
            "mobile_number": row.get("MobileNumber") or "",
            "pan_number": row.get("PANNumber") or "",
            "email_id": row.get("EmailID") or "",
            "customer_group": row.get("CustomerGroup") or "",
        }

    def _resolve_customer_group(self) -> str:
        active = {g["code"] for g in CustomerGroupService().list_active_groups()}
        if "ITR" in active:
            return "ITR"
        if "CRM" in active:
            return "CRM"
        if active:
            return sorted(active)[0]
        return "ITR"

    def convert_to_customer(
        self,
        lead_id: int,
        *,
        pan: str | None = None,
        user_id: int | None = None,
        user_name: str | None = None,
    ) -> dict:
        ensure_crm_schema()
        lead = self.get_lead(lead_id)
        if not lead:
            raise ValueError("Lead not found.")

        if lead.get("CustomerID"):
            return {
                "customer_id": int(lead["CustomerID"]),
                "linked": True,
                "created": False,
                "lead": lead,
            }

        existing_id: int | None = None
        normalized_pan = self.customer_repo._normalize_pan(pan)
        if normalized_pan and not self.customer_repo.is_placeholder_pan(normalized_pan):
            match = self.customer_repo.find_by_pan(normalized_pan)
            if match:
                existing_id = int(match["customer_id"])

        if not existing_id and lead.get("Mobile"):
            mobile_matches = self.customer_repo.find_by_mobile(lead["Mobile"])
            if mobile_matches:
                existing_id = int(mobile_matches[0]["customer_id"])

        if not existing_id and lead.get("Email"):
            match = self._find_by_email(lead["Email"])
            if match:
                existing_id = int(match["customer_id"])

        now = datetime.utcnow()
        created = False

        if existing_id:
            customer_id = existing_id
        else:
            self.customer_repo.ensure_schema()
            mobile = self.customer_repo._normalize_mobile(lead.get("Mobile"))
            payload = {
                "customer_group": self._resolve_customer_group(),
                "customer_type": "Individual",
                "customer_name": (lead.get("FullName") or "").strip(),
                "mobile_number": mobile or None,
                "email_id": (lead.get("Email") or "").strip() or None,
                "company_firm_name": (lead.get("BusinessName") or "").strip() or None,
                "pan_number": normalized_pan or CustomerRepository.PLACEHOLDER_PAN,
                "customer_status": "Active",
            }
            if not payload["customer_name"]:
                raise ValueError("Lead full name is required to create a customer.")
            record = self.customer_repo.save_full(payload)
            customer_id = int(record["customer_id"])
            created = True

        db.session.execute(
            text(
                """
                UPDATE dbo.CrmLead
                SET CustomerID = :cid, Status = N'Converted', ModifiedDate = :now
                WHERE LeadID = :id
                """
            ),
            {"cid": customer_id, "now": now, "id": lead_id},
        )
        db.session.commit()

        self.timeline.add_event(
            event_type="LeadConverted",
            title="Lead converted to customer",
            description=lead.get("FullName"),
            customer_id=customer_id,
            lead_id=lead_id,
            entity_type="CustomerMaster",
            entity_id=customer_id,
            user_id=user_id,
            user_name=user_name,
        )
        self.audit.log(
            action_name="LeadConverted",
            entity_type="CrmLead",
            entity_id=lead_id,
            new_value={"customer_id": customer_id, "created": created},
            user_id=user_id,
            user_name=user_name,
        )

        return {
            "customer_id": customer_id,
            "linked": not created,
            "created": created,
            "lead": self.get_lead(lead_id),
        }

    def dashboard_stats(self) -> dict:
        ensure_crm_schema()
        today = datetime.utcnow().date()
        today_count = db.session.execute(
            text(
                """
                SELECT COUNT(1) FROM dbo.CrmLead
                WHERE IsActive = 1 AND CAST(CreatedDate AS DATE) = :today
                """
            ),
            {"today": today},
        ).scalar() or 0
        open_count = db.session.execute(
            text(
                """
                SELECT COUNT(1) FROM dbo.CrmLead
                WHERE IsActive = 1 AND Status NOT IN (N'Converted', N'Closed', N'Lost')
                """
            ),
        ).scalar() or 0
        converted_count = db.session.execute(
            text(
                """
                SELECT COUNT(1) FROM dbo.CrmLead
                WHERE IsActive = 1 AND Status = N'Converted'
                """
            ),
        ).scalar() or 0
        return {
            "today_leads": int(today_count),
            "open_leads": int(open_count),
            "converted": int(converted_count),
        }
