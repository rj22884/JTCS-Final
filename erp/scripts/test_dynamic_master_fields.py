"""Unit tests for Chart-of-Account-Group dynamic master fields (no DB)."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.dyn_field_catalog import FIELD_LINKS, PROPERTY_FIELD_KEYS
from app.services.dynamic_master_fields import (
    EMPTY_GROUP_CONFIG_KEY,
    PROFILES,
    DynamicMasterFieldService,
)


def _svc() -> DynamicMasterFieldService:
    svc = DynamicMasterFieldService()
    svc.reset_cache()
    DynamicMasterFieldService._group_profiles = {
        10: "fixed_assets",
        11: "fixed_assets",
        20: "investments",
    }
    DynamicMasterFieldService._group_field_config = {}
    DynamicMasterFieldService._custom_fields = []
    return svc


def test_profile_mapping() -> None:
    svc = _svc()
    assert svc.profile_key_for_group(10) == "fixed_assets"
    assert svc.profile_key_for_group(20) == "investments"
    assert svc.profile_key_for_group(99) is None
    assert svc.profile_key_for_group(None) is None


def test_unused_extras_cleared_for_fixed_assets() -> None:
    extras = _svc().extra_form_payload(
        {
            "purchase_date": "2026-04-01",
            "depreciation_rate": "15",
            "appreciation_rate": "10",
        },
        10,
    )
    assert extras["purchase_date"] == "2026-04-01"
    assert extras["depreciation_rate"] == "15.00"
    assert extras["appreciation_rate"] == "0.00"


def test_unused_extras_cleared_for_investments() -> None:
    extras = _svc().extra_form_payload(
        {
            "purchase_date": "2026-04-01",
            "depreciation_rate": "15",
            "appreciation_rate": "10",
        },
        20,
    )
    assert extras["purchase_date"] == "2026-04-01"
    assert extras["depreciation_rate"] == "0.00"
    assert extras["appreciation_rate"] == "10.00"


def test_other_group_clears_all_extras() -> None:
    extras = _svc().extra_form_payload(
        {
            "purchase_date": "2026-04-01",
            "depreciation_rate": "15",
            "appreciation_rate": "10",
        },
        99,
    )
    assert extras["purchase_date"] == ""
    assert extras["depreciation_rate"] == "0.00"
    assert extras["appreciation_rate"] == "0.00"


def test_purchase_date_falls_back_to_opening_but_is_not_required() -> None:
    svc = _svc()
    extras = svc.extra_form_payload({}, 20, opening_date="2026-04-01")
    assert extras["purchase_date"] == "2026-04-01"
    svc.validate_required({"purchase_date": ""}, 20)
    svc.validate_required({}, 10)


def test_required_list_is_empty_by_default() -> None:
    svc = _svc()
    assert svc.required_keys_for_group(10) == []
    assert svc.required_keys_for_group(20) == []
    assert svc.client_config()["always_required"] == []


def test_annotate_groups() -> None:
    groups = [
        {"group_id": 10, "group_name": "Fixed Assets"},
        {"group_id": 20, "group_name": "Investments"},
        {"group_id": 5, "group_name": "Individual Client"},
    ]
    _svc().annotate_groups(groups)
    assert groups[0]["dyn_profile"] == "fixed_assets"
    assert groups[0]["is_fixed_asset"] is True
    assert groups[1]["dyn_profile"] == "investments"
    assert groups[1]["is_investment"] is True
    assert groups[2]["dyn_profile"] == ""


def test_extra_db_values() -> None:
    values = _svc().extra_db_values(
        {"purchase_date": "2026-04-01", "depreciation_rate": "15"},
        10,
    )
    assert values["PurchaseDate"].isoformat() == "2026-04-01"
    assert values["DepreciationRate"] == Decimal("15.00")
    assert values["AppreciationRate"] == Decimal("0.00")


def test_configured_group_uses_ticks() -> None:
    svc = _svc()
    DynamicMasterFieldService._group_field_config = {
        10: [
            {"key": "pan_number", "required": False},
            {"key": "purchase_date", "required": True},
        ]
    }
    keys = [f["key"] for f in svc.fields_for_group(10)]
    assert "pan_number" in keys
    assert "purchase_date" in keys
    assert "depreciation_rate" not in keys
    extras = svc.extra_form_payload(
        {
            "purchase_date": "2026-04-01",
            "depreciation_rate": "15",
            "appreciation_rate": "10",
        },
        10,
    )
    assert extras["purchase_date"] == "2026-04-01"
    assert extras["depreciation_rate"] == "0.00"
    assert extras["appreciation_rate"] == "0.00"


def test_property_location_fields_in_catalog() -> None:
    svc = _svc()
    keys = {row["key"] for row in svc.catalog_flat()}
    assert "investment_kind" in keys
    assert "property_state" in keys
    assert "property_district" in keys
    assert "property_tehsil" in keys
    assert "property_pincode" in keys
    assert "property_village" in keys
    assert "property_land_area" in keys
    assert "property_land_unit" in keys
    assert "property_land_value" in keys
    assert "property_area_class" not in keys
    assert "property_locality" not in keys
    assert "property_block" not in keys
    assert "property_ward" not in keys
    assert "property_address" not in keys
    spec = svc.spec_for_key("property_tehsil")
    assert spec["visible_when"] == {"investment_kind": ["Property"]}
    state = svc.spec_for_key("property_state")
    assert "india_loc:states" in (state.get("features") or [])
    village = svc.spec_for_key("property_village")
    assert village["label"] == "Village / Area"
    assert "india_loc:places" in (village.get("features") or [])
    units = svc.spec_for_key("property_land_unit")["options"]
    assert "Bigha" in units
    assert "Guntha (Gunta)" in units
    assert "Nali" in units
    assert "Kanal" in units
    land = svc.spec_for_key("property_land_value")
    assert "land_value_sync" in (land.get("features") or [])
    assert land["type"] == "money"
    assert "investment_kind" in PROFILES["investments"]["fields"]
    assert "property_state" in PROFILES["investments"]["fields"]
    assert set(PROPERTY_FIELD_KEYS).issubset(keys)
    loc = list(PROPERTY_FIELD_KEYS)
    assert loc.index("property_state") < loc.index("property_district")
    assert loc.index("property_district") < loc.index("property_tehsil")
    assert loc.index("property_tehsil") < loc.index("property_pincode")
    assert loc.index("property_pincode") < loc.index("property_village")
    assert loc.index("property_village") < loc.index("property_land_area")
    assert "property_area_class" not in FIELD_LINKS["area"]
    assert "property_locality" not in FIELD_LINKS
    assert "state" in FIELD_LINKS["pincode"]
    assert "district" in FIELD_LINKS["pincode"]
    assert "property_district" in FIELD_LINKS["property_state"]
    assert "property_tehsil" in FIELD_LINKS["property_district"]
    assert "property_pincode" in FIELD_LINKS["property_tehsil"]
    assert "property_village" in FIELD_LINKS["property_pincode"]
    assert "property_pincode" in FIELD_LINKS["property_village"]
    cfg = svc.catalog_for_editor()
    assert "state" in cfg["links"]["pincode"]


def test_client_config_marks_empty_group_as_configured() -> None:
    svc = _svc()
    DynamicMasterFieldService._group_field_config = {10: []}
    cfg = svc.client_config()
    assert cfg["group_fields"]["10"]["configured"] is True
    assert cfg["group_fields"]["10"]["fields"] == []


def test_empty_configured_map_shows_no_extras() -> None:
    svc = _svc()
    DynamicMasterFieldService._group_field_config = {10: []}
    assert svc.fields_for_group(10) == []
    extras = svc.extra_form_payload(
        {
            "purchase_date": "2026-04-01",
            "depreciation_rate": "15",
            "appreciation_rate": "10",
        },
        10,
    )
    assert extras["purchase_date"] == ""
    assert extras["depreciation_rate"] == "0.00"
    assert extras["appreciation_rate"] == "0.00"


def test_empty_payload_persists_configured_sentinel() -> None:
    rows = _svc()._parse_group_field_payload([])
    assert rows == [{"key": EMPTY_GROUP_CONFIG_KEY, "required": False, "order": 0}]


def test_custom_key_slug() -> None:
    svc = _svc()
    assert svc._unique_custom_key("Vehicle No.") == "custom_vehicle_no"
    DynamicMasterFieldService._custom_fields = [
        {
            "key": "custom_vehicle_no",
            "label": "Vehicle No.",
            "type": "text",
            "source": "custom",
            "section": "custom",
        }
    ]
    assert svc._unique_custom_key("Vehicle No.") == "custom_vehicle_no_2"


def test_required_custom_fails_validate() -> None:
    svc = _svc()
    DynamicMasterFieldService._custom_fields = [
        {
            "key": "custom_foo",
            "label": "Foo",
            "type": "text",
            "source": "custom",
            "section": "custom",
            "always_required": False,
        }
    ]
    DynamicMasterFieldService._group_field_config = {
        99: [{"key": "custom_foo", "required": True}]
    }
    try:
        svc.validate_required({"dyn_values": {}}, 99)
        raise AssertionError("expected required custom field to fail")
    except ValueError as exc:
        assert "Foo" in str(exc)
    svc.validate_required({"dyn_values": {"custom_foo": "yes"}}, 99)


def test_apply_to_payload_uses_first_group() -> None:
    payload = {
        "appreciation_rate": "8",
        "depreciation_rate": "12",
        "purchase_date": "2026-09-06",
    }
    _svc().apply_to_payload(payload, [20])
    assert payload["appreciation_rate"] == "8.00"
    assert payload["depreciation_rate"] == "0.00"
    assert payload["purchase_date"] == "2026-09-06"


def main() -> None:
    test_profile_mapping()
    test_unused_extras_cleared_for_fixed_assets()
    test_unused_extras_cleared_for_investments()
    test_other_group_clears_all_extras()
    test_purchase_date_falls_back_to_opening_but_is_not_required()
    test_required_list_is_empty_by_default()
    test_annotate_groups()
    test_extra_db_values()
    test_configured_group_uses_ticks()
    test_property_location_fields_in_catalog()
    test_client_config_marks_empty_group_as_configured()
    test_empty_configured_map_shows_no_extras()
    test_empty_payload_persists_configured_sentinel()
    test_custom_key_slug()
    test_required_custom_fails_validate()
    test_apply_to_payload_uses_first_group()
    print("dynamic master field tests passed")


if __name__ == "__main__":
    main()
