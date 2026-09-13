"""Office-PC presence for Other Login. VPS stores only heartbeat/jobs, never login vault data."""

from __future__ import annotations

import hmac
import json
import os
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.other_login_store import (
    DEFAULT_OFFICE_ROOT,
    data_root,
    ensure_office_layout,
    is_office_root_path,
    is_known_key,
    office_drive_available,
    read_local_token,
    read_workspace,
    utc_now_iso,
    write_workspace,
)

_LOCK = threading.Lock()
DEFAULT_TTL_SECONDS = 90
JOB_WAIT_SECONDS = 12
JOB_TTL_SECONDS = 120
MAX_JOBS = 20


def heartbeat_ttl_seconds() -> int:
    raw = (os.getenv("OTHER_LOGIN_HEARTBEAT_TTL") or str(DEFAULT_TTL_SECONDS)).strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TTL_SECONDS
    return max(30, min(value, 600))


def _presence_override() -> str | None:
    raw = (os.getenv("OTHER_LOGIN_PRESENCE") or "").strip().lower()
    if raw in {"online", "on", "1", "true", "yes"}:
        return "online"
    if raw in {"offline", "off", "0", "false", "no"}:
        return "offline"
    return None


def instance_dir() -> Path:
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            path = Path(current_app.instance_path)
            path.mkdir(parents=True, exist_ok=True)
            return path
    except Exception:
        pass
    path = Path(__file__).resolve().parents[2] / "instance"
    path.mkdir(parents=True, exist_ok=True)
    return path


def heartbeat_state_path() -> Path:
    return instance_dir() / "other_login_bridge.json"


def jobs_state_path() -> Path:
    return instance_dir() / "other_login_jobs.json"


def _read_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _parse_ts(raw: str | None) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _fresh(ts_raw: str | None, ttl: int | None = None) -> bool:
    stamp = _parse_ts(ts_raw)
    if stamp is None:
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds()
    return 0 <= age <= (ttl or heartbeat_ttl_seconds())


def office_computer_here() -> bool:
    """True when this process is running on the office PC that owns E:\\Web-Data."""
    if _presence_override() == "offline":
        return False
    if _presence_override() == "online" and is_office_root_path():
        return True
    root = data_root()
    if not office_drive_available(root):
        return False
    if not is_office_root_path(root) and _presence_override() != "online":
        return False
    return root.is_dir()


def vps_heartbeat_fresh() -> bool:
    state = _read_state(heartbeat_state_path())
    return bool(state.get("online")) and _fresh(state.get("ts"))


def computer_is_online() -> bool:
    override = _presence_override()
    if override == "offline":
        return False
    if override == "online":
        return True
    if office_computer_here():
        return True
    return vps_heartbeat_fresh()


def presence_payload() -> dict[str, Any]:
    office = office_computer_here()
    remote = vps_heartbeat_fresh()
    online = computer_is_online()
    source = "offline"
    if _presence_override() == "online":
        source = "override"
    elif office:
        source = "office-pc"
    elif remote:
        source = "heartbeat"
    state = _read_state(heartbeat_state_path())
    return {
        "ok": True,
        "online": online,
        "source": source,
        "data_root": str(DEFAULT_OFFICE_ROOT if office else data_root()),
        "office_computer": office,
        "last_seen": state.get("ts") if remote or state.get("ts") else None,
        "ttl_seconds": heartbeat_ttl_seconds(),
    }


def expected_bridge_token() -> str:
    env_token = (os.getenv("OTHER_LOGIN_BRIDGE_TOKEN") or "").strip().strip('"').strip("'")
    if env_token:
        return env_token
    if office_computer_here():
        return read_local_token()
    return ""


def tokens_match(provided: str | None) -> bool:
    expected = expected_bridge_token()
    incoming = (provided or "").strip()
    if not expected or not incoming:
        return False
    return hmac.compare_digest(expected, incoming)


def extract_request_token(payload: dict[str, Any] | None = None) -> str:
    from flask import request

    header = (request.headers.get("X-Other-Login-Token") or request.headers.get("X-API-Key") or "").strip()
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        auth = auth[7:].strip()
    body = (payload or {}).get("token") if isinstance(payload, dict) else ""
    query = (request.args.get("token") or "").strip()
    return str(header or auth or body or query or "").strip()


