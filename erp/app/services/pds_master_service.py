from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass

from app.models.ration_card import (
    PdsAroMaster,
    PdsDistrictMaster,
    PdsDsoMaster,
    PdsFpsMaster,
    PdsRationCardMaster,
    PdsSiMaster,
    PdsStateMaster,
)
from app.repositories.pds_master_repository import PdsMasterRepository
from app.utils.db_session import persist
from app.utils.master_delete_guard import assert_master_unused

WIKI_DISTRICTS_URL = (
    "https://en.wikipedia.org/w/api.php?action=parse"
    "&page=List_of_districts_of_Uttarakhand&prop=wikitext&format=json"
)

# Official 13 districts (same table as Wikipedia / Census 2011 codes). Used if the public API is down.
FALLBACK_UK_DISTRICTS = (
    ("AL", "Almora", "Almora", "Kumaon"),
    ("BA", "Bageshwar", "Bageshwar", "Kumaon"),
    ("CL", "Chamoli", "Gopeshwar", "Garhwal"),
    ("CP", "Champawat", "Champawat", "Kumaon"),
    ("DD", "Dehradun", "Dehradun", "Garhwal"),
    ("HA", "Haridwar", "Haridwar", "Garhwal"),
    ("NA", "Nainital", "Nainital", "Kumaon"),
    ("PA", "Pauri Garhwal", "Pauri", "Garhwal"),
    ("PI", "Pithoragarh", "Pithoragarh", "Kumaon"),
    ("RP", "Rudraprayag", "Rudraprayag", "Garhwal"),
    ("TE", "Tehri Garhwal", "New Tehri", "Garhwal"),
    ("UD", "Udham Singh Nagar", "Rudrapur", "Kumaon"),
    ("UT", "Uttarkashi", "Uttarkashi", "Garhwal"),
)

WIKI_LINK_RE = re.compile(r"\[\[(?:[^\|\]]*\|)?([^\]]+)\]\]")


def _wiki_text(cell: str) -> str:
    match = WIKI_LINK_RE.search(cell or "")
    if match:
        return match.group(1).strip()
    return re.sub(r"<[^>]+>", "", cell or "").strip()


def parse_wikipedia_districts(wikitext: str) -> list[dict]:
    rows: list[dict] = []
    for line in (wikitext or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "[[" not in stripped:
            continue
        cells = [part.strip() for part in stripped.lstrip("|").split("||")]
        if len(cells) < 3:
            continue
        code = re.sub(r"[^A-Za-z]", "", cells[1]).upper() if len(cells) > 1 else ""
        name_idx = 2
        if len(code) != 2:
            code = re.sub(r"[^A-Za-z]", "", cells[0]).upper()
            name_idx = 1
        if len(code) != 2 or name_idx >= len(cells):
            continue
        name = _wiki_text(cells[name_idx]).replace(" district", "").replace(" District", "").strip()
        if not name:
            continue
        hq_idx = name_idx + 1
        headquarters = _wiki_text(cells[hq_idx]) if hq_idx < len(cells) else ""
        division = ""
        for cell in cells:
            if "division" in cell.lower():
                division = _wiki_text(cell)
                break
        rows.append(
            {
                "district_code": code,
                "district_name": name,
                "headquarters": headquarters,
                "division_name": division,
            }
        )
    unique: dict[str, dict] = {}
    for row in rows:
        unique[row["district_code"]] = row
    return list(unique.values())


def fetch_wikipedia_districts() -> list[dict]:
    request = urllib.request.Request(
        WIKI_DISTRICTS_URL,
        headers={"User-Agent": "JTCS-ERP/1.0 (Uttarakhand PDS one-time import)"},
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))
    wikitext = ((payload.get("parse") or {}).get("wikitext") or {}).get("*") or ""
    rows = parse_wikipedia_districts(wikitext)
    if len(rows) < 10:
        raise ValueError("Wikipedia district table did not return Uttarakhand districts.")
    return rows


