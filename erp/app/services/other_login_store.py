"""Other Login vault on the office PC only: E:\\Web-Data\\<login-folder>.

Does not read or write ERP / SQL / Credentials Master / PDS data.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_OFFICE_ROOT = Path(r"E:\Web-Data")
BRIDGE_DIR_NAME = "_bridge"
TOKEN_FILE_NAME = "token.txt"
HEARTBEAT_FILE_NAME = "heartbeat.json"
MAX_DATA_BYTES = 1_000_000
MAX_RECORDS = 50
MAX_FIELD_LEN = 500
MAX_NOTES_LEN = 4000

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")

DEFAULT_PORTALS: dict[str, str] = {
    "uttarakhand_fps": "https://food.uk.gov.in/",
    "aadhaar": "https://myaadhaar.uidai.gov.in/",
    "pan": "https://www.incometax.gov.in/iec/foportal",
    "gst": "https://www.gst.gov.in/",
    "income_tax": "https://eportal.incometax.gov.in/",
    "tds_traces": "https://www.tdscpc.gov.in/",
    "epfo": "https://unifiedportal-mem.epfindia.gov.in/",
    "esic": "https://www.esic.gov.in/",
    "udyam": "https://udyamregistration.gov.in/",
    "mca": "https://www.mca.gov.in/",
    "digilocker": "https://www.digilocker.gov.in/",
    "edistrict_uk": "https://edistrict.uk.gov.in/",
    "bhulekh_uk": "https://bhulekh.uk.gov.in/",
    "vahan": "https://vahan.parivahan.gov.in/",
    "sarathi": "https://sarathi.parivahan.gov.in/",
    "passport_seva": "https://www.passportindia.gov.in/",
    "nps": "https://www.npscra.nsdl.co.in/",
    "gem": "https://gem.gov.in/",
    "cpgrams": "https://pgportal.gov.in/",
    "jan_aadhaar": "https://www.india.gov.in/",
    "pfms": "https://pfms.nic.in/",
    "eway_bill": "https://ewaybillgst.gov.in/",
    "einvoice": "https://einvoice.gst.gov.in/",
    "fssai": "https://foscos.fssai.gov.in/",
    "startup_india": "https://www.startupindia.gov.in/",
}

RECORD_FIELDS = ("id", "label", "user_id", "password", "email", "mobile", "notes")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def data_root() -> Path:
    raw = (os.getenv("OTHER_LOGIN_DATA_ROOT") or str(DEFAULT_OFFICE_ROOT)).strip().strip('"').strip("'")
    return Path(raw)


def is_office_root_path(root: Path | None = None) -> bool:
    target = (root or data_root()).resolve()
    return target == DEFAULT_OFFICE_ROOT.resolve()


def normalize_key(key: str | None) -> str:
    return (key or "").strip().lower()


def known_service_keys() -> tuple[str, ...]:
    from app.services.other_login_catalog import OTHER_LOGIN_SERVICES

    return tuple(item.key for item in OTHER_LOGIN_SERVICES)


def is_known_key(key: str | None) -> bool:
    needle = normalize_key(key)
    return bool(needle and _KEY_RE.fullmatch(needle) and needle in known_service_keys())


def _safe_child(root: Path, name: str) -> Path:
    child = (root / name).resolve()
    root_res = root.resolve()
    if child == root_res or root_res not in child.parents:
        raise ValueError("Invalid Other Login folder path.")
    return child


def service_dir(key: str) -> Path:
    needle = normalize_key(key)
    if not is_known_key(needle):
        raise ValueError("Unknown Other Login service.")
    return _safe_child(data_root(), needle)


def bridge_dir() -> Path:
    return _safe_child(data_root(), BRIDGE_DIR_NAME)


def token_path() -> Path:
    return bridge_dir() / TOKEN_FILE_NAME


def local_heartbeat_path() -> Path:
    return bridge_dir() / HEARTBEAT_FILE_NAME


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def atomic_write_json(path: Path, payload: Any) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if len(text.encode("utf-8")) > MAX_DATA_BYTES:
        raise ValueError("Other Login data is too large.")
    _atomic_write_text(path, text + "\n")


def read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _clip(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def empty_workspace(key: str, *, name: str = "", subtitle: str = "", portal_url: str = "") -> dict[str, Any]:
    needle = normalize_key(key)
    return {
        "key": needle,
        "name": name,
        "subtitle": subtitle,
        "portal_url": portal_url or DEFAULT_PORTALS.get(needle, ""),
        "notes": "",
        "records": [],
        "updated_at": None,
        "data_root": str(data_root()),
        "folder": str(service_dir(needle)) if is_known_key(needle) else "",
    }


def sanitize_workspace(key: str, payload: dict[str, Any] | None, *, name: str = "", subtitle: str = "") -> dict[str, Any]:
    needle = normalize_key(key)
    raw = payload if isinstance(payload, dict) else {}
    existing_portal = _clip(raw.get("portal_url"), MAX_FIELD_LEN)
    workspace = empty_workspace(
        needle,
        name=name or _clip(raw.get("name"), MAX_FIELD_LEN),
        subtitle=subtitle or _clip(raw.get("subtitle"), MAX_FIELD_LEN),
        portal_url=existing_portal,
    )
    workspace["notes"] = _clip(raw.get("notes"), MAX_NOTES_LEN)
    records: list[dict[str, str]] = []
    incoming = raw.get("records") if isinstance(raw.get("records"), list) else []
    for item in incoming[:MAX_RECORDS]:
        if not isinstance(item, dict):
            continue
        rec_id = _clip(item.get("id"), 80) or secrets.token_hex(8)
        records.append(
            {
                "id": rec_id,
                "label": _clip(item.get("label"), MAX_FIELD_LEN),
                "user_id": _clip(item.get("user_id"), MAX_FIELD_LEN),
                "password": _clip(item.get("password"), MAX_FIELD_LEN),
                "email": _clip(item.get("email"), MAX_FIELD_LEN),
                "mobile": _clip(item.get("mobile"), 32),
                "notes": _clip(item.get("notes"), MAX_NOTES_LEN),
            }
        )
    workspace["records"] = records
    workspace["updated_at"] = _clip(raw.get("updated_at"), 80) or None
    return workspace


def _service_meta(key: str) -> tuple[str, str, str]:
    from app.services.other_login_catalog import OTHER_LOGIN_SERVICES

    needle = normalize_key(key)
    for item in OTHER_LOGIN_SERVICES:
        if item.key == needle:
            return item.name, item.subtitle, item.icon
    return needle, "", "bi-box-arrow-in-right"


def ensure_service_folder(key: str) -> Path:
    needle = normalize_key(key)
    folder = service_dir(needle)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "files").mkdir(parents=True, exist_ok=True)
    name, subtitle, icon = _service_meta(needle)
    service_path = folder / "service.json"
    if not service_path.is_file():
        atomic_write_json(
            service_path,
            {
                "key": needle,
                "name": name,
                "subtitle": subtitle,
                "icon": icon,
                "portal_url": DEFAULT_PORTALS.get(needle, ""),
                "data_file": "data.json",
            },
        )
    data_path = folder / "data.json"
    if not data_path.is_file():
        workspace = empty_workspace(needle, name=name, subtitle=subtitle)
        workspace.pop("data_root", None)
        workspace.pop("folder", None)
        atomic_write_json(data_path, workspace)
    return folder


def read_local_token() -> str:
    env_token = (os.getenv("OTHER_LOGIN_BRIDGE_TOKEN") or "").strip().strip('"').strip("'")
    if env_token:
        return env_token
    path = token_path()
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


def ensure_bridge_token() -> str:
    folder = bridge_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = token_path()
    existing = ""
    if path.is_file():
        existing = path.read_text(encoding="utf-8").strip()
    if existing:
        return existing
    env_token = (os.getenv("OTHER_LOGIN_BRIDGE_TOKEN") or "").strip().strip('"').strip("'")
    token = env_token or secrets.token_hex(24)
    _atomic_write_text(path, token + "\n")
    return token


def write_local_heartbeat(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "online": True,
        "ts": utc_now_iso(),
        "data_root": str(data_root()),
        "services": list(known_service_keys()),
    }
    if extra:
        payload.update(extra)
    atomic_write_json(local_heartbeat_path(), payload)
    return payload


def ensure_layout() -> Path:
    root = data_root()
    root.mkdir(parents=True, exist_ok=True)
    readme = root / "README.txt"
    if not readme.is_file():
        _atomic_write_text(
            readme,
            (
                "JTCS Other Login — local data only.\n"
                "Har login ka data iske andar alag folder mein hai.\n"
                "Is folder ke bahar JTCS ERP / VPS data change nahi hota.\n"
                f"Root: {root}\n"
            ),
        )
    ensure_bridge_token()
    for key in known_service_keys():
        ensure_service_folder(key)
    write_local_heartbeat({"source": "ensure_layout"})
    return root


def office_drive_available(root: Path | None = None) -> bool:
    target = root or data_root()
    drive = getattr(target, "drive", "") or ""
    if not drive:
        return True
    return Path(f"{drive}/").exists()


def ensure_office_layout() -> bool:
    """Create E:\\Web-Data folders only on the office PC. Never on VPS/tests unless asked."""
    presence = (os.getenv("OTHER_LOGIN_PRESENCE") or "").strip().lower()
    if presence in {"offline", "off", "0", "false", "no"}:
        return False
    root = data_root()
    force = (os.getenv("OTHER_LOGIN_ENSURE") or "").strip().lower() in {"1", "true", "yes", "on"}
    if not force and not is_office_root_path(root):
        return False
    if not office_drive_available(root):
        return False
    try:
        ensure_layout()
        return True
    except OSError:
        return False


def read_workspace(key: str) -> dict[str, Any]:
    needle = normalize_key(key)
    name, subtitle, _icon = _service_meta(needle)
    folder = ensure_service_folder(needle)
    raw = read_json(folder / "data.json", {})
    workspace = sanitize_workspace(needle, raw if isinstance(raw, dict) else {}, name=name, subtitle=subtitle)
    workspace["data_root"] = str(data_root())
    workspace["folder"] = str(folder)
    return workspace


def write_workspace(key: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    needle = normalize_key(key)
    name, subtitle, _icon = _service_meta(needle)
    folder = ensure_service_folder(needle)
    workspace = sanitize_workspace(needle, payload, name=name, subtitle=subtitle)
    workspace["updated_at"] = utc_now_iso()
    stored = dict(workspace)
    stored.pop("data_root", None)
    stored.pop("folder", None)
    atomic_write_json(folder / "data.json", stored)
    workspace["data_root"] = str(data_root())
    workspace["folder"] = str(folder)
    return workspace