def record_heartbeat(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    host = str(body.get("host") or body.get("hostname") or "").strip()[:200]
    state = {
        "online": True,
        "ts": utc_now_iso(),
        "host": host,
        "data_root": str(body.get("data_root") or DEFAULT_OFFICE_ROOT),
        "services": body.get("services") if isinstance(body.get("services"), list) else [],
    }
    with _LOCK:
        _write_state(heartbeat_state_path(), state)
    return {"ok": True, "online": True, "ts": state["ts"], "ttl_seconds": heartbeat_ttl_seconds()}


def _empty_jobs() -> dict[str, Any]:
    return {"jobs": [], "results": {}}


def _prune_jobs(state: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    jobs = []
    for job in state.get("jobs") or []:
        if not isinstance(job, dict):
            continue
        created = _parse_ts(job.get("created_at"))
        if created is None:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if (now - created.astimezone(timezone.utc)).total_seconds() <= JOB_TTL_SECONDS:
            jobs.append(job)
    results = {}
    for job_id, result in (state.get("results") or {}).items():
        if not isinstance(result, dict):
            continue
        created = _parse_ts(result.get("at"))
        if created is None:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if (now - created.astimezone(timezone.utc)).total_seconds() <= JOB_TTL_SECONDS:
            results[str(job_id)] = result
    state["jobs"] = jobs[:MAX_JOBS]
    state["results"] = results
    return state


def enqueue_job(op: str, key: str, payload: dict[str, Any] | None = None) -> str:
    if op not in {"read", "write"}:
        raise ValueError("Unsupported Other Login job.")
    if not is_known_key(key):
        raise ValueError("Unknown Other Login service.")
    job_id = secrets.token_hex(12)
    job = {
        "id": job_id,
        "op": op,
        "key": key,
        "payload": payload if isinstance(payload, dict) else {},
        "created_at": utc_now_iso(),
    }
    with _LOCK:
        state = _prune_jobs(_read_state(jobs_state_path()) or _empty_jobs())
        state.setdefault("jobs", []).append(job)
        _write_state(jobs_state_path(), state)
    return job_id


def pull_jobs() -> list[dict[str, Any]]:
    with _LOCK:
        state = _prune_jobs(_read_state(jobs_state_path()) or _empty_jobs())
        jobs = list(state.get("jobs") or [])
        state["jobs"] = []
        _write_state(jobs_state_path(), state)
    return jobs


def store_job_result(job_id: str, result: dict[str, Any]) -> None:
    clean_id = (job_id or "").strip()
    if not clean_id:
        return
    payload = dict(result) if isinstance(result, dict) else {"ok": False, "error": "Invalid result"}
    payload["at"] = utc_now_iso()
    with _LOCK:
        state = _prune_jobs(_read_state(jobs_state_path()) or _empty_jobs())
        state.setdefault("results", {})[clean_id] = payload
        _write_state(jobs_state_path(), state)


def take_job_result(job_id: str) -> dict[str, Any] | None:
    clean_id = (job_id or "").strip()
    if not clean_id:
        return None
    with _LOCK:
        state = _prune_jobs(_read_state(jobs_state_path()) or _empty_jobs())
        results = state.get("results") or {}
        result = results.pop(clean_id, None)
        state["results"] = results
        _write_state(jobs_state_path(), state)
    return result if isinstance(result, dict) else None


def execute_local_job(job: dict[str, Any]) -> dict[str, Any]:
    op = str(job.get("op") or "").strip().lower()
    key = str(job.get("key") or "").strip().lower()
    try:
        if op == "read":
            return {"ok": True, "data": read_workspace(key)}
        if op == "write":
            return {"ok": True, "data": write_workspace(key, job.get("payload") if isinstance(job.get("payload"), dict) else {})}
        return {"ok": False, "error": "Unsupported job."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def workspace_via_bridge(key: str, *, op: str = "read", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not computer_is_online():
        return {"ok": False, "error": "Office computer is off. Other Login is disabled.", "offline": True}
    if office_computer_here():
        ensure_office_layout()
        data = write_workspace(key, payload) if op == "write" else read_workspace(key)
        return {"ok": True, "data": data, "source": "office-pc"}
    job_id = enqueue_job(op, key, payload)
    deadline = time.time() + JOB_WAIT_SECONDS
    while time.time() < deadline:
        result = take_job_result(job_id)
        if result is not None:
            result.setdefault("source", "bridge")
            return result
        time.sleep(0.25)
    return {
        "ok": False,
        "error": "Office computer is on, but E:\\Web-Data bridge did not answer. Start Other Login Bridge on the PC.",
        "timeout": True,
    }
