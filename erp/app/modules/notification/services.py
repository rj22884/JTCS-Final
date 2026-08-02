"""Notification create / read / archive APIs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text

from app.extensions import db
from app.modules.shared.schema import ensure_crm_schema


NOTIFICATION_TYPES = (
    "Website",
    "WhatsApp",
    "Email",
    "Task",
    "Reminder",
    "GST",
    "TDS",
    "ITR",
    "Payment",
    "Document",
    "Internal",
)


class NotificationService:
    def create(
        self,
        *,
        notification_type: str,
        title: str,
        message: str | None = None,
        user_id: int | None = None,
        link_url: str | None = None,
        priority: str = "Normal",
        customer_id: int | None = None,
        lead_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
    ) -> int:
        ensure_crm_schema()
        ntype = notification_type if notification_type in NOTIFICATION_TYPES else "Internal"
        row = db.session.execute(
            text(
                """
                INSERT INTO dbo.Notification
                    (UserID, NotificationType, Title, Message, LinkURL, Priority,
                     CustomerID, LeadID, EntityType, EntityID)
                OUTPUT INSERTED.NotificationID
                VALUES
                    (:user_id, :ntype, :title, :message, :link_url, :priority,
                     :customer_id, :lead_id, :entity_type, :entity_id)
                """
            ),
            {
                "user_id": user_id,
                "ntype": ntype,
                "title": (title or "Notification")[:255],
                "message": message,
                "link_url": (link_url or "")[:500] or None,
                "priority": (priority or "Normal")[:20],
                "customer_id": customer_id,
                "lead_id": lead_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
            },
        ).first()
        db.session.commit()
        return int(row[0]) if row else 0

    def notify_roles_or_all(
        self,
        *,
        notification_type: str,
        title: str,
        message: str | None = None,
        link_url: str | None = None,
        priority: str = "Normal",
        customer_id: int | None = None,
        lead_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
    ) -> int:
        """Broadcast to active users (Reception/Manager/Admin) or create unassigned row."""
        ensure_crm_schema()
        users = db.session.execute(
            text(
                """
                SELECT UserID FROM dbo.Users
                WHERE UserStatus = N'Active'
                  AND (
                    Role LIKE N'%Administrator%'
                    OR Role LIKE N'%Admin%'
                    OR Role LIKE N'%Manager%'
                    OR Role LIKE N'%Reception%'
                    OR Role LIKE N'%Operator%'
                  )
                """
            )
        ).scalars().all()
        count = 0
        if not users:
            self.create(
                notification_type=notification_type,
                title=title,
                message=message,
                link_url=link_url,
                priority=priority,
                customer_id=customer_id,
                lead_id=lead_id,
                entity_type=entity_type,
                entity_id=entity_id,
            )
            return 1
        for uid in users:
            self.create(
                notification_type=notification_type,
                title=title,
                message=message,
                user_id=int(uid),
                link_url=link_url,
                priority=priority,
                customer_id=customer_id,
                lead_id=lead_id,
                entity_type=entity_type,
                entity_id=entity_id,
            )
            count += 1
        return count

    def unread_count(self, user_id: int | None) -> int:
        ensure_crm_schema()
        if not user_id:
            return 0
        return int(
            db.session.execute(
                text(
                    """
                    SELECT COUNT(1) FROM dbo.Notification
                    WHERE UserID = :uid AND IsRead = 0 AND IsArchived = 0
                    """
                ),
                {"uid": user_id},
            ).scalar()
            or 0
        )

    def list_for_user(
        self,
        user_id: int | None,
        *,
        include_archived: bool = False,
        unread_only: bool = False,
        page: int = 1,
        page_size: int = 30,
    ) -> dict:
        ensure_crm_schema()
        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        offset = (page - 1) * page_size
        clauses = ["(UserID = :uid OR UserID IS NULL)"]
        params: dict = {"uid": user_id, "limit": page_size, "offset": offset}
        if not include_archived:
            clauses.append("IsArchived = 0")
        if unread_only:
            clauses.append("IsRead = 0")
        where = " AND ".join(clauses)
        total = db.session.execute(
            text(f"SELECT COUNT(1) FROM dbo.Notification WHERE {where}"),
            params,
        ).scalar() or 0
        rows = db.session.execute(
            text(
                f"""
                SELECT NotificationID, UserID, NotificationType, Title, Message, LinkURL,
                       Priority, IsRead, IsArchived, CustomerID, LeadID, EntityType, EntityID,
                       CreatedDate, ReadDate
                FROM dbo.Notification
                WHERE {where}
                ORDER BY CreatedDate DESC, NotificationID DESC
                OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
                """
            ),
            params,
        ).mappings().all()
        return {
            "total": int(total),
            "page": page,
            "page_size": page_size,
            "unread_count": self.unread_count(user_id),
            "rows": [dict(r) for r in rows],
        }

    def mark_read(self, notification_id: int, user_id: int | None) -> None:
        ensure_crm_schema()
        db.session.execute(
            text(
                """
                UPDATE dbo.Notification
                SET IsRead = 1, ReadDate = :now
                WHERE NotificationID = :id
                  AND (UserID = :uid OR UserID IS NULL)
                """
            ),
            {"id": notification_id, "uid": user_id, "now": datetime.utcnow()},
        )
        db.session.commit()

    def mark_all_read(self, user_id: int | None) -> None:
        ensure_crm_schema()
        db.session.execute(
            text(
                """
                UPDATE dbo.Notification
                SET IsRead = 1, ReadDate = :now
                WHERE IsRead = 0 AND IsArchived = 0
                  AND (UserID = :uid OR UserID IS NULL)
                """
            ),
            {"uid": user_id, "now": datetime.utcnow()},
        )
        db.session.commit()

    def archive(self, notification_id: int, user_id: int | None) -> None:
        ensure_crm_schema()
        db.session.execute(
            text(
                """
                UPDATE dbo.Notification
                SET IsArchived = 1, IsRead = 1, ReadDate = COALESCE(ReadDate, :now)
                WHERE NotificationID = :id
                  AND (UserID = :uid OR UserID IS NULL)
                """
            ),
            {"id": notification_id, "uid": user_id, "now": datetime.utcnow()},
        )
        db.session.commit()
