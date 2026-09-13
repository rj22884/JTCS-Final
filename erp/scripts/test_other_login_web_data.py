"""Other Login local vault stays under a dedicated root and never touches other ERP data."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ERP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ERP_ROOT))


def main() -> int:
    from app.services.other_login_bridge import computer_is_online, execute_local_job, tokens_match
    from app.services.other_login_catalog import list_other_login_services
    from app.services.other_login_store import (
        DEFAULT_OFFICE_ROOT,
        ensure_layout,
        known_service_keys,
        read_workspace,
        service_dir,
        write_workspace,
    )

    with tempfile.TemporaryDirectory(prefix="jtcs-ol-") as raw:
        root = Path(raw)
        os.environ["OTHER_LOGIN_DATA_ROOT"] = str(root)
        os.environ["OTHER_LOGIN_ENSURE"] = "1"
        os.environ["OTHER_LOGIN_PRESENCE"] = "offline"
        os.environ.pop("OTHER_LOGIN_BRIDGE_TOKEN", None)

        ensure_layout()
        keys = known_service_keys()
        if len(keys) != 25:
            raise SystemExit(f"Expected 25 folders, got {len(keys)}")
        for key in keys:
            folder = root / key
            if not (folder / "service.json").is_file() or not (folder / "data.json").is_file():
                raise SystemExit(f"Missing local files for {key}")
        if not (root / "_bridge" / "token.txt").is_file():
            raise SystemExit("Bridge token was not created")
        if computer_is_online():
            raise SystemExit("Offline override failed")
        disabled = list_other_login_services()
        if any(item.enabled for item in disabled):
            raise SystemExit("Offline catalog leaked an enabled login")
        os.environ["OTHER_LOGIN_PRESENCE"] = "online"
        if not computer_is_online():
            raise SystemExit("Presence override did not turn Other Login on")
        if any(not item.enabled for item in list_other_login_services()):
            raise SystemExit("Online catalog left a login disabled")

        saved = write_workspace(
            "aadhaar",
            {
                "portal_url": "https://myaadhaar.uidai.gov.in/",
                "notes": "office vault",
                "records": [{"label": "Main", "user_id": "demo", "password": "secret"}],
            },
        )
        loaded = read_workspace("aadhaar")
        if loaded.get("notes") != "office vault" or not loaded.get("records"):
            raise SystemExit("Aadhaar workspace did not persist in the temp Web-Data root")
        if Path(loaded["folder"]).resolve() != (root / "aadhaar").resolve():
            raise SystemExit("Workspace folder escaped the Other Login root")
        if DEFAULT_OFFICE_ROOT.resolve() == Path(saved["folder"]).resolve():
            raise SystemExit("Test wrote into the real E:\\Web-Data folder")

        try:
            service_dir("../users")
        except ValueError:
            pass
        else:
            raise SystemExit("Path traversal was not rejected")

        job = execute_local_job({"op": "read", "key": "gst"})
        if not job.get("ok") or job["data"]["key"] != "gst":
            raise SystemExit("Local job read failed")
        token = (root / "_bridge" / "token.txt").read_text(encoding="utf-8").strip()
        os.environ["OTHER_LOGIN_BRIDGE_TOKEN"] = token
        if not tokens_match(token):
            raise SystemExit("Bridge token mismatch")
        if tokens_match("wrong-token"):
            raise SystemExit("Wrong bridge token was accepted")

        print("WEB-DATA OK", root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
