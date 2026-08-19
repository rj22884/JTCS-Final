"""Tally-style financial statement builders on top of FinancialReportEngine."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.extensions import db
from app.services.financial_statements.engine import ZERO, FinancialReportEngine


class FinancialStatementsService:
    REPORTS = (
        ("balance-sheet", "Balance Sheet"),
        ("profit-loss", "Profit & Loss"),
        ("trial-balance", "Trial Balance"),
        ("trading-account", "Trading Account"),
        ("cash-flow", "Cash Flow"),
        ("fund-flow", "Fund Flow"),
        ("depreciation-chart", "Depreciation Chart"),
        ("fixed-assets-schedule", "Schedule of Fixed Assets"),
        ("ratio-analysis", "Ratio Analysis"),
    )

    def __init__(self, engine: FinancialReportEngine | None = None):
        self.engine = engine or FinancialReportEngine()

    def resolve_period(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> tuple[date, date]:
        today = date.today()
        d2 = self.engine.parse_date(date_to, today)
        d1 = self.engine.parse_date(date_from, self.engine.fy_start(d2))
        if d1 > d2:
            d1, d2 = d2, d1
        return d1, d2

    def meta(self, report_key: str, date_from: date, date_to: date) -> dict[str, Any]:
        label = dict(self.REPORTS).get(report_key, report_key)
        return {
            "report_key": report_key,
            "report_title": label,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "fy_label": f"FY {self.engine.fy_start(date_to).year}-{str(self.engine.fy_start(date_to).year + 1)[2:]}",
        }

    def build(
        self,
        report_key: str,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        d1, d2 = self.resolve_period(date_from, date_to)
        key = (report_key or "balance-sheet").strip().lower()
        builders = {
            "balance-sheet": self.balance_sheet,
            "profit-loss": self.profit_and_loss,
            "trial-balance": self.trial_balance,
            "trading-account": self.trading_account,
            "cash-flow": self.cash_flow,
            "fund-flow": self.fund_flow,
            "depreciation-chart": self.depreciation_chart,
            "fixed-assets-schedule": self.fixed_assets_schedule,
            "ratio-analysis": self.ratio_analysis,
        }
        fn = builders.get(key, self.balance_sheet)
        payload = fn(d1, d2, search=search)
        payload["meta"] = self.meta(key, d1, d2)
        return payload

    def balance_sheet(
        self, date_from: date, date_to: date, *, search: str | None = None
    ) -> dict[str, Any]:
        """Liabilities (left) / Assets (right) — Tally layout."""
        ledgers = self.engine.compute_ledger_balances(
            date_from=date_from, date_to=date_to, search=search
        )
        # Hide ledgers whose closing is zero for the selected period
        # (opening + period movements within From–To).
        ledgers = [
            led
            for led in ledgers
            if abs(self.engine.money(led.get("closing"))) >= Decimal("0.01")
        ]
        liabilities = self.engine.sort_tally_roots(
            self.engine.rollup_groups(ledgers, natures={"Liability"}),
            side="liability",
        )
        assets = self.engine.sort_tally_roots(
            self.engine.rollup_groups(ledgers, natures={"Asset"}),
            side="asset",
        )
        # P&L net transferred to BS
        pl = self._pl_net(ledgers)
        if pl != ZERO:
            liabilities.append(
                {
                    "GroupID": 0,
                    "GroupName": "Profit & Loss A/c",
                    "GroupNature": "Liability",
                    "children": [],
                    "ledgers": [],
                    "closing": pl,
                    "display_closing": abs(pl),
                    "has_children": False,
                    "is_pl_transfer": True,
                }
            )
        liab_total = sum((self.engine.money(n["closing"]) for n in liabilities), ZERO)
        asset_total = sum((self.engine.money(n["closing"]) for n in assets), ZERO)
        return {
            "layout": "tally-bs",
            "left": {"title": "Liabilities", "nodes": liabilities, "total": liab_total},
            "right": {"title": "Assets", "nodes": assets, "total": asset_total},
            "difference": self.engine.money(asset_total - liab_total),
            "balanced": abs(asset_total - liab_total) < Decimal("0.01"),
        }

    def _pl_net(self, ledgers: list[dict[str, Any]]) -> Decimal:
        income = sum(
            (self.engine.money(l["closing"]) for l in ledgers if l.get("nature") == "Income"),
            ZERO,
        )
        expense = sum(
            (self.engine.money(l["closing"]) for l in ledgers if l.get("nature") == "Expense"),
            ZERO,
        )
        return income - expense

    def profit_and_loss(
        self, date_from: date, date_to: date, *, search: str | None = None
    ) -> dict[str, Any]:
        ledgers = self.engine.compute_ledger_balances(
            date_from=date_from, date_to=date_to, search=search
        )
        incomes = [l for l in ledgers if l.get("nature") == "Income"]
        expenses = [l for l in ledgers if l.get("nature") == "Expense"]
        groups_by_id = {
            int(g["GroupID"]): g for g in self.engine.load_groups(active_only=False)
        }

        def is_direct(led: dict) -> bool:
            return self.engine.is_trading_group(led.get("group_id"), groups_by_id)

        direct_income = self.engine.rollup_groups(
            [l for l in incomes if is_direct(l)], natures={"Income"}
        )
        indirect_income = self.engine.rollup_groups(
            [l for l in incomes if not is_direct(l)], natures={"Income"}
        )
        direct_expense = self.engine.rollup_groups(
            [l for l in expenses if is_direct(l)], natures={"Expense"}
        )
        indirect_expense = self.engine.rollup_groups(
            [l for l in expenses if not is_direct(l)], natures={"Expense"}
        )

        di = sum((self.engine.money(n["closing"]) for n in direct_income), ZERO)
        de = sum((self.engine.money(n["closing"]) for n in direct_expense), ZERO)
        ii = sum((self.engine.money(n["closing"]) for n in indirect_income), ZERO)
        ie = sum((self.engine.money(n["closing"]) for n in indirect_expense), ZERO)
        gross = di - de
        net = gross + ii - ie
        return {
            "layout": "pnl",
            "sections": [
                {"title": "Direct Income", "nodes": direct_income, "total": di},
                {"title": "Direct Expenses", "nodes": direct_expense, "total": de},
                {"title": "Gross Profit / (Loss)", "nodes": [], "total": gross, "emphasis": True},
                {"title": "Indirect Income", "nodes": indirect_income, "total": ii},
                {"title": "Indirect Expenses", "nodes": indirect_expense, "total": ie},
                {"title": "Net Profit / (Loss)", "nodes": [], "total": net, "emphasis": True},
            ],
            "gross_profit": gross,
            "net_profit": net,
        }

    def trial_balance(
        self, date_from: date, date_to: date, *, search: str | None = None
    ) -> dict[str, Any]:
        ledgers = self.engine.compute_ledger_balances(
            date_from=date_from, date_to=date_to, search=search
        )
        rows = []
        total_dr = ZERO
        total_cr = ZERO
        for led in sorted(ledgers, key=lambda x: (x.get("group_name") or "", x.get("ledger_name") or "")):
            closing = self.engine.money(led["closing"])
            if closing == ZERO and led["debit"] == ZERO and led["credit"] == ZERO:
                continue
            nature = led.get("nature") or "Asset"
            if nature in {"Asset", "Expense"}:
                dr = closing if closing > 0 else ZERO
                cr = abs(closing) if closing < 0 else ZERO
            else:
                cr = closing if closing > 0 else ZERO
                dr = abs(closing) if closing < 0 else ZERO
            # Prefer period movement presentation with opening absorbed into closing TB
            rows.append(
                {
                    "ledger_key": led["ledger_key"],
                    "ledger_name": led["ledger_name"],
                    "group_name": led["group_name"],
                    "nature": nature,
                    "opening": led["opening"],
                    "debit": dr,
                    "credit": cr,
                    "period_debit": led["debit"],
                    "period_credit": led["credit"],
                    "customer_group": led.get("customer_group") or "",
                }
            )
            total_dr += dr
            total_cr += cr
        # Force balance with suspense if tiny rounding / incomplete mapping
        diff = self.engine.money(total_dr - total_cr)
        if abs(diff) >= Decimal("0.01"):
            if diff > 0:
                rows.append(
                    {
                        "ledger_key": "suspense-cr",
                        "ledger_name": "Difference in Opening Balances",
                        "group_name": "Suspense A/c",
                        "nature": "Liability",
                        "opening": ZERO,
                        "debit": ZERO,
                        "credit": diff,
                        "period_debit": ZERO,
                        "period_credit": ZERO,
                        "is_balancing": True,
                    }
                )
                total_cr += diff
            else:
                rows.append(
                    {
                        "ledger_key": "suspense-dr",
                        "ledger_name": "Difference in Opening Balances",
                        "group_name": "Suspense A/c",
                        "nature": "Asset",
                        "opening": ZERO,
                        "debit": abs(diff),
                        "credit": ZERO,
                        "period_debit": ZERO,
                        "period_credit": ZERO,
                        "is_balancing": True,
                    }
                )
                total_dr += abs(diff)
        return {
            "layout": "trial-balance",
            "rows": rows,
            "total_debit": total_dr,
            "total_credit": total_cr,
            "balanced": abs(total_dr - total_cr) < Decimal("0.01"),
        }

    def trading_account(
        self, date_from: date, date_to: date, *, search: str | None = None
    ) -> dict[str, Any]:
        pnl = self.profit_and_loss(date_from, date_to, search=search)
        sections = [s for s in pnl["sections"] if s["title"] in {
            "Direct Income", "Direct Expenses", "Gross Profit / (Loss)"
        }]
        return {"layout": "trading", "sections": sections, "gross_profit": pnl["gross_profit"]}

    def cash_flow(
        self, date_from: date, date_to: date, *, search: str | None = None
    ) -> dict[str, Any]:
        self.engine.ensure_schema()
        cash_group_ids = self.engine.group_ids_under_names({"cash-in-hand", "bank accounts"})
        gid_sql = "1 = 0"
        params: dict[str, Any] = {"d1": date_from, "d2": date_to}
        if cash_group_ids:
            placeholders = []
            for i, gid in enumerate(sorted(cash_group_ids)):
                key = f"cg{i}"
                placeholders.append(f":{key}")
                params[key] = gid
            gid_sql = "g.GroupID IN (" + ", ".join(placeholders) + ")"
        rows = db.session.execute(
            text(
                f"""
                SELECT
                    ISNULL(t.LedgerKind, N'OTHER') AS kind,
                    SUM(ISNULL(t.Debit, 0)) AS debit,
                    SUM(ISNULL(t.Credit, 0)) AS credit
                FROM dbo.JtcsBankTransaction t
                INNER JOIN dbo.JtcsBankAccountMaster b
                    ON b.JtcsBankAccountID = t.JtcsBankAccountID
                LEFT JOIN dbo.ChartOfGroupMaster g ON g.GroupID = b.ChartGroupID
                WHERE t.TransactionDate >= :d1 AND t.TransactionDate <= :d2
                  AND (
                        LOWER(LTRIM(RTRIM(ISNULL(b.BankName, N'')))) = N'cash'
                     OR LOWER(LTRIM(RTRIM(ISNULL(b.AccountNumber, N'')))) = N'cash'
                     OR {gid_sql}
                  )
                GROUP BY ISNULL(t.LedgerKind, N'OTHER')
                """
            ),
            params,
        ).mappings().all()
        operating_in = ZERO
        operating_out = ZERO
        investing = ZERO
        financing = ZERO
        detail = []
        for r in rows:
            kind = (r.get("kind") or "").upper()
            debit = self.engine.money(r["debit"])
            credit = self.engine.money(r["credit"])
            detail.append({"kind": kind, "debit": debit, "credit": credit})
            if kind in {"RECEIPT", "PAYMENT", "OTHER"}:
                operating_in += credit
                operating_out += debit
            elif "CONTRA" in kind:
                investing += credit - debit
            else:
                financing += credit - debit
        net = operating_in - operating_out + investing + financing
        return {
            "layout": "cash-flow",
            "sections": [
                {"title": "Operating Activities (Inflows)", "amount": operating_in},
                {"title": "Operating Activities (Outflows)", "amount": operating_out},
                {"title": "Investing / Contra (Net)", "amount": investing},
                {"title": "Financing / Other (Net)", "amount": financing},
                {"title": "Net Increase / (Decrease) in Cash", "amount": net, "emphasis": True},
            ],
            "detail": detail,
        }

    def fund_flow(
        self, date_from: date, date_to: date, *, search: str | None = None
    ) -> dict[str, Any]:
        """Simplified fund flow from movement in BS groups."""
        ledgers = self.engine.compute_ledger_balances(
            date_from=date_from, date_to=date_to, search=search
        )
        sources = []
        applications = []
        for led in ledgers:
            if led.get("nature") not in {"Asset", "Liability"}:
                continue
            mv = self.engine.money(led["debit"] - led["credit"])
            if led.get("nature") == "Liability":
                change = self.engine.money(led["credit"] - led["debit"])
                if change > 0:
                    sources.append({"name": led["ledger_name"], "amount": change})
                elif change < 0:
                    applications.append({"name": led["ledger_name"], "amount": abs(change)})
            else:
                change = self.engine.money(led["debit"] - led["credit"])
                if change > 0:
                    applications.append({"name": led["ledger_name"], "amount": change})
                elif change < 0:
                    sources.append({"name": led["ledger_name"], "amount": abs(change)})
        src_total = sum((self.engine.money(x["amount"]) for x in sources), ZERO)
        app_total = sum((self.engine.money(x["amount"]) for x in applications), ZERO)
        return {
            "layout": "fund-flow",
            "sources": sources,
            "applications": applications,
            "sources_total": src_total,
            "applications_total": app_total,
        }

    def depreciation_chart(
        self, date_from: date, date_to: date, *, search: str | None = None
    ) -> dict[str, Any]:
        self.engine.ensure_schema()
        self._recompute_depreciation(date_to)
        needle = (search or "").strip().lower()
        fa_group_ids = self.engine.group_ids_under_names({"fixed assets"})
        rows = db.session.execute(
            text(
                """
                SELECT AssetID, AssetName, PurchaseDate, PurchaseValue, DepreciationRate,
                       OpeningAccumulatedDep, CurrentYearDepreciation,
                       AccumulatedDepreciation, WDV, Method, GroupID, AccountID
                FROM dbo.FixedAssetMaster
                WHERE IsActive = 1
                ORDER BY AssetName
                """
            )
        ).mappings().all()
        account_group: dict[int, int] = {}
        try:
            coa_rows = db.session.execute(
                text("SELECT AccountID, GroupID FROM dbo.ChartOfAccountMaster WHERE IsActive = 1")
            ).mappings().all()
            account_group = {
                int(r["AccountID"]): int(r["GroupID"])
                for r in coa_rows
                if r.get("AccountID") and r.get("GroupID")
            }
        except Exception:
            db.session.rollback()
        out = []
        seen_accounts: set[int] = set()
        for r in rows:
            if needle and needle not in (r.get("AssetName") or "").lower():
                continue
            gid = r.get("GroupID")
            aid = r.get("AccountID")
            mapped_gid = account_group.get(int(aid)) if aid else None
            in_fa = False
            if not fa_group_ids:
                in_fa = True
            elif gid and int(gid) in fa_group_ids:
                in_fa = True
            elif mapped_gid and mapped_gid in fa_group_ids:
                in_fa = True
            elif not gid and not mapped_gid:
                in_fa = True
            if not in_fa:
                continue
            if aid:
                seen_accounts.add(int(aid))
            out.append(
                {
                    "asset_id": r["AssetID"],
                    "asset_name": r["AssetName"],
                    "purchase_date": r["PurchaseDate"].isoformat() if r["PurchaseDate"] else "",
                    "purchase_value": self.engine.money(r["PurchaseValue"]),
                    "depreciation_rate": self.engine.money(r["DepreciationRate"]),
                    "opening_accumulated": self.engine.money(r["OpeningAccumulatedDep"]),
                    "current_year_depreciation": self.engine.money(r["CurrentYearDepreciation"]),
                    "accumulated_depreciation": self.engine.money(r["AccumulatedDepreciation"]),
                    "wdv": self.engine.money(r["WDV"]),
                    "method": r.get("Method") or "WDV",
                }
            )
        if fa_group_ids:
            ledgers = self.engine.compute_ledger_balances(
                date_from=date_from, date_to=date_to, search=search
            )
            for led in ledgers:
                aid = led.get("account_id")
                if not aid or int(aid) in seen_accounts:
                    continue
                if int(led.get("group_id") or 0) not in fa_group_ids:
                    continue
                if abs(self.engine.money(led.get("closing"))) < Decimal("0.01") and abs(
                    self.engine.money(led.get("opening"))
                ) < Decimal("0.01"):
                    continue
                opening = self.engine.money(led.get("opening"))
                closing = self.engine.money(led.get("closing"))
                out.append(
                    {
                        "asset_id": None,
                        "asset_name": led.get("ledger_name") or "",
                        "purchase_date": "",
                        "purchase_value": abs(opening) if opening else abs(closing),
                        "depreciation_rate": ZERO,
                        "opening_accumulated": ZERO,
                        "current_year_depreciation": ZERO,
                        "accumulated_depreciation": ZERO,
                        "wdv": abs(closing),
                        "method": "WDV",
                    }
                )
        return {
            "layout": "depreciation",
            "rows": out,
            "totals": {
                "purchase_value": sum((r["purchase_value"] for r in out), ZERO),
                "current_year_depreciation": sum((r["current_year_depreciation"] for r in out), ZERO),
                "accumulated_depreciation": sum((r["accumulated_depreciation"] for r in out), ZERO),
                "wdv": sum((r["wdv"] for r in out), ZERO),
            },
        }

    def fixed_assets_schedule(
        self, date_from: date, date_to: date, *, search: str | None = None
    ) -> dict[str, Any]:
        chart = self.depreciation_chart(date_from, date_to, search=search)
        return {
            "layout": "fixed-assets",
            "rows": chart["rows"],
            "totals": chart["totals"],
        }

    def ratio_analysis(
        self, date_from: date, date_to: date, *, search: str | None = None
    ) -> dict[str, Any]:
        bs = self.balance_sheet(date_from, date_to, search=search)
        pnl = self.profit_and_loss(date_from, date_to, search=search)
        assets = self.engine.money(bs["right"]["total"])
        liabilities = self.engine.money(bs["left"]["total"])
        net_profit = self.engine.money(pnl["net_profit"])
        # Approximate current assets / liabilities from top-level group names
        ca = sum(
            (
                self.engine.money(n["closing"])
                for n in bs["right"]["nodes"]
                if "current asset" in (n.get("GroupName") or "").lower()
            ),
            ZERO,
        )
        cl = sum(
            (
                self.engine.money(n["closing"])
                for n in bs["left"]["nodes"]
                if "current liab" in (n.get("GroupName") or "").lower()
            ),
            ZERO,
        )
        if ca == ZERO:
            ca = assets
        if cl == ZERO:
            cl = liabilities if liabilities else Decimal("1")

        def ratio(num: Decimal, den: Decimal) -> Decimal | None:
            if den == ZERO:
                return None
            return (num / den).quantize(Decimal("0.01"))

        ratios = [
            {"name": "Current Ratio", "value": ratio(ca, cl), "formula": "Current Assets / Current Liabilities"},
            {"name": "Debt-Equity (approx)", "value": ratio(liabilities, assets - liabilities if assets > liabilities else Decimal("1")), "formula": "Liabilities / Capital"},
            {"name": "Net Profit Ratio (%)", "value": ratio(net_profit * 100, abs(pnl.get("sections", [{}])[0].get("total") or Decimal("1"))), "formula": "Net Profit / Direct Income × 100"},
            {"name": "Return on Assets (%)", "value": ratio(net_profit * 100, assets if assets else Decimal("1")), "formula": "Net Profit / Total Assets × 100"},
            {"name": "Gross Profit Ratio (%)", "value": ratio(self.engine.money(pnl["gross_profit"]) * 100, abs(pnl.get("sections", [{}])[0].get("total") or Decimal("1"))), "formula": "Gross Profit / Direct Income × 100"},
        ]
        return {"layout": "ratios", "ratios": ratios, "assets": assets, "liabilities": liabilities, "net_profit": net_profit}

    def _recompute_depreciation(self, as_of: date) -> None:
        rows = db.session.execute(
            text(
                """
                SELECT AssetID, PurchaseDate, PurchaseValue, DepreciationRate,
                       OpeningAccumulatedDep, Method
                FROM dbo.FixedAssetMaster WHERE IsActive = 1
                """
            )
        ).mappings().all()
        fy_start = self.engine.fy_start(as_of)
        for r in rows:
            purchase = r["PurchaseDate"]
            if isinstance(purchase, datetime):
                purchase = purchase.date()
            rate = self.engine.money(r["DepreciationRate"])
            cost = self.engine.money(r["PurchaseValue"])
            open_acc = self.engine.money(r["OpeningAccumulatedDep"])
            method = (r.get("Method") or "WDV").upper()
            wdv_open = cost - open_acc
            if wdv_open < ZERO:
                wdv_open = ZERO
            # Full year if purchased before FY; else proportionate months
            if purchase and purchase > as_of:
                cy = ZERO
            else:
                months = 12
                if purchase and purchase > fy_start:
                    months = max(1, (as_of.year - purchase.year) * 12 + as_of.month - purchase.month + 1)
                    months = min(12, months)
                if method == "SL":
                    cy = (cost * rate / Decimal("100") * Decimal(months) / Decimal("12")).quantize(Decimal("0.01"))
                else:
                    cy = (wdv_open * rate / Decimal("100") * Decimal(months) / Decimal("12")).quantize(Decimal("0.01"))
            acc = open_acc + cy
            wdv = cost - acc
            if wdv < ZERO:
                wdv = ZERO
            db.session.execute(
                text(
                    """
                    UPDATE dbo.FixedAssetMaster
                    SET CurrentYearDepreciation = :cy,
                        AccumulatedDepreciation = :acc,
                        WDV = :wdv,
                        UpdatedDate = SYSUTCDATETIME()
                    WHERE AssetID = :id
                    """
                ),
                {"cy": cy, "acc": acc, "wdv": wdv, "id": r["AssetID"]},
            )
        db.session.commit()

    def serialize_node(self, node: dict) -> dict:
        """JSON-safe tree node."""
        return {
            "group_id": node.get("GroupID"),
            "group_name": node.get("GroupName"),
            "nature": node.get("GroupNature"),
            "closing": str(self.engine.money(node.get("closing"))),
            "display_closing": str(self.engine.money(node.get("display_closing"))),
            "has_children": bool(node.get("has_children")),
            "is_pl_transfer": bool(node.get("is_pl_transfer")),
            "children": [self.serialize_node(c) for c in node.get("children") or []],
            "ledgers": [
                {
                    "ledger_key": l.get("ledger_key"),
                    "ledger_name": l.get("ledger_name"),
                    "group_name": l.get("group_name"),
                    "customer_group": l.get("customer_group") or "",
                    "closing": str(self.engine.money(l.get("closing"))),
                    "display_closing": str(self.engine.money(l.get("display_closing"))),
                    "debit": str(self.engine.money(l.get("debit"))),
                    "credit": str(self.engine.money(l.get("credit"))),
                    "opening": str(self.engine.money(l.get("opening"))),
                    "closing_dr_cr": l.get("closing_dr_cr"),
                }
                for l in node.get("ledgers") or []
            ],
        }

    def to_jsonable(self, payload: dict) -> dict:
        """Convert Decimal/date trees for jsonify."""
        meta = payload.get("meta") or {}
        layout = payload.get("layout")
        out: dict[str, Any] = {"meta": meta, "layout": layout}

        def money_str(v):
            return str(self.engine.money(v))

        if layout == "tally-bs":
            out["left"] = {
                "title": payload["left"]["title"],
                "total": money_str(payload["left"]["total"]),
                "nodes": [self.serialize_node(n) for n in payload["left"]["nodes"]],
            }
            out["right"] = {
                "title": payload["right"]["title"],
                "total": money_str(payload["right"]["total"]),
                "nodes": [self.serialize_node(n) for n in payload["right"]["nodes"]],
            }
            out["difference"] = money_str(payload.get("difference"))
            out["balanced"] = bool(payload.get("balanced"))
        elif layout in {"pnl", "trading"}:
            out["sections"] = [
                {
                    "title": s["title"],
                    "total": money_str(s.get("total")),
                    "emphasis": bool(s.get("emphasis")),
                    "nodes": [self.serialize_node(n) for n in s.get("nodes") or []],
                }
                for s in payload.get("sections") or []
            ]
            if "gross_profit" in payload:
                out["gross_profit"] = money_str(payload["gross_profit"])
            if "net_profit" in payload:
                out["net_profit"] = money_str(payload["net_profit"])
        elif layout == "trial-balance":
            out["rows"] = [
                {
                    **{k: (money_str(v) if k in {"opening", "debit", "credit", "period_debit", "period_credit"} else v)
                       for k, v in r.items()}
                }
                for r in payload.get("rows") or []
            ]
            out["total_debit"] = money_str(payload.get("total_debit"))
            out["total_credit"] = money_str(payload.get("total_credit"))
            out["balanced"] = bool(payload.get("balanced"))
        elif layout == "cash-flow":
            out["sections"] = [
                {"title": s["title"], "amount": money_str(s.get("amount")), "emphasis": bool(s.get("emphasis"))}
                for s in payload.get("sections") or []
            ]
            out["detail"] = [
                {"kind": d["kind"], "debit": money_str(d["debit"]), "credit": money_str(d["credit"])}
                for d in payload.get("detail") or []
            ]
        elif layout == "fund-flow":
            out["sources"] = [{"name": x["name"], "amount": money_str(x["amount"])} for x in payload.get("sources") or []]
            out["applications"] = [{"name": x["name"], "amount": money_str(x["amount"])} for x in payload.get("applications") or []]
            out["sources_total"] = money_str(payload.get("sources_total"))
            out["applications_total"] = money_str(payload.get("applications_total"))
        elif layout in {"depreciation", "fixed-assets"}:
            out["rows"] = [
                {
                    **r,
                    "purchase_value": money_str(r["purchase_value"]),
                    "depreciation_rate": money_str(r["depreciation_rate"]),
                    "opening_accumulated": money_str(r["opening_accumulated"]),
                    "current_year_depreciation": money_str(r["current_year_depreciation"]),
                    "accumulated_depreciation": money_str(r["accumulated_depreciation"]),
                    "wdv": money_str(r["wdv"]),
                }
                for r in payload.get("rows") or []
            ]
            out["totals"] = {k: money_str(v) for k, v in (payload.get("totals") or {}).items()}
        elif layout == "ratios":
            out["ratios"] = [
                {
                    "name": r["name"],
                    "value": None if r["value"] is None else money_str(r["value"]),
                    "formula": r["formula"],
                }
                for r in payload.get("ratios") or []
            ]
            out["assets"] = money_str(payload.get("assets"))
            out["liabilities"] = money_str(payload.get("liabilities"))
            out["net_profit"] = money_str(payload.get("net_profit"))
        return out
