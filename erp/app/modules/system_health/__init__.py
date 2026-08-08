"""System Health & Infrastructure Monitoring Center (Admin Mission Control)."""

from app.modules.system_health.routes import bp as system_health_bp
from app.modules.system_health.routes import ensure_system_health_menus

__all__ = ["system_health_bp", "ensure_system_health_menus"]
