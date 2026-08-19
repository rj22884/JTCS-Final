"""Tests for Customer Master CoA→Customer Group filter and FS classification."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.customer_group_service import CustomerGroupService
from app.services.financial_statements.engine import FinancialReportEngine


def test_html_field_order() -> None:
    html = (ROOT / "app" / "templates" / "masters" / "customer_master.html").read_text(
        encoding="utf-8"
    )
    chart_pos = html.find('for="cm_chart_groups"')
    group_pos = html.find('for="cm_customer_group"')
    assert chart_pos > 0 and group_pos > 0
    assert chart_pos < group_pos, "Chart of Account Group must appear before Customer Group"
    assert 'id="cmChartGroupBar"' in html
    assert "d-none" not in html[html.find("cmChartGroupBar") : html.find("cmChartGroupBar") + 80]


def test_customer_group_filter() -> None:
    fn = CustomerGroupService.filter_codes_for_chart
    usage = {"ITR": [10], "GST": [20], "TDS": [10, 11]}
    natures = {10: "Asset", 11: "Asset", 20: "Income"}
    asset_codes = fn(
        active_codes=["ITR", "GST", "TDS", "MISC"],
        chart_group_id=10,
        chart_nature="Asset",
        usage=usage,
        nature_by_chart_id=natures,
    )
    assert "ITR" in asset_codes
    assert "TDS" in asset_codes
    assert "MISC" in asset_codes  # unused stays available
    assert "GST" not in asset_codes  # used only with Income

    income_codes = fn(
        active_codes=["ITR", "GST", "TDS", "MISC"],
        chart_group_id=20,
        chart_nature="Income",
        usage=usage,
        nature_by_chart_id=natures,
    )
    assert "GST" in income_codes
    assert "ITR" not in income_codes
    assert "MISC" in income_codes

    none = fn(
        active_codes=["ITR"],
        chart_group_id=None,
        chart_nature="Asset",
        usage=usage,
        nature_by_chart_id=natures,
    )
    assert none == []

    legacy = fn(
        active_codes=["ITR", "GST"],
        chart_group_id=10,
        chart_nature="Asset",
        usage=usage,
        nature_by_chart_id=natures,
        include_code="GST",
    )
    assert "GST" in legacy


def test_trading_group_uses_chart_hierarchy() -> None:
    engine = FinancialReportEngine()
    by_id = {
        1: {
            "GroupID": 1,
            "GroupName": "Direct Incomes",
            "ParentGroupID": None,
            "GroupNature": "Income",
            "UnderType": "Liabilities",
        },
        2: {
            "GroupID": 2,
            "GroupName": "Consulting Fees",
            "ParentGroupID": 1,
            "GroupNature": "Income",
            "UnderType": "Liabilities",
        },
        3: {
            "GroupID": 3,
            "GroupName": "Indirect Incomes",
            "ParentGroupID": None,
            "GroupNature": "Income",
            "UnderType": "Liabilities",
        },
        4: {
            "GroupID": 4,
            "GroupName": "Rent Income",
            "ParentGroupID": 3,
            "GroupNature": "Income",
            "UnderType": "Liabilities",
        },
        5: {
            "GroupID": 5,
            "GroupName": "Individual Client",
            "ParentGroupID": None,
            "GroupNature": "Asset",
            "UnderType": "Assets",
        },
    }
    assert engine.is_trading_group(1, by_id) is True
    assert engine.is_trading_group(2, by_id) is True
    assert engine.is_trading_group(3, by_id) is False
    assert engine.is_trading_group(4, by_id) is False
    assert engine.is_trading_group(5, by_id) is False
    assert engine._nature_from_group(by_id[5], by_id) == "Asset"
    assert engine._nature_from_group(by_id[2], by_id) == "Income"


def test_live_reports() -> dict:
    from decimal import Decimal

    from app import create_app
    from app.services.financial_statements.reports import FinancialStatementsService

    app = create_app()
    out = {}
    with app.app_context():
        svc = FinancialStatementsService()
        tb = svc.trial_balance(*svc.resolve_period(None, None))
        out["tb_balanced"] = bool(tb.get("balanced"))
        out["tb_debit"] = str(tb.get("total_debit"))
        out["tb_credit"] = str(tb.get("total_credit"))
        diff = abs(svc.engine.money(tb.get("total_debit")) - svc.engine.money(tb.get("total_credit")))
        out["tb_diff"] = str(diff)
        assert diff < Decimal("0.01"), f"Trial Balance Dr/Cr mismatch: {diff}"

        bs = svc.balance_sheet(*svc.resolve_period(None, None))
        out["bs_layout"] = bs.get("layout")
        assert bs.get("layout") == "tally-bs"
        for node in (bs.get("right") or {}).get("nodes") or []:
            assert (node.get("GroupNature") or "Asset") in {"Asset", "Liability"}

        pnl = svc.profit_and_loss(*svc.resolve_period(None, None))
        out["pnl_net"] = str(pnl.get("net_profit"))
        titles = [s.get("title") for s in pnl.get("sections") or []]
        assert "Direct Income" in titles
        assert "Indirect Expenses" in titles

        trading = svc.trading_account(*svc.resolve_period(None, None))
        t_titles = [s.get("title") for s in trading.get("sections") or []]
        assert "Direct Income" in t_titles
        assert "Indirect Income" not in t_titles

        for key in ("cash_flow", "fund_flow", "depreciation_chart", "ratio_analysis"):
            getattr(svc, key)(*svc.resolve_period(None, None))
            out[key] = "ok"
    return out


def main() -> int:
    test_html_field_order()
    print("TEST 1 HTML order: PASS")
    test_customer_group_filter()
    print("TEST 2/3 filter + invalid combo: PASS")
    test_trading_group_uses_chart_hierarchy()
    print("TEST 9 trading classification: PASS")
    live = {}
    try:
        live = test_live_reports()
        print("TEST 5-8,10-12 live reports: PASS", live)
    except Exception as exc:  # noqa: BLE001
        print("LIVE REPORTS skipped/failed:", exc)
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
