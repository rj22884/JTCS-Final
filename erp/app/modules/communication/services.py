"""Conversation and message services for Communication Center."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text

from app.extensions import db
from app.modules.shared.schema import ensure_crm_schema
from app.modules.shared.timeline_service import TimelineService


class CommunicationService:
    def open_conversation(
        self,
        *,
        channel: str,
        subject: str | None = None,
        customer_id: int | None = None,
        lead_id: int | None = None,
        priority: str = "Normal",
        assigned_user_id: int | None = None,
        initial_body: str | None = None,
        direction: str = "Inbound",
        user_id: int | None = None,
        user_name: str | None = None,
    ) -> int:
        ensure_crm_schema()
        now = datetime.utcnow()
        row = db.session.execute(
            text(
                """
                INSERT INTO dbo.CrmConversation
                    (CustomerID, LeadID, Subject, Channel, Status, Priority, AssignedUserID, LastMessageAt, UnreadCount)
                OUTPUT INSERTED.ConversationID
                VALUES
                    (:customer_id, :lead_id, :subject, :channel, N'Open', :priority, :assigned_user_id, :now, 1)
                """
            ),
            {
                "customer_id": customer_id,
                "lead_id": lead_id,
                "subject": (subject or "Conversation")[:255],
                "channel": (channel or "Website")[:50],
                "priority": (priority or "Normal")[:20],
                "assigned_user_id": assigned_user_id,
                "now": now,
            },
        ).first()
        conversation_id = int(row[0])
        if initial_body:
            self.add_message(
                conversation_id,
                body=initial_body,
                channel=channel,
                direction=direction,
                user_id=user_id,
                user_name=user_name,
                bump_unread=False,
            )
        TimelineService().add_event(
            event_type="ConversationOpened",
            title=f"Conversation opened ({channel})",
            description=subject,
            customer_id=customer_id,
            lead_id=lead_id,
            entity_type="CrmConversation",
            entity_id=conversation_id,
            user_id=user_id,
            user_name=user_name,
        )
        return conversation_id

    def add_message(
        self,
        conversation_id: int,
        *,
        body: str,
        channel: str,
        direction: str = "Outbound",
        is_internal_note: bool = False,
        attachment_path: str | None = None,
        attachment_name: str | None = None,
        user_id: int | None = None,
        user_name: str | None = None,
        bump_unread: bool = True,
    ) -> int:
        ensure_crm_schema()
        now = datetime.utcnow()
        row = db.session.execute(
            text(
                """
                INSERT INTO dbo.CrmMessage
                    (ConversationID, Direction, Channel, Body, AttachmentPath, AttachmentName,
                     CreatedByUserID, CreatedByName, IsInternalNote)
                OUTPUT INSERTED.MessageID
                VALUES
                    (:cid, :direction, :channel, :body, :apath, :aname, :uid, :uname, :internal)
                """
            ),
            {
                "cid": conversation_id,
                "direction": direction[:20],
                "channel": channel[:50],
                "body": body,
                "apath": attachment_path,
                "aname": attachment_name,
                "uid": user_id,
                "uname": (user_name or "")[:150] or None,
                "internal": 1 if is_internal_note else 0,
            },
        ).first()
        unread_sql = "UnreadCount = UnreadCount + 1," if bump_unread and direction == "Inbound" else ""
        db.session.execute(
            text(
                f"""
                UPDATE dbo.CrmConversation
                SET LastMessageAt = :now, ModifiedDate = :now, {unread_sql}
                    Status = CASE WHEN Status = N'Closed' THEN N'Open' ELSE Status END
                WHERE ConversationID = :cid
                """
            ),
            {"now": now, "cid": conversation_id},
        )
        db.session.commit()
        return int(row[0]) if row else 0

    def list_conversations(
        self,
        *,
        status: str | None = None,
        priority: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 40,
    ) -> dict:
        ensure_crm_schema()
        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        offset = (page - 1) * page_size
        clauses = ["c.IsActive = 1"]
        params: dict = {"limit": page_size, "offset": offset}
        if status:
            clauses.append("c.Status = :status")
            params["status"] = status
        if priority:
            clauses.append("c.Priority = :priority")
            params["priority"] = priority
        if search:
            clauses.append(
                "(c.Subject LIKE :like OR cm.CustomerName LIKE :like OR l.FullName LIKE :like OR cm.MobileNumber LIKE :like)"
            )
            params["like"] = f"%{search.strip()}%"
        where = " AND ".join(clauses)
        total = db.session.execute(
            text(
                f"""
                SELECT COUNT(1)
                FROM dbo.CrmConversation c
                LEFT JOIN dbo.CustomerMaster cm ON cm.CustomerID = c.CustomerID
                LEFT JOIN dbo.CrmLead l ON l.LeadID = c.LeadID
                WHERE {where}
                """
            ),
            params,
        ).scalar() or 0
        rows = db.session.execute(
            text(
                f"""
                SELECT c.ConversationID, c.CustomerID, c.LeadID, c.Subject, c.Channel, c.Status,
                       c.Priority, c.AssignedUserID, c.LastMessageAt, c.UnreadCount, c.CreatedDate,
                       cm.CustomerName, cm.MobileNumber, cm.EmailID, cm.WhatsAppNumber,
                       l.FullName AS LeadName, l.Mobile AS LeadMobile, l.Email AS LeadEmail
                FROM dbo.CrmConversation c
                LEFT JOIN dbo.CustomerMaster cm ON cm.CustomerID = c.CustomerID
                LEFT JOIN dbo.CrmLead l ON l.LeadID = c.LeadID
                WHERE {where}
                ORDER BY COALESCE(c.LastMessageAt, c.CreatedDate) DESC
                OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
                """
            ),
            params,
        ).mappings().all()
        return {"total": int(total), "page": page, "page_size": page_size, "rows": [dict(r) for r in rows]}

    def get_conversation(self, conversation_id: int) -> dict | None:
        ensure_crm_schema()
        row = db.session.execute(
            text(
                """
                SELECT c.ConversationID, c.CustomerID, c.LeadID, c.Subject, c.Channel, c.Status,
                       c.Priority, c.AssignedUserID, c.LastMessageAt, c.UnreadCount, c.CreatedDate,
                       cm.CustomerName, cm.MobileNumber, cm.EmailID, cm.WhatsAppNumber,
                       cm.PANNumber, cm.GSTNumber, cm.CustomerStatus,
                       l.FullName AS LeadName, l.Mobile AS LeadMobile, l.Email AS LeadEmail,
                       l.Status AS LeadStatus, l.Source AS LeadSource
                FROM dbo.CrmConversation c
                LEFT JOIN dbo.CustomerMaster cm ON cm.CustomerID = c.CustomerID
                LEFT JOIN dbo.CrmLead l ON l.LeadID = c.LeadID
                WHERE c.ConversationID = :id AND c.IsActive = 1
                """
            ),
            {"id": conversation_id},
        ).mappings().first()
        return dict(row) if row else None

    def list_messages(self, conversation_id: int) -> list[dict]:
        ensure_crm_schema()
        rows = db.session.execute(
            text(
                """
                SELECT MessageID, ConversationID, Direction, Channel, Body, AttachmentPath,
                       AttachmentName, CreatedByUserID, CreatedByName, CreatedDate, IsInternalNote
                FROM dbo.CrmMessage
                WHERE ConversationID = :id
                ORDER BY CreatedDate ASC, MessageID ASC
                """
            ),
            {"id": conversation_id},
        ).mappings().all()
        return [dict(r) for r in rows]

    def mark_read(self, conversation_id: int) -> None:
        ensure_crm_schema()
        db.session.execute(
            text(
                """
                UPDATE dbo.CrmConversation
                SET UnreadCount = 0, ModifiedDate = :now
                WHERE ConversationID = :id
                """
            ),
            {"id": conversation_id, "now": datetime.utcnow()},
        )
        db.session.commit()

    def update_conversation(
        self,
        conversation_id: int,
        *,
        status: str | None = None,
        priority: str | None = None,
        assigned_user_id: int | None = None,
        assign_set: bool = False,
    ) -> None:
        ensure_crm_schema()
        sets = ["ModifiedDate = :now"]
        params: dict = {"id": conversation_id, "now": datetime.utcnow()}
        if status:
            sets.append("Status = :status")
            params["status"] = status
        if priority:
            sets.append("Priority = :priority")
            params["priority"] = priority
        if assign_set:
            sets.append("AssignedUserID = :assigned")
            params["assigned"] = assigned_user_id
        db.session.execute(
            text(f"UPDATE dbo.CrmConversation SET {', '.join(sets)} WHERE ConversationID = :id"),
            params,
        )
        db.session.commit()

    def unread_message_count(self) -> int:
        ensure_crm_schema()
        return int(
            db.session.execute(
                text(
                    """
                    SELECT COALESCE(SUM(UnreadCount), 0)
                    FROM dbo.CrmConversation
                    WHERE IsActive = 1 AND Status <> N'Closed'
                    """
                )
            ).scalar()
            or 0
        )
