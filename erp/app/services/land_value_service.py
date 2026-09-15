"""Public land purchase value — UK GIS circle rates + CircleRate locality pages."""

from __future__ import annotations

import json
import re
import statistics
import time
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

UK_GIS = (
    "https://gis.eregistrationukgov.in/server/rest/services/"
    "UKSTAMPS/SRO_Circle_Rate_Main_Basemap/MapServer/21/query"
)
CIRCLERATE_SEARCH = "https://circlerate.co.in/api/search"
CIRCLERATE_SITE = "https://circlerate.co.in"
USER_AGENT = "JTCS-ERP-LandValue/1.0"
CACHE_TTL = 6 * 3600
TWO = Decimal("0.01")

UNIT_TO_SQM = {
    "sq. ft.": Decimal("0.09290304"),
    "sq. yd. (gaj)": Decimal("0.83612736"),
    "gaj": Decimal("0.83612736"),
    "sq. mt.": Decimal("1"),
    "sq. m": Decimal("1"),
    "sq. km.": Decimal("1000000"),
    "acre": Decimal("4046.8564224"),
    "hectare": Decimal("10000"),
    "are": Decimal("100"),
    "centiare": Decimal("1"),
    "bigha": Decimal("2508.38"),
    "pucca bigha": Decimal("2529.285"),
    "kaccha bigha": Decimal("1618.74"),
    "biswa": Decimal("125.419"),
    "biswansi": Decimal("6.27095"),
    "katha (kattha)": Decimal("126.441"),
    "katha": Decimal("126.441"),
    "dhur": Decimal("6.322"),
    "dismil (decimal)": Decimal("40.468564"),
    "dismil": Decimal("40.468564"),
    "decimal": Decimal("40.468564"),
    "kanal": Decimal("505.857"),
    "marla": Decimal("25.2929"),
    "killa": Decimal("4046.8564224"),
    "guntha (gunta)": Decimal("101.17141"),
    "guntha": Decimal("101.17141"),
    "gunta": Decimal("101.17141"),
    "cent": Decimal("40.468564"),
    "ground": Decimal("222.967"),
    "ankanam": Decimal("60.201"),
    "nali": Decimal("200.670"),
    "mutthi": Decimal("16.7225"),
    "lecha": Decimal("13.378"),
    "chatak": Decimal("16.7225"),
    "karam": Decimal("5.574"),
    "satak": Decimal("40.468564"),
    "percent": Decimal("40.468564"),
    "vigha": Decimal("1858.06"),
    "kani": Decimal("1600"),
    "ghumaon": Decimal("4046.8564224"),
}

UK_STATES = {"uttarakhand", "uttaranchal"}
RURAL_CLASSES = {"rural", ""}


def _q2(value: Decimal) -> Decimal:
    return value.quantize(TWO, rounding=ROUND_HALF_UP)


def _fold(value: str) -> str:
    return " ".join(str(value or "").replace(",", " ").split()).casefold()


def _unit_key(unit: str) -> str:
    return _fold(unit).replace("sq ft", "sq. ft.").replace("sq mt", "sq. mt.")


