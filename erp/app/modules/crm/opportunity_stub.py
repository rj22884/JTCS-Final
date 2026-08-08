"""Phase 2 stub — Opportunities module."""

from __future__ import annotations


class OpportunityStub:
    def list_opportunities(self, **kwargs) -> dict:
        return {
            "ok": False,
            "error": "Phase 2 — Opportunities module not enabled",
            "total": 0,
            "rows": [],
        }

    def create_opportunity(self, **kwargs) -> dict:
        return {"ok": False, "error": "Phase 2 — Opportunities module not enabled"}
