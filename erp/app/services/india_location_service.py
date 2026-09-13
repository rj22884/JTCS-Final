"""India address dropdowns — LGD (Bharatlas) + India Post public APIs."""

from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BHARATLAS = "https://bharatlas.com/api/v1/layers"
POSTAL_OFFICE = "https://api.postalpincode.in/postoffice/{name}"
POSTAL_PINCODE = "https://api.postalpincode.in/pincode/{pin}"
STATES_DISTRICTS_FALLBACK = (
    "https://raw.githubusercontent.com/sab99r/Indian-States-And-Districts/"
    "master/states-and-districts.json"
)
USER_AGENT = "JTCS-ERP-IndiaLocation/1.0"
CACHE_TTL = {
    "states": 24 * 3600,
    "districts": 12 * 3600,
    "talukas": 6 * 3600,
    "blocks": 6 * 3600,
    "villages": 2 * 3600,
    "panchayats": 2 * 3600,
    "pincodes": 2 * 3600,
    "places": 2 * 3600,
}

ULB_KINDS = (
    "Municipal Corporation",
    "Municipal Council",
    "Nagar Palika Parishad",
    "Nagar Panchayat",
    "Cantonment Board",
    "Industrial Development Authority",
)


class IndiaLocationService:
    _cache: dict[str, tuple[float, list[dict]]] = {}

    def list_options(
        self,
        level: str,
        *,
        state: str = "",
        district: str = "",
        taluka: str = "",
        village: str = "",
        pincode: str = "",
    ) -> list[dict]:
        level = (level or "").strip().lower()
        state = (state or "").strip()
        district = (district or "").strip()
        taluka = (taluka or "").strip()
        village = (village or "").strip()
        pincode = (pincode or "").strip()
        if level == "states":
            return self._states()
        if level == "districts":
            if not state:
                return []
            return self._districts(state)
        if level in {"talukas", "tehsils"}:
            if not state or not district:
                return []
            return self._talukas(state, district)
        if level == "blocks":
            if not state or not district:
                return []
            return self._blocks(state, district)
        if level in {"places", "villages", "towns", "locality"}:
            rows = self._places_for_pincode(pincode) if pincode else []
            if rows:
                return rows
            if not state or not district:
                return []
            return self._villages(state, district, taluka)
        if level == "panchayats":
            if not state or not district:
                return []
            return self._panchayats(state, district, taluka)
        if level == "pincodes":
            return self._pincodes_for_area(state, district, taluka)
        if level == "ulb":
            if not district:
                return []
            title = self._pretty(district)
            return [{"value": f"{title} {kind}", "label": f"{title} {kind}"} for kind in ULB_KINDS]
        raise ValueError("Unknown location level.")

    def _states(self) -> list[dict]:
        cached = self._from_cache("states")
        if cached is not None:
            return cached
        try:
            payload = self._bharatlas("lgd_states", {"limit": "50", "select": "STNAME"})
            rows = [
                {"value": raw, "label": self._pretty(raw)}
                for raw in (r.get("STNAME") for r in payload)
                if raw
            ]
            rows.sort(key=lambda r: r["label"])
        except Exception:
            rows = self._fallback_states()
        self._to_cache("states", rows)
        return rows

    def _districts(self, state: str) -> list[dict]:
        key = f"districts:{state.casefold()}"
        cached = self._from_cache(key)
        if cached is not None:
            return cached
        try:
            payload = self._bharatlas(
                "lgd_districts",
                {"stname": self._lgd_state(state), "limit": "200", "select": "dtname"},
            )
            rows = self._unique_name_rows(payload, "dtname")
        except Exception:
            rows = self._fallback_districts(state)
        self._to_cache(key, rows)
        return rows

    def _talukas(self, state: str, district: str) -> list[dict]:
        key = f"talukas:{state.casefold()}:{district.casefold()}"
        cached = self._from_cache(key)
        if cached is not None:
            return cached
        rows = self._query_name_rows(
            "lgd_subdistricts",
            {
                "stname": self._lgd_state(state),
                "dtname": district,
                "limit": "500",
                "select": "sdtname",
            },
            "sdtname",
            retry_upper_keys=("dtname",),
        )
        self._to_cache(key, rows)
        return rows

    def _blocks(self, state: str, district: str) -> list[dict]:
        key = f"blocks:{state.casefold()}:{district.casefold()}"
        cached = self._from_cache(key)
        if cached is not None:
            return cached
        rows = self._query_name_rows(
            "lgd_blocks",
            {
                "state": self._lgd_state(state),
                "district": district,
                "limit": "500",
                "select": "block_name",
            },
            "block_name",
            retry_upper_keys=("district",),
        )
        self._to_cache(key, rows)
        return rows

    def _villages(self, state: str, district: str, taluka: str) -> list[dict]:
        key = f"villages:{state.casefold()}:{district.casefold()}:{taluka.casefold()}"
        cached = self._from_cache(key)
        if cached is not None:
            return cached
        params = {
            "stname": self._lgd_state(state),
            "dtname": district,
            "limit": "1000",
            "select": "vilname11",
        }
        if taluka:
            params["sdtname"] = taluka
        rows = self._query_name_rows(
            "lgd_villages",
            params,
            "vilname11",
            retry_upper_keys=("dtname", "sdtname"),
        )
        self._to_cache(key, rows)
        return rows

    def _panchayats(self, state: str, district: str, taluka: str) -> list[dict]:
        key = f"panchayats:{state.casefold()}:{district.casefold()}:{taluka.casefold()}"
        cached = self._from_cache(key)
        if cached is not None:
            return cached
        params = {
            "stname": self._lgd_state(state),
            "dtname": district,
            "limit": "1000",
            "select": "gp_name",
        }
        if taluka:
            params["sdtname"] = taluka
        rows = self._query_name_rows(
            "lgd_panchayats",
            params,
            "gp_name",
            retry_upper_keys=("dtname", "sdtname"),
        )
        self._to_cache(key, rows)
        return rows

    def _query_name_rows(
        self,
        layer: str,
        params: dict,
        field: str,
        retry_upper_keys: tuple[str, ...] = (),
    ) -> list[dict]:
        try:
            rows = self._unique_name_rows(self._bharatlas(layer, params), field)
            if rows or not retry_upper_keys:
                return rows
            alt = dict(params)
            for key in retry_upper_keys:
                if alt.get(key):
                    alt[key] = str(alt[key]).upper()
            return self._unique_name_rows(self._bharatlas(layer, alt), field)
        except Exception:
            return []

    def _pincodes_for_area(self, state: str, district: str, taluka: str) -> list[dict]:
        if not (district or taluka):
            return []
        key = f"pincodes:{state.casefold()}:{district.casefold()}:{taluka.casefold()}"
        cached = self._from_cache(key)
        if cached is not None:
            return cached
        offices = self._postal_offices(taluka) if taluka else []
        if not offices and district:
            offices = self._postal_offices(district)
        filtered = [
            office
            for office in offices
            if self._office_matches_area(office, state, district)
        ]
        rows = self._unique_pincode_rows(filtered or offices)
        self._to_cache(key, rows)
        return rows

    def _pincodes(self, place: str) -> list[dict]:
        if not place:
            return []
        key = f"pincodes:{place.casefold()}"
        cached = self._from_cache(key)
        if cached is not None:
            return cached
        rows = self._unique_pincode_rows(self._postal_offices(place))
        self._to_cache(key, rows)
        return rows

    def _places_for_pincode(self, pincode: str) -> list[dict]:
        pin = "".join(ch for ch in str(pincode) if ch.isdigit())
        if len(pin) != 6:
            return []
        key = f"places:{pin}"
        cached = self._from_cache(key)
        if cached is not None:
            return cached
        seen: set[str] = set()
        rows = []
        for office in self._postal_by_pincode(pin):
            name = (office.get("name") or "").strip()
            fold = name.casefold()
            if not name or fold in seen:
                continue
            seen.add(fold)
            rows.append({"value": name, "label": self._pretty(name)})
        rows.sort(key=lambda r: r["label"])
        self._to_cache(key, rows)
        return rows

    @staticmethod
    def _unique_pincode_rows(offices: list[dict]) -> list[dict]:
        seen: set[str] = set()
        rows = []
        for office in offices:
            pin = str(office.get("pincode") or "").strip()
            name = office.get("name") or ""
            if not pin or pin in seen:
                continue
            seen.add(pin)
            label = f"{pin} — {name}" if name else pin
            rows.append({"value": pin, "label": label})
        rows.sort(key=lambda r: r["value"])
        return rows

    @staticmethod
    def _office_matches_area(office: dict, state: str, district: str) -> bool:
        office_district = (office.get("district") or "").casefold()
        office_state = (office.get("state") or "").casefold()
        want_district = district.casefold()
        want_state = state.casefold()
        if want_district and office_district:
            if want_district not in office_district and office_district not in want_district:
                return False
        if want_state and office_state:
            if want_state not in office_state and office_state not in want_state:
                return False
        return True

    def _postal_offices(self, name: str) -> list[dict]:
        if not name:
            return []
        return self._parse_postal_payload(self._http_json_soft(POSTAL_OFFICE.format(name=name.strip())))

    def _postal_by_pincode(self, pin: str) -> list[dict]:
        return self._parse_postal_payload(self._http_json_soft(POSTAL_PINCODE.format(pin=pin)))

    def _http_json_soft(self, url: str):
        try:
            return self._http_json(url)
        except Exception:
            return None

    @staticmethod
    def _parse_postal_payload(payload) -> list[dict]:
        row = payload[0] if isinstance(payload, list) and payload else {}
        if str(row.get("Status") or "").lower() != "success":
            return []
        out = []
        for office in row.get("PostOffice") or []:
            if not isinstance(office, dict):
                continue
            out.append(
                {
                    "name": (office.get("Name") or "").strip(),
                    "pincode": str(office.get("Pincode") or "").strip(),
                    "district": (office.get("District") or "").strip(),
                    "state": (office.get("State") or "").strip(),
                    "block": (office.get("Block") or office.get("Division") or "").strip(),
                }
            )
        return out

    def _fallback_states(self) -> list[dict]:
        data = self._http_json(STATES_DISTRICTS_FALLBACK)
        rows = []
        for item in data.get("states") or []:
            name = (item.get("state") or "").strip()
            if name:
                rows.append({"value": name, "label": name})
        rows.sort(key=lambda r: r["label"])
        return rows

    def _fallback_districts(self, state: str) -> list[dict]:
        data = self._http_json(STATES_DISTRICTS_FALLBACK)
        want = state.casefold()
        for item in data.get("states") or []:
            name = (item.get("state") or "").strip()
            if name.casefold() == want or self._lgd_state(name) == self._lgd_state(state):
                return [
                    {"value": d, "label": d}
                    for d in (item.get("districts") or [])
                    if d
                ]
        return []

    def _bharatlas(self, layer: str, params: dict) -> list[dict]:
        url = f"{BHARATLAS}/{layer}/query?{urlencode(params)}"
        payload = self._http_json(url)
        data = payload.get("data") if isinstance(payload, dict) else {}
        return list((data or {}).get("rows") or [])

    def _http_json(self, url: str):
        req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ValueError("Unable to load India location data right now.") from exc

    @staticmethod
    def _unique_name_rows(payload: list[dict], field: str) -> list[dict]:
        seen: set[str] = set()
        rows = []
        for item in payload:
            raw = str((item or {}).get(field) or "").strip()
            if not raw:
                continue
            key = raw.casefold()
            if key in seen:
                continue
            seen.add(key)
            rows.append({"value": raw, "label": IndiaLocationService._pretty(raw)})
        rows.sort(key=lambda r: r["label"])
        return rows

    @staticmethod
    def _pretty(name: str) -> str:
        text = " ".join(str(name or "").replace(",", " ").split())
        if not text:
            return ""
        small = {"and", "of", "&"}
        parts = []
        for idx, word in enumerate(text.split()):
            low = word.lower()
            if word == "&":
                parts.append("&")
            elif idx and low in small:
                parts.append(low)
            else:
                parts.append(word[:1].upper() + word[1:].lower())
        return " ".join(parts)

    @staticmethod
    def _lgd_state(name: str) -> str:
        text = " ".join(str(name or "").replace(",", " ").split()).upper()
        aliases = {
            "JAMMU AND KASHMIR": "JAMMU & KASHMIR",
            "ANDAMAN AND NICOBAR ISLANDS": "ANDAMAN & NICOBAR",
            "ANDAMAN AND NICOBAR": "ANDAMAN & NICOBAR",
            "DADRA AND NAGAR HAVELI AND DAMAN AND DIU": "DADRA,NAGAR HAVELI,DAMAN & DIU",
            "NCT OF DELHI": "DELHI",
            "ORISSA": "ODISHA",
            "PONDICHERRY": "PUDUCHERRY",
        }
        return aliases.get(text, text)

    def _from_cache(self, key: str) -> list[dict] | None:
        row = IndiaLocationService._cache.get(key)
        if not row:
            return None
        ttl = CACHE_TTL.get(key.split(":")[0], 3600)
        if time.time() - row[0] > ttl:
            return None
        return row[1]

    def _to_cache(self, key: str, rows: list[dict]) -> None:
        IndiaLocationService._cache[key] = (time.time(), rows)
