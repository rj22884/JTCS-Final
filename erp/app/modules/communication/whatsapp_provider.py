"""WhatsApp channel providers — wa.me now; Cloud API later."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.modules.crm.whatsapp import wa_me_url


@runtime_checkable
class WhatsAppProvider(Protocol):
    def open_chat_url(self, mobile: str | None, message: str | None = None) -> str | None:
        ...

    def send_message(self, mobile: str, body: str) -> dict:
        ...


class WaMeProvider:
    """Current provider: opens https://wa.me/{mobile} (no Cloud API)."""

    def open_chat_url(self, mobile: str | None, message: str | None = None) -> str | None:
        url = wa_me_url(mobile)
        if not url or not message:
            return url
        from urllib.parse import quote

        return f"{url}?text={quote(message)}"

    def send_message(self, mobile: str, body: str) -> dict:
        return {
            "ok": False,
            "error": "WhatsApp Cloud API not configured. Use open_chat_url (wa.me) for now.",
            "wa_url": self.open_chat_url(mobile, body),
        }


class WhatsAppCloudApiProvider:
    """Future WhatsApp Cloud API provider (not wired)."""

    def open_chat_url(self, mobile: str | None, message: str | None = None) -> str | None:
        return WaMeProvider().open_chat_url(mobile, message)

    def send_message(self, mobile: str, body: str) -> dict:
        return {"ok": False, "error": "WhatsApp Cloud API not configured"}


def get_whatsapp_provider() -> WhatsAppProvider:
    return WaMeProvider()
