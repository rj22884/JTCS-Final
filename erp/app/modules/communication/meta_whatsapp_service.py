"""Meta WhatsApp Cloud API service abstraction for CRM.

Wraps Integration Settings + WhatsAppMetaClient. Does not hard-code credentials.
Does not log tokens. Safe to call when Meta is not configured (returns ok=False).
"""

from __future__ import annotations

import logging
from typing import Any

from app.modules.communication.whatsapp_provider import (
    WhatsAppCloudApiProvider,
    _normalize_e164,
    is_cloud_api_configured,
)

logger = logging.getLogger(__name__)


class MetaWhatsAppService:
    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config

    def _cfg(self) -> dict[str, Any]:
        if self._config is not None:
            return self._config
        from app.modules.settings.services import IntegrationSettingsService

        return IntegrationSettingsService().get_provider_config_decrypted("whatsapp_meta") or {}

    def is_configured(self) -> bool:
        return is_cloud_api_configured(self._cfg())

    def is_test_mode(self) -> bool:
        return not self.is_configured()

    def _provider(self) -> WhatsAppCloudApiProvider:
        cfg = self._cfg()
        if not is_cloud_api_configured(cfg):
            raise RuntimeError("WhatsApp Cloud API is not configured.")
        return WhatsAppCloudApiProvider(cfg)

    def check_token(self) -> dict[str, Any]:
        try:
            from app.modules.settings.whatsapp_health_service import WhatsAppHealthService

            return WhatsAppHealthService().token_health()
        except Exception as exc:
            logger.exception("check_token failed")
            return {"ok": False, "error": str(exc)}

    def refresh_metadata(self) -> dict[str, Any]:
        try:
            from app.modules.settings.whatsapp_health_service import WhatsAppHealthService

            return WhatsAppHealthService().refresh_metadata()
        except Exception as exc:
            logger.exception("refresh_metadata failed")
            return {"ok": False, "error": str(exc)}

    def get_phone_number_metadata(self) -> dict[str, Any]:
        cfg = self._cfg()
        pid = (cfg.get("phone_number_id") or "").strip()
        if not pid:
            return {"ok": False, "error": "Phone Number ID is not configured."}
        try:
            from app.modules.settings.whatsapp_meta_client import WhatsAppMetaClient

            client = WhatsAppMetaClient(
                access_token=(cfg.get("access_token") or "").strip(),
                graph_api_version=cfg.get("graph_api_version"),
            )
            return {"ok": True, "data": client.get_phone(pid)}
        except Exception as exc:
            logger.exception("get_phone_number_metadata failed")
            return {"ok": False, "error": str(exc)}

    def get_business_metadata(self) -> dict[str, Any]:
        cfg = self._cfg()
        waba = (cfg.get("waba_id") or "").strip()
        if not waba:
            return {"ok": False, "error": "WhatsApp Business Account ID is not configured."}
        try:
            from app.modules.settings.whatsapp_meta_client import WhatsAppMetaClient

            client = WhatsAppMetaClient(
                access_token=(cfg.get("access_token") or "").strip(),
                graph_api_version=cfg.get("graph_api_version"),
            )
            return {"ok": True, "data": client.get_waba(waba)}
        except Exception as exc:
            logger.exception("get_business_metadata failed")
            return {"ok": False, "error": str(exc)}

    def send_text_message(self, mobile: str, body: str) -> dict[str, Any]:
        return self._provider().send_message(mobile, body)

    def send_template_message(
        self,
        mobile: str,
        *,
        template_name: str,
        language: str = "en",
        components: list | None = None,
    ) -> dict[str, Any]:
        cfg = self._cfg()
        try:
            client = self._provider()._client()
            to = _normalize_e164(mobile)
            data = client.send_template(
                self._provider()._phone_number_id(),
                to,
                template_name=template_name,
                language_code=language,
                components=components or [],
            )
            messages = data.get("messages") or []
            wamid = (messages[0] or {}).get("id") if messages else None
            return {"ok": True, "external_message_id": wamid, "raw": data}
        except AttributeError:
            logger.info("send_template not available on Meta client; falling back to text")
            return self.send_text_message(mobile, template_name)
        except Exception as exc:
            logger.exception("send_template_message failed")
            return {"ok": False, "error": str(exc)}

    def send_media_message(self, mobile: str, **kwargs) -> dict[str, Any]:
        return self._provider().send_media(mobile, **kwargs)

    def download_media(self, media_id: str) -> dict[str, Any]:
        return self._provider().download_media(media_id)

    def get_message_status(self, external_message_id: str) -> dict[str, Any]:
        """Status is webhook-driven; this is a lookup stub for CRM."""
        from app.modules.communication.services import CommunicationService

        rows = CommunicationService().list_messages_by_external_id(external_message_id)
        if not rows:
            return {"ok": False, "error": "Message not found"}
        row = rows[0]
        return {
            "ok": True,
            "status": row.get("DeliveryStatus"),
            "message_id": row.get("MessageID"),
        }

    def subscribe_webhook(self) -> dict[str, Any]:
        try:
            from app.modules.settings.whatsapp_health_service import WhatsAppHealthService

            return WhatsAppHealthService().subscribe_webhooks()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def verify_webhook(self, hub_mode: str, hub_verify_token: str, hub_challenge: str) -> str | None:
        if (hub_mode or "") != "subscribe":
            return None
        expected = (self._cfg().get("webhook_verify_token") or "").strip()
        if not expected or hub_verify_token != expected:
            return None
        return hub_challenge
