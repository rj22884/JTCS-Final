"""Fixture tests for WhatsApp Inbox Meta template selection. No network and no sends."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.communication.whatsapp_template_catalog import (  # noqa: E402
    merge_template_rows,
    public_meta_error,
    select_inbox_templates,
)
from app.modules.settings.whatsapp_meta_client import WhatsAppMetaClient  # noqa: E402


NUMBER_CHANGE = {
    "name": "number_change",
    "status": "APPROVED",
    "language": "en",
    "category": "MARKETING",
    "quality_score": {"score": "UNKNOWN"},
    "components": [
        {"type": "HEADER", "format": "TEXT", "text": "whatsapp additional meta verfied number"},
        {
            "type": "BODY",
            "text": "Hello {{1}},\n\nOur WhatsApp service is now also available at this number: {{2}}.",
        },
        {
            "type": "BUTTONS",
            "buttons": [
                {"type": "QUICK_REPLY", "text": "Quick Reply"},
                {"type": "URL", "text": "Visit Website"},
            ],
        },
    ],
}

UTILITY = {
    "name": "payment_reminder",
    "status": "APPROVED",
    "language": "en",
    "category": "UTILITY",
    "components": [{"type": "BODY", "text": "Dear {{1}}, payment is pending."}],
}


def check(name: str, ok: bool) -> None:
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        raise SystemExit(1)


def main() -> None:
    rows = select_inbox_templates(
        [
            NUMBER_CHANGE,
            UTILITY,
            {"name": "pending_mkt", "status": "PENDING", "language": "en", "category": "MARKETING", "components": []},
            {"name": "rejected_mkt", "status": "REJECTED", "language": "en", "category": "MARKETING", "components": []},
            {"name": "paused_util", "status": "PAUSED", "language": "en", "category": "UTILITY", "components": []},
            {"name": "disabled_mkt", "status": "DISABLED", "language": "en", "category": "MARKETING", "components": []},
            {"name": "active_auth", "status": "ACTIVE", "language": "en", "category": "AUTHENTICATION", "components": [{"type": "BODY", "text": "Code {{1}}"}]},
        ]
    )
    names = [row["Name"] for row in rows]
    check("includes approved marketing number_change", "number_change" in names)
    check("includes approved utility", "payment_reminder" in names)
    check("includes active authentication", "active_auth" in names)
    check("excludes pending rejected paused disabled", names == ["active_auth", "number_change", "payment_reminder"])

    number = next(row for row in rows if row["Name"] == "number_change")
    check("number_change language en", number["LanguageCode"] == "en")
    check("number_change category MARKETING", number["Category"] == "MARKETING")
    check("number_change status APPROVED", number["TemplateStatus"] == "APPROVED")
    check("quality pending still included", number["Source"] == "meta")
    keys = [item["key"] for item in number["Variables"]]
    labels = {item["key"]: item["label"] for item in number["Variables"]}
    sources = {item["key"]: item["source"] for item in number["Variables"]}
    check("placeholders 1 and 2", keys == ["1", "2"])
    check("{{1}} customer name", labels["1"] == "Customer name" and sources["1"] == "customer_name")
    check("{{2}} business number", labels["2"] == "Business WhatsApp number" and sources["2"] == "business_whatsapp_number")
    check("preview keeps both placeholders", "{{1}}" in number["Body"] and "{{2}}" in number["Body"])
    check("header is in preview", number["Body"].startswith("whatsapp additional meta verfied number"))
    check("buttons are metadata", [b["text"] for b in number["Buttons"]] == ["Quick Reply", "Visit Website"])
    check("buttons are not pasted into the body", "Visit Website" not in number["Body"])

    utility = next(row for row in rows if row["Name"] == "payment_reminder")
    check("utility category kept", utility["Category"] == "UTILITY")
    check("empty payload", select_inbox_templates([]) == [])
    check("empty none", select_inbox_templates(None) == [])

    merged = merge_template_rows(
        [number],
        [
            {
                "Name": "ITR Document Reminder",
                "ExternalTemplateName": "itr_document_reminder",
                "LanguageCode": "en",
                "Category": "UTILITY",
                "Body": "local",
            },
            {
                "Name": "number_change",
                "ExternalTemplateName": "number_change",
                "LanguageCode": "en",
                "Body": "stale local",
            },
        ],
    )
    check("meta row wins over same local name", merged[0]["Body"] != "stale local" and merged[0]["Source"] == "meta")
    check("local utility draft remains", any(row["ExternalTemplateName"] == "itr_document_reminder" for row in merged))
    check("duplicate name dropped", len(merged) == 2)

    leaked = public_meta_error("fail access_token=EAASECRET123&x=1 Bearer EAASECRET123")
    check("token redacted", "EAASECRET123" not in leaked and "REDACTED" in leaked)

    class Pager(WhatsAppMetaClient):
        def __init__(self):
            super().__init__(access_token="not-a-real-token")
            self.calls = []

        def get(self, path, params=None):
            self.calls.append((path, dict(params or {})))
            after = (params or {}).get("after")
            if not after:
                return {
                    "data": [NUMBER_CHANGE],
                    "paging": {"cursors": {"after": "cursor-2"}, "next": "https://graph.example/next?access_token=SECRET"},
                }
            return {"data": [UTILITY], "paging": {"cursors": {"after": "cursor-2"}}}

    pager = Pager()
    pages = pager.list_message_templates("1345400804135444")
    selected = select_inbox_templates(pages)
    check("pagination returns both pages", [row["name"] for row in pages] == ["number_change", "payment_reminder"])
    check("second page uses cursor not next url", pager.calls[1][1].get("after") == "cursor-2")
    check("paged marketing and utility both usable", [row["Name"] for row in selected] == ["number_change", "payment_reminder"])
    check("pager did not record the next url", all("SECRET" not in str(call) for call in pager.calls))
    print("ALL PASS")


if __name__ == "__main__":
    main()