class LandValueService:
    _cache: dict[str, tuple[float, Any]] = {}

    def lookup(
        self,
        *,
        state: str = "",
        district: str = "",
        tehsil: str = "",
        village: str = "",
        town: str = "",
        locality: str = "",
        area_class: str = "",
        land_area: str | float | Decimal = "",
        land_unit: str = "",
    ) -> dict[str, Any]:
        place = (village or town or locality or "").strip()
        if not (state or "").strip():
            raise ValueError("Select State first.")
        if not (district or "").strip():
            raise ValueError("Select District first.")
        if not place:
            raise ValueError("Select Village / Town / Locality first.")
        sqm = self.area_to_sqm(land_area, land_unit)
        if sqm <= 0:
            raise ValueError("Enter Land Area and Land Unit first.")

        if _fold(state) in UK_STATES:
            hit = self._uk_gis(state, district, tehsil, place, area_class)
        else:
            hit = self._circlerate(state, district, tehsil, place, area_class)
        value = self.compute_value(sqm, hit["rate"], hit["rate_unit"])
        unit_rate = self.compute_value(
            self.area_to_sqm("1", land_unit),
            hit["rate"],
            hit["rate_unit"],
        )
        unit_name = (land_unit or "").strip() or "unit"
        return {
            "ok": True,
            "value": str(_q2(value)),
            "rate": str(_q2(Decimal(str(hit["rate"])))),
            "rate_unit": hit["rate_unit"],
            "rate_label": hit.get("rate_label") or "",
            "unit_rate": str(_q2(unit_rate)),
            "unit_rate_label": f"₹{_q2(unit_rate)} / {unit_name}",
            "matched_place": hit.get("matched_place") or place,
            "source": hit.get("source") or "",
            "source_url": hit.get("source_url") or "",
            "area_sqm": str(_q2(sqm)),
            "note": hit.get("note") or "",
        }

    @staticmethod
    def area_to_sqm(land_area, land_unit: str) -> Decimal:
        try:
            area = Decimal(str(land_area or "").strip() or "0")
        except (InvalidOperation, ValueError):
            raise ValueError("Land Area is invalid.") from None
        if area <= 0:
            return Decimal("0")
        factor = UNIT_TO_SQM.get(_unit_key(land_unit))
        if factor is None:
            raise ValueError("Select a Land Unit.")
        return area * factor

    @staticmethod
    def compute_value(area_sqm: Decimal, rate, rate_unit: str) -> Decimal:
        rate_n = Decimal(str(rate))
        if rate_unit == "hectare":
            return area_sqm / Decimal("10000") * rate_n
        return area_sqm * rate_n

    @staticmethod
    def pick_uk_rate(attrs: dict[str, Any], area_class: str) -> tuple[Decimal, str, str]:
        rural = _fold(area_class) in RURAL_CLASSES
        if rural:
            keys = (
                "CR_Agri_Land",
                "CR_Agri_Beyond_200",
                "CR_Agri_Beyond_350",
                "CR_Agri_Beyond_50",
                "CR_Agri_0_200",
                "CR_Agri_0_50",
            )
            unit = "hectare"
            label = "agricultural circle rate / hectare"
        else:
            keys = (
                "CR_Non_Agri_Land",
                "CR_Non_Agri_Beyond_200",
                "CR_Non_Agri_Beyond_350",
                "CR_Non_Agri_Beyond_50",
                "CR_Non_Agri_0_200",
                "Circle_Rate",
            )
            unit = "sqm"
            label = "non-agricultural circle rate / sq.m"
        for key in keys:
            raw = attrs.get(key)
            if raw in (None, "", 0, 0.0):
                continue
            try:
                rate = Decimal(str(raw))
            except (InvalidOperation, ValueError):
                continue
            if rate > 0:
                return rate, unit, label
        raise ValueError("Circle rate is not published for this village.")

    @staticmethod
    def parse_inr(text: str) -> Decimal | None:
        raw = re.sub(r"[^\d.]", "", str(text or "").replace(",", ""))
        if not raw:
            return None
        try:
            value = Decimal(raw)
        except (InvalidOperation, ValueError):
            return None
        return value if value > 0 else None

    @staticmethod
    def parse_circlerate_land_rates(html: str) -> list[Decimal]:
        body = html
        start = html.lower().find("<tbody")
        end = html.lower().find("</tbody>", start)
        if start >= 0 and end > start:
            body = html[start:end]
        rates: list[Decimal] = []
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, flags=re.I | re.S):
            cells = [
                re.sub(r"<[^>]+>", " ", cell)
                for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.I | re.S)
            ]
            texts = [" ".join(cell.split()) for cell in cells]
            if len(texts) < 2:
                continue
            amount = LandValueService.parse_inr(texts[1])
            if amount is not None:
                rates.append(amount)
        return rates

    def _uk_gis(
        self,
        state: str,
        district: str,
        tehsil: str,
        place: str,
        area_class: str,
    ) -> dict[str, Any]:
        rows = self._uk_query(district, tehsil, place)
        if not rows and tehsil:
            rows = self._uk_query(district, "", place)
        if not rows:
            raise ValueError("No Uttarakhand GIS circle rate found for this village.")
        attrs = self._best_uk_row(rows, district, tehsil, place)
        rate, unit, label = self.pick_uk_rate(attrs, area_class)
        village = attrs.get("Village_Name") or place
        return {
            "rate": rate,
            "rate_unit": unit,
            "rate_label": label,
            "matched_place": village,
            "source": "Uttarakhand Stamps & Registration GIS circle rates",
            "source_url": "https://gis.eregistrationukgov.in/gisportal/",
            "note": f"{village}, {attrs.get('Tehsil_Name') or tehsil}, {attrs.get('DistrictName') or district}",
        }

    def _uk_query(self, district: str, tehsil: str, place: str) -> list[dict]:
        where = [self._like("Village_Name", place)]
        if district:
            where.append(
                f"({self._like('DistrictName', district)} OR {self._like('District_Name_Eng', district)})"
            )
        if tehsil:
            where.append(
                f"({self._like('Tehsil_Name', tehsil)} OR {self._like('SubdistrictName', tehsil)})"
            )
        key = f"uk:{_fold(district)}:{_fold(tehsil)}:{_fold(place)}"
        cached = self._from_cache(key)
        if cached is not None:
            return cached
        params = {
            "where": " AND ".join(where),
            "outFields": ",".join(
                (
                    "Village_Name",
                    "DistrictName",
                    "District_Name_Eng",
                    "Tehsil_Name",
                    "SubdistrictName",
                    "Type",
                    "CR_Agri_Land",
                    "CR_Non_Agri_Land",
                    "CR_Agri_Beyond_200",
                    "CR_Non_Agri_Beyond_200",
                    "CR_Agri_Beyond_350",
                    "CR_Non_Agri_Beyond_350",
                    "CR_Agri_Beyond_50",
                    "CR_Non_Agri_Beyond_50",
                    "CR_Agri_0_200",
                    "CR_Non_Agri_0_200",
                    "CR_Agri_0_50",
                    "Circle_Rate",
                    "SRO_Name",
                )
            ),
            "returnGeometry": "false",
            "resultRecordCount": "40",
            "f": "json",
        }
        payload = self._http_json(f"{UK_GIS}?{urlencode(params)}")
        rows = [feat.get("attributes") or {} for feat in (payload.get("features") or [])]
        self._to_cache(key, rows)
        return rows

    def _best_uk_row(self, rows: list[dict], district: str, tehsil: str, place: str) -> dict:
        want = _fold(place)

        def score(row: dict) -> int:
            name = _fold(row.get("Village_Name") or "")
            pts = 0
            if name == want:
                pts += 80
            elif want and want in name:
                pts += 40
            if _fold(row.get("Type") or "") == "revenue":
                pts += 10
            if tehsil and _fold(row.get("Tehsil_Name") or "") == _fold(tehsil):
                pts += 10
            if district and _fold(row.get("DistrictName") or "") == _fold(district):
                pts += 5
            return pts

        return max(rows, key=score)

    def _circlerate(
        self,
        state: str,
        district: str,
        tehsil: str,
        place: str,
        area_class: str,
    ) -> dict[str, Any]:
        hits = self._circlerate_search(place) or self._circlerate_search(f"{place} {district}")
        if not hits:
            raise ValueError("No public circle-rate locality found for this place.")
        hit = self._best_circlerate_hit(hits, state, district, tehsil, place)
        path = str(hit.get("path") or "").strip()
        if not path:
            raise ValueError("No public circle-rate page found for this place.")
        html = self._circlerate_page(path)
        rates = self.parse_circlerate_land_rates(html)
        if not rates:
            raise ValueError("Circle-rate table has no land value for this locality.")
        rate = statistics.median(rates)
        return {
            "rate": rate,
            "rate_unit": "sqm",
            "rate_label": "ready reckoner land rate / sq.m",
            "matched_place": hit.get("display_name") or place,
            "source": "Government circle / ready reckoner rates via CircleRate.co.in",
            "source_url": CIRCLERATE_SITE + path,
            "note": f"{hit.get('display_name') or place} — median of {len(rates)} land rates",
        }

    def _circlerate_search(self, query: str) -> list[dict]:
        query = (query or "").strip()
        if not query:
            return []
        key = f"crsearch:{_fold(query)}"
        cached = self._from_cache(key)
        if cached is not None:
            return cached
        payload = self._http_json(f"{CIRCLERATE_SEARCH}?q={quote(query)}")
        rows = payload if isinstance(payload, list) else []
        self._to_cache(key, rows)
        return rows

    def _best_circlerate_hit(
        self,
        hits: list[dict],
        state: str,
        district: str,
        tehsil: str,
        place: str,
    ) -> dict:
        def score(hit: dict) -> int:
            pts = 0
            if place and _fold(hit.get("village") or hit.get("display_name") or "") == _fold(place):
                pts += 50
            elif place and _fold(place) in _fold(hit.get("display_name") or ""):
                pts += 25
            if district and _fold(hit.get("district") or "") == _fold(district):
                pts += 20
            if state and _fold(hit.get("state") or "") == _fold(state):
                pts += 20
            if tehsil and _fold(hit.get("taluka") or "") == _fold(tehsil):
                pts += 10
            return pts

        return max(hits, key=score)

    def _circlerate_page(self, path: str) -> str:
        path = path if path.startswith("/") else "/" + path
        key = f"crpage:{path}"
        cached = self._from_cache(key)
        if cached is not None:
            return cached
        html = self._http_text(CIRCLERATE_SITE + path)
        self._to_cache(key, html)
        return html

    @staticmethod
    def _like(field: str, value: str) -> str:
        text = str(value or "").replace("'", "''").strip().upper()
        return f"UPPER({field}) LIKE '%{text}%'"

    def _http_json(self, url: str):
        return json.loads(self._http_text(url))

    def _http_text(self, url: str) -> str:
        req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/html"})
        try:
            with urlopen(req, timeout=25) as resp:
                return resp.read().decode("utf-8", "replace")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise ValueError("Unable to load public land value right now.") from exc

    def _from_cache(self, key: str):
        row = LandValueService._cache.get(key)
        if not row:
            return None
        if time.time() - row[0] > CACHE_TTL:
            return None
        return row[1]

    def _to_cache(self, key: str, value) -> None:
        LandValueService._cache[key] = (time.time(), value)
