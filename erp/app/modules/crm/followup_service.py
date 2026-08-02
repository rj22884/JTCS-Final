"""CRM follow-up scheduling and completion."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text

from app.extensions import db
from app.modules.notification.services import NotificationService
from app.modules.shared.audit_service import AuditService
from app.modules.shared.schema import ensure_crm_schema
from app.modules.shared.timeline_service import TimelineService


class CrmFollowUpService:
    PAGE_SIZE = 50
    FOLLOWUP_TYPES = ("Phone Call", "WhatsApp", "Email", "Meeting", "Reminder")

    def __init__(
        self,
        *,
        notifications: NotificationService | None = None,
        timeline: TimelineService | None = None,
        audit: AuditService | None = None,
    ):
        self.notifications = notifications or NotificationService()
        self.timeline = timeline or TimelineService()
        self.audit = audit or AuditService()

    def list_followups(
        self,
        *,
        status: str | None = None,
        followup_type: str | None = None,
        customer_id: int | None = None,
        lead_id: int | None = None,
        assigned_user_id: int | None = None,
        due_before: datetime | None = None,
        page: int = 1,
    ) -> dict:
        ensure_crm_schema()
        page = max(1, page)
        offset = (page - 1) * self.PAGE_SIZE
        clauses = ["IsActive = 1"]
        params: dict = {"limit": self.PAGE_SIZE, "offset": offset}
        if status:
            clauses.append("Status = :status")
            params["status"] = status
        if followup_type:
            clauses.append("FollowUpType = :followup_type")
            params["followup_type"] = followup_type
        if customer_id:
            clauses.append("CustomerID = :customer_id")
            params["customer_id"] = customer_id
        if lead_id:
            clauses.append("LeadID = :lead_id")
            params["lead_id"] = lead_id
        if assigned_user_id:
            clauses.append("AssignedUserID = :assigned_user_id")
            params["assigned_user_id"] = assigned_user_id
        if due_before:
            clauses.append("DueAt <= :due_before")
            params["due_before"] = due_before
        where = " AND ".join(clauses)
        total = db.session.execute(
            text(f"SELECT COUNT(1) FROM dbo.CrmFollowUp WHERE {where}"),
            params,
        ).scalar() or 0
        rows = db.session.execute(
            text(
                f"""
                SELECT FollowUpID, CustomerID, LeadID, FollowUpType, Subject, Notes, DueAt,
                       Status, Priority, AssignedUserID, AssignedUserName, CompletedDate,
                       CreatedByUserID, CreatedByName, CreatedDate, ModifiedDate
                FROM dbo.CrmFollowUp
                WHERE {where}
                ORDER BY DueAt ASC, FollowUpID DESC
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

    def get_followup(self, followup_id: int) -> dict | None:
        ensure_crm_schema()
        row = db.session.execute(
            text(
                """
                SELECT FollowUpID, CustomerID, LeadID, FollowUpType, Subject, Notes, DueAt,
                       Status, Priority, AssignedUserID, AssignedUserName, CompletedDate,
                       CreatedByUserID, CreatedByName, CreatedDate, ModifiedDate
                FROM dbo.CrmFollowUp
                WHERE FollowUpID = :id AND IsActive = 1
                """
            ),
            {"id": followup_id},
        ).mappings().first()
        return dict(row) if row else None

    def create_followup(
        self,
        *,
        followup_type: str,
        due_at: datetime,
        subject: str | None = None,
        notes: str | None = None,
        customer_id: int | None = None,
        lead_id: int | None = None,
        priority: str = "Normal",
        assigned_user_id: int | None = None,
        assigned_user_name: str | None = None,
        user_id: int | None = None,
        user_name: str | None = None,
    ) -> dict:
        ensure_crm_schema()
        ftype = (followup_type or "").strip()
        if ftype not in self.FOLLOWUP_TYPES:
            raise ValueError(f"Follow-up type must be one of: {', '.join(self.FOLLOWUP_TYPES)}")

        now = datetime.utcnow()
        row = db.session.execute(
            text(
                """
                INSERT INTO dbo.CrmFollowUp
                    (CustomerID, LeadID, FollowUpType, Subject, Notes, DueAt, Status, Priority,
                     AssignedUserID, AssignedUserName, CreatedByUserID, CreatedByName, CreatedDate)
                OUTPUT INSERTED.FollowUpID
                VALUES
                    (:customer_id, :lead_id, :followup_type, :subject, :notes, :due_at, N'Pending', :priority,
                     :assigned_user_id, :assigned_user_name, :user_id, :user_name, :now)
                """
            ),
            {
                "customer_id": customer_id,
                "lead_id": lead_id,
                "followup_type": ftype[:30],
                "subject": (subject or ftype)[:255],
                "notes": notes,
                "due_at": due_at,
                "priority": (priority or "Normal")[:20],
                "assigned_user_id": assigned_user_id,
                "assigned_user_name": (assigned_user_name or "")[:150] or None,
                "user_id": user_id,
                "user_name": (user_name or "")[:150] or None,
                "now": now,
            },
        ).first()
        followup_id = int(row[0])

        self.timeline.add_event(
            event_type="FollowUpScheduled",
            title=f"Follow-up: {ftype}",
            description=subject or notes,
            customer_id=customer_id,
            lead_id=lead_id,
            entity_type="CrmFollowUp",
            entity_id=followup_id,
            user_id=user_id,
            user_name=user_name,
        )

        notify_user = assigned_user_id or user_id
        self.notifications.create(
            notification_type="Reminder",
            title=f"Follow-up scheduled: {subject or ftype}",
            message=notes,
            user_id=notify_user,
            link_url=f"/crm/followups/{followup_id}",
            priority=priority,
            customer_id=customer_id,
            lead_id=lead_id,
            entity_type="CrmFollowUp",
            entity_id=followup_id,
        )

        self.audit.log(
            action_name="FollowUpCreated",
            entity_type="CrmFollowUp",
            entity_id=followup_id,
            new_value={"followup_type": ftype, "due_at": due_at.isoformat()},
            user_id=user_id,
            user_name=user_name,
        )
        return self.get_followup(followup_id) or {}

    def update_followup(
        self,
        followup_id: int,
        *,
        followup_type: str | None = None,
        subject: str | None = None,
        notes: str | None = None,
        due_at: datetime | None = None,
        status: str | None = None,
        priority: str | None = None,
        assigned_user_id: int | None = None,
        assigned_user_name: str | None = None,
        assign_set: bool = False,
        user_id: int | None = None,
        user_name: str | None = None,
    ) -> dict:
        ensure_crm_schema()
        old = self.get_followup(followup_id)
        if not old:
            raise ValueError("Follow-up not found.")

        sets = ["ModifiedDate = :now"]
        params: dict = {"id": followup_id, "now": datetime.utcnow()}
        if followup_type is not None:
            if followup_type not in self.FOLLOWUP_TYPES:
                raise ValueError(f"Follow-up type must be one of: {', '.join(self.FOLLOWUP_TYPES)}")
            sets.append("FollowUpType = :followup_type")
            params["followup_type"] = followup_type[:30]
        if subject is not None:
            sets.append("Subject = :subject")
            params["subject"] = subject[:255]
        if notes is not None:
            sets.append("Notes = :notes")
            params["notes"] = notes
        if due_at is not None:
            sets.append("DueAt = :due_at")
            params["due_at"] = due_at
        if status is not None:
            sets.append("Status = :status")
            params["status"] = status[:30]
        if priority is not None:
            sets.append("Priority = :priority")
            params["priority"] = priority[:20]
        if assign_set:
            sets.append("AssignedUserID = :assigned_user_id")
            sets.append("AssignedUserName = :assigned_user_name")
            params["assigned_user_id"] = assigned_user_id
            params["assigned_user_name"] = (assigned_user_name or "")[:150] or None

        db.session.execute(
            text(f"UPDATE dbo.CrmFollowUp SET {', '.join(sets)} WHERE FollowUpID = :id"),
            params,
        )
        db.session.commit()

        updated = self.get_followup(followup_id)
        self.audit.log(
            action_name="FollowUpUpdated",
            entity_type="CrmFollowUp",
            entity_id=followup_id,
            old_value=old,
            new_value=updated,
            user_id=user_id,
            user_name=user_name,
        )
        return updated or {}

    def complete_followup(
        self,
        followup_id: int,
        *,
        user_id: int | None = None,
        user_name: str | None = None,
    ) -> dict:
        ensure_crm_schema()
        old = self.get_followup(followup_id)
        if not old:
            raise ValueError("Follow-up not found.")

        now = datetime.utcnow()
        db.session.execute(
            text(
                """
                UPDATE dbo.CrmFollowUp
                SET Status = N'Completed', CompletedDate = :now, ModifiedDate = :now
                WHERE FollowUpID = :id
                """
            ),
            {"id": followup_id, "now": now},
        )
        db.session.commit()

        self.timeline.add_event(
            event_type="FollowUpCompleted",
            title=f"Follow-up completed: {old.get('FollowUpType')}",
            description=old.get("Subject"),
            customer_id=old.get("CustomerID"),
            lead_id=old.get("LeadID"),
            entity_type="CrmFollowUp",
            entity_id=followup_id,
            user_id=user_id,
            user_name=user_name,
        )
        self.audit.log(
            action_name="FollowUpCompleted",
            entity_type="CrmFollowUp",
            entity_id=followup_id,
            old_value=old,
            user_id=user_id,
            user_name=user_name,
        )
        return self.get_followup(followup_id) or {}

    def delete_followup(
        self,
        followup_id: int,
        *,
        user_id: int | None = None,
        user_name: str | None = None,
    ) -> None:
        ensure_crm_schema()
        old = self.get_followup(followup_id)
        if not old:
            raise ValueError("Follow-up not found.")

        db.session.execute(
            text(
                """
                UPDATE dbo.CrmFollowUp
                SET IsActive = 0, ModifiedDate = :now
                WHERE FollowUpID = :id
                """
            ),
            {"id": followup_id, "now": datetime.utcnow()},
        )
        db.session.commit()
        self.audit.log(
            action_name="FollowUpDeleted",
            entity_type="CrmFollowUp",
            entity_id=followup_id,
            old_value=old,
            user_id=user_id,
            user_name=user_name,
        )