@dataclass(frozen=True)
class PdsField:
    column: str
    key: str
    label: str
    required: bool = False
    maxlength: int = 120
    kind: str = "text"


@dataclass(frozen=True)
class PdsEntity:
    slug: str
    title: str
    model: type
    pk_column: str
    pk_key: str
    icon: str
    url: str
    menu_order: int
    fields: tuple[PdsField, ...]
    parent_slug: str | None = None
    parent_column: str | None = None
    parent_required: bool = False
    extra_parents: tuple[tuple[str, str, bool], ...] = ()
    child_slug: str | None = None


def _f(column: str, key: str, label: str, *, required: bool = False, maxlength: int = 120, kind: str = "text") -> PdsField:
    return PdsField(column, key, label, required, maxlength, kind)


ENTITIES: dict[str, PdsEntity] = {
    "state": PdsEntity(
        "state",
        "State Master",
        PdsStateMaster,
        "StateID",
        "state_id",
        "bi-globe-asia-australia",
        "/public-report/ration-card/state-master",
        2,
        (
            _f("StateCode", "state_code", "State Code", required=True, maxlength=10),
            _f("StateName", "state_name", "State Name", required=True, maxlength=120),
        ),
        child_slug="district",
    ),
    "district": PdsEntity(
        "district",
        "District Master",
        PdsDistrictMaster,
        "DistrictID",
        "district_id",
        "bi-geo-alt",
        "/public-report/ration-card/district-master",
        3,
        (
            _f("DistrictCode", "district_code", "District Code", required=True, maxlength=20),
            _f("DistrictName", "district_name", "District Name", required=True, maxlength=120),
            _f("Headquarters", "headquarters", "Headquarters", maxlength=120),
            _f("DivisionName", "division_name", "Division", maxlength=80),
        ),
        parent_slug="state",
        parent_column="StateID",
        parent_required=True,
        child_slug="dso",
    ),
    "dso": PdsEntity(
        "dso",
        "DSO Master",
        PdsDsoMaster,
        "DsoID",
        "dso_id",
        "bi-building",
        "/public-report/ration-card/dso-master",
        4,
        (
            _f("DsoCode", "dso_code", "DSO Code", required=True, maxlength=40),
            _f("DsoName", "dso_name", "DSO Name", required=True, maxlength=200),
            _f("OfficerName", "officer_name", "Officer Name", maxlength=200),
            _f("MobileNumber", "mobile_number", "Mobile", maxlength=20),
            _f("Address", "address", "Address", maxlength=400, kind="textarea"),
        ),
        parent_slug="district",
        parent_column="DistrictID",
        parent_required=True,
        child_slug="aro",
    ),
    "aro": PdsEntity(
        "aro",
        "ARO Master",
        PdsAroMaster,
        "AroID",
        "aro_id",
        "bi-diagram-3",
        "/public-report/ration-card/aro-master",
        5,
        (
            _f("AroCode", "aro_code", "ARO Code", required=True, maxlength=40),
            _f("AroName", "aro_name", "ARO Name", required=True, maxlength=200),
            _f("OfficerName", "officer_name", "Officer Name", maxlength=200),
            _f("MobileNumber", "mobile_number", "Mobile", maxlength=20),
            _f("Address", "address", "Address", maxlength=400, kind="textarea"),
        ),
        parent_slug="dso",
        parent_column="DsoID",
        parent_required=True,
        child_slug="si",
    ),
    "si": PdsEntity(
        "si",
        "SI Master",
        PdsSiMaster,
        "SiID",
        "si_id",
        "bi-person-badge",
        "/public-report/ration-card/si-master",
        6,
        (
            _f("SiCode", "si_code", "SI Code", required=True, maxlength=40),
            _f("SiName", "si_name", "SI Name", required=True, maxlength=200),
            _f("OfficerName", "officer_name", "Officer Name", maxlength=200),
            _f("MobileNumber", "mobile_number", "Mobile", maxlength=20),
            _f("Address", "address", "Address", maxlength=400, kind="textarea"),
        ),
        parent_slug="aro",
        parent_column="AroID",
        parent_required=True,
        child_slug="fps",
    ),
    "fps": PdsEntity(
        "fps",
        "FPS Master",
        PdsFpsMaster,
        "FpsRowID",
        "fps_row_id",
        "bi-shop",
        "/public-report/ration-card/fps-master",
        7,
        (
            _f("FpsCode", "fps_code", "FPS ID", required=True, maxlength=80),
            _f("ExistingFpsId", "existing_fps_id", "Existing FPS ID", maxlength=80),
            _f("FpsName", "fps_name", "FPS / Shop Name", required=True, maxlength=200),
            _f("DealerName", "dealer_name", "Dealer Name", maxlength=200),
            _f("TehsilName", "tehsil_name", "Tehsil", maxlength=120),
            _f("MobileNumber", "mobile_number", "Mobile", maxlength=20),
            _f("Address", "address", "Address", maxlength=400, kind="textarea"),
        ),
        parent_slug="district",
        parent_column="DistrictID",
        parent_required=True,
        extra_parents=(("dso", "DsoID", False), ("aro", "AroID", False), ("si", "SiID", False)),
        child_slug="ration-card",
    ),
    "ration-card": PdsEntity(
        "ration-card",
        "Ration Card Master",
        PdsRationCardMaster,
        "CardID",
        "card_id",
        "bi-card-heading",
        "/public-report/ration-card/ration-card-master",
        8,
        (
            _f("RcNumber", "rc_number", "RC Number", required=True, maxlength=80),
            _f("ExistingRcNumber", "existing_rc_number", "Existing RC Number", maxlength=80),
            _f("SchemeName", "scheme_name", "Scheme", maxlength=80),
            _f("HofName", "hof_name", "Head of Family", maxlength=200),
            _f("MemberCount", "member_count", "Members", maxlength=10, kind="number"),
            _f("MobileNumber", "mobile_number", "Mobile", maxlength=20),
        ),
        parent_slug="fps",
        parent_column="FpsRowID",
        parent_required=True,
    ),
}

