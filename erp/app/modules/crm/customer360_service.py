"""Customer 360 — aggregated profile and activity."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.extensions import db
from app.modules.communication.services import CommunicationService
from app.modules.crm.followup_service import CrmFollowUpService
from app.modules.crm.task_service import CrmTaskService
from app.modules.documents.services import DocumentService
from app.modules.shared.schema import ensure_crm_schema
from app.modules.shared.timeline_service import TimelineService
from app.repositories.customer_repository import CustomerRepository


class Customer360Service:
    def __init__(
        self,
        *,
        customer_repo: CustomerRepository | None = None,
        communication: CommunicationService | None = None,
        tasks: CrmTaskService | None = None,
        followups: CrmFollowUpService | None = None,
        timeline: TimelineService | None = None,
        documents: DocumentService | None = None,
    ):
        self.customer_repo = customer_repo or CustomerRepository()
        self.communication = communication or CommunicationService()
        self.tasks = tasks or CrmTaskService()
        self.followups = followups or CrmFollowUpService()
        self.timeline = timeline or TimelineService()
        self.documents = documents or DocumentService()

    def get(self, customer_id: int) -> dict:
        """Alias used by CRM routes / Customer 360 page."""
        return self.get_profile(customer_id)

    def get_profile(self, customer_id: int) -> dict:
        ensure_crm_schema()
        self.customer_repo.ensure_schema()
        try:
            profile = self.customer_repo.get_full(customer_id)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if not profile:
            raise ValueError("Customer not found.")

        conversations = self._list_conversations(customer_id)
        task_list = self.tasks.list_tasks(customer_id=customer_id, page=1)
        followup_list = self.followups.list_followups(customer_id=customer_id, page=1)
        timeline_events = self.timeline.list_events(customer_id=customer_id, page=1, page_size=100)
        document_list = self.documents.list_documents(customer_id=customer_id)
        followup_entries = self._list_followup_entries(customer_id)
        invoices = self._list_invoices(customer_id)
        outstanding = self._compute_outstanding(customer_id, profile)

        by_channel: dict[str, int] = {}
        unread_total = 0
        for c in conversations:
            ch = c.get("Channel") or "Other"
            by_channel[ch] = by_channel.get(ch, 0) + 1
            unread_total += int(c.get("UnreadCount") or 0)

        return {
            "profile": profile,
            "conversations": conversations,
            "communication_summary": {
                "conversation_count": len(conversations),
                "unread_total": unread_total,
                "by_channel": by_channel,
            },
            "tasks": task_list.get("rows", []),
            "followups": followup_list.get("rows", []),
            "timeline": timeline_events.get("rows", []),
            "documents": document_list,
            "followup_entries": followup_entries,
            "invoices": invoices,
            "outstanding": outstanding,
        }

    def _list_conversations(self, customer_id: int) -> list[dict]:
        rows = db.session.execute(
            text(
                """
                SELECT ConversationID, CustomerID, LeadID, Subject, Channel, Status,
                       Priority, AssignedUserID, LastMessageAt, UnreadCount, CreatedDate
                FROM dbo.CrmConversation
                WHERE CustomerID = :cid AND IsActive = 1
                ORDER BY COALESCE(LastMessageAt, CreatedDate) DESC
                """
            ),
            {"cid": customer_id},
        ).mappings().all()
        return [dict(r) for r in rows]

    def _list_followup_entries(self, customer_id: int) -> list[dict]:
        try:
            rows = db.session.execute(
                text(
                    """
                    SELECT TOP 20 EntryID, ModuleCode, WorkDate, TaxPeriod, ReturnType,
                           BillNo, BillDate, BillAmount, ReturnFilingStatus, CreatedDate
                    FROM dbo.FollowupEntryMaster
                    WHERE CustomerID = :cid AND IsActive = 1
                    ORDER BY WorkDate DESC, EntryID DESC
                    """
                ),
                {"cid": customer_id},
            ).mappings().all()
            return [dict(r) for r in rows]
        except Exception:
            db.session.rollback()
            return []

    def _list_invoices(self, customer_id: int) -> list[dict]:
        try:
            rows = db.session.execute(
                text(
                    """
                    SELECT TOP 20 InvoiceID, InvoiceNo, InvoiceDate, InvoiceValue, InvoiceKind
                    FROM dbo.GstInvoice
                    WHERE CustomerID = :cid
                    ORDER BY InvoiceDate DESC, InvoiceID DESC
                    """
                ),
                {"cid": customer_id},
            ).mappings().all()
            return [dict(r) for r in rows]
        except Exception:
            db.session.rollback()
            return []

    def _compute_outstanding(self, customer_id: int, profile: dict) -> dict:
        opening = profile.get("opening_balance")
        opening_dr_cr = (profile.get("opening_balance_dr_cr") or "Dr").strip()
        opening_amount = Decimal(str(opening or 0))

        invoice_total = Decimal("0")
        try:
            val = db.session.execute(
                text(
                    """
                    SELECT COALESCE(SUM(InvoiceValue), 0)
                    FROM dbo.GstInvoice
                    WHERE CustomerID = :cid
                    """
                ),
                {"cid": customer_id},
            ).scalar()
            invoice_total = Decimal(str(val or 0))
        except Exception:
            db.session.rollback()

        if opening_dr_cr.lower() in ("cr", "credit"):
            balance = invoice_total - opening_amount
        else:
            balance = opening_amount + invoice_total

        return {
            "opening_balance": str(opening_amount),
            "opening_balance_dr_cr": opening_dr_cr,
            "invoice_total": str(invoice_total),
            "estimated_outstanding": str(balance.quantize(Decimal("0.01"))),
        }
