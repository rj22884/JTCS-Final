"""Thin controller for Integration Settings."""

from __future__ import annotations

from app.modules.settings.audit_service import IntegrationSettingsAuditService
from app.modules.settings.services import IntegrationSettingsService
from app.modules.settings.whatsapp_oauth_service import WhatsAppOAuthService


class IntegrationSettingsController:
    def __init__(self, service: IntegrationSettingsService | None = None):
        self.service = service or IntegrationSettingsService()
        self.oauth = WhatsAppOAuthService(self.service)

    def page_context(self) -> dict:
        data = self.service.get_all_masked()
        return {
            "providers": data["providers"],
            "catalog": self.service.providers_catalog(),
        }

    def load_all(self) -> dict:
        return self.service.get_all_masked()

    def save(self, provider: str, payload: dict) -> dict:
        return self.service.save_provider_settings(provider, payload)

    def generate_verify_token(self) -> dict:
        return self.service.generate_whatsapp_verify_token()

    def test_whatsapp(self, *, send_test_message: bool = False, test_to_number: str | None = None) -> dict:
        return self.service.test_whatsapp_connection(
            send_test_message=send_test_message,
            test_to_number=test_to_number,
        )

    def status(self) -> dict:
        return self.service.status_summary()

    def whatsapp_audit(self, limit: int = 50) -> dict:
        rows = IntegrationSettingsAuditService().list_recent(provider="whatsapp_meta", limit=limit)
        return {"ok": True, "rows": rows}

    def token_guide(self) -> dict:
        return self.oauth.token_guide()
