"""Dashboard What's New — auto from new menus + publish_whats_new()."""

from __future__ import annotations

from app.services.whats_new_service import list_whats_new, publish_whats_new

__all__ = ["list_whats_new", "publish_whats_new"]
