from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.land_value_service import LandValueService


def test_area_and_uk_value() -> None:
    svc = LandValueService()
    nali = svc.area_to_sqm("1", "Nali")
    assert nali > Decimal("200") and nali < Decimal("201")
    rate, unit, _ = svc.pick_uk_rate({"CR_Agri_Beyond_200": 13000000}, "Rural")
    assert unit == "hectare"
    value = svc.compute_value(nali, rate, unit)
    assert value > Decimal("260000") and value < Decimal("261000")
    urban_rate, urban_unit, _ = svc.pick_uk_rate({"CR_Non_Agri_Beyond_200": 6000}, "Urban")
    assert urban_unit == "sqm"
    urban = svc.compute_value(svc.area_to_sqm("100", "Sq. Mt."), urban_rate, urban_unit)
    assert urban == Decimal("600000")


def test_parse_circlerate_table() -> None:
    html = """
    <table><thead><tr><th>Zone</th><th>Land</th><th>Residential</th></tr></thead>
    <tbody>
      <tr><td>A</td><td>₹10,000</td><td>₹20,000</td></tr>
      <tr><td>B</td><td>₹12,000</td><td>₹22,000</td></tr>
    </tbody></table>
    """
    rates = LandValueService.parse_circlerate_land_rates(html)
    assert rates == [Decimal("10000"), Decimal("12000")]
    assert LandValueService.parse_inr("₹1,38,490") == Decimal("138490")


def test_live_uk_anandpur() -> None:
    row = LandValueService().lookup(
        state="UTTARAKHAND",
        district="Nainital",
        tehsil="Haldwani",
        village="Anandpur",
        area_class="Rural",
        land_area="1",
        land_unit="Nali",
    )
    assert row["ok"] is True
    assert Decimal(row["value"]) > 0
    assert "Anandpur" in (row["matched_place"] or "")
    assert Decimal(row["unit_rate"]) > 0
    assert "Nali" in (row["unit_rate_label"] or "")


def main() -> None:
    test_area_and_uk_value()
    test_parse_circlerate_table()
    test_live_uk_anandpur()
    print("land value tests passed")


if __name__ == "__main__":
    main()
