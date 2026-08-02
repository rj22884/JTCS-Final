"""AI provider protocol and stub implementations."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class NotConfiguredError(RuntimeError):
    """Raised when an AI provider is not configured."""


@runtime_checkable
class AiProvider(Protocol):
    def complete(self, prompt: str, *, system: str | None = None) -> dict[str, Any]:
        ...


class BaseAiProvider:
    provider_name: str = "base"

    def complete(self, prompt: str, *, system: str | None = None) -> dict[str, Any]:
        raise NotConfiguredError(f"{self.provider_name} is not configured")


class OpenAIProvider(BaseAiProvider):
    provider_name = "openai"

    def complete(self, prompt: str, *, system: str | None = None) -> dict[str, Any]:
        return {"ok": False, "error": "AI provider not configured"}


class ClaudeProvider(BaseAiProvider):
    provider_name = "claude"

    def complete(self, prompt: str, *, system: str | None = None) -> dict[str, Any]:
        return {"ok": False, "error": "AI provider not configured"}


class GeminiProvider(BaseAiProvider):
    provider_name = "gemini"

    def complete(self, prompt: str, *, system: str | None = None) -> dict[str, Any]:
        return {"ok": False, "error": "AI provider not configured"}


class AiDraftService:
    """Generate draft replies for CRM channels (stub until providers are configured)."""

    def __init__(self, provider: AiProvider | None = None):
        self.provider = provider or OpenAIProvider()

    def draft_reply(self, channel: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        ctx = context or {}
        customer = ctx.get("customer_name") or ctx.get("lead_name") or "there"
        subject = ctx.get("subject") or "your enquiry"
        channel_label = (channel or "message").strip().title()

        stub_message = (
            f"Dear {customer},\n\n"
            f"Thank you for reaching out regarding {subject}. "
            f"We have received your {channel_label} and will respond shortly.\n\n"
            f"Regards,\nJTCS Team"
        )

        if isinstance(self.provider, BaseAiProvider):
            provider_result = self.provider.complete(
                f"Draft a {channel_label} reply for: {subject}",
            )
            if not provider_result.get("ok", False):
                return {
                    "ok": True,
                    "draft": stub_message,
                    "provider": getattr(self.provider, "provider_name", "stub"),
                    "ai_available": False,
                }

        return {
            "ok": True,
            "draft": stub_message,
            "provider": getattr(self.provider, "provider_name", "stub"),
            "ai_available": False,
        }
