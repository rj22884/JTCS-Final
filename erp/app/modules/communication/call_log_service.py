"""Manual call logs linked to Customer Master / Leads / Conversations."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text

from app.extensions import db
from app.modules.communication.services import CommunicationService
from app.modules.shared.schema import ensure_crm_schema
from app.modules.shared.timeline_service import TimelineService


class CallLogService:
    def list_logs(
        self,
        *,
        customer_id: int | None = None,
        lead_id: int | None = None,
        page: int = 1,
        page_size: int = 40,
    ) -> dict:
        ensure_crm_schema()
        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        offset = (page - 1) * page_size
        clauses = ["cl.IsActive = 1"]
        params: dict = {"limit": page_size, "offset": offset}
        if customer_id:
            clauses.append("cl.CustomerID = :customer_id")
            params["customer_id"] = customer_id
        if lead_id:
            clauses.append("cl.LeadID = :lead_id")
            params["lead_id"] = lead_id
        where = " AND ".join(clauses)
        total = db.session.execute(
            text(f"SELECT COUNT(1) FROM dbo.CrmCallLog cl WHERE {where}"),
            params,
        ).scalar() or 0
        rows = db.session.execute(
            text(
                f"""
                SELECT cl.CallLogID, cl.CustomerID, cl.LeadID, cl.ConversationID, cl.Direction,
                       cl.CallStatus, cl.PhoneNumber, cl.DurationSeconds, cl.RecordingURL,
                       cl.Notes, cl.NextFollowUpAt, cl.CalledAt, cl.CreatedByName, cl.CreatedDate,
                       cm.CustomerName, l.FullName AS LeadName
                FROM dbo.CrmCallLog cl
                LEFT JOIN dbo.CustomerMaster cm ON cm.CustomerID = cl.CustomerID
                LEFT JOIN dbo.CrmLead l ON l.LeadID = cl.LeadID
                WHERE {where}
                ORDER BY cl.CalledAt DESC
                OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
                """
            ),
            params,
        ).mappings().all()
        return {"total": int(total), "page": page, "page_size": page_size, "rows": [dict(r) for r in rows]}

    def create(
        self,
        *,
        direction: str = "Outgoing",
        call_status: str = "Completed",
        phone_number: str | None = None,
        customer_id: int | None = None,
        lead_id: int | None = None,
        duration_seconds: int | None = None,
        recording_url: str | None = None,
        notes: str | None = None,
        next_follow_up_at: datetime | None = None,
        called_at: datetime | None = None,
        user_id: int | None = None,
        user_name: str | None = None,
        open_conversation: bool = True,
    ) -> dict:
        ensure_crm_schema()
        called = called_at or datetime.utcnow()
        conversation_id = None
        if open_conversation and (customer_id or lead_id or phone_number):
            conversation_id = CommunicationService().find_or_open_conversation(
                channel="Phone",
                subject=f"Call {direction}: {phone_number or ''}".strip(),
                customer_id=customer_id,
                lead_id=lead_id,
                contact_mobile=phone_number,
            )
            CommunicationService().add_message(
                conversation_id,
                body=notes or f"{direction} call ({call_status})"
                + (f" · {duration_seconds}s" if duration_seconds else ""),
                channel="Phone",
                direction="Inbound" if direction == "Incoming" else "Outbound",
                media_type="call",
                user_id=user_id,
                user_name=user_name,
                bump_unread=direction == "Incoming" and call_status == "Missed",
            )

        row = db.session.execute(
            text(
                """
                INSERT INTO dbo.CrmCallLog
                    (CustomerID, LeadID, ConversationID, Direction, CallStatus, PhoneNumber,
                     DurationSeconds, RecordingURL, Notes, NextFollowUpAt, CalledAt,
                     CreatedByUserID, CreatedByName)
                OUTPUT INSERTED.CallLogID
                VALUES
                    (:customer_id, :lead_id, :conversation_id, :direction, :call_status, :phone,
                     :duration, :recording, :notes, :next_fu, :called_at, :uid, :uname)
                """
            ),
            {
                "customer_id": customer_id,
                "lead_id": lead_id,
                "conversation_id": conversation_id,
                "direction": (direction or "Outgoing")[:20],
                "call_status": (call_status or "Completed")[:30],
                "phone": (phone_number or "")[:30] or None,
                "duration": duration_seconds,
                "recording": (recording_url or "")[:500] or None,
                "notes": notes,
                "next_fu": next_follow_up_at,
                "called_at": called,
                "uid": user_id,
                "uname": (user_name or "")[:150] or None,
            },
        ).first()
        call_id = int(row[0]) if row else 0
        db.session.commit()

        TimelineService().add_event(
            event_type="CallLogged",
            title=f"{direction} call ({call_status})",
            description=notes,
            customer_id=customer_id,
            lead_id=lead_id,
            entity_type="CrmCallLog",
            entity_id=call_id,
            user_id=user_id,
            user_name=user_name,
        )
        return {"call_log_id": call_id, "conversation_id": conversation_id}
