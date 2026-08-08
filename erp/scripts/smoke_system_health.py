"""Smoke test for System Health Mission Control (run inside ERP venv)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from app import create_app

    app = create_app()
    with app.app_context():
        from app.modules.system_health.repository import SystemHealthRepository
        from app.modules.system_health.service import SystemHealthService

        SystemHealthRepository().ensure_schema()
        svc = SystemHealthService()
        data = svc.scan(persist=True)
        assert data.get("ok") is True
        assert "summary" in data
        assert "application" in data
        assert "database" in data
        print("Overall:", data.get("overall_score"), data.get("overall_label"))
        print("DB:", data["database"].get("status"), data["database"].get("database_name"))
        print("API score:", (data.get("api_health") or {}).get("global_health_score"))
        print("Alerts:", len(data.get("alerts") or []))
        charts = svc.charts()
        assert charts.get("ok") is True
        name, mime, body = svc.export_report("csv")
        assert "Overall Score" in body
        print("Export:", name, len(body), "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
