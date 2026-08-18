"""Append-only CRM timeline writer."""

from __future__ import annotations

from sqlalchemy import text

from app.extensions import db
from app.modules.shared.schema import ensure_crm_schema


class TimelineService:
    def add_event(
        self,
        *,
        event_type: str,
        title: str,
        description: str | None = None,
        customer_id: int | None = None,
        lead_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        user_id: int | None = None,
        user_name: str | None = None,
    ) -> int:
        ensure_crm_schema()
        row = db.session.execute(
            text(
                """
                INSERT INTO dbo.CrmTimelineEvent
                    (CustomerID, LeadID, EventType, Title, Description, EntityType, EntityID,
                     CreatedByUserID, CreatedByName)
                OUTPUT INSERTED.EventID
                VALUES
                    (:customer_id, :lead_id, :event_type, :title, :description, :entity_type, :entity_id,
                     :user_id, :user_name)
                """
            ),
            {
                "customer_id": customer_id,
                "lead_id": lead_id,
                "event_type": (event_type or "Activity")[:50],
                "title": (title or "Event")[:255],
                "description": description,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "user_id": user_id,
                "user_name": (user_name or "")[:150] or None,
            },
        ).first()
        db.session.commit()
        return int(row[0]) if row else 0

    def reassign_conversation(
        self,
        conversation_id: int,
        *,
        customer_id: int | None,
        lead_id: int | None = None,
    ) -> None:
        """Move this conversation's timeline events to the selected customer only."""
        ensure_crm_schema()
        db.session.execute(
            text(
                """
                UPDATE dbo.CrmTimelineEvent
                SET CustomerID = :cid, LeadID = :lid
                WHERE EntityType = N'CrmConversation' AND EntityID = :conv
                """
            ),
            {"cid": customer_id, "lid": lead_id, "conv": int(conversation_id)},
        )
        db.session.execute(
            text(
                """
                UPDATE t
                SET t.CustomerID = :cid, t.LeadID = :lid
                FROM dbo.CrmTimelineEvent t
                INNER JOIN dbo.CrmMessage m ON m.MessageID = t.EntityID
                WHERE t.EntityType = N'CrmMessage'
                  AND m.ConversationID = :conv
                """
            ),
            {"cid": customer_id, "lid": lead_id, "conv": int(conversation_id)},
        )
        db.session.commit()

    def list_events(
        self,
        *,
        customer_id: int | None = None,
        lead_id: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        ensure_crm_schema()
        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        offset = (page - 1) * page_size
        clauses = ["1=1"]
        params: dict = {"limit": page_size, "offset": offset}
        if customer_id:
            clauses.append("CustomerID = :customer_id")
            params["customer_id"] = customer_id
        if lead_id:
            clauses.append("LeadID = :lead_id")
            params["lead_id"] = lead_id
        where = " AND ".join(clauses)
        total = db.session.execute(
            text(f"SELECT COUNT(1) FROM dbo.CrmTimelineEvent WHERE {where}"),
            params,
        ).scalar() or 0
        rows = db.session.execute(
            text(
                f"""
                SELECT EventID, CustomerID, LeadID, EventType, Title, Description,
                       EntityType, EntityID, CreatedByUserID, CreatedByName, CreatedDate
                FROM dbo.CrmTimelineEvent
                WHERE {where}
                ORDER BY CreatedDate DESC, EventID DESC
                OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
                """
            ),
            params,
        ).mappings().all()
        return {
            "total": int(total),
            "page": page,
            "page_size": page_size,
            "rows": [dict(r) for r in rows],
        }
