"""Central Chart-of-Account-Group → dynamic master fields.

Only the selected Chart of Account Group decides which extra fields appear.
Per-form mandatories (e.g. Customer Name) stay on their own screens.
Extra fields are required only when the profile/catalog marks them required.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.dyn_field_catalog import (
    CUSTOMER_FIELD_LIBRARY,
    EAV_SOURCES,
    FIELD_LINKS,
    LIBRARY_BY_KEY,
    PROPERTY_FIELD_KEYS,
    SECTION_LABELS,
    SKIP_DYN_RENDER,
)


ZERO = Decimal("0.00")

# Future required extras: set required=True here or list the key on the profile.
FIELD_CATALOG: dict[str, dict[str, Any]] = {
    "purchase_date": {
        "key": "purchase_date",
        "db": "PurchaseDate",
        "label": "Purchase Date",
        "label_template": "{entity} Purchase Date",
        "type": "date",
        "tier": "basic",
        "required": False,
    },
    "depreciation_rate": {
        "key": "depreciation_rate",
        "db": "DepreciationRate",
        "label": "Depreciation Rate",
        "type": "percent",
        "tier": "advanced",
        "required": False,
        "features": ["depreciation_sync"],
        "hint": (
            "From the public Income-tax depreciation chart for the purchase date. "
            "Charge applies only when purchase date, rate, and opening value are set."
        ),
    },
    "appreciation_rate": {
        "key": "appreciation_rate",
        "db": "AppreciationRate",
        "label": "Appreciation Rate",
        "type": "percent",
        "tier": "advanced",
        "required": False,
        "features": [],
        "hint": (
            "Appreciation posts to P&L (income) and increases the Balance Sheet "
            "value only when purchase date, rate, and opening value are all set."
        ),
    },
}

PROFILES: dict[str, dict[str, Any]] = {
    "fixed_assets": {
        "key": "fixed_assets",
        "match_names": (
            "fixed assets",
            "computers printers & electric items",
            "immovable property",
        ),
        "fields": ("purchase_date", "depreciation_rate"),
        "required": (),
    },
    "investments": {
        "key": "investments",
        "match_names": ("investments", "investment"),
        "fields": ("purchase_date", "appreciation_rate") + PROPERTY_FIELD_KEYS,
        "required": (),
    },
}

ALL_EXTRA_KEYS = tuple(FIELD_CATALOG.keys())


def _text(value) -> str:
    if value in (None, ""):
        return ""
    if hasattr(value, "isoformat"):
        return str(value.isoformat())[:10]
    return str(value).strip()


def _as_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("Purchase date is invalid.") from exc


def _money(value, default: str = "0") -> Decimal:
    if value in (None, ""):
        return Decimal(default).quantize(Decimal("0.01"))
    try:
        return Decimal(str(value).replace(",", "")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal(default).quantize(Decimal("0.01"))


ALLOWED_CUSTOM_TYPES = ("text", "textarea", "date", "number", "percent", "email", "select")
EMPTY_GROUP_CONFIG_KEY = "__none__"
EXTRA_FIELD_KEYS = frozenset(FIELD_CATALOG.keys())


class DynamicMasterFieldService:
    """Group-id → profile / saved ticks → visible extra fields."""

    _group_profiles: dict[int, str] | None = None
    _group_field_config: dict[int, list[dict[str, Any]]] | None = None
    _custom_fields: list[dict[str, Any]] | None = None

    def reset_cache(self) -> None:
        DynamicMasterFieldService._group_profiles = None
        DynamicMasterFieldService._group_field_config = None
        DynamicMasterFieldService._custom_fields = None

    def profile_key_for_group(self, group_id) -> str | None:
        if not group_id:
            return None
        try:
            gid = int(group_id)
        except (TypeError, ValueError):
            return None
        mapping = self._group_profile_map()
        return mapping.get(gid)

    @staticmethod
    def _client_field(spec: dict[str, Any]) -> dict[str, Any]:
        return {
            "key": spec["key"],
            "label": spec["label"],
            "label_template": spec.get("label_template") or spec["label"],
            "type": spec["type"],
            "tier": spec.get("tier") or "basic",
            "required": bool(spec.get("required")),
            "features": list(spec.get("features") or ()),
            "hint": spec.get("hint") or "",
            "source": spec.get("source") or "customer",
            "section": spec.get("section") or "custom",
            "maxlength": spec.get("maxlength"),
            "options": list(spec.get("options") or ()),
            "visible_when": dict(spec.get("visible_when") or {}),
            "visible_when_any": dict(spec.get("visible_when_any") or {}),
        }

    def spec_for_key(self, field_key: str) -> dict[str, Any] | None:
        key = (field_key or "").strip()
        if not key:
            return None
        lib = LIBRARY_BY_KEY.get(key)
        if lib:
            return dict(lib)
        extra = FIELD_CATALOG.get(key)
        if extra:
            row = dict(extra)
            row.setdefault("source", "extra")
            row.setdefault("section", "extra")
            row.setdefault("locked", True)
            return row
        for custom in self._custom_field_rows():
            if custom.get("key") == key:
                return dict(custom)
        return None

    def fields_for_group(self, group_id) -> list[dict[str, Any]]:
        if not group_id:
            return []
        try:
            gid = int(group_id)
        except (TypeError, ValueError):
            return []
        configured = self._configured_group_fields()
        if gid in configured:
            return self._resolve_field_rows(configured[gid])
        key = self.profile_key_for_group(gid)
        if not key:
            return []
        profile = PROFILES[key]
        required = {str(k) for k in (profile.get("required") or ())}
        items = [
            {"key": field_key, "required": field_key in required}
            for field_key in (profile.get("fields") or ())
        ]
        return self._resolve_field_rows(items)

    def required_keys_for_group(self, group_id) -> list[str]:
        return [f["key"] for f in self.fields_for_group(group_id) if f.get("required")]

    def annotate_groups(self, groups: list[dict]) -> list[dict]:
        mapping = self._group_profile_map()
        for group in groups:
            try:
                gid = int(group.get("group_id") or 0)
            except (TypeError, ValueError):
                gid = 0
            profile = mapping.get(gid) or ""
            group["dyn_profile"] = profile
            group["is_fixed_asset"] = profile == "fixed_assets"
            group["is_investment"] = profile == "investments"
        return groups

    def client_config(self) -> dict[str, Any]:
        profiles = {}
        for key, profile in PROFILES.items():
            profiles[key] = {
                "key": key,
                "fields": list(profile.get("fields") or ()),
                "required": list(profile.get("required") or ()),
            }
        fields = {spec["key"]: self._client_field(spec) for spec in self.catalog_flat()}
        group_fields: dict[str, dict[str, Any]] = {}
        for gid, items in self._configured_group_fields().items():
            resolved = self._resolve_field_rows(items)
            group_fields[str(gid)] = {
                "configured": True,
                "fields": [
                    self._client_field(row)
                    for row in resolved
                    if row["key"] not in SKIP_DYN_RENDER
                ],
            }
        return {
            "fields": fields,
            "profiles": profiles,
            "group_profiles": {str(gid): key for gid, key in self._group_profile_map().items()},
            "group_fields": group_fields,
            "always_required": [],
            "skip_keys": list(SKIP_DYN_RENDER),
        }

    def catalog_for_editor(self) -> dict[str, Any]:
        sections: dict[str, list[dict[str, Any]]] = {}
        for spec in self.catalog_flat():
            section = spec.get("section") or "custom"
            sections.setdefault(section, []).append(
                {
                    "key": spec["key"],
                    "label": spec["label"],
                    "type": spec["type"],
                    "source": spec.get("source") or "customer",
                    "locked": bool(spec.get("locked")),
                    "always_on": bool(spec.get("always_on")),
                    "always_required": bool(spec.get("always_required")),
                    "hint": spec.get("hint") or "",
                    "options": list(spec.get("options") or ()),
                }
            )
        return {
            "sections": [
                {
                    "key": key,
                    "label": SECTION_LABELS.get(key, key.title()),
                    "fields": fields,
                }
                for key, fields in sections.items()
            ],
            "section_labels": SECTION_LABELS,
            "links": {key: list(deps) for key, deps in FIELD_LINKS.items()},
        }

    def catalog_flat(self) -> list[dict[str, Any]]:
        out = [dict(row) for row in CUSTOMER_FIELD_LIBRARY]
        seen = {row["key"] for row in out}
        for custom in self._custom_field_rows():
            if custom["key"] in seen:
                continue
            out.append(custom)
            seen.add(custom["key"])
        return out

    def fields_for_group_editor(self, group_id) -> dict[str, Any]:
        try:
            gid = int(group_id or 0)
        except (TypeError, ValueError):
            gid = 0
        configured = self._configured_group_fields()
        selected = []
        if gid and gid in configured:
            selected = [
                {"key": item["key"], "required": bool(item.get("required"))}
                for item in configured[gid]
                if item.get("key")
                and item["key"] != EMPTY_GROUP_CONFIG_KEY
                and (item["key"] == "customer_name" or self.spec_for_key(item["key"]))
            ]
            has_config = True
        else:
            has_config = False
            for field in self.fields_for_group(gid):
                selected.append({"key": field["key"], "required": bool(field.get("required"))})
        selected.append({"key": "customer_name", "required": True})
        # de-dupe, customer_name first conceptually
        seen = set()
        unique = []
        for item in selected:
            key = item["key"]
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return {
            "configured": has_config,
            "selected": unique,
            "catalog": self.catalog_for_editor(),
        }

    def save_group_fields(self, group_id: int, fields) -> list[dict[str, Any]]:
        gid = int(group_id)
        rows = self._parse_group_field_payload(fields)
        from app.repositories.dynamic_master_fields_repository import (
            DynamicMasterFieldsRepository,
        )
        from app.utils.db_session import persist

        repo = DynamicMasterFieldsRepository()

        def _write() -> list[dict[str, Any]]:
            repo.replace_group_fields(gid, rows)
            return rows

        saved = persist(_write)
        self.reset_cache()
        return saved

    def create_custom_field(self, payload: dict) -> dict[str, Any]:
        label = (payload.get("label") or payload.get("Label") or "").strip()
        if not label:
            raise ValueError("Field label is required.")
        if len(label) > 150:
            raise ValueError("Field label must be at most 150 characters.")
        field_type = (payload.get("type") or payload.get("FieldType") or "text").strip().lower()
        if field_type not in ALLOWED_CUSTOM_TYPES:
            raise ValueError("Select a valid field type.")
        hint = (payload.get("hint") or payload.get("Hint") or "").strip()[:400]
        key = self._unique_custom_key(payload.get("key") or label)
        from app.repositories.dynamic_master_fields_repository import (
            DynamicMasterFieldsRepository,
        )
        from app.utils.db_session import persist

        repo = DynamicMasterFieldsRepository()
        if repo.get_custom_field(key) or key in LIBRARY_BY_KEY or key in FIELD_CATALOG:
            raise ValueError("A field with this name already exists.")

        def _write() -> dict:
            return repo.create_custom_field(
                {"key": key, "label": label, "type": field_type, "hint": hint or None}
            )

        saved = persist(_write)
        self.reset_cache()
        return self._custom_row(saved)

    def update_custom_field(self, field_key: str, payload: dict) -> dict[str, Any]:
        key = (field_key or "").strip()
        if key in LIBRARY_BY_KEY or key in FIELD_CATALOG:
            raise ValueError("Built-in fields cannot be edited.")
        label = (payload.get("label") or payload.get("Label") or "").strip()
        if not label:
            raise ValueError("Field label is required.")
        field_type = (payload.get("type") or payload.get("FieldType") or "text").strip().lower()
        if field_type not in ALLOWED_CUSTOM_TYPES:
            raise ValueError("Select a valid field type.")
        hint = (payload.get("hint") or payload.get("Hint") or "").strip()[:400]
        from app.repositories.dynamic_master_fields_repository import (
            DynamicMasterFieldsRepository,
        )
        from app.utils.db_session import persist

        repo = DynamicMasterFieldsRepository()

        def _write() -> dict:
            return repo.update_custom_field(
                key, {"label": label, "type": field_type, "hint": hint or None}
            )

        saved = persist(_write)
        self.reset_cache()
        return self._custom_row(saved)

    def delete_custom_field(self, field_key: str) -> str:
        key = (field_key or "").strip()
        if key in LIBRARY_BY_KEY or key in FIELD_CATALOG:
            raise ValueError("Built-in fields cannot be deleted.")
        from app.repositories.dynamic_master_fields_repository import (
            DynamicMasterFieldsRepository,
        )
        from app.utils.db_session import persist

        repo = DynamicMasterFieldsRepository()
        if not repo.get_custom_field(key):
            raise ValueError("Custom field not found.")

        def _write() -> str:
            repo.delete_custom_field(key)
            return "Field deleted."

        message = persist(_write)
        self.reset_cache()
        return message

    def customer_dyn_values(self, customer_id: int | None) -> dict[str, str]:
        if not customer_id:
            return {}
        try:
            from app.repositories.dynamic_master_fields_repository import (
                DynamicMasterFieldsRepository,
            )

            return DynamicMasterFieldsRepository().get_customer_values(int(customer_id))
        except Exception:
            return {}

    def save_customer_dyn_values(self, customer_id: int, payload: dict) -> None:
        raw = payload.get("dyn_values")
        if raw is None:
            raw = payload.get("custom_values")
        if raw is None:
            return
        if not isinstance(raw, dict):
            raw = {}
        cleaned = {}
        for key, value in raw.items():
            spec = self.spec_for_key(str(key))
            if not spec or spec.get("source") not in EAV_SOURCES:
                continue
            cleaned[str(key)] = "" if value is None else str(value)
        from app.repositories.dynamic_master_fields_repository import (
            DynamicMasterFieldsRepository,
        )

        DynamicMasterFieldsRepository().replace_customer_values(int(customer_id), cleaned)

    def _resolve_field_rows(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen = set()
        for item in items:
            key = str(item.get("key") or "").strip()
            if not key or key in seen:
                continue
            spec = self.spec_for_key(key)
            if not spec:
                continue
            seen.add(key)
            row = dict(spec)
            row["required"] = bool(spec.get("always_required")) or bool(item.get("required"))
            out.append(row)
        return out

    def _parse_group_field_payload(self, fields) -> list[dict[str, Any]]:
        if fields is None:
            return []
        if isinstance(fields, dict):
            fields = fields.get("fields") or fields.get("selected") or []
        if not isinstance(fields, list):
            raise ValueError("Field selection is invalid.")
        rows = []
        seen = set()
        for idx, raw in enumerate(fields):
            if isinstance(raw, str):
                key = raw.strip()
                required = False
            elif isinstance(raw, dict):
                key = str(raw.get("key") or raw.get("FieldKey") or "").strip()
                required = str(raw.get("required") or raw.get("IsRequired") or "").lower() in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
            else:
                continue
            if not key or key in seen:
                continue
            if key in {EMPTY_GROUP_CONFIG_KEY, "customer_name"}:
                continue
            if not self.spec_for_key(key):
                raise ValueError(f"Unknown field: {key}")
            seen.add(key)
            rows.append({"key": key, "required": required, "order": (idx + 1) * 10})
        if not rows:
            rows.append({"key": EMPTY_GROUP_CONFIG_KEY, "required": False, "order": 0})
        return rows

    def _custom_field_rows(self) -> list[dict[str, Any]]:
        if DynamicMasterFieldService._custom_fields is not None:
            return DynamicMasterFieldService._custom_fields
        rows: list[dict[str, Any]] = []
        try:
            from app.repositories.dynamic_master_fields_repository import (
                DynamicMasterFieldsRepository,
            )

            for item in DynamicMasterFieldsRepository().list_custom_fields():
                rows.append(self._custom_row(item))
        except Exception:
            rows = []
        DynamicMasterFieldService._custom_fields = rows
        return rows

    @staticmethod
    def _custom_row(item: dict) -> dict[str, Any]:
        key = str(item.get("FieldKey") or item.get("key") or "")
        return {
            "key": key,
            "label": item.get("Label") or item.get("label") or key,
            "type": (item.get("FieldType") or item.get("type") or "text"),
            "source": "custom",
            "section": "custom",
            "locked": False,
            "always_on": False,
            "always_required": False,
            "hint": item.get("Hint") or item.get("hint") or "",
            "label_template": item.get("Label") or item.get("label") or key,
            "tier": "basic",
            "features": [],
            "required": False,
        }

    def _unique_custom_key(self, raw: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", (raw or "").strip().lower()).strip("_")[:48]
        if not slug:
            slug = "field"
        if not slug.startswith("custom_"):
            slug = "custom_" + slug
        base = slug
        n = 2
        existing = {row["key"] for row in self.catalog_flat()}
        while slug in existing:
            slug = f"{base}_{n}"
            n += 1
        return slug[:80]

    def _configured_group_fields(self) -> dict[int, list[dict[str, Any]]]:
        if DynamicMasterFieldService._group_field_config is not None:
            return DynamicMasterFieldService._group_field_config
        mapping: dict[int, list[dict[str, Any]]] = {}
        try:
            from app.repositories.dynamic_master_fields_repository import (
                DynamicMasterFieldsRepository,
            )

            repo = DynamicMasterFieldsRepository()
            for gid in repo.configured_group_ids():
                mapping[int(gid)] = []
            for row in repo.list_all_group_fields():
                mapping.setdefault(int(row["GroupID"]), []).append(
                    {
                        "key": row["FieldKey"],
                        "required": bool(row["IsRequired"]),
                        "order": int(row["DisplayOrder"] or 100),
                    }
                )
        except Exception:
            mapping = {}
        DynamicMasterFieldService._group_field_config = mapping
        return mapping

    def extra_form_payload(
        self,
        payload: dict,
        group_id,
        *,
        opening_date=None,
    ) -> dict[str, str]:
        """Form-key extras for the selected group. Unused extras are cleared."""
        visible = {f["key"] for f in self.fields_for_group(group_id)}
        purchase = _text(payload.get("purchase_date") or payload.get("PurchaseDate"))
        if not purchase and opening_date not in (None, ""):
            purchase = _text(opening_date)[:10]
        if "purchase_date" not in visible:
            purchase = ""
        dep = _money(
            payload.get("depreciation_rate")
            if payload.get("depreciation_rate") not in (None, "")
            else payload.get("DepreciationRate")
        )
        app = _money(
            payload.get("appreciation_rate")
            if payload.get("appreciation_rate") not in (None, "")
            else payload.get("AppreciationRate")
        )
        if "depreciation_rate" not in visible:
            dep = ZERO
        if "appreciation_rate" not in visible:
            app = ZERO
        if dep < ZERO or dep > Decimal("100"):
            raise ValueError("Depreciation Rate must be between 0 and 100.")
        if app < ZERO or app > Decimal("100"):
            raise ValueError("Appreciation Rate must be between 0 and 100.")
        return {
            "purchase_date": purchase,
            "depreciation_rate": str(dep),
            "appreciation_rate": str(app),
        }

    def extra_db_values(
        self,
        payload: dict,
        group_id,
        *,
        opening_date=None,
    ) -> dict[str, Any]:
        form = self.extra_form_payload(payload, group_id, opening_date=opening_date)
        return {
            "PurchaseDate": _as_date(form["purchase_date"]),
            "DepreciationRate": _money(form["depreciation_rate"]),
            "AppreciationRate": _money(form["appreciation_rate"]),
        }

    def extra_serialize(self, row) -> dict[str, str]:
        purchase = getattr(row, "PurchaseDate", None)
        if isinstance(row, dict):
            purchase = row.get("PurchaseDate") or row.get("purchase_date")
            dep = row.get("DepreciationRate")
            if dep is None:
                dep = row.get("depreciation_rate")
            app = row.get("AppreciationRate")
            if app is None:
                app = row.get("appreciation_rate")
        else:
            dep = getattr(row, "DepreciationRate", None)
            app = getattr(row, "AppreciationRate", None)
        if hasattr(purchase, "isoformat"):
            purchase_s = purchase.isoformat()
        else:
            purchase_s = str(purchase or "")[:10]
        return {
            "purchase_date": purchase_s,
            "depreciation_rate": str(dep if dep is not None else "0.00"),
            "appreciation_rate": str(app if app is not None else "0.00"),
        }

    def validate_required(self, payload: dict, group_id) -> None:
        extras = self.extra_form_payload(
            payload,
            group_id,
            opening_date=payload.get("opening_balance_date") or payload.get("OpeningBalanceDate"),
        )
        dyn_values = payload.get("dyn_values") if isinstance(payload.get("dyn_values"), dict) else {}
        for field in self.fields_for_group(group_id):
            if not field.get("required") or field["key"] in SKIP_DYN_RENDER:
                continue
            key = field["key"]
            value = extras.get(key)
            if value in (None, ""):
                value = payload.get(key)
            if value in (None, "") and dyn_values:
                value = dyn_values.get(key)
            text = _text(value)
            if field.get("type") == "percent":
                empty = text in {"", "0", "0.00", "0.0"}
            else:
                empty = not text
            if empty:
                raise ValueError(f"{field['label']} is required.")

    def apply_to_payload(self, payload: dict, group_ids: list[int] | None) -> None:
        gid = None
        for raw in group_ids or []:
            try:
                gid = int(raw)
            except (TypeError, ValueError):
                continue
            if gid:
                break
        extras = self.extra_form_payload(
            payload,
            gid,
            opening_date=payload.get("opening_balance_date") or payload.get("OpeningBalanceDate"),
        )
        payload.update(extras)
        self.validate_required(payload, gid)

    def _group_profile_map(self) -> dict[int, str]:
        if DynamicMasterFieldService._group_profiles is not None:
            return DynamicMasterFieldService._group_profiles
        mapping: dict[int, str] = {}
        try:
            from app.services.depreciation_service import DepreciationService

            dep = DepreciationService()
            for gid in dep.fixed_asset_group_ids():
                mapping[int(gid)] = "fixed_assets"
            for gid in dep.investment_group_ids():
                mapping.setdefault(int(gid), "investments")
        except Exception:
            mapping = {}
        DynamicMasterFieldService._group_profiles = mapping
        return mapping