MENU_ITEMS = tuple(
    (entity.title, entity.icon, entity.url, entity.menu_order, entity.title)
    for entity in sorted(ENTITIES.values(), key=lambda item: item.menu_order)
)


class PdsMasterService:
    def __init__(self, repository: PdsMasterRepository | None = None):
        self.repo = repository or PdsMasterRepository()

    @staticmethod
    def entity(slug: str) -> PdsEntity:
        entity = ENTITIES.get((slug or "").strip().lower())
        if entity is None:
            raise ValueError("Unknown PDS master.")
        return entity

    def page_config(self, slug: str) -> dict:
        entity = self.entity(slug)
        parents = []
        if entity.parent_slug:
            parent = self.entity(entity.parent_slug)
            parents.append(
                {
                    "slug": parent.slug,
                    "column": entity.parent_column,
                    "key": parent.pk_key,
                    "label": parent.title.replace(" Master", ""),
                    "required": entity.parent_required,
                }
            )
        for extra_slug, extra_column, extra_required in entity.extra_parents:
            extra = self.entity(extra_slug)
            parents.append(
                {
                    "slug": extra.slug,
                    "column": extra_column,
                    "key": extra.pk_key,
                    "label": extra.title.replace(" Master", ""),
                    "required": extra_required,
                }
            )
        return {
            "slug": entity.slug,
            "title": entity.title,
            "url": entity.url,
            "pk_key": entity.pk_key,
            "fields": [
                {
                    "column": field.column,
                    "key": field.key,
                    "label": field.label,
                    "required": field.required,
                    "maxlength": field.maxlength,
                    "kind": field.kind,
                }
                for field in entity.fields
            ],
            "parents": parents,
            "import_note": self._import_note(entity.slug),
        }

    @staticmethod
    def _import_note(slug: str) -> str:
        if slug in {"state", "district"}:
            return "Uttarakhand is imported once from the public Wikipedia district list. Other states can be added later."
        if slug == "dso":
            return "One DSO office row is created per Uttarakhand district as a starting point. Officer names can be edited here."
        if slug == "ration-card":
            return (
                "FPS ID + RC Number is the match key. A new pair is appended. "
                "A matching pair is overwritten: Existing RC Number is cleared and Members is replaced."
            )
        return "Add records here. Public FPS / ration-card dumps are not available without a government login."

    def _label(self, entity: PdsEntity, row) -> str:
        name = None
        code = None
        for field in entity.fields:
            value = getattr(row, field.column, None)
            if not value:
                continue
            if field.column.endswith("Name") or field.column in {"FpsName", "HofName"}:
                name = name or value
            if "Code" in field.column or field.column in {"FpsCode", "RcNumber", "ExistingFpsId"}:
                code = code or value
        if name and code and str(name) != str(code):
            return f"{name} ({code})"
        return str(name or code or getattr(row, entity.pk_column))

    def serialize(self, slug: str, row) -> dict:
        entity = self.entity(slug)
        payload = {
            entity.pk_key: getattr(row, entity.pk_column),
            "active_status": bool(getattr(row, "ActiveStatus", True)),
            "source": getattr(row, "Source", None) or "",
            "label": self._label(entity, row),
        }
        for field in entity.fields:
            value = getattr(row, field.column, None)
            payload[field.key] = value if value is not None else ""
        if entity.parent_column:
            payload[entity.parent_column] = getattr(row, entity.parent_column)
            payload[ENTITIES[entity.parent_slug].pk_key] = getattr(row, entity.parent_column)
        for extra_slug, extra_column, _required in entity.extra_parents:
            payload[extra_column] = getattr(row, extra_column)
            payload[ENTITIES[extra_slug].pk_key] = getattr(row, extra_column)
        return payload

    def list_records(
        self,
        slug: str,
        *,
        search: str | None = None,
        parent_id: int | None = None,
        fps_row_id: int | None = None,
    ) -> list[dict]:
        entity = self.entity(slug)
        filters = {}
        if fps_row_id:
            if entity.slug == "fps":
                filters[entity.pk_column] = int(fps_row_id)
            elif entity.slug == "ration-card":
                filters["FpsRowID"] = int(fps_row_id)
            else:
                return []
        elif entity.parent_column and parent_id:
            filters[entity.parent_column] = parent_id
        rows = self.repo.list_rows(entity.model, search=search, filters=filters)
        parent_labels = self._parent_labels(entity, rows)
        extra_labels = {
            extra_slug: self._lookup_labels(ENTITIES[extra_slug], {getattr(row, extra_column) for row in rows})
            for extra_slug, extra_column, _req in entity.extra_parents
        }
        result = []
        for row in rows:
            item = self.serialize(slug, row)
            if entity.parent_column:
                item["parent_label"] = parent_labels.get(getattr(row, entity.parent_column), "")
            for extra_slug, extra_column, _req in entity.extra_parents:
                item[f"{extra_slug}_label"] = extra_labels[extra_slug].get(getattr(row, extra_column), "")
            result.append(item)
        return result

    def options(self, slug: str, *, parent_id: int | None = None) -> list[dict]:
        rows = self.list_records(slug, parent_id=parent_id)
        entity = self.entity(slug)
        return [{"id": row[entity.pk_key], "label": row["label"]} for row in rows]

    def _lookup_labels(self, entity: PdsEntity, ids: set) -> dict[int, str]:
        labels = {}
        for row_id in ids:
            if not row_id:
                continue
            row = self.repo.get(entity.model, int(row_id))
            if row is not None:
                labels[int(row_id)] = self._label(entity, row)
        return labels

    def _parent_labels(self, entity: PdsEntity, rows: list) -> dict[int, str]:
        if not entity.parent_slug or not entity.parent_column:
            return {}
        ids = {getattr(row, entity.parent_column) for row in rows}
        return self._lookup_labels(self.entity(entity.parent_slug), ids)

    def get_record(self, slug: str, row_id: int) -> dict:
        entity = self.entity(slug)
        row = self.repo.get(entity.model, row_id)
        if row is None:
            raise ValueError(f"{entity.title} record not found.")
        item = self.serialize(slug, row)
        if entity.parent_column:
            labels = self._parent_labels(entity, [row])
            item["parent_label"] = labels.get(getattr(row, entity.parent_column), "")
        for extra_slug, extra_column, _req in entity.extra_parents:
            extra_labels = self._lookup_labels(ENTITIES[extra_slug], {getattr(row, extra_column)})
            item[f"{extra_slug}_label"] = extra_labels.get(getattr(row, extra_column), "")
        return item

    def _clean(self, value, maxlength: int) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        return text[:maxlength]

    def _parse_form(self, entity: PdsEntity, form: dict) -> dict:
        data = {}
        for field in entity.fields:
            raw = form.get(field.column, form.get(field.key))
            if field.kind == "number":
                text = str(raw or "").strip()
                if not text:
                    if field.required:
                        raise ValueError(f"{field.label} is required.")
                    data[field.column] = None
                    continue
                try:
                    data[field.column] = int(float(text))
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{field.label} must be a number.") from exc
                continue
            value = self._clean(raw, field.maxlength)
            if field.required and not value:
                raise ValueError(f"{field.label} is required.")
            data[field.column] = value
        if "ActiveStatus" in form or "active_status" in form:
            active_raw = str(form.get("ActiveStatus", form.get("active_status", ""))).strip().lower()
            data["ActiveStatus"] = active_raw in {"1", "true", "on", "yes"}
        else:
            data["ActiveStatus"] = True
        if entity.parent_column:
            raw_parent = form.get(entity.parent_column) or form.get(ENTITIES[entity.parent_slug].pk_key)
            if not raw_parent and entity.parent_required:
                raise ValueError(f"{ENTITIES[entity.parent_slug].title.replace(' Master', '')} is required.")
            data[entity.parent_column] = int(raw_parent) if str(raw_parent or "").isdigit() else None
            if entity.parent_required and not data[entity.parent_column]:
                raise ValueError(f"{ENTITIES[entity.parent_slug].title.replace(' Master', '')} is required.")
        for extra_slug, extra_column, extra_required in entity.extra_parents:
            raw_extra = form.get(extra_column) or form.get(ENTITIES[extra_slug].pk_key)
            data[extra_column] = int(raw_extra) if str(raw_extra or "").isdigit() else None
            if extra_required and not data[extra_column]:
                raise ValueError(f"{ENTITIES[extra_slug].title.replace(' Master', '')} is required.")
        return data

    def create_record(self, slug: str, form: dict, *, created_by: str = "System") -> dict:
        entity = self.entity(slug)
        data = self._parse_form(entity, form)

        def _write() -> dict:
            if entity.slug == "ration-card":
                row, _action = self.upsert_ration_card_row(
                    data, actor=created_by, source="manual", wipe_existing_on_update=False
                )
                return self.serialize(slug, row)
            row = self.repo.create(entity.model, {**data, "CreatedBy": created_by, "Source": data.get("Source") or "manual"})
            return self.serialize(slug, row)

        return persist(_write)

    def upsert_ration_card_row(
        self,
        data: dict,
        *,
        actor: str,
        source: str = "manual",
        wipe_existing_on_update: bool = False,
    ):
        fps_row_id = data.get("FpsRowID")
        rc_number = str(data.get("RcNumber") or "").strip()
        if not fps_row_id or not rc_number:
            raise ValueError("FPS and RC Number are required.")
        found = self.repo.find_ration_card(int(fps_row_id), rc_number)
        payload = {**data, "Source": source, "RcNumber": rc_number[:80]}
        if found is None:
            row = self.repo.create(PdsRationCardMaster, {**payload, "CreatedBy": actor})
            return row, "added"
        update = {**payload, "ModifiedBy": actor}
        if wipe_existing_on_update:
            update["ExistingRcNumber"] = None
        self.repo.update(found, update)
        return found, "updated"

    def upsert_ration_cards(self, cards: list[dict], *, actor: str) -> dict:
        added = 0
        updated = 0
        for data in cards:
            _row, action = self.upsert_ration_card_row(
                data, actor=actor, source="csv-import", wipe_existing_on_update=True
            )
            if action == "added":
                added += 1
            else:
                updated += 1
        return {"added": added, "updated": updated}

    def update_record(self, slug: str, row_id: int, form: dict, *, modified_by: str = "System") -> dict:
        entity = self.entity(slug)
        data = self._parse_form(entity, form)

        def _write() -> dict:
            row = self.repo.get(entity.model, row_id)
            if row is None:
                raise ValueError(f"{entity.title} record not found.")
            self.repo.update(row, {**data, "ModifiedBy": modified_by})
            return self.serialize(slug, row)

        return persist(_write)

    def delete_record(self, slug: str, row_id: int) -> str:
        entity = self.entity(slug)

        def _write() -> str:
            row = self.repo.get(entity.model, row_id)
            if row is None:
                raise ValueError(f"{entity.title} record not found.")
            assert_master_unused(
                table=entity.model.__tablename__,
                pk_column=entity.pk_column,
                pk_value=row_id,
                display_name=entity.title,
            )
            self.repo.delete(row)
            return f"{entity.title} deleted."

        return persist(_write)

    def import_uttarakhand_once(self) -> dict:
        self.repo.ensure_schema()
        if self.repo.import_done("uttarakhand-geo"):
            return {"skipped": True, "message": "Uttarakhand geography was already imported."}

        source = "wikipedia"
        try:
            districts = fetch_wikipedia_districts()
        except Exception:
            districts = [
                {
                    "district_code": code,
                    "district_name": name,
                    "headquarters": hq,
                    "division_name": division,
                }
                for code, name, hq, division in FALLBACK_UK_DISTRICTS
            ]
            source = "fallback-official-list"

        def _write() -> dict:
            state = None
            existing_states = self.repo.list_rows(PdsStateMaster, search="Uttarakhand")
            for row in existing_states:
                if (row.StateCode or "").upper() in {"05", "5", "UK"} or (row.StateName or "").lower() == "uttarakhand":
                    state = row
                    break
            if state is None:
                state = self.repo.create(
                    PdsStateMaster,
                    {
                        "StateCode": "05",
                        "StateName": "Uttarakhand",
                        "Source": source,
                        "CreatedBy": "System",
                    },
                )
            created = 0
            for item in districts:
                code = (item.get("district_code") or "").upper()
                found = None
                for row in self.repo.list_rows(PdsDistrictMaster, filters={"StateID": state.StateID}):
                    if (row.DistrictCode or "").upper() == code:
                        found = row
                        break
                if found is None:
                    district = self.repo.create(
                        PdsDistrictMaster,
                        {
                            "StateID": state.StateID,
                            "DistrictCode": code,
                            "DistrictName": item["district_name"],
                            "Headquarters": item.get("headquarters") or None,
                            "DivisionName": item.get("division_name") or None,
                            "Source": source,
                            "CreatedBy": "System",
                        },
                    )
                    created += 1
                else:
                    district = found
                dso_code = f"{code}-DSO"
                has_dso = any(
                    (row.DsoCode or "").upper() == dso_code
                    for row in self.repo.list_rows(PdsDsoMaster, filters={"DistrictID": district.DistrictID})
                )
                if not has_dso:
                    self.repo.create(
                        PdsDsoMaster,
                        {
                            "DistrictID": district.DistrictID,
                            "DsoCode": dso_code,
                            "DsoName": f"{item['district_name']} DSO",
                            "Source": "structure",
                            "CreatedBy": "System",
                        },
                    )
            self.repo.mark_import(
                "uttarakhand-geo",
                source=source,
                row_count=len(districts),
                detail="Uttarakhand state + districts; one DSO office row per district.",
            )
            return {
                "skipped": False,
                "source": source,
                "districts": len(districts),
                "created": created,
                "message": f"Imported Uttarakhand ({len(districts)} districts) from {source}.",
            }

        return persist(_write)
