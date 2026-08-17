"""CRM calendar — tasks and follow-up due dates."""

from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import text

from app.extensions import db
from app.modules.shared.schema import ensure_crm_schema


class CalendarService:
    def list_events(
        self,
        *,
        from_date: date | datetime | None = None,
        to_date: date | datetime | None = None,
    ) -> list[dict]:
        ensure_crm_schema()
        start = self._as_datetime(from_date, end_of_day=False)
        end = self._as_datetime(to_date, end_of_day=True)
        if start is None:
            start = datetime.combine(date.today(), time.min)
        if end is None:
            end = datetime.combine(date.today(), time.max)

        events: list[dict] = []

        task_rows = db.session.execute(
            text(
                """
                SELECT TaskID, CustomerID, LeadID, Title, Status, Priority, Deadline,
                       AssignedUserID, AssignedUserName
                FROM dbo.CrmTask
                WHERE IsActive = 1 AND Deadline IS NOT NULL
                  AND Deadline >= :start AND Deadline <= :end
                ORDER BY Deadline ASC
                """
            ),
            {"start": start, "end": end},
        ).mappings().all()
        for row in task_rows:
            events.append(
                {
                    "event_type": "task",
                    "event_id": row["TaskID"],
                    "title": row["Title"],
                    "starts_at": row["Deadline"],
                    "status": row["Status"],
                    "priority": row["Priority"],
                    "customer_id": row["CustomerID"],
                    "lead_id": row["LeadID"],
                    "assigned_user_id": row["AssignedUserID"],
                    "assigned_user_name": row["AssignedUserName"],
                }
            )

        followup_rows = db.session.execute(
            text(
                """
                SELECT FollowUpID, CustomerID, LeadID, FollowUpType, Subject, Status,
                       Priority, DueAt, AssignedUserID, AssignedUserName
                FROM dbo.CrmFollowUp
                WHERE IsActive = 1
                  AND DueAt >= :start AND DueAt <= :end
                ORDER BY DueAt ASC
                """
            ),
            {"start": start, "end": end},
        ).mappings().all()
        for row in followup_rows:
            events.append(
                {
                    "event_type": "followup",
                    "event_id": row["FollowUpID"],
                    "title": row["Subject"] or row["FollowUpType"],
                    "starts_at": row["DueAt"],
                    "status": row["Status"],
                    "priority": row["Priority"],
                    "followup_type": row["FollowUpType"],
                    "customer_id": row["CustomerID"],
                    "lead_id": row["LeadID"],
                    "assigned_user_id": row["AssignedUserID"],
                    "assigned_user_name": row["AssignedUserName"],
                }
            )

        try:
            from app.services.hr_service import list_calendar_events

            events.extend(list_calendar_events(start, end))
        except Exception:
            db.session.rollback()

        events.sort(key=lambda e: e.get("starts_at") or datetime.min)
        return events

    @staticmethod
    def _as_datetime(value: date | datetime | None, *, end_of_day: bool) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if end_of_day:
            return datetime.combine(value, time.max)
        return datetime.combine(value, time.min)
