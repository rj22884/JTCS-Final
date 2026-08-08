"""Smoke test for Integration Health service (run inside ERP venv)."""

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
        from app.modules.settings.repositories import IntegrationSettingsRepository
        from app.modules.settings.integration_health_service import IntegrationHealthService

        repo = IntegrationSettingsRepository()
        repo.ensure_health_schema()
        svc = IntegrationHealthService()
        dash = svc.dashboard(run_scan=True, force=True)
        assert dash.get("ok") is True
        assert dash.get("summary", {}).get("total", 0) >= 10
        assert isinstance(dash.get("integrations"), list)
        print("OK integrations:", dash["summary"]["total"])
        print("Global score:", dash.get("global_health_score"), dash.get("global_label"))
        print("Alerts:", len(dash.get("alerts") or []))
        if dash["integrations"]:
            code = dash["integrations"][0]["code"]
            detail = svc.provider_detail(code)
            assert detail.get("ok") is True
            print("Detail OK:", code)
        name, mime, body = svc.export_report("csv")
        assert "Provider" in body
        print("Export:", name, mime, "bytes", len(body))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
