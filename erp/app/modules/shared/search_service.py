"""Global search across customers, ledgers, items, invoices, and CRM records."""

from __future__ import annotations

from sqlalchemy import text

from app.extensions import db
from app.modules.shared.schema import ensure_crm_schema
from app.repositories.customer_repository import CustomerRepository


def _hit(base: dict | None = None, **fields) -> dict:
    row = dict(base or {})
    row.update(fields)
    title = row.get("title") or row.get("label") or row.get("customer_name") or "Untitled"
    subtitle = row.get("subtitle") or ""
    href = row.get("href") or "#"
    row["title"] = str(title).strip() or "Untitled"
    row["subtitle"] = str(subtitle).strip()
    row["href"] = href
    return row


def _safe(fn, fallback):
    try:
        return fn()
    except Exception:
        db.session.rollback()
        return fallback


class GlobalSearchService:
    def search(self, query: str, *, limit: int = 20) -> dict:
        ensure_crm_schema()
        needle = (query or "").strip()
        empty = {
            "query": needle,
            "customers": [],
            "leads": [],
            "invoices": [],
            "items": [],
            "ledgers": [],
            "documents": [],
        }
        if len(needle) < 2:
            return empty

        like = f"%{needle}%"
        lim = max(1, min(int(limit or 20), 40))

        customers = []
        for c in CustomerRepository().search(needle, limit=lim):
            cid = c.get("customer_id")
            bits = [c.get("mobile_number"), c.get("pan_number"), c.get("customer_status")]
            customers.append(
                _hit(
                    c,
                    title=c.get("customer_name") or "",
                    subtitle=" · ".join(b for b in bits if b),
                    href=f"/crm/customer-360/{cid}" if cid else "/masters/customer",
                )
            )

        return {
            "query": needle,
            "customers": customers,
            "leads": _safe(lambda: self._search_leads(like, needle, lim), []),
            "invoices": _safe(lambda: self._search_invoices(like, needle, lim), []),
            "items": _safe(lambda: self._search_items(needle, lim), []),
            "ledgers": _safe(lambda: self._search_ledgers(needle, lim), []),
            "documents": _safe(lambda: self._search_documents(like, lim), []),
        }

    def _search_leads(self, like: str, exact: str, limit: int) -> list[dict]:
        rows = db.session.execute(
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
            {"limit": limit, "like": like, "exact": exact},
        ).mappings().all()
        out = []
        for r in rows:
            lid = r.get("LeadID")
            out.append(
                _hit(
                    dict(r),
                    title=r.get("FullName") or "",
                    subtitle=" · ".join(
                        b for b in (r.get("Mobile"), r.get("Email"), r.get("Status")) if b
                    ),
                    href=f"/crm/leads/{lid}" if lid else "/crm/leads",
                )
            )
        return out

    def _search_invoices(self, like: str, exact: str, limit: int) -> list[dict]:
        rows = db.session.execute(
            text(
                """
                SELECT TOP (:limit)
                    InvoiceID, InvoiceNo, CustomerID, CustomerName, InvoiceValue,
                    InvoiceDate, VoucherType, TallyBillNo
                FROM dbo.GstInvoice
                WHERE InvoiceNo LIKE :like
                   OR CustomerName LIKE :like
                   OR ISNULL(TallyBillNo, N'') LIKE :like
                   OR CAST(InvoiceID AS NVARCHAR(20)) = :exact
                ORDER BY InvoiceDate DESC
                """
            ),
            {"limit": limit, "like": like, "exact": exact},
        ).mappings().all()
        out = []
        for r in rows:
            no = (r.get("InvoiceNo") or "").strip()
            name = (r.get("CustomerName") or "").strip()
            voucher = (r.get("VoucherType") or "SALE").strip().upper()
            href = (
                "/accounting/invoice/purchase"
                if voucher == "PURCHASE"
                else "/accounting/invoice/sale"
            )
            value = r.get("InvoiceValue")
            sub_bits = [name]
            if value is not None:
                sub_bits.append(f"₹ {value}")
            out.append(
                _hit(
                    {k: r[k] for k in r.keys()},
                    title=no or name,
                    subtitle=" · ".join(b for b in sub_bits if b),
                    href=href,
                )
            )
        return out

    def _search_items(self, needle: str, limit: int) -> list[dict]:
        from app.services.item_master_service import ItemMasterService

        rows = ItemMasterService().list_records(search=needle, active_only=False)[:limit]
        out = []
        for it in rows:
            code = (it.get("item_code") or "").strip()
            hsn = (it.get("hsn_sac") or "").strip()
            sub = " · ".join(b for b in (code, f"HSN/SAC {hsn}" if hsn else "") if b)
            out.append(
                _hit(
                    it,
                    title=it.get("item_name") or code,
                    subtitle=sub or "Item",
                    href="/masters/item",
                )
            )
        return out

    def _search_ledgers(self, needle: str, limit: int) -> list[dict]:
        from app.services.ledger_report_service import LedgerReportService

        rows = LedgerReportService().search_ledgers(kind="all", search=needle, limit=limit)
        out = []
        for row in rows:
            kind = (row.get("kind") or "").strip().lower()
            if kind in {"customer", "item"}:
                continue
            if kind == "bank":
                href = "/masters/bank"
            elif kind == "work":
                href = "/masters/income-expense"
            else:
                href = "/Reports_and_analysis/ledger_report"
            out.append(
                _hit(
                    row,
                    title=row.get("label") or "",
                    subtitle=row.get("subtitle") or kind.title(),
                    href=href,
                )
            )
        return out

    def _search_documents(self, like: str, limit: int) -> list[dict]:
        rows = db.session.execute(
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
        out = []
        for r in rows:
            out.append(
                _hit(
                    dict(r),
                    title=r.get("Title") or r.get("FileName") or "",
                    subtitle=r.get("FolderType") or "Document",
                    href="/crm/documents",
                )
            )
        return out
