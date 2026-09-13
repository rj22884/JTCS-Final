"""Office-PC agent: keep E:\\Web-Data folders ready and tell VPS the computer is on."""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ERP_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ERP_ROOT.parent
sys.path.insert(0, str(ERP_ROOT))

from dotenv import load_dotenv

load_dotenv(ERP_ROOT / ".env")

from app.services.other_login_bridge import execute_local_job
from app.services.other_login_store import (
    data_root,
    ensure_bridge_token,
    ensure_layout,
    known_service_keys,
    utc_now_iso,
    write_local_heartbeat,
)

DEFAULT_VPS = "https://app.jtcsxpert.com"
HEARTBEAT_EVERY = 15
JOB_POLL_EVERY = 2
LOCK_NAME = "agent.lock"


def _vps_base() -> str:
    return (os.getenv("OTHER_LOGIN_VPS_URL") or DEFAULT_VPS).strip().rstrip("/")


def _lock_path() -> Path:
    return data_root() / "_bridge" / LOCK_NAME


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, 0, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def acquire_lock() -> bool:
    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            old = int(path.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            old = 0
        if old != os.getpid() and _pid_running(old):
            print(f"Other Login bridge already running (pid {old})")
            return False
    path.write_text(str(os.getpid()), encoding="utf-8")
    return True


def post_json(url: str, payload: dict, token: str, timeout: int = 12) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Other-Login-Token": token,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def get_json(url: str, token: str, timeout: int = 12) -> dict:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "X-Other-Login-Token": token,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def send_heartbeat(token: str) -> None:
    payload = write_local_heartbeat(
        {
            "source": "local-bridge",
            "host": socket.gethostname(),
            "ts": utc_now_iso(),
        }
    )
    payload["token"] = token
    payload["host"] = socket.gethostname()
    url = f"{_vps_base()}/other-login/api/local-heartbeat"
    try:
        result = post_json(url, payload, token)
        print(f"heartbeat ok ts={result.get('ts')}")
    except Exception as exc:
        print(f"heartbeat pending (VPS not reachable): {exc}")


def process_jobs(token: str) -> None:
    url = f"{_vps_base()}/other-login/api/local-jobs"
    try:
        payload = get_json(url, token)
    except Exception:
        return
    for job in payload.get("jobs") or []:
        if not isinstance(job, dict):
            continue
        result = execute_local_job(job)
        try:
            post_json(
                f"{_vps_base()}/other-login/api/local-job-result",
                {"id": job.get("id"), "result": result, "token": token},
                token,
            )
        except Exception as exc:
            print(f"job result failed: {exc}")


def main() -> int:
    os.chdir(ERP_ROOT)
    root = ensure_layout()
    token = ensure_bridge_token()
    if not acquire_lock():
        return 0
    print(f"Other Login data root: {root}")
    print(f"Folders: {', '.join(known_service_keys())}")
    print(f"VPS: {_vps_base()}")
    last_heartbeat = 0.0
    try:
        while True:
            now = time.time()
            if now - last_heartbeat >= HEARTBEAT_EVERY:
                send_heartbeat(token)
                last_heartbeat = now
            process_jobs(token)
            time.sleep(JOB_POLL_EVERY)
    except KeyboardInterrupt:
        print("Other Login bridge stopped")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
