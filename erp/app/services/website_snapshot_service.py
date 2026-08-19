"""Public login-page Business Snapshot. Reuses dashboard + P&L logic only."""

from __future__ import annotations

from calendar import month_abbr
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.extensions import db
from app.services.dashboard_service import DashboardService
from app.services.financial_statements.engine import (
    RECEIVABLE_GROUP_NAMES,
    ZERO,
    FinancialReportEngine,
)
from app.services.financial_statements.reports import FinancialStatementsService

PAYABLE_GROUP_NAMES = {"sundry creditors"}


class WebsiteSnapshotService:
    def __init__(self) -> None:
        self.dashboard = DashboardService()
        self.engine = FinancialReportEngine()
        self.statements = FinancialStatementsService(self.engine)

    @staticmethod
    def _money(value) -> float:
        return float(Decimal(str(value or 0)).quantize(Decimal("0.01")))

    @staticmethod
    def _card(value, *, available: bool = True) -> dict[str, Any]:
        if not available:
            return {"available": False, "value": None}
        return {"available": True, "value": WebsiteSnapshotService._money(value)}

    def _month_period(self, today: date | None = None) -> tuple[date, date]:
        return self.dashboard.month_bounds(today)

    def _daily_series(self, date_from: date, date_to: date) -> dict[str, Any]:
        rows = db.session.execute(
            text(
                """
                SELECT
                    TransactionDate AS txn_date,
                    ISNULL(SUM(SaleAmount), 0) AS sales,
                    ISNULL(SUM(IncomeAmount), 0) AS income,
                    ISNULL(SUM(ExpenseAmount), 0) AS expense
                FROM JTCSDailyTransaction
                WHERE TransactionDate >= :date_from
                  AND TransactionDate <= :date_to
                  AND Status = N'Posted'
                GROUP BY TransactionDate
                ORDER BY TransactionDate
                """
            ),
            {"date_from": date_from, "date_to": date_to},
        ).mappings().all()
        by_day = {
            row["txn_date"]: {
                "sales": Decimal(str(row["sales"] or 0)),
                "income": Decimal(str(row["income"] or 0)),
                "expense": Decimal(str(row["expense"] or 0)),
            }
            for row in rows
            if row["txn_date"]
        }
        labels: list[str] = []
        sales: list[float] = []
        income: list[float] = []
        expense: list[float] = []
        cursor = date_from
        while cursor <= date_to:
            bucket = by_day.get(cursor) or {}
            labels.append(str(cursor.day))
            sales.append(self._money(bucket.get("sales") or 0))
            income.append(self._money(bucket.get("income") or 0))
            expense.append(self._money(bucket.get("expense") or 0))
            cursor += timedelta(days=1)
        return {
            "labels": labels,
            "sales": sales,
            "income": income,
            "expense": expense,
        }

    def _month_profit(self, date_from: date, date_to: date) -> dict[str, Any]:
        pnl = self.statements.profit_and_loss(date_from, date_to)
        net = pnl.get("net_profit")
        if net is None:
            return self._card(None, available=False)
        return self._card(net)

    def _group_is_payable(self, group_id: int | None, by_id: dict[int, dict]) -> bool:
        cur = by_id.get(int(group_id)) if group_id else None
        seen: set[int] = set()
        hops = 0
        while cur and hops < 40:
            gid = int(cur["GroupID"])
            if gid in seen:
                break
            seen.add(gid)
            name = (cur.get("GroupName") or "").strip().casefold()
            if name in PAYABLE_GROUP_NAMES:
                return True
            pid = cur.get("ParentGroupID")
            cur = by_id.get(int(pid)) if pid else None
            hops += 1
        return False

    def _receivable_payable(self, as_of: date) -> tuple[dict[str, Any], dict[str, Any]]:
        fy_start = self.engine.fy_start(as_of)
        ledgers = self.engine.compute_ledger_balances(date_from=fy_start, date_to=as_of)
        groups_by_id = {int(g["GroupID"]): g for g in self.engine.load_groups(active_only=False)}
        receivable = ZERO
        payable = ZERO
        saw_receivable = False
        saw_payable = False
        for led in ledgers:
            gid = led.get("group_id")
            if self.engine._group_is_receivable(gid, groups_by_id):
                saw_receivable = True
                receivable += self.engine.money(led.get("closing"))
            elif self._group_is_payable(gid, groups_by_id):
                saw_payable = True
                payable += self.engine.money(led.get("closing"))
        return (
            self._card(receivable, available=saw_receivable),
            self._card(payable, available=saw_payable),
        )

    def get_snapshot(self, today: date | None = None) -> dict[str, Any]:
        today = today or date.today()
        date_from, date_to = self._month_period(today)
        period_label = f"{month_abbr[today.month].upper()} {today.year}"

        metrics = self.dashboard.get_metrics(date_from, date_to)
        series = self._daily_series(date_from, date_to)

        profit = self._card(None, available=False)
        try:
            profit = self._month_profit(date_from, date_to)
        except Exception:
            db.session.rollback()
            profit = self._card(None, available=False)

        receivable = self._card(None, available=False)
        payable = self._card(None, available=False)
        try:
            receivable, payable = self._receivable_payable(date_to)
        except Exception:
            db.session.rollback()

        return {
            "ok": True,
            "period": {
                "label": period_label,
                "month": today.month,
                "year": today.year,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
            },
            "cards": {
                "sales": self._card(metrics.total_sales),
                "income": self._card(sum(series["income"])),
                "expense": self._card(metrics.total_expenses),
                "profit": profit,
                "bank": self._card(metrics.bank_closing_balance),
                "cash": self._card(metrics.cash_closing_balance),
                "receivable": receivable,
                "payable": payable,
            },
            "charts": {
                "sales_income": {
                    "labels": series["labels"],
                    "sales": series["sales"],
                    "income": series["income"],
                },
                "income_expense": {
                    "labels": series["labels"],
                    # Same series as dashboard analytics: IncomeAmount + SaleAmount vs Expense.
                    "income": [
                        round(s + i, 2)
                        for s, i in zip(series["sales"], series["income"])
                    ],
                    "expense": series["expense"],
                },
            },
        }
