"""India GST state codes (first 2 digits of GSTIN) by state / UT name."""

from __future__ import annotations

# Official GST state codes (as commonly used on GST portal).
_GST_STATE_CODES: dict[str, str] = {
    "jammu and kashmir": "01",
    "jammu & kashmir": "01",
    "himachal pradesh": "02",
    "punjab": "03",
    "chandigarh": "04",
    "uttarakhand": "05",
    "haryana": "06",
    "delhi": "07",
    "nct of delhi": "07",
    "rajasthan": "08",
    "uttar pradesh": "09",
    "bihar": "10",
    "sikkim": "11",
    "arunachal pradesh": "12",
    "nagaland": "13",
    "manipur": "14",
    "mizoram": "15",
    "tripura": "16",
    "meghalaya": "17",
    "assam": "18",
    "west bengal": "19",
    "jharkhand": "20",
    "odisha": "21",
    "orissa": "21",
    "chhattisgarh": "22",
    "madhya pradesh": "23",
    "gujarat": "24",
    "dadra and nagar haveli and daman and diu": "26",
    "dadra and nagar haveli": "26",
    "daman and diu": "26",
    "maharashtra": "27",
    "andhra pradesh": "28",  # pre-split / legacy; also used in some feeds
    "andhra pradesh (new)": "37",
    "karnataka": "29",
    "goa": "30",
    "lakshadweep": "31",
    "kerala": "32",
    "tamil nadu": "33",
    "puducherry": "34",
    "pondicherry": "34",
    "andaman and nicobar islands": "35",
    "andaman & nicobar islands": "35",
    "telangana": "36",
    "andhra pradesh (new state)": "37",
    "ladakh": "38",
    "other territory": "97",
    "other country": "99",
}


def gst_code_for_state(state: str | None) -> str:
    if not state:
        return ""
    key = " ".join(str(state).strip().lower().split())
    if key in _GST_STATE_CODES:
        return _GST_STATE_CODES[key]
    # Soft match: remove punctuation
    compact = key.replace("&", "and")
    if compact in _GST_STATE_CODES:
        return _GST_STATE_CODES[compact]
    # Andhra Pradesh: postal API often returns "Andhra Pradesh" — prefer 37 (current)
    if key == "andhra pradesh":
        return "37"
    return ""
