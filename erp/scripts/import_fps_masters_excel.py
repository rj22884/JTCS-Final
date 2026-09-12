"""Overwrite PDS State / District / DSO / ARO / FPS from the coded FPS Excel."""
from __future__ import annotations

import sys
from pathlib import Path

ERP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ERP_ROOT))

from app import create_app
from app.services.pds_master_service import PdsMasterService

DEFAULT_FILE = Path(r"C:\Users\USER\Downloads\DistrictWiseFpsDetails_Merged_WithCodes.xlsx")


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FILE
    app = create_app()
    with app.app_context():
        result = PdsMasterService().import_district_fps_workbook(path, actor="Excel Import")
    for key in (
        "message",
        "fps_rows",
        "unique_states",
        "unique_districts",
        "unique_dso",
        "unique_aro",
        "state_added",
        "state_updated",
        "district_added",
        "district_updated",
        "dso_added",
        "dso_updated",
        "aro_added",
        "aro_updated",
        "fps_added",
        "fps_updated",
        "district_deactivated",
        "dso_deactivated",
        "aro_deactivated",
    ):
        print(f"{key}: {result.get(key)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
