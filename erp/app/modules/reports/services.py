"""CRM analytics and reporting queries."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import text

from app.extensions import db
from app.modules.shared.schema import ensure_crm_schema


class CrmReportService:
    def lead_summary(self) -> dict:
        ensure_crm_schema()
        rows = db.session.execute(
            text(
                """
                SELECT Status, COUNT(1) AS Cnt
                FROM dbo.CrmLead
                WHERE IsActive = 1
                GROUP BY Status
                ORDER BY Cnt DESC
                """
            ),
        ).mappings().all()
        by_status = {str(r["Status"]): int(r["Cnt"]) for r in rows}
        total = sum(by_status.values())
        return {"total": total, "by_status": by_status}

    def conversion_stats(self, *, days: int = 30) -> dict:
        ensure_crm_schema()
        since = datetime.utcnow() - timedelta(days=max(1, days))
        created = db.session.execute(
            text(
                """
                SELECT COUNT(1) FROM dbo.CrmLead
                WHERE IsActive = 1 AND CreatedDate >= :since
                """
            ),
            {"since": since},
        ).scalar() or 0
        converted = db.session.execute(
            text(
                """
                SELECT COUNT(1) FROM dbo.CrmLead
                WHERE IsActive = 1 AND Status = N'Converted' AND ModifiedDate >= :since
                """
            ),
            {"since": since},
        ).scalar() or 0
        rate = (float(converted) / float(created) * 100.0) if created else 0.0
        return {
            "period_days": days,
            "leads_created": int(created),
            "leads_converted": int(converted),
            "conversion_rate_pct": round(rate, 2),
        }

    def pending_followups(self, *, limit: int = 50) -> list[dict]:
        ensure_crm_schema()
        rows = db.session.execute(
            text(
                """
                SELECT TOP (:limit)
                       f.FollowUpID, f.CustomerID, f.LeadID, f.FollowUpType, f.Subject,
                       f.DueAt, f.Priority, f.AssignedUserID, f.AssignedUserName,
                       cm.CustomerName, l.FullName AS LeadName
                FROM dbo.CrmFollowUp f
                LEFT JOIN dbo.CustomerMaster cm ON cm.CustomerID = f.CustomerID
                LEFT JOIN dbo.CrmLead l ON l.LeadID = f.LeadID
                WHERE f.IsActive = 1 AND f.Status = N'Pending'
                ORDER BY f.DueAt ASC
                """
            ),
            {"limit": min(max(1, limit), 200)},
        ).mappings().all()
        return [dict(r) for r in rows]

    def pending_documents_count(self) -> dict:
        ensure_crm_schema()
        customers_with_docs = db.session.execute(
            text(
                """
                SELECT COUNT(DISTINCT CustomerID)
                FROM dbo.CrmDocument
                WHERE IsActive = 1
                """
            ),
        ).scalar() or 0
        active_customers = db.session.execute(
            text(
                """
                SELECT COUNT(1) FROM dbo.CustomerMaster
                WHERE CustomerStatus = N'Active'
                """
            ),
        ).scalar() or 0
        pending = max(0, int(active_customers) - int(customers_with_docs))
        return {
            "active_customers": int(active_customers),
            "customers_with_documents": int(customers_with_docs),
            "customers_without_documents": pending,
        }

    def staff_performance(self, *, days: int = 30) -> list[dict]:
        ensure_crm_schema()
        since = datetime.utcnow() - timedelta(days=max(1, days))
        rows = db.session.execute(
            text(
                """
                SELECT AssignedUserID, AssignedUserName, COUNT(1) AS CompletedCount
                FROM dbo.CrmTask
                WHERE IsActive = 1 AND Status = N'Completed'
                  AND CompletedDate >= :since
                  AND AssignedUserID IS NOT NULL
                GROUP BY AssignedUserID, AssignedUserName
                ORDER BY CompletedCount DESC, AssignedUserName
                """
            ),
            {"since": since},
        ).mappings().all()
        return [
            {
                "assigned_user_id": r["AssignedUserID"],
                "assigned_user_name": r["AssignedUserName"],
                "tasks_completed": int(r["CompletedCount"]),
            }
            for r in rows
        ]

    def daily_activity(self, *, days: int = 14) -> list[dict]:
        ensure_crm_schema()
        start = date.today() - timedelta(days=max(1, days) - 1)
        rows = db.session.execute(
            text(
                """
                SELECT CAST(CreatedDate AS DATE) AS ActivityDate, COUNT(1) AS EventCount
                FROM dbo.CrmTimelineEvent
                WHERE CreatedDate >= :start
                GROUP BY CAST(CreatedDate AS DATE)
                ORDER BY ActivityDate ASC
                """
            ),
            {"start": start},
        ).mappings().all()
        counts = {r["ActivityDate"]: int(r["EventCount"]) for r in rows}
        result = []
        for offset in range(days):
            day = start + timedelta(days=offset)
            result.append(
                {
                    "date": day.isoformat(),
                    "event_count": counts.get(day, 0),
                }
            )
        return result
