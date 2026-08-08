"""Smoke checks for Communication Center Phase 1 (no live Meta send)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from app.modules.communication.customer_link_service import normalize_phone, phones_match
from app.modules.communication.services import CommunicationService
from app.modules.communication.webhook_service import WhatsAppWebhookService
from app.modules.shared.schema import ensure_communication_center_schema, ensure_crm_menus, ensure_crm_schema


def main() -> int:
    app = create_app()
    failures: list[str] = []

    with app.app_context():
        try:
            ensure_crm_schema()
            ensure_communication_center_schema()
            ensure_crm_menus()
            print("OK schema + menus")
        except Exception as exc:
            failures.append(f"schema/menus: {exc}")
            print("FAIL schema/menus", exc)

        if not phones_match("9876543210", "+91 98765 43210"):
            failures.append("phone match failed")
            print("FAIL phone match")
        else:
            print("OK phone normalize", normalize_phone("+91-98765-43210"))

        # Webhook fixture (no DB write if duplicate path fails — uses unique id)
        fixture = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "contacts": [{"wa_id": "919999998888", "profile": {"name": "Smoke Test"}}],
                                "messages": [
                                    {
                                        "from": "919999998888",
                                        "id": "wamid.smoke_test_do_not_use_in_prod",
                                        "timestamp": "1700000000",
                                        "type": "text",
                                        "text": {"body": "Smoke test inbound"},
                                    }
                                ],
                                "statuses": [],
                            }
                        }
                    ]
                }
            ],
        }
        try:
            result = WhatsAppWebhookService().process_payload(fixture)
            print("OK webhook process", json.dumps({k: result.get(k) for k in ("ok", "messages", "statuses", "errors")}))
            if not result.get("ok"):
                failures.append("webhook not ok")
        except Exception as exc:
            failures.append(f"webhook: {exc}")
            print("FAIL webhook", exc)

        try:
            stats = CommunicationService().dashboard_stats()
            assert "today_messages" in stats
            print("OK dashboard_stats keys", sorted(stats.keys())[:8], "...")
        except Exception as exc:
            failures.append(f"dashboard: {exc}")
            print("FAIL dashboard", exc)

        # Status update path
        try:
            CommunicationService().update_delivery_status(
                external_message_id="wamid.smoke_test_do_not_use_in_prod",
                status="read",
            )
            print("OK delivery status update")
        except Exception as exc:
            failures.append(f"status: {exc}")
            print("FAIL status", exc)

    if failures:
        print("SMOKE FAILED:", "; ".join(failures))
        return 1
    print("SMOKE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
