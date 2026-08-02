"""Global search across customers, leads, invoices, documents."""

from __future__ import annotations

from sqlalchemy import text

from app.extensions import db
from app.modules.shared.schema import ensure_crm_schema
from app.repositories.customer_repository import CustomerRepository


class GlobalSearchService:
    def search(self, query: str, *, limit: int = 20) -> dict:
        ensure_crm_schema()
        needle = (query or "").strip()
        if len(needle) < 2:
            return {"query": needle, "customers": [], "leads": [], "invoices": [], "documents": []}

        customers = CustomerRepository().search(needle, limit=limit)
        like = f"%{needle}%"
        leads = db.session.execute(
            text(
                """
                SELECT TOP (:limit) LeadID, FullName, Mobile, Email, Status, Source, CreatedDate
                FROM dbo.CrmLead
                WHERE IsActive = 1
                  AND (
                    FullName LIKE :like
                    OR Mobile LIKE :like
                    OR Email LIKE :like
                    OR BusinessName LIKE :like
                    OR CAST(LeadID AS NVARCHAR(20)) = :exact
                  )
                ORDER BY CreatedDate DESC
                """
            ),
            {"limit": limit, "like": like, "exact": needle},
        ).mappings().all()

        invoices: list[dict] = []
        try:
            invoices = [
                dict(r)
                for r in db.session.execute(
                    text(
                        """
                        SELECT TOP (:limit) InvoiceID, InvoiceNumber, CustomerID, GrandTotal, InvoiceDate
                        FROM dbo.GstInvoice
                        WHERE InvoiceNumber LIKE :like
                           OR CAST(InvoiceID AS NVARCHAR(20)) = :exact
                        ORDER BY InvoiceDate DESC
                        """
                    ),
                    {"limit": limit, "like": like, "exact": needle},
                ).mappings().all()
            ]
        except Exception:
            db.session.rollback()
            invoices = []

        documents = db.session.execute(
            text(
                """
                SELECT TOP (:limit) DocumentID, CustomerID, FolderType, Title, FileName, CreatedDate
                FROM dbo.CrmDocument
                WHERE IsActive = 1
                  AND (Title LIKE :like OR FileName LIKE :like OR FolderType LIKE :like)
                ORDER BY CreatedDate DESC
                """
            ),
            {"limit": limit, "like": like},
        ).mappings().all()

        return {
            "query": needle,
            "customers": customers,
            "leads": [dict(r) for r in leads],
            "invoices": invoices,
            "documents": [dict(r) for r in documents],
        }
