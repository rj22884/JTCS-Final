"""Phase 2 stub — broadcast and scheduled messaging."""

from __future__ import annotations


class BroadcastStub:
    def create_broadcast(self, **kwargs) -> dict:
        return {"ok": False, "error": "Phase 2 — Broadcast messaging not enabled"}

    def schedule_message(self, **kwargs) -> dict:
        return {"ok": False, "error": "Phase 2 — Scheduled messages not enabled"}
