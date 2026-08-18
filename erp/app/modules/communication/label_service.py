"""Conversation labels for Communication Center."""

from __future__ import annotations

from sqlalchemy import text

from app.extensions import db
from app.modules.shared.schema import ensure_crm_schema


class LabelService:
    def list_labels(self) -> list[dict]:
        ensure_crm_schema()
        rows = db.session.execute(
            text(
                """
                SELECT LabelID, LabelName, Color
                FROM dbo.CrmLabel
                WHERE IsActive = 1
                ORDER BY LabelName
                """
            )
        ).mappings().all()
        return [dict(r) for r in rows]

    def conversation_labels(self, conversation_id: int) -> list[dict]:
        ensure_crm_schema()
        rows = db.session.execute(
            text(
                """
                SELECT l.LabelID, l.LabelName, l.Color
                FROM dbo.CrmConversationLabel cl
                INNER JOIN dbo.CrmLabel l ON l.LabelID = cl.LabelID
                WHERE cl.ConversationID = :cid AND l.IsActive = 1
                ORDER BY l.LabelName
                """
            ),
            {"cid": conversation_id},
        ).mappings().all()
        return [dict(r) for r in rows]

    def set_labels(self, conversation_id: int, label_ids: list[int]) -> list[dict]:
        ensure_crm_schema()
        db.session.execute(
            text("DELETE FROM dbo.CrmConversationLabel WHERE ConversationID = :cid"),
            {"cid": conversation_id},
        )
        for lid in {int(x) for x in (label_ids or []) if x}:
            db.session.execute(
                text(
                    """
                    INSERT INTO dbo.CrmConversationLabel (ConversationID, LabelID)
                    VALUES (:cid, :lid)
                    """
                ),
                {"cid": conversation_id, "lid": lid},
            )
        db.session.commit()
        return self.conversation_labels(conversation_id)
