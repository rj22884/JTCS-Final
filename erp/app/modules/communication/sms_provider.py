"""Phase 2 stub — SMS gateway provider."""

from __future__ import annotations


class SmsGatewayProvider:
    def send_sms(self, mobile: str, body: str) -> dict:
        return {"ok": False, "error": "Phase 2 — SMS gateway not enabled"}

    def delivery_report(self, external_id: str) -> dict:
        return {"ok": False, "error": "Phase 2 — SMS gateway not enabled"}
