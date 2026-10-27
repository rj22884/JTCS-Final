"""Unit tests for Item Master fixed-asset depreciation (no database)."""
from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.depreciation_service import DepreciationService


def test_car_rate_from_public_chart() -> None:
    svc = DepreciationService()
    # Skip live HTTP in lookup by matching only.
    row = svc._match_block(item_code="CAR", item_name="Car XL6", hsn_sac="870321")
    assert row is not None
    assert row["key"] == "motor-car"
    found = svc.lookup_public_rate(
        purchase_date=date(2025, 10, 31),
        item_code="CAR",
        item_name="Car XL6",
        hsn_sac="870321",
        ping_public=False,
    )
    assert Decimal(found["rate"]) == Decimal("15.00")
    assert found["method"] == "WDV"


def test_computer_rate_change_by_purchase_date() -> None:
    svc = DepreciationService()
    old = svc.lookup_public_rate(
        purchase_date=date(2016, 6, 1),
        item_code="PC",
        item_name="Laptop",
        hsn_sac="8471",
        ping_public=False,
    )
    new = svc.lookup_public_rate(
        purchase_date=date(2024, 6, 1),
        item_code="PC",
        item_name="Laptop",
        hsn_sac="8471",
        ping_public=False,
    )
    assert Decimal(old["rate"]) == Decimal("60.00")
    assert Decimal(new["rate"]) == Decimal("40.00")


def test_half_year_when_used_under_180_days() -> None:
    svc = DepreciationService()
    calc = svc.calculate(
        cost=Decimal("1370000"),
        rate=Decimal("15"),
        purchase_date=date(2025, 10, 31),
        as_of=date(2026, 3, 31),
    )
    # 31-Oct-2025 to 31-Mar-2026 = 152 days → 50% of 15% = 7.5%
    assert calc["half_year"] == Decimal("1")
    assert calc["current_year"] == Decimal("102750.00")
    assert calc["wdv"] == Decimal("1267250.00")


def test_h1_before_30_sep() -> None:
    svc = DepreciationService()
    calc = svc.calculate(
        cost=Decimal("1370000"),
        rate=Decimal("15"),
        purchase_date=date(2025, 10, 31),
        as_of=date(2026, 9, 6),
        cap_today=False,
    )
    # No opening date → cost is from purchase; close FY 2025-26 then H1
    assert calc["current_year"] == Decimal("95043.75")
    assert calc["wdv"] == Decimal("1172206.25")
    assert calc["half_year"] == Decimal("1")
    assert calc["accumulated"] == Decimal("197793.75")


def test_h1_from_fy_opening_balance() -> None:
    svc = DepreciationService()
    calc = svc.calculate(
        cost=Decimal("1370000"),
        rate=Decimal("15"),
        purchase_date=date(2025, 10, 31),
        opening_date=date(2026, 4, 1),
        as_of=date(2026, 9, 6),
        cap_today=False,
    )
    # Opening is already 01/04 WDV — only 01/04–30/09 on 13,70,000
    assert calc["current_year"] == Decimal("102750.00")
    assert calc["wdv"] == Decimal("1267250.00")
    assert calc["accumulated"] == Decimal("102750.00")


def test_april_first_closes_previous_year() -> None:
    svc = DepreciationService()
    calc = svc.calculate(
        cost=Decimal("1370000"),
        rate=Decimal("15"),
        purchase_date=date(2025, 10, 31),
        as_of=date(2026, 4, 1),
        cap_today=False,
    )
    assert calc["current_year"] == Decimal("0.00")
    assert calc["wdv"] == Decimal("1267250.00")
    assert calc["accumulated"] == Decimal("102750.00")


def test_april_first_with_fy_opening() -> None:
    svc = DepreciationService()
    on_open = svc.calculate(
        cost=Decimal("1370000"),
        rate=Decimal("15"),
        purchase_date=date(2025, 10, 31),
        opening_date=date(2026, 4, 1),
        as_of=date(2026, 4, 1),
        cap_today=False,
    )
    assert on_open["current_year"] == Decimal("0.00")
    assert on_open["wdv"] == Decimal("1370000.00")
    next_open = svc.calculate(
        cost=Decimal("1370000"),
        rate=Decimal("15"),
        purchase_date=date(2025, 10, 31),
        opening_date=date(2026, 4, 1),
        as_of=date(2027, 4, 1),
        cap_today=False,
    )
    assert next_open["current_year"] == Decimal("0.00")
    assert next_open["wdv"] == Decimal("1164500.00")


def test_h2_from_1_oct_to_system_date() -> None:
    svc = DepreciationService()
    calc = svc.calculate(
        cost=Decimal("1370000"),
        rate=Decimal("15"),
        purchase_date=date(2025, 10, 31),
        as_of=date(2026, 10, 15),
        cap_today=False,
    )
    # After 2025-26 close: book 12,67,250. H1 95,043.75 + H2 15/182 of 95,043.75
    h1 = Decimal("95043.75")
    h2 = (Decimal("95043.75") * Decimal("15") / Decimal("182")).quantize(Decimal("0.01"))
    assert calc["current_year"] == h1 + h2
    assert calc["wdv"] == Decimal("1267250.00") - calc["current_year"]


def test_future_purchase_falls_back_to_opening_date() -> None:
    svc = DepreciationService()
    calc = svc.calculate(
        cost=Decimal("1370000"),
        rate=Decimal("15"),
        purchase_date=date(2026, 10, 31),
        opening_date=date(2025, 10, 31),
        as_of=date(2026, 9, 6),
        cap_today=False,
    )
    assert calc["current_year"] == Decimal("95043.75")
    assert calc["wdv"] == Decimal("1172206.25")


