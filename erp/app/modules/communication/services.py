"""Conversation and message services for Communication Center."""

from __future__ import annotations

from datetime import datetime, timedelta

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
        contact_mobile: str | None = None,
        contact_email: str | None = None,
        external_thread_key: str | None = None,
        match_status: str | None = None,
    ) -> int:
        ensure_crm_schema()
        now = datetime.utcnow()
        if not match_status:
            if customer_id or lead_id:
                match_status = "Linked"
            else:
                match_status = "Unknown"
        row = db.session.execute(
            text(
                """
                INSERT INTO dbo.CrmConversation
                    (CustomerID, LeadID, Subject, Channel, Status, Priority, AssignedUserID,
                     LastMessageAt, UnreadCount, ContactMobile, ContactEmail, ExternalThreadKey,
                     MatchStatus)
                OUTPUT INSERTED.ConversationID
                VALUES
                    (:customer_id, :lead_id, :subject, :channel, N'New', :priority, :assigned_user_id,
                     :now, 1, :contact_mobile, :contact_email, :external_thread_key, :match_status)
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
                "contact_mobile": (contact_mobile or "")[:30] or None,
                "contact_email": (contact_email or "")[:255] or None,
                "external_thread_key": (external_thread_key or "")[:128] or None,
                "match_status": (match_status or "Unknown")[:30],
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
        if customer_id or lead_id:
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

    def find_open_conversation(
        self,
        *,
        channel: str | None = None,
        customer_id: int | None = None,
        lead_id: int | None = None,
        contact_mobile: str | None = None,
        contact_email: str | None = None,
        external_thread_key: str | None = None,
    ) -> dict | None:
        ensure_crm_schema()
        clauses = ["c.IsActive = 1", "c.Status <> N'Closed'", "ISNULL(c.IsArchived, 0) = 0"]
        params: dict = {}
        if channel:
            clauses.append("c.Channel = :channel")
            params["channel"] = channel
        if external_thread_key:
            clauses.append("c.ExternalThreadKey = :ethread")
            params["ethread"] = external_thread_key[:128]
        elif contact_mobile:
            clauses.append(
                "(c.ContactMobile = :mobile OR c.ExternalThreadKey = :mobile)"
            )
            params["mobile"] = contact_mobile[:30]
        elif contact_email:
            clauses.append("LOWER(c.ContactEmail) = LOWER(:email)")
            params["email"] = contact_email[:255]
        elif customer_id:
            clauses.append("c.CustomerID = :customer_id")
            params["customer_id"] = customer_id
        elif lead_id:
            clauses.append("c.LeadID = :lead_id")
            params["lead_id"] = lead_id
        else:
            return None
        where = " AND ".join(clauses)
        row = db.session.execute(
            text(
                f"""
                SELECT TOP 1 c.ConversationID, c.CustomerID, c.LeadID, c.Subject, c.Channel,
                       c.Status, c.Priority, c.AssignedUserID, c.UnreadCount, c.ContactMobile,
                       c.ContactEmail, c.ExternalThreadKey
                FROM dbo.CrmConversation c
                WHERE {where}
                ORDER BY COALESCE(c.LastMessageAt, c.CreatedDate) DESC
                """
            ),
            params,
        ).mappings().first()
        return dict(row) if row else None

    def find_open_whatsapp_thread(self, mobile: str | None) -> dict | None:
        """Find an open WhatsApp conversation by normalized last-10 mobile digits."""
        from app.modules.communication.customer_link_service import last10_digits

        ensure_crm_schema()
        last10 = last10_digits(mobile)
        if not last10:
            return None
        row = db.session.execute(
            text(
                """
                SELECT TOP 1 c.ConversationID, c.CustomerID, c.LeadID, c.Subject, c.Channel,
                       c.Status, c.Priority, c.AssignedUserID, c.UnreadCount, c.ContactMobile,
                       c.ContactEmail, c.ExternalThreadKey, c.MatchStatus
                FROM dbo.CrmConversation c
                WHERE c.IsActive = 1
                  AND c.Status <> N'Closed'
                  AND ISNULL(c.IsArchived, 0) = 0
                  AND c.Channel = N'WhatsApp'
                  AND (
                        RIGHT(REPLACE(REPLACE(REPLACE(ISNULL(c.ExternalThreadKey, N''), N' ', N''), N'-', N''), N'+', N''), 10)
                            = :last10
                     OR RIGHT(REPLACE(REPLACE(REPLACE(ISNULL(c.ContactMobile, N''), N' ', N''), N'-', N''), N'+', N''), 10)
                            = :last10
                  )
                ORDER BY COALESCE(c.LastMessageAt, c.CreatedDate) DESC
                """
            ),
            {"last10": last10},
        ).mappings().first()
        return dict(row) if row else None

    def find_or_open_conversation(
        self,
        *,
        channel: str,
        subject: str | None = None,
        customer_id: int | None = None,
        lead_id: int | None = None,
        contact_mobile: str | None = None,
        contact_email: str | None = None,
        external_thread_key: str | None = None,
        priority: str = "Normal",
    ) -> int:
        thread_key = external_thread_key or contact_mobile or contact_email
        existing = None
        for kwargs in (
            {"channel": channel, "external_thread_key": thread_key} if thread_key else None,
            {"channel": channel, "contact_mobile": contact_mobile} if contact_mobile else None,
            {"channel": channel, "contact_email": contact_email} if contact_email else None,
            {"channel": channel, "customer_id": customer_id} if customer_id else None,
            {"channel": channel, "lead_id": lead_id} if lead_id else None,
            # Lead created via CustomerLinkService opens channel=source (WhatsApp)
            {"lead_id": lead_id} if lead_id else None,
            {"customer_id": customer_id} if customer_id else None,
        ):
            if not kwargs:
                continue
            existing = self.find_open_conversation(**kwargs)
            if existing:
                break
        if existing:
            cid = int(existing["ConversationID"])
            # Backfill link fields if missing
            sets = []
            params: dict = {"id": cid, "now": datetime.utcnow()}
            if customer_id and not existing.get("CustomerID"):
                sets.append("CustomerID = :customer_id")
                params["customer_id"] = customer_id
            if lead_id and not existing.get("LeadID"):
                sets.append("LeadID = :lead_id")
                params["lead_id"] = lead_id
            if contact_mobile and not existing.get("ContactMobile"):
                sets.append("ContactMobile = :contact_mobile")
                params["contact_mobile"] = contact_mobile[:30]
            if contact_email and not existing.get("ContactEmail"):
                sets.append("ContactEmail = :contact_email")
                params["contact_email"] = contact_email[:255]
            if sets:
                sets.append("ModifiedDate = :now")
                db.session.execute(
                    text(f"UPDATE dbo.CrmConversation SET {', '.join(sets)} WHERE ConversationID = :id"),
                    params,
                )
                db.session.commit()
            return cid
        return self.open_conversation(
            channel=channel,
            subject=subject,
            customer_id=customer_id,
            lead_id=lead_id,
            priority=priority,
            contact_mobile=contact_mobile,
            contact_email=contact_email,
            external_thread_key=external_thread_key or contact_mobile or contact_email,
        )

    def message_exists_by_external_id(self, external_message_id: str) -> bool:
        ensure_crm_schema()
        if not external_message_id:
            return False
        return bool(
            db.session.execute(
                text(
                    """
                    SELECT TOP 1 1 FROM dbo.CrmMessage
                    WHERE ExternalMessageID = :eid
                    """
                ),
                {"eid": external_message_id[:128]},
            ).scalar()
        )

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
        attachment_mime_type: str | None = None,
        attachment_size_bytes: int | None = None,
        media_type: str | None = None,
        external_message_id: str | None = None,
        delivery_status: str | None = None,
        error_detail: str | None = None,
        is_test: bool = False,
        user_id: int | None = None,
        user_name: str | None = None,
        bump_unread: bool = True,
    ) -> int:
        ensure_crm_schema()
        if external_message_id and self.message_exists_by_external_id(external_message_id):
            row = db.session.execute(
                text(
                    "SELECT TOP 1 MessageID FROM dbo.CrmMessage WHERE ExternalMessageID = :eid"
                ),
                {"eid": external_message_id[:128]},
            ).first()
            return int(row[0]) if row else 0

        now = datetime.utcnow()
        row = db.session.execute(
            text(
                """
                INSERT INTO dbo.CrmMessage
                    (ConversationID, Direction, Channel, Body, AttachmentPath, AttachmentName,
                     AttachmentMimeType, AttachmentSizeBytes, MediaType, ExternalMessageID,
                     DeliveryStatus, StatusUpdatedAt, ErrorDetail, IsTest,
                     CreatedByUserID, CreatedByName, IsInternalNote)
                OUTPUT INSERTED.MessageID
                VALUES
                    (:cid, :direction, :channel, :body, :apath, :aname,
                     :amime, :asize, :mtype, :eid,
                     :dstatus, :now, :err, :is_test,
                     :uid, :uname, :internal)
                """
            ),
            {
                "cid": conversation_id,
                "direction": direction[:20],
                "channel": channel[:50],
                "body": body,
                "apath": attachment_path,
                "aname": attachment_name,
                "amime": (attachment_mime_type or "")[:100] or None,
                "asize": attachment_size_bytes,
                "mtype": (media_type or "")[:30] or None,
                "eid": (external_message_id or "")[:128] or None,
                "dstatus": (delivery_status or "")[:30] or None,
                "now": now if delivery_status else None,
                "err": (error_detail or "")[:500] or None,
                "is_test": 1 if is_test else 0,
                "uid": user_id,
                "uname": (user_name or "")[:150] or None,
                "internal": 1 if is_internal_note else 0,
            },
        ).first()
        unread_sql = "UnreadCount = UnreadCount + 1," if bump_unread and direction == "Inbound" else ""
        inbound_sql = "LastInboundAt = :now," if direction == "Inbound" else ""
        outbound_sql = "LastOutboundAt = :now," if direction == "Outbound" else ""
        preview = (body or "")[:240]
        if direction == "Inbound":
            status_sql = """
                Status = CASE
                    WHEN Status IN (N'Closed', N'Resolved') THEN N'Open'
                    WHEN Status = N'Waiting for Internal Team' THEN Status
                    ELSE N'Pending Reply'
                END,
            """
        elif direction == "Outbound" and not is_internal_note:
            status_sql = "Status = N'Waiting for Customer',"
        else:
            status_sql = ""
        db.session.execute(
            text(
                f"""
                UPDATE dbo.CrmConversation
                SET LastMessageAt = :now, ModifiedDate = :now, {unread_sql}
                    {inbound_sql} {outbound_sql} {status_sql}
                    LastMessagePreview = :preview,
                    IsArchived = 0
                WHERE ConversationID = :cid
                """
            ),
            {"now": now, "cid": conversation_id, "preview": preview},
        )
        db.session.commit()
        return int(row[0]) if row else 0

    def update_delivery_status(
        self,
        *,
        external_message_id: str,
        status: str,
        error_detail: str | None = None,
    ) -> bool:
        ensure_crm_schema()
        if not external_message_id:
            return False
        # Normalize Meta statuses
        mapping = {
            "received": "Received",
            "sent": "Sent",
            "delivered": "Delivered",
            "read": "Read",
            "failed": "Failed",
            "deleted": "Deleted",
        }
        normalized = mapping.get((status or "").lower(), (status or "").title())[:30]
        result = db.session.execute(
            text(
                """
                UPDATE dbo.CrmMessage
                SET DeliveryStatus = :status,
                    StatusUpdatedAt = :now,
                    ErrorDetail = COALESCE(:err, ErrorDetail)
                WHERE ExternalMessageID = :eid
                """
            ),
            {
                "status": normalized,
                "now": datetime.utcnow(),
                "err": (error_detail or "")[:500] or None,
                "eid": external_message_id[:128],
            },
        )
        db.session.commit()
        return bool(result.rowcount)

    def list_conversations(
        self,
        *,
        status: str | None = None,
        priority: str | None = None,
        search: str | None = None,
        channel: str | None = None,
        unread_only: bool = False,
        archived: bool = False,
        pinned_only: bool = False,
        starred_only: bool = False,
        has_attachments: bool = False,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        page_size: int = 40,
        assigned_user_id: int | None = None,
        assigned_to_me: int | None = None,
        unknown_only: bool = False,
        pending_reply: bool = False,
        high_priority: bool = False,
        label_id: int | None = None,
        message_search: str | None = None,
    ) -> dict:
        ensure_crm_schema()
        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        offset = (page - 1) * page_size
        clauses = ["c.IsActive = 1"]
        params: dict = {"limit": page_size, "offset": offset}
        if archived:
            clauses.append("ISNULL(c.IsArchived, 0) = 1")
        else:
            clauses.append("ISNULL(c.IsArchived, 0) = 0")
        if status:
            clauses.append("c.Status = :status")
            params["status"] = status
        if priority:
            clauses.append("c.Priority = :priority")
            params["priority"] = priority
        if channel:
            clauses.append("c.Channel = :channel")
            params["channel"] = channel
        if unread_only:
            clauses.append("c.UnreadCount > 0")
        if pending_reply:
            clauses.append("c.Status = N'Pending Reply'")
        if high_priority:
            clauses.append("c.Priority IN (N'High', N'Urgent')")
        if assigned_to_me:
            clauses.append("c.AssignedUserID = :assigned_me")
            params["assigned_me"] = assigned_to_me
        elif assigned_user_id:
            clauses.append("c.AssignedUserID = :assigned_user_id")
            params["assigned_user_id"] = assigned_user_id
        if unknown_only:
            clauses.append("c.CustomerID IS NULL AND c.LeadID IS NULL")
        if label_id:
            clauses.append(
                """EXISTS (
                    SELECT 1 FROM dbo.CrmConversationLabel cl
                    WHERE cl.ConversationID = c.ConversationID AND cl.LabelID = :label_id
                )"""
            )
            params["label_id"] = label_id
        if message_search:
            clauses.append(
                """EXISTS (
                    SELECT 1 FROM dbo.CrmMessage ms
                    WHERE ms.ConversationID = c.ConversationID
                      AND ms.Body LIKE :msg_like
                )"""
            )
            params["msg_like"] = f"%{message_search.strip()}%"
        if pinned_only:
            clauses.append("ISNULL(c.IsPinned, 0) = 1")
        if starred_only:
            clauses.append("ISNULL(c.IsStarred, 0) = 1")
        if has_attachments:
            clauses.append(
                """EXISTS (
                    SELECT 1 FROM dbo.CrmMessage m
                    WHERE m.ConversationID = c.ConversationID
                      AND m.AttachmentPath IS NOT NULL
                )"""
            )
        if date_from:
            clauses.append("COALESCE(c.LastMessageAt, c.CreatedDate) >= :date_from")
            params["date_from"] = date_from
        if date_to:
            clauses.append("COALESCE(c.LastMessageAt, c.CreatedDate) < :date_to")
            params["date_to"] = date_to
        if search:
            clauses.append(
                "(c.Subject LIKE :like OR cm.CustomerName LIKE :like OR l.FullName LIKE :like "
                "OR cm.MobileNumber LIKE :like OR c.ContactMobile LIKE :like OR c.ContactEmail LIKE :like "
                "OR CAST(c.ConversationID AS NVARCHAR(20)) = :exact "
                "OR u.FullName LIKE :like OR c.LastMessagePreview LIKE :like "
                "OR EXISTS (SELECT 1 FROM dbo.CrmMessage ms "
                "           WHERE ms.ConversationID = c.ConversationID AND ms.Body LIKE :like))"
            )
            params["like"] = f"%{search.strip()}%"
            params["exact"] = search.strip()
        where = " AND ".join(clauses)
        total = db.session.execute(
            text(
                f"""
                SELECT COUNT(1)
                FROM dbo.CrmConversation c
                LEFT JOIN dbo.CustomerMaster cm ON cm.CustomerID = c.CustomerID
                LEFT JOIN dbo.CrmLead l ON l.LeadID = c.LeadID
                LEFT JOIN dbo.Users u ON u.UserID = c.AssignedUserID
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
                       c.ContactMobile, c.ContactEmail, c.ExternalThreadKey,
                       c.AssignedDate, c.AssignedByUserID, c.LastMessagePreview,
                       ISNULL(c.IsPinned, 0) AS IsPinned,
                       ISNULL(c.IsArchived, 0) AS IsArchived,
                       ISNULL(c.IsStarred, 0) AS IsStarred,
                       ISNULL(c.MatchStatus,
                              CASE WHEN c.CustomerID IS NULL AND c.LeadID IS NULL THEN N'Unknown' ELSE N'Linked' END
                       ) AS MatchStatus,
                       CASE WHEN c.CustomerID IS NULL AND c.LeadID IS NULL
                             AND ISNULL(c.MatchStatus, N'Unknown') IN (N'Unknown', N'') THEN 1 ELSE 0 END AS IsUnknown,
                       CASE WHEN c.CustomerID IS NULL AND c.LeadID IS NULL
                             AND c.MatchStatus = N'Ambiguous' THEN 1 ELSE 0 END AS IsAmbiguous,
                       CASE WHEN c.CustomerID IS NULL AND c.LeadID IS NULL
                             AND c.MatchStatus = N'Unlinked' THEN 1 ELSE 0 END AS IsUnlinked,
                       cm.CustomerName, cm.MobileNumber, cm.EmailID, cm.WhatsAppNumber,
                       l.FullName AS LeadName, l.Mobile AS LeadMobile, l.Email AS LeadEmail,
                       u.FullName AS AssignedUserName
                FROM dbo.CrmConversation c
                LEFT JOIN dbo.CustomerMaster cm ON cm.CustomerID = c.CustomerID
                LEFT JOIN dbo.CrmLead l ON l.LeadID = c.LeadID
                LEFT JOIN dbo.Users u ON u.UserID = c.AssignedUserID
                WHERE {where}
                ORDER BY ISNULL(c.IsPinned, 0) DESC,
                         COALESCE(c.LastMessageAt, c.CreatedDate) DESC
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
                       c.ContactMobile, c.ContactEmail, c.ExternalThreadKey,
                       c.AssignedDate, c.AssignedByUserID, c.LastMessagePreview,
                       ISNULL(c.IsPinned, 0) AS IsPinned,
                       ISNULL(c.IsArchived, 0) AS IsArchived,
                       ISNULL(c.IsStarred, 0) AS IsStarred,
                       ISNULL(c.MatchStatus,
                              CASE WHEN c.CustomerID IS NULL AND c.LeadID IS NULL THEN N'Unknown' ELSE N'Linked' END
                       ) AS MatchStatus,
                       CASE WHEN c.CustomerID IS NULL AND c.LeadID IS NULL
                             AND ISNULL(c.MatchStatus, N'Unknown') IN (N'Unknown', N'') THEN 1 ELSE 0 END AS IsUnknown,
                       CASE WHEN c.CustomerID IS NULL AND c.LeadID IS NULL
                             AND c.MatchStatus = N'Ambiguous' THEN 1 ELSE 0 END AS IsAmbiguous,
                       CASE WHEN c.CustomerID IS NULL AND c.LeadID IS NULL
                             AND c.MatchStatus = N'Unlinked' THEN 1 ELSE 0 END AS IsUnlinked,
                       cm.CustomerName, cm.MobileNumber, cm.EmailID, cm.WhatsAppNumber,
                       cm.PANNumber, cm.GSTNumber, cm.CustomerStatus,
                       l.FullName AS LeadName, l.Mobile AS LeadMobile, l.Email AS LeadEmail,
                       l.Status AS LeadStatus, l.Source AS LeadSource,
                       u.FullName AS AssignedUserName
                FROM dbo.CrmConversation c
                LEFT JOIN dbo.CustomerMaster cm ON cm.CustomerID = c.CustomerID
                LEFT JOIN dbo.CrmLead l ON l.LeadID = c.LeadID
                LEFT JOIN dbo.Users u ON u.UserID = c.AssignedUserID
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
                       AttachmentName, AttachmentMimeType, AttachmentSizeBytes, MediaType,
                       ExternalMessageID, DeliveryStatus, StatusUpdatedAt, ErrorDetail,
                       ISNULL(IsStarred, 0) AS IsStarred,
                       ISNULL(IsTest, 0) AS IsTest,
                       CreatedByUserID, CreatedByName, CreatedDate, IsInternalNote
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
        assigned_by_user_id: int | None = None,
        assigned_by_name: str | None = None,
        is_pinned: bool | None = None,
        is_archived: bool | None = None,
        is_starred: bool | None = None,
        customer_id: int | None = None,
        lead_id: int | None = None,
        subject: str | None = None,
        match_status: str | None = None,
        customer_set: bool = False,
        lead_set: bool = False,
    ) -> None:
        ensure_crm_schema()
        existing = self.get_conversation(conversation_id)
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
            sets.append("AssignedDate = :now")
            sets.append("AssignedByUserID = :assigned_by")
            params["assigned"] = assigned_user_id
            params["assigned_by"] = assigned_by_user_id
        if customer_set:
            sets.append("CustomerID = :customer_id")
            params["customer_id"] = customer_id
        elif customer_id is not None:
            sets.append("CustomerID = :customer_id")
            params["customer_id"] = customer_id
        if lead_set:
            sets.append("LeadID = :lead_id")
            params["lead_id"] = lead_id
        elif lead_id is not None:
            sets.append("LeadID = :lead_id")
            params["lead_id"] = lead_id
        if match_status:
            sets.append("MatchStatus = :match_status")
            params["match_status"] = match_status[:30]
        if subject:
            sets.append("Subject = :subject")
            params["subject"] = subject[:255]
        if is_pinned is not None:
            sets.append("IsPinned = :pinned")
            params["pinned"] = 1 if is_pinned else 0
        if is_archived is not None:
            sets.append("IsArchived = :archived")
            params["archived"] = 1 if is_archived else 0
        if is_starred is not None:
            sets.append("IsStarred = :starred")
            params["starred"] = 1 if is_starred else 0
        db.session.execute(
            text(f"UPDATE dbo.CrmConversation SET {', '.join(sets)} WHERE ConversationID = :id"),
            params,
        )
        db.session.commit()

        from app.modules.shared.audit_service import AuditService

        if status and existing and (existing.get("Status") or "") != status:
            AuditService().log(
                action_name="ConversationStatusChanged",
                entity_type="CrmConversation",
                entity_id=conversation_id,
                old_value=existing.get("Status"),
                new_value=status,
                user_id=assigned_by_user_id,
                user_name=assigned_by_name,
            )
        if assign_set and assigned_user_id:
            AuditService().log(
                action_name="ConversationAssigned",
                entity_type="CrmConversation",
                entity_id=conversation_id,
                old_value=existing.get("AssignedUserID") if existing else None,
                new_value=assigned_user_id,
                user_id=assigned_by_user_id,
                user_name=assigned_by_name,
            )
            from app.modules.notification.services import NotificationService

            NotificationService().create(
                notification_type="WhatsApp",
                title="Conversation assigned to you",
                message=(existing or {}).get("Subject") or f"Conversation #{conversation_id}",
                user_id=int(assigned_user_id),
                link_url=f"/crm/inbox?c={conversation_id}",
                priority=(existing or {}).get("Priority") or "Normal",
                customer_id=(existing or {}).get("CustomerID"),
                lead_id=(existing or {}).get("LeadID"),
                entity_type="CrmConversation",
                entity_id=conversation_id,
            )

    def unread_message_count(self, *, channel: str | None = None) -> int:
        ensure_crm_schema()
        clauses = ["IsActive = 1", "Status <> N'Closed'", "ISNULL(IsArchived, 0) = 0"]
        params: dict = {}
        if channel:
            clauses.append("Channel = :channel")
            params["channel"] = channel
        where = " AND ".join(clauses)
        return int(
            db.session.execute(
                text(
                    f"""
                    SELECT COALESCE(SUM(UnreadCount), 0)
                    FROM dbo.CrmConversation
                    WHERE {where}
                    """
                ),
                params,
            ).scalar()
            or 0
        )

    def dashboard_stats(self) -> dict:
        """KPI cards for Communication Center dashboard."""
        ensure_crm_schema()
        now = datetime.utcnow()
        start_today = datetime(now.year, now.month, now.day)
        start_tomorrow = start_today + timedelta(days=1)

        def _scalar(sql: str, params: dict | None = None) -> int:
            try:
                return int(db.session.execute(text(sql), params or {}).scalar() or 0)
            except Exception:
                db.session.rollback()
                return 0

        today_messages = _scalar(
            """
            SELECT COUNT(1) FROM dbo.CrmMessage
            WHERE CreatedDate >= :a AND CreatedDate < :b AND ISNULL(IsInternalNote, 0) = 0
            """,
            {"a": start_today, "b": start_tomorrow},
        )
        unread = self.unread_message_count()
        pending_replies = _scalar(
            """
            SELECT COUNT(1) FROM dbo.CrmConversation
            WHERE IsActive = 1 AND ISNULL(IsArchived, 0) = 0
              AND Status IN (N'Pending Reply', N'Pending')
            """
        )
        resolved = _scalar(
            """
            SELECT COUNT(1) FROM dbo.CrmConversation
            WHERE IsActive = 1 AND Status IN (N'Closed', N'Resolved')
              AND ModifiedDate >= :a AND ModifiedDate < :b
            """,
            {"a": start_today, "b": start_tomorrow},
        )
        open_convs = _scalar(
            """
            SELECT COUNT(1) FROM dbo.CrmConversation
            WHERE IsActive = 1 AND ISNULL(IsArchived, 0) = 0
              AND Status NOT IN (N'Closed', N'Resolved')
            """
        )
        today_calls = _scalar(
            """
            SELECT COUNT(1) FROM dbo.CrmCallLog
            WHERE IsActive = 1 AND CalledAt >= :a AND CalledAt < :b
            """,
            {"a": start_today, "b": start_tomorrow},
        )
        today_emails = _scalar(
            """
            SELECT COUNT(1) FROM dbo.CrmMessage
            WHERE Channel = N'Email' AND CreatedDate >= :a AND CreatedDate < :b
              AND ISNULL(IsInternalNote, 0) = 0
            """,
            {"a": start_today, "b": start_tomorrow},
        )
        website = _scalar(
            """
            SELECT COUNT(1) FROM dbo.CrmConversation
            WHERE Channel = N'Website' AND CreatedDate >= :a AND CreatedDate < :b AND IsActive = 1
            """,
            {"a": start_today, "b": start_tomorrow},
        )
        ai_convs = _scalar(
            """
            SELECT COUNT(1) FROM dbo.CrmConversation
            WHERE Channel = N'AI' AND IsActive = 1 AND ISNULL(IsArchived, 0) = 0
            """
        )
        failed_messages = _scalar(
            """
            SELECT COUNT(1) FROM dbo.CrmMessage
            WHERE DeliveryStatus = N'Failed' AND CreatedDate >= :a AND CreatedDate < :b
            """,
            {"a": start_today, "b": start_tomorrow},
        )
        total_customers = _scalar(
            """
            SELECT COUNT(1) FROM dbo.CustomerMaster
            WHERE ISNULL(CustomerStatus, N'Active') <> N'Inactive'
            """
        )
        # Simple average response: minutes between last inbound and following outbound (sample)
        avg_row = db.session.execute(
            text(
                """
                SELECT AVG(CAST(DATEDIFF(MINUTE, i.CreatedDate, o.CreatedDate) AS FLOAT))
                FROM dbo.CrmMessage i
                CROSS APPLY (
                    SELECT TOP 1 o2.CreatedDate
                    FROM dbo.CrmMessage o2
                    WHERE o2.ConversationID = i.ConversationID
                      AND o2.Direction = N'Outbound'
                      AND o2.CreatedDate > i.CreatedDate
                      AND ISNULL(o2.IsInternalNote, 0) = 0
                    ORDER BY o2.CreatedDate
                ) o
                WHERE i.Direction = N'Inbound'
                  AND i.CreatedDate >= DATEADD(DAY, -7, SYSUTCDATETIME())
                """
            )
        ).scalar()
        avg_response = round(float(avg_row), 1) if avg_row is not None else None

        recent = db.session.execute(
            text(
                """
                SELECT TOP 12 EventID, EventType, Title, Description, CustomerID, LeadID, CreatedDate
                FROM dbo.CrmTimelineEvent
                ORDER BY CreatedDate DESC
                """
            )
        ).mappings().all()

        return {
            "today_messages": today_messages,
            "unread_messages": unread,
            "pending_replies": pending_replies,
            "resolved_today": resolved,
            "open_conversations": open_convs,
            "today_calls": today_calls,
            "today_emails": today_emails,
            "website_enquiries": website,
            "ai_conversations": ai_convs,
            "failed_messages": failed_messages,
            "total_customers": total_customers,
            "avg_response_minutes": avg_response,
            "customer_satisfaction": None,  # Phase 2 placeholder
            "recent_activities": [dict(r) for r in recent],
        }

    def list_messages_by_external_id(self, external_message_id: str) -> list[dict]:
        ensure_crm_schema()
        if not external_message_id:
            return []
        rows = db.session.execute(
            text(
                """
                SELECT MessageID, ConversationID, DeliveryStatus, ExternalMessageID, IsTest
                FROM dbo.CrmMessage
                WHERE ExternalMessageID = :eid
                """
            ),
            {"eid": external_message_id[:128]},
        ).mappings().all()
        return [dict(r) for r in rows]

    def record_webhook_event(self, external_event_id: str, event_type: str) -> bool:
        """Return True if this event is new (inserted). False if duplicate."""
        ensure_crm_schema()
        eid = (external_event_id or "").strip()[:160]
        if not eid:
            return True
        existing = db.session.execute(
            text("SELECT TOP 1 1 FROM dbo.CrmWebhookEvent WHERE ExternalEventID = :eid"),
            {"eid": eid},
        ).scalar()
        if existing:
            return False
        try:
            db.session.execute(
                text(
                    """
                    INSERT INTO dbo.CrmWebhookEvent (ExternalEventID, EventType)
                    VALUES (:eid, :etype)
                    """
                ),
                {"eid": eid, "etype": (event_type or "unknown")[:50]},
            )
            db.session.commit()
            return True
        except Exception:
            db.session.rollback()
            return False

