"""Map Meta message_template payloads into WhatsApp Inbox rows.

Pure helpers: no HTTP, no database, no tokens.
"""

from __future__ import annotations

import re
from typing import Any

# Cloud API uses APPROVED. Manager shows that as Active, including quality pending.
USABLE_TEMPLATE_STATUSES = frozenset({"APPROVED", "ACTIVE"})

_PLACEHOLDER = re.compile(r"\{\{\s*(\d+)\s*\}\}")
_TOKEN = re.compile(r"EAA[A-Za-z0-9]+")
_ACCESS = re.compile(r"(access_token=)[^&\s]+", re.I)

VARIABLE_LABELS = {
    "1": "Customer name",
    "2": "Business WhatsApp number",
}
VARIABLE_SOURCES = {
    "1": "customer_name",
    "2": "business_whatsapp_number",
}


def public_meta_error(exc: BaseException | str) -> str:
    """Staff-facing fetch error with tokens removed."""
    text = str(exc or "").strip() or "WhatsApp templates could not be loaded from Meta."
    text = _TOKEN.sub("EAA***", text)
    text = _ACCESS.sub(r"\1REDACTED", text)
    text = re.sub(r"(Bearer\s+)\S+", r"\1REDACTED", text, flags=re.I)
    return text[:300]


def _component_text(component: dict[str, Any]) -> str:
    return str(component.get("text") or "").strip()


def preview_body(components: list[dict[str, Any]] | None) -> str:
    header = ""
    body = ""
    for component in components or []:
        kind = str(component.get("type") or "").upper()
        text = _component_text(component)
        if kind == "HEADER" and text and not header:
            header = text
        elif kind == "BODY" and text and not body:
            body = text
    parts = [part for part in (header, body) if part]
    return "\n\n".join(parts)


def variable_specs(components: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    """Positional body/header placeholders. {{1}} customer name, {{2}} business number."""
    seen: list[str] = []
    for component in components or []:
        kind = str(component.get("type") or "").upper()
        if kind not in {"BODY", "HEADER"}:
            continue
        for number in _PLACEHOLDER.findall(_component_text(component)):
            if number not in seen:
                seen.append(number)
    specs: list[dict[str, str]] = []
    for number in seen:
        specs.append(
            {
                "key": number,
                "label": VARIABLE_LABELS.get(number) or ("Variable {{" + number + "}}"),
                "source": VARIABLE_SOURCES.get(number) or "",
            }
        )
    return specs


def button_summaries(components: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    buttons: list[dict[str, str]] = []
    for component in components or []:
        if str(component.get("type") or "").upper() != "BUTTONS":
            continue
        for button in component.get("buttons") or []:
            if not isinstance(button, dict):
                continue
            buttons.append(
                {
                    "type": str(button.get("type") or ""),
                    "text": str(button.get("text") or ""),
                }
            )
    return buttons


def is_usable_template(row: dict[str, Any]) -> bool:
    """Approved/active templates of every category, including Marketing."""
    status = str(row.get("status") or "").strip().upper()
    name = str(row.get("name") or "").strip()
    return bool(name) and status in USABLE_TEMPLATE_STATUSES


def map_meta_template(row: dict[str, Any]) -> dict[str, Any]:
    components = list(row.get("components") or [])
    name = str(row.get("name") or "").strip()
    language = str(row.get("language") or "en").strip() or "en"
    category = str(row.get("category") or "").strip().upper()
    status = str(row.get("status") or "").strip().upper()
    variables = variable_specs(components)
    return {
        "TemplateID": None,
        "Name": name,
        "Channel": "WhatsApp",
        "Subject": None,
        "Body": preview_body(components),
        "ExternalTemplateName": name,
        "LanguageCode": language,
        "Category": category,
        "Variables": variables,
        "VariablesJson": ",".join(item["key"] for item in variables),
        "TemplateStatus": status,
        "IsActive": True,
        "Source": "meta",
        "Buttons": button_summaries(components),
    }


def select_inbox_templates(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    selected = [map_meta_template(row) for row in (rows or []) if is_usable_template(row)]
    selected.sort(key=lambda item: (item.get("Name") or "").lower())
    return selected


def _row_key(row: dict[str, Any]) -> str:
    name = str(row.get("ExternalTemplateName") or row.get("Name") or "").strip().lower()
    language = str(row.get("LanguageCode") or "").strip().lower()
    return f"{name}|{language}"


def merge_template_rows(
    meta_rows: list[dict[str, Any]] | None,
    local_rows: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Meta rows first. A local row with the same name and language is skipped."""
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in list(meta_rows or []) + list(local_rows or []):
        key = _row_key(row)
        if not key.strip("|"):
            continue
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
    return merged
