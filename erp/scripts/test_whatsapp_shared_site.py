"""Both domains share one WhatsApp inbox, API, and webhook. No network and no sends."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.communication.webhook_service import WhatsAppWebhookService  # noqa: E402
from app.modules.communication.whatsapp_template_catalog import template_message_components  # noqa: E402
from app.modules.shared.audit_service import AuditService  # noqa: E402
from app.whatsapp_site import (  # noqa: E402
    SHARED_API,
    SHARED_TABLES,
    SHARED_UI,
    SHARED_WEBHOOKS,
    gate_decision,
    home_path,
    is_whatsapp_host,
    path_allowed,
)


def check(name: str, ok: bool) -> None:
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        raise SystemExit(1)


class _Events:
    def __init__(self) -> None:
        self.seen: set[str] = set()
        self.statuses: list[dict] = []

    def record_webhook_event(self, external_event_id: str, event_type: str) -> bool:
        if external_event_id in self.seen:
            return False
        self.seen.add(external_event_id)
        return True

    def update_delivery_status(self, **kwargs) -> bool:
        self.statuses.append(kwargs)
        return True


def main() -> None:
    check("production host is the focused site", is_whatsapp_host("whatsapp.jtcsxpert.com"))
    check("erp host is not the focused site", not is_whatsapp_host("app.jtcsxpert.com"))
    check("local dev host is focused", is_whatsapp_host("whatsapp.localhost:8000"))
    check("focused home is the shared inbox", home_path("whatsapp.jtcsxpert.com") == "/crm/inbox?channel=WhatsApp")
    check("erp home stays the dashboard", home_path("app.jtcsxpert.com") == "/dashboard")

    for path in SHARED_API + SHARED_WEBHOOKS:
        check(f"focused host allows {path}", path_allowed(path))
    check("invoice page is blocked", gate_decision("whatsapp.jtcsxpert.com", "/accounting/invoice") == "/crm/inbox?channel=WhatsApp")
    check("customer master is blocked", gate_decision("whatsapp.jtcsxpert.com", "/masters/customers") == "/crm/inbox?channel=WhatsApp")
    check("blocked API is denied", gate_decision("whatsapp.jtcsxpert.com", "/api/invoices") == "deny")
    check("erp host is not gated", gate_decision("app.jtcsxpert.com", "/accounting/invoice") is None)
    check("webhook stays open on the focused host", gate_decision("whatsapp.jtcsxpert.com", "/webhooks/whatsapp") is None)
    check("template API stays open", gate_decision("whatsapp.jtcsxpert.com", "/api/crm/templates") is None)
    check("reply API stays open", path_allowed("/api/crm/conversations/15/reply"))

    source = (ROOT / "app" / "whatsapp_site.py").read_text(encoding="utf-8")
    check("no second database in the host policy", "sqlite" not in source.lower() and "jtcs.db" not in source)
    check("shared tables are the CRM store", "dbo.CrmMessage" in SHARED_TABLES and "dbo.CrmConversation" in SHARED_TABLES)
    for relative in SHARED_UI:
        check(f"shared UI file exists {relative}", (ROOT.parent / relative).is_file())

    routes = (ROOT / "app" / "modules" / "crm" / "routes.py").read_text(encoding="utf-8")
    check("template list uses the shared catalog service", "list_inbox_templates" in routes)
    check("reply uses the shared template send", "send_template_message" in routes)

    components = template_message_components({"1": "Asha", "2": "+91 84770 05566"})
    check(
        "template parameters come from the shared catalog",
        components[0]["parameters"][0]["text"] == "Asha" and components[0]["parameters"][1]["text"] == "+91 84770 05566",
    )

    original_log = AuditService.log
    AuditService.log = lambda self, **kwargs: None  # noqa: ARG005
    try:
        service = WhatsAppWebhookService()
        events = _Events()
        service.comm = events
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "statuses": [{"id": "wamid.SHARED1", "status": "delivered"}],
                            }
                        }
                    ]
                }
            ],
        }
        first = service.process_payload(payload)
        second = service.process_payload(payload)
        check("first status is stored once", first["statuses"] == 1 and len(events.statuses) == 1)
        check("duplicate webhook does not store the status again", second["statuses"] == 0 and len(events.statuses) == 1)
        events.seen.add("msg:wamid.IN1")
        duplicate = service.ingest_inbound(
            mobile="919876543210",
            body="Hi",
            external_message_id="wamid.IN1",
        )
        check("duplicate inbound is ignored", duplicate.get("duplicate") is True)
    finally:
        AuditService.log = original_log

    print("ALL PASS")


if __name__ == "__main__":
    main()