def test_future_purchase_keeps_cost_when_no_opening() -> None:
    svc = DepreciationService()
    calc = svc.calculate(
        cost=Decimal("1370000"),
        rate=Decimal("15"),
        purchase_date=date(2026, 10, 31),
        as_of=date(2026, 9, 6),
    )
    assert calc["current_year"] == Decimal("0.00")
    assert calc["wdv"] == Decimal("1370000.00")


def test_full_year_on_31_march() -> None:
    svc = DepreciationService()
    calc = svc.calculate(
        cost=Decimal("1370000"),
        rate=Decimal("15"),
        purchase_date=date(2025, 10, 31),
        as_of=date(2027, 3, 31),
        cap_today=False,
    )
    assert calc["half_year"] == Decimal("0")
    assert calc["current_year"] == Decimal("190087.50")
    assert calc["wdv"] == Decimal("1077162.50")


def test_appreciation_h1_from_fy_opening() -> None:
    svc = DepreciationService()
    calc = svc.calculate_appreciation(
        cost=Decimal("100000"),
        rate=Decimal("10"),
        purchase_date=date(2025, 4, 1),
        opening_date=date(2026, 4, 1),
        as_of=date(2026, 9, 6),
        cap_today=False,
    )
    # Opening is already 01/04 book — only first-half 50% of 10%
    assert calc["current_year"] == Decimal("5000.00")
    assert calc["current_value"] == Decimal("105000.00")
    assert calc["accumulated"] == Decimal("5000.00")
    assert calc["half_year"] == Decimal("1")


def test_appreciation_april_first_closes_previous_year() -> None:
    svc = DepreciationService()
    calc = svc.calculate_appreciation(
        cost=Decimal("100000"),
        rate=Decimal("10"),
        purchase_date=date(2025, 4, 1),
        as_of=date(2026, 4, 1),
        cap_today=False,
    )
    assert calc["current_year"] == Decimal("0.00")
    assert calc["current_value"] == Decimal("110000.00")
    assert calc["accumulated"] == Decimal("10000.00")


def test_appreciation_skips_when_inputs_missing() -> None:
    svc = DepreciationService()
    no_rate = svc.calculate_appreciation(
        cost=Decimal("100000"),
        rate=Decimal("0"),
        purchase_date=date(2026, 4, 1),
        as_of=date(2026, 9, 6),
        cap_today=False,
    )
    assert no_rate["current_year"] == Decimal("0.00")
    assert no_rate["current_value"] == Decimal("100000.00")
    no_date = svc.calculate_appreciation(
        cost=Decimal("100000"),
        rate=Decimal("10"),
        purchase_date=None,
        opening_date=None,
        as_of=date(2026, 9, 6),
        cap_today=False,
    )
    assert no_date["current_year"] == Decimal("0.00")
    no_cost = svc.calculate_appreciation(
        cost=Decimal("0"),
        rate=Decimal("10"),
        purchase_date=date(2026, 4, 1),
        as_of=date(2026, 9, 6),
        cap_today=False,
    )
    assert no_cost["current_year"] == Decimal("0.00")
    assert no_cost["current_value"] == Decimal("0.00")


def test_find_existing_appreciation_ledger() -> None:
    from app.services.financial_statements.engine import FinancialReportEngine

    ledgers = [
        {
            "source": "coa",
            "nature": "Income",
            "ledger_name": "Appreciation",
            "group_name": "Income (Indirect)",
            "closing": Decimal("0.00"),
        },
        {
            "source": "coa",
            "nature": "Income",
            "ledger_name": "Rent Income",
            "group_name": "Indirect Incomes",
            "closing": Decimal("12000.00"),
        },
    ]
    found = FinancialReportEngine._find_appreciation_ledger(ledgers)
    assert found is not None
    assert found["ledger_name"] == "Appreciation"


def test_find_existing_depreciation_ledger() -> None:
    from app.services.financial_statements.engine import FinancialReportEngine

    ledgers = [
        {
            "source": "coa",
            "nature": "Expense",
            "ledger_name": "Depreciation",
            "group_name": "Expenses (Direct)",
            "closing": Decimal("0.00"),
        },
        {
            "source": "coa",
            "nature": "Expense",
            "ledger_name": "Medical Expenses",
            "group_name": "Expenses (Direct)",
            "closing": Decimal("10378.00"),
        },
    ]
    found = FinancialReportEngine._find_depreciation_ledger(ledgers)
    assert found is not None
    assert found["ledger_name"] == "Depreciation"


def main() -> None:
    test_car_rate_from_public_chart()
    test_computer_rate_change_by_purchase_date()
    test_half_year_when_used_under_180_days()
    test_h1_before_30_sep()
    test_h1_from_fy_opening_balance()
    test_april_first_closes_previous_year()
    test_april_first_with_fy_opening()
    test_h2_from_1_oct_to_system_date()
    test_future_purchase_falls_back_to_opening_date()
    test_future_purchase_keeps_cost_when_no_opening()
    test_full_year_on_31_march()
    test_appreciation_h1_from_fy_opening()
    test_appreciation_april_first_closes_previous_year()
    test_appreciation_skips_when_inputs_missing()
    test_find_existing_appreciation_ledger()
    test_find_existing_depreciation_ledger()
    print("item fixed-asset depreciation tests passed")


if __name__ == "__main__":
    main()
