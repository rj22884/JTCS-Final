"""Phase 2 stub — AI chatbot / OpenAI integration."""

from __future__ import annotations


class AiChatbotStub:
    def suggest_replies(self, conversation_id: int, last_message: str | None = None) -> dict:
        return {
            "ok": False,
            "error": "Phase 2 — OpenAI suggested replies not enabled",
            "suggestions": [],
        }

    def escalate_to_human(self, conversation_id: int) -> dict:
        return {"ok": False, "error": "Phase 2 — AI escalate not enabled"}

    def summarize(self, conversation_id: int) -> dict:
        return {"ok": False, "error": "Phase 2 — AI summary not enabled"}
