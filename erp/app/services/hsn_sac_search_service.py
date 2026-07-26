"""HSN/SAC code search via public open-data JSON (GitHub), with local cache."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Public open-data masters (no API key).
_PUBLIC_SOURCES = (
    "https://raw.githubusercontent.com/mhdstk/gst-master-data/main/data/sac.json",
    "https://raw.githubusercontent.com/mhdstk/gst-master-data/main/data/hsn.json",
)

_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "hsn_sac_master_cache.json"
_LOCK = threading.Lock()
_ROWS: list[dict] | None = None


def _normalize_row(raw: dict) -> dict | None:
    code = str(raw.get("code") or raw.get("hsn_code") or raw.get("hsn") or "").strip()
    if not code:
        return None
    desc = str(raw.get("desc") or raw.get("description") or raw.get("name") or "").strip()
    kind = str(raw.get("type") or "").strip().lower()
    if kind in {"services", "service", "sac"}:
        hsn_type = "SAC"
    elif kind in {"goods", "good", "hsn"}:
        hsn_type = "HSN"
    elif code.startswith("99"):
        hsn_type = "SAC"
    else:
        hsn_type = "HSN"
    return {
        "code": code,
        "description": desc,
        "hsn_sac_type": hsn_type,
        "label": f"{code} — {desc}" if desc else code,
    }


def _fetch_json(url: str) -> list:
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; JTCS-ItemMaster/1.0)",
            "Accept": "application/json",
        },
    )
    with urlopen(req, timeout=40) as resp:
        raw = resp.read()
    data = json.loads(raw.decode("utf-8"))
    if isinstance(data, dict):
        for key in ("data", "rows", "items", "results"):
            if isinstance(data.get(key), list):
                return data[key]
        return []
    return data if isinstance(data, list) else []


def _load_cache_file() -> list[dict]:
    if not _CACHE_PATH.exists():
        return []
    try:
        data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [r for r in (_normalize_row(x) for x in data) if r]
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return []
    return []


def _save_cache_file(rows: list[dict]) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _seed_rows() -> list[dict]:
    """Minimal offline fallback if public fetch fails."""
    seeds = [
        ("997212", "SAC", "Other accounting and bookkeeping services"),
        ("998221", "SAC", "Legal services"),
        ("998231", "SAC", "Accounting and bookkeeping services"),
        ("998232", "SAC", "Auditing services"),
        ("998314", "SAC", "Information technology consulting and support services"),
        ("997331", "SAC", "Licensing services for the right to use computer software"),
        ("998599", "SAC", "Other support services n.e.c."),
        ("8471", "HSN", "Automatic data processing machines and units thereof"),
        ("847130", "HSN", "Portable automatic data processing machines"),
        ("4901", "HSN", "Printed books, brochures, leaflets"),
    ]
    return [
        {
            "code": code,
            "description": desc,
            "hsn_sac_type": kind,
            "label": f"{code} — {desc}",
        }
        for code, kind, desc in seeds
    ]


def ensure_loaded(*, force_refresh: bool = False) -> list[dict]:
    global _ROWS
    with _LOCK:
        if _ROWS is not None and not force_refresh:
            return _ROWS

        rows: list[dict] = []
        seen: set[str] = set()

        cached = _load_cache_file()
        if cached and not force_refresh:
            _ROWS = cached
            return _ROWS

        for url in _PUBLIC_SOURCES:
            try:
                for raw in _fetch_json(url):
                    if not isinstance(raw, dict):
                        continue
                    row = _normalize_row(raw)
                    if not row:
                        continue
                    key = f"{row['hsn_sac_type']}:{row['code']}"
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(row)
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError, OSError):
                continue

        if not rows:
            rows = cached or _seed_rows()
        else:
            _save_cache_file(rows)

        _ROWS = rows
        return _ROWS


def search_hsn_sac(
    query: str,
    *,
    hsn_sac_type: str | None = None,
    limit: int = 25,
) -> list[dict]:
    q = (query or "").strip().lower()
    if len(q) < 2:
        return []

    rows = ensure_loaded()
    type_filter = (hsn_sac_type or "").strip().upper()
    if type_filter not in {"HSN", "SAC"}:
        type_filter = ""

    starts: list[dict] = []
    contains: list[dict] = []
    for row in rows:
        if type_filter and row["hsn_sac_type"] != type_filter:
            continue
        code = row["code"].lower()
        desc = (row["description"] or "").lower()
        if code.startswith(q) or desc.startswith(q):
            starts.append(row)
        elif q in code or q in desc:
            contains.append(row)
        if len(starts) >= limit:
            break

    out = starts + [r for r in contains if r not in starts]
    return out[: max(1, min(int(limit or 25), 50))]
