"""
ITR Followup ↔ KDK Software sync orchestration.

Credentials are entered in the login modal; the browser may remember them locally
for the next Sync prompt. Password is never written to sync.log.
"""
from __future__ import annotations

import logging
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.repositories.followup_repository import FollowupRepository
from app.services.followup_service import FollowupService
from app.utils.db_session import persist

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.sync_itr import SyncClientInput, parse_portal_date, sync_clients_sync  # noqa: E402

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "sync.log"

# Whole-job hard timeout (login + all clients). Prevents infinite "Logging in..." UI.
JOB_HARD_TIMEOUT_SEC = 45 * 60
LOGIN_HARD_TIMEOUT_SEC = 180

_logger = logging.getLogger("jtcs.itr_kdk_sync")
if not _logger.handlers:
    _logger.setLevel(logging.INFO)
    handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    _logger.addHandler(handler)
    _logger.propagate = False

_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()
_CANCEL: set[str] = set()


class ItrKdkSyncService:
    """Background KDK sync jobs for ITR Followup grid rows."""

    def __init__(self, followup_repo: FollowupRepository | None = None):
        self.repo = followup_repo or FollowupRepository()

    @staticmethod
    def _set_job(job_id: str, **kwargs: Any) -> None:
        with _LOCK:
            job = _JOBS.get(job_id) or {"job_id": job_id}
            job.update(kwargs)
            job["updated_at"] = datetime.utcnow().isoformat() + "Z"
            _JOBS[job_id] = job

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with _LOCK:
            job = _JOBS.get(job_id)
            return dict(job) if job else None

    def cancel_job(self, job_id: str) -> bool:
        with _LOCK:
            job = _JOBS.get(job_id)
            if not job:
                return False
            _CANCEL.add(job_id)
            job["status"] = "failed"
            job["error"] = "Sync cancelled."
            job["message"] = "Sync cancelled."
            job["updated_at"] = datetime.utcnow().isoformat() + "Z"
            job["finished_at"] = job["updated_at"]
            _JOBS[job_id] = job
            return True

    @staticmethod
    def _is_cancelled(job_id: str) -> bool:
        with _LOCK:
            return job_id in _CANCEL

    def ensure_schema(self) -> None:
        self.repo.ensure_filing_status_columns()

    @staticmethod
    def _log_line(*, customer: str, pan: str, period: str, status: str) -> None:
        _logger.info(
            "Customer=%s | PAN=%s | Period=%s | Status=%s | Time=%s",
            customer or "",
            pan or "",
            period or "",
            status or "",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    def update_entry_filing(
        self,
        *,
        entry_id: int | None,
        customer: str,
        period: str,
        return_filing_status: str | None,
        filing_date_raw: str | None,
    ) -> bool:
        self.ensure_schema()
        filing_date = parse_portal_date(filing_date_raw)

        def _write() -> bool:
            if entry_id:
                row = self.repo.get_entry(entry_id)
                if row is None or (row.ModuleCode or "").upper() != "ITR":
                    return False
                self.repo.update_entry(
                    row,
                    {
                        "ReturnFilingStatus": (return_filing_status or "")[:150] or None,
                        "FilingDate": filing_date,
                        "ModifiedDate": datetime.utcnow(),
                    },
                )
                return True

            matched = self.repo.find_active_itr_by_customer_period(customer, period)
            if matched is None:
                return False
            self.repo.update_entry(
                matched,
                {
                    "ReturnFilingStatus": (return_filing_status or "")[:150] or None,
                    "FilingDate": filing_date,
                    "ModifiedDate": datetime.utcnow(),
                },
            )
            return True

        return bool(persist(_write))

    def _clients_from_grid(self) -> list[SyncClientInput]:
        service = FollowupService("ITR")
        rows = service.list_entries()
        clients: list[SyncClientInput] = []
        for row in rows:
            pan = (row.get("pan_number") or "").strip()
            period = (row.get("tax_period") or "").strip()
            entry_id = int(row.get("entry_id") or row.get("EntryID") or 0)
            if not entry_id or not period:
                continue
            clients.append(
                SyncClientInput(
                    entry_id=entry_id,
                    customer=(row.get("customer_name") or "").strip(),
                    pan=pan,
                    period=period,
                    return_type=(row.get("return_type") or row.get("ReturnType") or "Original").strip()
                    or "Original",
                )
            )
        return clients

    def start_sync(
        self,
        *,
        user_id: str,
        password: str,
        app=None,
        headless: bool = True,
        entry_id: int | None = None,
    ) -> dict[str, Any]:
        user_id = (user_id or "").strip()
        password = password or ""
        if not user_id or not password:
            raise ValueError("KDK Mobile Number and Password are required.")

        self.ensure_schema()
        clients = self._clients_from_grid()
        if entry_id is not None:
            try:
                entry_id = int(entry_id)
            except (TypeError, ValueError):
                raise ValueError("Invalid entry_id.") from None
            clients = [c for c in clients if c.entry_id == entry_id]
            if not clients:
                raise ValueError("ITR Followup record not found to sync.")
        if not clients:
            raise ValueError("No ITR Followup records found to sync.")

        job_id = uuid.uuid4().hex
        self._set_job(
            job_id,
            status="running",
            message="Launching browser...",
            login_status="",
            total=len(clients),
            completed=0,
            current_client="",
            current_pan="",
            current_period="",
            results=[],
            error=None,
            started_at=datetime.utcnow().isoformat() + "Z",
        )

        def _runner() -> None:
            ctx = app.app_context() if app is not None else None
            if ctx is not None:
                ctx.push()
            watchdog_stop = threading.Event()
            login_phase_done = threading.Event()

            def _watchdog() -> None:
                # Fail only if still stuck in login/launch — not during All-tab / client sync.
                if not watchdog_stop.wait(LOGIN_HARD_TIMEOUT_SEC):
                    if login_phase_done.is_set():
                        return
                    job = self.get_job(job_id) or {}
                    if job.get("status") == "running" and int(job.get("completed") or 0) == 0:
                        self._set_job(
                            job_id,
                            status="failed",
                            error="Login timed out. Check KDK Mobile Number/Password or network.",
                            message="Login timed out. Check KDK Mobile Number/Password or network.",
                            finished_at=datetime.utcnow().isoformat() + "Z",
                        )
                        _CANCEL.add(job_id)

            threading.Thread(target=_watchdog, name=f"itr-kdk-wd-{job_id[:8]}", daemon=True).start()

            try:
                def progress_cb(payload: dict[str, Any]) -> None:
                    if self._is_cancelled(job_id):
                        raise RuntimeError("Sync cancelled.")
                    phase = payload.get("phase")
                    preview = payload.get("preview_image")
                    if phase in {"navigate", "client", "result"}:
                        login_phase_done.set()
                    if phase == "login":
                        updates = {"message": payload.get("message") or ""}
                        if payload.get("login_ok") is True:
                            updates["login_status"] = "Login Successfully"
                            updates["message"] = "Login Successfully"
                        elif payload.get("login_ok") is False:
                            updates["login_status"] = "Login Failed"
                            updates["message"] = "Login Failed"
                        elif (payload.get("message") or "").strip().lower() == "login successfully":
                            updates["login_status"] = "Login Successfully"
                        if preview:
                            updates["preview_image"] = preview
                        self._set_job(job_id, **updates)
                    elif phase == "client":
                        updates = {
                            "status": "running",
                            "message": payload.get("message") or "Syncing...",
                            "completed": max(0, int(payload.get("index") or 1) - 1),
                            "total": int(payload.get("total") or len(clients)),
                            "current_client": payload.get("customer") or "",
                            "current_pan": payload.get("pan") or "",
                            "current_period": payload.get("period") or "",
                        }
                        if preview:
                            updates["preview_image"] = preview
                        self._set_job(job_id, **updates)
                    elif phase == "result":
                        result = payload.get("result") or {}
                        status_text = result.get("return_filing_status") or result.get("error") or ""
                        try:
                            self.update_entry_filing(
                                entry_id=result.get("entry_id"),
                                customer=result.get("customer") or "",
                                period=result.get("period") or "",
                                return_filing_status=status_text,
                                filing_date_raw=result.get("filing_date"),
                            )
                        except Exception as exc:
                            status_text = f"Update failed: {exc}"
                        self._log_line(
                            customer=result.get("customer") or "",
                            pan=result.get("pan") or "",
                            period=result.get("period") or "",
                            status=status_text,
                        )
                        with _LOCK:
                            job = _JOBS.get(job_id) or {}
                            results = list(job.get("results") or [])
                            results.append(result)
                            job["results"] = results
                            job["completed"] = len(results)
                            job["updated_at"] = datetime.utcnow().isoformat() + "Z"
                            if preview:
                                job["preview_image"] = preview
                            _JOBS[job_id] = job
                    elif phase == "navigate":
                        updates = {"message": payload.get("message") or ""}
                        if preview:
                            updates["preview_image"] = preview
                        self._set_job(job_id, **updates)
                        login_phase_done.set()
                    elif preview:
                        self._set_job(job_id, preview_image=preview)

                sync_clients_sync(
                    user_id=user_id,
                    password=password,
                    clients=clients,
                    progress_cb=progress_cb,
                    headless=headless,
                )
                if self._is_cancelled(job_id):
                    return
                self._set_job(
                    job_id,
                    status="completed",
                    message="Sync completed.",
                    completed=len(clients),
                    current_client="",
                    current_pan="",
                    current_period="",
                    finished_at=datetime.utcnow().isoformat() + "Z",
                )
            except Exception as exc:
                if self._is_cancelled(job_id):
                    return
                message = str(exc) or "Sync failed."
                login_status = ""
                if "Login Failed" in message:
                    message = "Login Failed"
                    login_status = "Login Failed"
                elif "Executable doesn't exist" in message or "Playwright browser missing" in message:
                    message = (
                        "Playwright browser missing. Run once: "
                        ".venv\\Scripts\\python.exe -m playwright install chromium"
                    )
                updates = {
                    "status": "failed",
                    "error": message,
                    "message": message,
                    "finished_at": datetime.utcnow().isoformat() + "Z",
                }
                if login_status:
                    updates["login_status"] = login_status
                self._set_job(job_id, **updates)
                _logger.info(
                    "Customer=- | PAN=- | Period=- | Status=%s | Time=%s",
                    message,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
            finally:
                watchdog_stop.set()
                with _LOCK:
                    _CANCEL.discard(job_id)
                if ctx is not None:
                    ctx.pop()

        thread = threading.Thread(target=_runner, name=f"itr-kdk-sync-{job_id[:8]}", daemon=True)
        thread.start()
        return {"job_id": job_id, "total": len(clients), "status": "running"}
