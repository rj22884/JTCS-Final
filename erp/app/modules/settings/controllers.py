"""Thin controller for Integration Settings."""

from __future__ import annotations

from app.modules.settings.audit_service import IntegrationSettingsAuditService
from app.modules.settings.integration_health_service import IntegrationHealthService
from app.modules.settings.services import IntegrationSettingsService
from app.modules.settings.whatsapp_health_service import WhatsAppHealthService
from app.modules.settings.whatsapp_oauth_service import WhatsAppOAuthService


class IntegrationSettingsController:
    def __init__(self, service: IntegrationSettingsService | None = None):
        self.service = service or IntegrationSettingsService()
        self.oauth = WhatsAppOAuthService(self.service)
        self.health = WhatsAppHealthService(self.service)
        self.integration_health = IntegrationHealthService(self.service)

    def page_context(self) -> dict:
        data = self.service.get_all_masked()
        wa_card = None
        try:
            wa_card = self.health.account_card()
        except Exception:
            wa_card = None
        return {
            "providers": data["providers"],
            "catalog": self.service.providers_catalog(),
            "whatsapp_card": wa_card,
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

    def refresh_metadata(self) -> dict:
        return self.health.refresh_metadata()

    def token_health(self) -> dict:
        return self.health.token_health()

    def webhook_info(self) -> dict:
        return self.health.webhook_info()

    def subscribe_webhooks(self) -> dict:
        return self.health.subscribe_webhooks()

    def unsubscribe_webhooks(self) -> dict:
        return self.health.unsubscribe_webhooks()

    def account_card(self) -> dict:
        return self.health.account_card()

    def health_dashboard(self, *, force: bool = False) -> dict:
        return self.integration_health.dashboard(run_scan=True, force=force)

    def health_scan(self) -> dict:
        return self.integration_health.scan_all(force=True)

    def health_detail(self, provider: str) -> dict:
        return self.integration_health.provider_detail(provider)

    def health_refresh(self, provider: str) -> dict:
        return self.integration_health.refresh_provider(provider)

    def health_test(self, provider: str) -> dict:
        return self.integration_health.test_provider(provider)

    def health_alerts(self) -> dict:
        return self.integration_health.list_alerts()

    def health_history(self, period: str = "daily") -> dict:
        return self.integration_health.history_series(period)

    def health_export(self, fmt: str = "csv") -> tuple[str, str, str]:
        return self.integration_health.export_report(fmt)
