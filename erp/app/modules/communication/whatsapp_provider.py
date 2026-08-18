"""WhatsApp outbound providers — Cloud API preferred when credentials exist."""

from __future__ import annotations

import logging
import re
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class WhatsAppProvider(Protocol):
    def send_message(self, mobile: str, body: str) -> dict: ...

    def open_chat_url(self, mobile: str, body: str = "") -> str | None: ...


def _normalize_e164(mobile: str) -> str:
    digits = re.sub(r"\D", "", mobile or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 10:
        digits = "91" + digits
    return digits


class WaMeProvider:
    """Fallback: opens https://wa.me/{mobile} (no Cloud API send)."""

    def open_chat_url(self, mobile: str, body: str = "") -> str | None:
        digits = _normalize_e164(mobile)
        if not digits:
            return None
        from urllib.parse import quote

        url = f"https://wa.me/{digits}"
        if body:
            url += f"?text={quote(body)}"
        return url

    def send_message(self, mobile: str, body: str) -> dict:
        return {
            "ok": False,
            "error": "WhatsApp Cloud API not configured. Use open_chat_url (wa.me) for now.",
            "wa_url": self.open_chat_url(mobile, body),
        }


class WhatsAppCloudApiProvider:
    """Production Meta WhatsApp Cloud API provider."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def _client(self):
        from app.modules.settings.whatsapp_meta_client import WhatsAppMetaClient

        token = (self.config.get("access_token") or "").strip()
        version = (self.config.get("graph_api_version") or "v21.0").strip()
        if not token:
            raise RuntimeError("WhatsApp access_token missing")
        return WhatsAppMetaClient(access_token=token, graph_api_version=version)

    def _phone_number_id(self) -> str:
        pid = (self.config.get("phone_number_id") or "").strip()
        if not pid:
            raise RuntimeError("WhatsApp phone_number_id missing")
        return pid

    def open_chat_url(self, mobile: str, body: str = "") -> str | None:
        return WaMeProvider().open_chat_url(mobile, body)

    def send_message(self, mobile: str, body: str) -> dict:
        try:
            client = self._client()
            to = _normalize_e164(mobile)
            if not to:
                return {"ok": False, "error": "Invalid mobile number"}
            data = client.send_text(self._phone_number_id(), to, body)
            messages = data.get("messages") or []
            wamid = (messages[0] or {}).get("id") if messages else None
            return {"ok": True, "external_message_id": wamid, "raw": data}
        except Exception as exc:
            logger.exception("WhatsApp Cloud API send_message failed")
            return {"ok": False, "error": str(exc)}

    def send_media(
        self,
        mobile: str,
        *,
        media_type: str,
        link: str | None = None,
        media_id: str | None = None,
        caption: str | None = None,
        filename: str | None = None,
    ) -> dict:
        try:
            client = self._client()
            to = _normalize_e164(mobile)
            data = client.send_media(
                self._phone_number_id(),
                to,
                media_type=media_type,
                link=link,
                media_id=media_id,
                caption=caption,
                filename=filename,
            )
            messages = data.get("messages") or []
            wamid = (messages[0] or {}).get("id") if messages else None
            return {"ok": True, "external_message_id": wamid, "raw": data}
        except Exception as exc:
            logger.exception("WhatsApp Cloud API send_media failed")
            return {"ok": False, "error": str(exc)}

    def mark_as_read(self, message_id: str) -> dict:
        try:
            client = self._client()
            data = client.mark_as_read(self._phone_number_id(), message_id)
            return {"ok": True, "raw": data}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def download_media(self, media_id: str) -> dict:
        try:
            client = self._client()
            return client.download_media(media_id)
        except Exception as exc:
            logger.exception("WhatsApp media download failed")
            return {"ok": False, "error": str(exc)}


class MockWhatsAppProvider:
    """Development/test provider — no Meta credentials required.

    Outbound messages succeed with a synthetic Meta-style ID and are marked TEST.
    """

    def open_chat_url(self, mobile: str, body: str = "") -> str | None:
        return WaMeProvider().open_chat_url(mobile, body)

    def send_message(self, mobile: str, body: str) -> dict:
        to = _normalize_e164(mobile)
        if not to:
            return {"ok": False, "error": "Invalid mobile number", "is_test": True}
        fake_id = f"TEST-{to[-10:] if len(to) >= 10 else to}-{int(__import__('time').time())}"
        return {
            "ok": True,
            "external_message_id": fake_id,
            "is_test": True,
            "wa_url": self.open_chat_url(mobile, body),
        }

    def send_media(self, mobile: str, **kwargs) -> dict:
        return self.send_message(mobile, kwargs.get("caption") or "[media]")


def is_cloud_api_configured(config: dict[str, Any] | None = None) -> bool:
    cfg = config
    if cfg is None:
        try:
            from app.modules.settings.services import IntegrationSettingsService

            cfg = IntegrationSettingsService().get_provider_config_decrypted("whatsapp_meta")
        except Exception:
            return False
    required = ("access_token", "phone_number_id")
    return all((cfg.get(k) or "").strip() for k in required)


def get_whatsapp_provider() -> WhatsAppProvider:
    """Cloud API when Integration Settings are complete; otherwise test/mock provider."""
    try:
        from app.modules.settings.services import IntegrationSettingsService

        cfg = IntegrationSettingsService().get_provider_config_decrypted("whatsapp_meta")
        if is_cloud_api_configured(cfg):
            return WhatsAppCloudApiProvider(cfg)
    except Exception:
        logger.debug("WhatsApp Cloud API config unavailable; using mock test provider")
    return MockWhatsAppProvider()
