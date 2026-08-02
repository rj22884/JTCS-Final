"""Integration Settings module (isolated)."""

from app.modules.settings.routes import bp as integration_settings_bp
from app.modules.settings.routes import ensure_integration_settings_bootstrap

__all__ = ["integration_settings_bp", "ensure_integration_settings_bootstrap"]
