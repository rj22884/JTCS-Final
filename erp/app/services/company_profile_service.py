"""Company profile used by the header and by sale invoices."""

from __future__ import annotations

import re

from flask import current_app

from app.repositories.user_repository import CompanyRepository
from app.utils.db_session import persist
from app.utils.roles import has_admin_role

GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]$")
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
PIN_RE = re.compile(r"^[1-9][0-9]{5}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

STATES = (
    ("01", "Jammu and Kashmir"),
    ("02", "Himachal Pradesh"),
    ("03", "Punjab"),
    ("04", "Chandigarh"),
    ("05", "Uttarakhand"),
    ("06", "Haryana"),
    ("07", "Delhi"),
    ("08", "Rajasthan"),
    ("09", "Uttar Pradesh"),
    ("10", "Bihar"),
    ("11", "Sikkim"),
    ("12", "Arunachal Pradesh"),
    ("13", "Nagaland"),
    ("14", "Manipur"),
    ("15", "Mizoram"),
    ("16", "Tripura"),
    ("17", "Meghalaya"),
    ("18", "Assam"),
    ("19", "West Bengal"),
    ("20", "Jharkhand"),
    ("21", "Odisha"),
    ("22", "Chhattisgarh"),
    ("23", "Madhya Pradesh"),
    ("24", "Gujarat"),
    ("27", "Maharashtra"),
    ("29", "Karnataka"),
    ("30", "Goa"),
    ("32", "Kerala"),
    ("33", "Tamil Nadu"),
    ("36", "Telangana"),
    ("37", "Andhra Pradesh"),
)

_STATE_CODE_BY_NAME = {name.lower(): code for code, name in STATES}
_STATE_NAME_BY_CODE = {code: name for code, name in STATES}


def _text(value) -> str:
    return (value or "").strip()


def _config_fallback() -> dict[str, str]:
    cfg = current_app.config
    return {
        "name": cfg.get("COMPANY_DISPLAY_NAME", "Joshi Tax Consultancy & Services"),
        "gstin": cfg.get("COMPANY_GSTIN", "05AEBPJ1665H2ZR"),
        "pan": cfg.get("COMPANY_PAN", "AEBPJ1665H"),
        "cin": cfg.get("COMPANY_CIN", ""),
        "address": cfg.get(
            "COMPANY_ADDRESS",
            "Sanjay Colony, Nainital Road, Haldwani, Uttarakhand 263139",
        ),
        "city": "",
        "pincode": "",
        "state": cfg.get("COMPANY_STATE", "Uttarakhand"),
        "state_code": cfg.get("COMPANY_STATE_CODE", "05"),
        "phone": cfg.get("COMPANY_PHONE", "9412040614"),
        "email": cfg.get("COMPANY_EMAIL", "admin@jtcsxpert.com"),
        "website": cfg.get("COMPANY_WEBSITE", "www.jtcsxpert.com"),
        "logo_filename": "img/jtcs_invoice_logo.png",
    }


def _composed_address(line: str, city: str, state: str, pincode: str, fallback: str) -> str:
    if not any((line, city, pincode)):
        return fallback
    blob = line.lower()
    parts = [line] if line else []
    if city and city.lower() not in blob:
        parts.append(city)
    tail = " ".join(
        part
        for part in (state, pincode)
        if part and part.lower() not in blob
    )
    if tail:
        parts.append(tail)
    return ", ".join(part for part in parts if part)


def invoice_company() -> dict[str, str]:
    """Seller block on sale invoices. Saved profile values win; otherwise config."""
    fallback = _config_fallback()
    try:
        row = CompanyRepository().get_profile()
    except Exception:
        return fallback
    if row is None:
        return fallback

    name = _text(row.CompanyName)
    if name in {"", "JTCS", "JTCS ERP"}:
        name = fallback["name"]

    gstin = _text(getattr(row, "GSTIN", None)) or fallback["gstin"]
    state = _text(getattr(row, "State", None)) or fallback["state"]
    state_code = _text(getattr(row, "StateCode", None))
    if not state_code and len(gstin) >= 2 and gstin[:2].isdigit():
        state_code = gstin[:2]
    if not state_code:
        state_code = _STATE_CODE_BY_NAME.get(state.lower(), "") or fallback["state_code"]

    line = _text(getattr(row, "AddressLine", None))
    city = _text(getattr(row, "City", None))
    pincode = _text(getattr(row, "Pincode", None))
    return {
        "name": name,
        "gstin": gstin,
        "pan": _text(getattr(row, "PAN", None)) or fallback["pan"],
        "cin": _text(getattr(row, "CIN", None)) or fallback["cin"],
        "address": _composed_address(line, city, state, pincode, fallback["address"]),
        "city": city,
        "pincode": pincode,
        "state": state,
        "state_code": state_code,
        "phone": _text(getattr(row, "Phone", None)) or fallback["phone"],
        "email": _text(getattr(row, "Email", None)) or fallback["email"],
        "website": _text(getattr(row, "Website", None)) or fallback["website"],
        "logo_filename": fallback["logo_filename"],
    }


def form_values() -> dict[str, str]:
    """Profile form. Empty saved fields show the values already printed on invoices."""
    current = invoice_company()
    row = None
    try:
        row = CompanyRepository().get_profile()
    except Exception:
        row = None
    saved_line = _text(getattr(row, "AddressLine", None)) if row is not None else ""
    saved_city = _text(getattr(row, "City", None)) if row is not None else ""
    saved_pin = _text(getattr(row, "Pincode", None)) if row is not None else ""
    address = saved_line or ("" if saved_city or saved_pin else current["address"])
    return {
        "company_name": current["name"],
        "address": address,
        "city": saved_city or current["city"],
        "pincode": saved_pin or current["pincode"],
        "state": _text(getattr(row, "State", None)) if row is not None and _text(getattr(row, "State", None)) else current["state"],
        "gstin": _text(getattr(row, "GSTIN", None)) if row is not None and _text(getattr(row, "GSTIN", None)) else current["gstin"],
        "pan": _text(getattr(row, "PAN", None)) if row is not None and _text(getattr(row, "PAN", None)) else current["pan"],
        "cin": _text(getattr(row, "CIN", None)) if row is not None else current["cin"],
        "phone": _text(getattr(row, "Phone", None)) if row is not None and _text(getattr(row, "Phone", None)) else current["phone"],
        "email": _text(getattr(row, "Email", None)) if row is not None and _text(getattr(row, "Email", None)) else current["email"],
        "website": _text(getattr(row, "Website", None)) if row is not None and _text(getattr(row, "Website", None)) else current["website"],
    }


def _clean_form(form) -> dict[str, str]:
    gstin = _text(form.get("gstin")).upper().replace(" ", "")
    pan = _text(form.get("pan")).upper().replace(" ", "")
    if not pan and GSTIN_RE.match(gstin):
        pan = gstin[2:12]
    return {
        "company_name": _text(form.get("company_name")),
        "address": _text(form.get("address")),
        "city": _text(form.get("city")),
        "pincode": _text(form.get("pincode")),
        "state": _text(form.get("state")),
        "gstin": gstin,
        "pan": pan,
        "cin": _text(form.get("cin")).upper(),
        "phone": _text(form.get("phone")),
        "email": _text(form.get("email")).lower(),
        "website": _text(form.get("website")),
    }


def validate_profile(data: dict[str, str], *, can_edit_name: bool) -> str | None:
    if can_edit_name and not data["company_name"]:
        return "Company name is required."
    if len(data["company_name"]) > 200:
        return "Company name is too long."
    if data["gstin"] and not GSTIN_RE.match(data["gstin"]):
        return "Enter a valid 15-character GSTIN."
    if data["pan"] and not PAN_RE.match(data["pan"]):
        return "Enter a valid PAN."
    if data["pincode"] and not PIN_RE.match(data["pincode"]):
        return "Enter a 6-digit PIN code."
    if data["email"] and not EMAIL_RE.match(data["email"]):
        return "Enter a valid email address."
    if data["state"] and data["state"].lower() not in _STATE_CODE_BY_NAME:
        return "Select a state."
    if data["gstin"]:
        code = data["gstin"][:2]
        expected = _STATE_NAME_BY_CODE.get(code, "")
        if expected and data["state"] and data["state"].lower() != expected.lower():
            return f"GSTIN state code {code} belongs to {expected}."
    return None


def save_profile(form, role: str | None) -> tuple[bool, str, dict[str, str]]:
    can_edit_name = has_admin_role(role)
    data = _clean_form(form)
    error = validate_profile(data, can_edit_name=can_edit_name)
    if error:
        return False, error, data

    state_code = ""
    if data["gstin"]:
        state_code = data["gstin"][:2]
    elif data["state"]:
        state_code = _STATE_CODE_BY_NAME.get(data["state"].lower(), "")

    def _write():
        repo = CompanyRepository()
        row = repo.get_profile()
        if row is None:
            return False
        payload = {
            "AddressLine": data["address"] or None,
            "City": data["city"] or None,
            "Pincode": data["pincode"] or None,
            "State": data["state"] or None,
            "StateCode": state_code or None,
            "GSTIN": data["gstin"] or None,
            "PAN": data["pan"] or None,
            "CIN": data["cin"] or None,
            "Phone": data["phone"] or None,
            "Email": data["email"] or None,
            "Website": data["website"] or None,
        }
        if can_edit_name:
            payload["CompanyName"] = data["company_name"]
        repo.update(row, payload)
        return True

    if not persist(_write):
        return False, "Company profile is not set up yet.", data
    return True, "Company profile saved. Bills and invoices use this GSTIN.", data
