"""Live index quotes for the ERP header ticker (no API key)."""

from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

_LOCK = threading.Lock()
_CACHE: dict = {"ts": 0.0, "payload": None}
_CACHE_SECONDS = 50
_IST = timezone(timedelta(hours=5, minutes=30))

_WIDGET_URL = "https://www.moneycontrol.com/mc/widget/globalindices"

_INDICES = (
    {
        "id": "nifty50",
        "label": "Nifty 50",
        "short": "Nifty",
        "row": 1,
        "source": "moneycontrol",
        "url": "https://priceapi.moneycontrol.com/pricefeed/notapplicable/inidicesindia/in%3BNSX",
    },
    {
        "id": "sensex",
        "label": "Sensex",
        "short": "Sensex",
        "row": 1,
        "source": "moneycontrol",
        "url": "https://priceapi.moneycontrol.com/pricefeed/notapplicable/inidicesindia/in%3BSEN",
    },
    {
        "id": "banknifty",
        "label": "Bank Nifty",
        "short": "BankNf",
        "row": 1,
        "source": "moneycontrol",
        "url": "https://priceapi.moneycontrol.com/pricefeed/notapplicable/inidicesindia/in%3Bnbx",
    },
    {
        "id": "giftnifty",
        "label": "GIFT Nifty",
        "short": "GIFT Nifty",
        "row": 2,
        "source": "widget",
        "widget_name": "GIFT NIFTY",
    },
    {
        "id": "taiwan",
        "label": "Taiwan Index",
        "short": "Taiwan",
        "row": 2,
        "source": "yahoo",
        "yahoo": "^TWII",
    },
    {
        "id": "nikkei",
        "label": "Nikkei 225",
        "short": "Nikkei",
        "row": 2,
        "source": "yahoo",
        "yahoo": "^N225",
    },
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html,text/plain,*/*",
    "Referer": "https://www.moneycontrol.com/",
}

_WIDGET_ROW_RE = re.compile(
    r">(?P<name>GIFT NIFTY|Nikkei 225)</a>.*?</td>\s*"
    r"<td>(?P<price>[0-9,]+\.?[0-9]*)</td>\s*"
    r"<td><span class=\"(?:red|green)_color\">(?P<change>[+\-]?[0-9,]+\.?[0-9]*)</span></td>\s*"
    r"<td><span class=\"(?:red|green)_color\">\((?P<percent>[+\-]?[0-9,]+\.?[0-9]*)%?\)</span></td>",
    re.IGNORECASE | re.DOTALL,
)


def _empty_row(spec: dict) -> dict:
    return {
        "id": spec["id"],
        "label": spec["label"],
        "short": spec["short"],
        "row": int(spec.get("row") or 1),
        "price": None,
        "change": None,
        "percent": None,
        "market_state": "",
        "updated": "",
        "ok": False,
        "note": spec.get("note") or "",
    }


def _num(value) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _http_get(url: str, *, timeout: int = 8) -> bytes:
    req = Request(url, headers=_HEADERS)
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _ist_now() -> datetime:
    return datetime.now(_IST)


def _gift_session_open(now: datetime | None = None) -> bool:
    """NSE IX / GIFT Nifty is open most of the weekday in IST."""
    now = now or _ist_now()
    weekday = now.weekday()
    minutes = now.hour * 60 + now.minute
    if weekday == 6:
        return False
    if weekday == 5 and minutes >= 165:
        return False
    if weekday == 0 and minutes < 390:
        return False
    return True


def _fetch_moneycontrol(spec: dict) -> dict:
    row = _empty_row(spec)
    try:
        raw = json.loads(_http_get(spec["url"]).decode("utf-8", errors="replace"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
        return row
    data = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(data, dict):
        return row
    price = _num(data.get("pricecurrent"))
    if price is None:
        return row
    row["price"] = round(price, 2)
    row["change"] = round(_num(data.get("pricechange")) or 0.0, 2)
    row["percent"] = round(_num(data.get("pricepercentchange")) or 0.0, 2)
    row["market_state"] = str(data.get("market_state") or "").strip().upper()
    row["updated"] = str(data.get("lastupd") or "").strip()
    row["ok"] = True
    return row


def _fetch_yahoo(spec: dict) -> dict:
    row = _empty_row(spec)
    symbol = quote(spec["yahoo"], safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
    try:
        raw = json.loads(_http_get(url).decode("utf-8", errors="replace"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
        return row
    chart = raw.get("chart") if isinstance(raw, dict) else None
    result = None
    if isinstance(chart, dict):
        rows = chart.get("result") or []
        if rows:
            result = rows[0]
    if not isinstance(result, dict):
        return row
    meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
    price = _num(meta.get("regularMarketPrice"))
    prev = _num(meta.get("chartPreviousClose") or meta.get("previousClose"))
    if price is None:
        return row
    change = round(price - prev, 2) if prev else 0.0
    percent = round((change / prev) * 100, 2) if prev else 0.0
    last_ts = _num(meta.get("regularMarketTime")) or 0.0
    open_now = last_ts > 0 and (time.time() - last_ts) < 25 * 60
    row["price"] = round(price, 2)
    row["change"] = change
    row["percent"] = percent
    row["market_state"] = "OPEN" if open_now else "CLOSED"
    if last_ts:
        row["updated"] = datetime.fromtimestamp(last_ts, tz=_IST).strftime("%d %b %H:%M")
    row["ok"] = True
    return row


def _fetch_widget_html() -> str:
    try:
        return _http_get(_WIDGET_URL, timeout=10).decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError, OSError):
        return ""


def _parse_widget_index(spec: dict, html: str) -> dict:
    row = _empty_row(spec)
    name = (spec.get("widget_name") or spec["label"]).strip().casefold()
    if not html:
        return row
    for match in _WIDGET_ROW_RE.finditer(html):
        if (match.group("name") or "").strip().casefold() != name:
            continue
        price = _num(match.group("price"))
        if price is None:
            return row
        row["price"] = round(price, 2)
        row["change"] = round(_num(match.group("change")) or 0.0, 2)
        row["percent"] = round(_num(match.group("percent")) or 0.0, 2)
        row["market_state"] = "OPEN" if _gift_session_open() else "CLOSED"
        row["updated"] = _ist_now().strftime("%d %b %H:%M")
        row["ok"] = True
        return row
    return row


def _fetch_one(spec: dict, widget_html: str) -> dict:
    source = spec.get("source") or "moneycontrol"
    if source == "yahoo":
        return _fetch_yahoo(spec)
    if source == "widget":
        return _parse_widget_index(spec, widget_html)
    return _fetch_moneycontrol(spec)


def get_quotes(*, force: bool = False) -> dict:
    now = time.time()
    with _LOCK:
        if (
            not force
            and _CACHE["payload"] is not None
            and (now - float(_CACHE["ts"] or 0)) < _CACHE_SECONDS
        ):
            return _CACHE["payload"]

    widget_needed = any(spec.get("source") == "widget" for spec in _INDICES)
    widget_html = _fetch_widget_html() if widget_needed else ""
    with ThreadPoolExecutor(max_workers=6) as pool:
        indices = list(pool.map(lambda spec: _fetch_one(spec, widget_html), _INDICES))

    live = any(
        item.get("ok") and str(item.get("market_state") or "").upper() == "OPEN"
        for item in indices
    ) or _gift_session_open()
    payload = {
        "ok": any(item.get("ok") for item in indices),
        "live": live,
        "indices": indices,
        "fetched_at": int(now),
    }
    with _LOCK:
        _CACHE["ts"] = now
        _CACHE["payload"] = payload
    return payload
