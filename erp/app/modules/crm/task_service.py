"""CRM task CRUD and completion."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text

from app.extensions import db
from app.modules.shared.audit_service import AuditService
from app.modules.shared.schema import ensure_crm_schema
from app.modules.shared.timeline_service import TimelineService


class CrmTaskService:
    PAGE_SIZE = 50
    VALID_STATUSES = ("Pending", "InProgress", "Completed", "Cancelled")

    def __init__(
        self,
        *,
        timeline: TimelineService | None = None,
        audit: AuditService | None = None,
    ):
        self.timeline = timeline or TimelineService()
        self.audit = audit or AuditService()

    def list_tasks(
        self,
        *,
        status: str | None = None,
        customer_id: int | None = None,
        lead_id: int | None = None,
        assigned_user_id: int | None = None,
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
            params["status"] = status
        if customer_id:
            clauses.append("CustomerID = :customer_id")
            params["customer_id"] = customer_id
        if lead_id:
            clauses.append("LeadID = :lead_id")
            params["lead_id"] = lead_id
        if assigned_user_id:
            clauses.append("AssignedUserID = :assigned_user_id")
            params["assigned_user_id"] = assigned_user_id
        if search:
            clauses.append("(Title LIKE :like OR Description LIKE :like)")
            params["like"] = f"%{search.strip()}%"
        where = " AND ".join(clauses)
        total = db.session.execute(
            text(f"SELECT COUNT(1) FROM dbo.CrmTask WHERE {where}"),
            params,
        ).scalar() or 0
        rows = db.session.execute(
            text(
                f"""
                SELECT TaskID, CustomerID, LeadID, Title, Description, Priority, Status,
                       Progress, Deadline, AssignedUserID, AssignedUserName,
                       CreatedByUserID, CreatedByName, CompletedDate, CreatedDate, ModifiedDate
                FROM dbo.CrmTask
                WHERE {where}
                ORDER BY
                    CASE WHEN Deadline IS NULL THEN 1 ELSE 0 END,
                    Deadline ASC,
                    CreatedDate DESC
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

    def get_task(self, task_id: int) -> dict | None:
        ensure_crm_schema()
        row = db.session.execute(
            text(
                """
                SELECT TaskID, CustomerID, LeadID, Title, Description, Priority, Status,
                       Progress, Deadline, AssignedUserID, AssignedUserName,
                       CreatedByUserID, CreatedByName, CompletedDate, CreatedDate, ModifiedDate
                FROM dbo.CrmTask
                WHERE TaskID = :id AND IsActive = 1
                """
            ),
            {"id": task_id},
        ).mappings().first()
        return dict(row) if row else None

    def create_task(
        self,
        *,
        title: str,
        description: str | None = None,
        customer_id: int | None = None,
        lead_id: int | None = None,
        priority: str = "Normal",
        deadline: datetime | None = None,
        assigned_user_id: int | None = None,
        assigned_user_name: str | None = None,
        user_id: int | None = None,
        user_name: str | None = None,
        conversation_id: int | None = None,
        source: str | None = None,
    ) -> dict:
        ensure_crm_schema()
        title_text = (title or "").strip()
        if not title_text:
            raise ValueError("Task title is required.")

        now = datetime.utcnow()
        row = db.session.execute(
            text(
                """
                INSERT INTO dbo.CrmTask
                    (CustomerID, LeadID, Title, Description, Priority, Status, Progress,
                     Deadline, AssignedUserID, AssignedUserName, CreatedByUserID, CreatedByName, CreatedDate)
                OUTPUT INSERTED.TaskID
                VALUES
                    (:customer_id, :lead_id, :title, :description, :priority, N'Pending', 0,
                     :deadline, :assigned_user_id, :assigned_user_name, :user_id, :user_name, :now)
                """
            ),
            {
                "customer_id": customer_id,
                "lead_id": lead_id,
                "title": title_text[:255],
                "description": description,
                "priority": (priority or "Normal")[:20],
                "deadline": deadline,
                "assigned_user_id": assigned_user_id,
                "assigned_user_name": (assigned_user_name or "")[:150] or None,
                "user_id": user_id,
                "user_name": (user_name or "")[:150] or None,
                "now": now,
            },
        ).first()
        task_id = int(row[0])
        db.session.commit()
        if conversation_id or source:
            try:
                db.session.execute(
                    text(
                        """
                        UPDATE dbo.CrmTask
                        SET ConversationID = COALESCE(:cid, ConversationID),
                            Source = COALESCE(:source, Source)
                        WHERE TaskID = :id
                        """
                    ),
                    {
                        "cid": conversation_id,
                        "source": (source or "")[:50] or None,
                        "id": task_id,
                    },
                )
                db.session.commit()
            except Exception:
                db.session.rollback()

        self.timeline.add_event(
            event_type="TaskCreated",
            title=f"Task: {title_text}",
            description=description,
            customer_id=customer_id,
            lead_id=lead_id,
            entity_type="CrmTask",
            entity_id=task_id,
            user_id=user_id,
            user_name=user_name,
        )
        self.audit.log(
            action_name="TaskCreated",
            entity_type="CrmTask",
            entity_id=task_id,
            new_value={"title": title_text},
            user_id=user_id,
            user_name=user_name,
        )
        return self.get_task(task_id) or {}

    def update_task(
        self,
        task_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        priority: str | None = None,
        status: str | None = None,
        progress: int | None = None,
        deadline: datetime | None = None,
        assigned_user_id: int | None = None,
        assigned_user_name: str | None = None,
        assign_set: bool = False,
        user_id: int | None = None,
        user_name: str | None = None,
    ) -> dict:
        ensure_crm_schema()
        old = self.get_task(task_id)
        if not old:
            raise ValueError("Task not found.")

        sets = ["ModifiedDate = :now"]
        params: dict = {"id": task_id, "now": datetime.utcnow()}
        if title is not None:
            sets.append("Title = :title")
            params["title"] = title[:255]
        if description is not None:
            sets.append("Description = :description")
            params["description"] = description
        if priority is not None:
            sets.append("Priority = :priority")
            params["priority"] = priority[:20]
        if status is not None:
            sets.append("Status = :status")
            params["status"] = status[:30]
        if progress is not None:
            sets.append("Progress = :progress")
            params["progress"] = max(0, min(100, int(progress)))
        if deadline is not None:
            sets.append("Deadline = :deadline")
            params["deadline"] = deadline
        if assign_set:
            sets.append("AssignedUserID = :assigned_user_id")
            sets.append("AssignedUserName = :assigned_user_name")
            params["assigned_user_id"] = assigned_user_id
            params["assigned_user_name"] = (assigned_user_name or "")[:150] or None

        db.session.execute(
            text(f"UPDATE dbo.CrmTask SET {', '.join(sets)} WHERE TaskID = :id"),
            params,
        )
        db.session.commit()

        updated = self.get_task(task_id)
        self.audit.log(
            action_name="TaskUpdated",
            entity_type="CrmTask",
            entity_id=task_id,
            old_value=old,
            new_value=updated,
            user_id=user_id,
            user_name=user_name,
        )
        return updated or {}

    def complete_task(
        self,
        task_id: int,
        *,
        user_id: int | None = None,
        user_name: str | None = None,
    ) -> dict:
        ensure_crm_schema()
        old = self.get_task(task_id)
        if not old:
            raise ValueError("Task not found.")

        now = datetime.utcnow()
        db.session.execute(
            text(
                """
                UPDATE dbo.CrmTask
                SET Status = N'Completed', Progress = 100, CompletedDate = :now, ModifiedDate = :now
                WHERE TaskID = :id
                """
            ),
            {"id": task_id, "now": now},
        )
        db.session.commit()

        self.timeline.add_event(
            event_type="TaskCompleted",
            title=f"Task completed: {old.get('Title')}",
            customer_id=old.get("CustomerID"),
            lead_id=old.get("LeadID"),
            entity_type="CrmTask",
            entity_id=task_id,
            user_id=user_id,
            user_name=user_name,
        )
        self.audit.log(
            action_name="TaskCompleted",
            entity_type="CrmTask",
            entity_id=task_id,
            old_value=old,
            user_id=user_id,
            user_name=user_name,
        )
        return self.get_task(task_id) or {}

    def delete_task(
        self,
        task_id: int,
        *,
        user_id: int | None = None,
        user_name: str | None = None,
    ) -> None:
        ensure_crm_schema()
        old = self.get_task(task_id)
        if not old:
            raise ValueError("Task not found.")

        db.session.execute(
            text(
                """
                UPDATE dbo.CrmTask
                SET IsActive = 0, ModifiedDate = :now
                WHERE TaskID = :id
                """
            ),
            {"id": task_id, "now": datetime.utcnow()},
        )
        db.session.commit()
        self.audit.log(
            action_name="TaskDeleted",
            entity_type="CrmTask",
            entity_id=task_id,
            old_value=old,
            user_id=user_id,
            user_name=user_name,
        )
