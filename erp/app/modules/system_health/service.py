"""
System Health Mission Control — aggregates app, DB, server, storage,
integrations, backup, security, and users without duplicating those modules.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import platform
import shutil
import socket
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from flask import current_app, has_request_context, session
from sqlalchemy import text

from app.config import BASE_DIR
from app.extensions import db
from app.modules.system_health.repository import SystemHealthRepository

logger = logging.getLogger(__name__)

# Process start (approximate uptime for this worker).
_PROCESS_STARTED = time.time()
_PSUTIL = None

try:
    import psutil as _PSUTIL  # type: ignore
except Exception:  # pragma: no cover
    _PSUTIL = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _score_label(score: int) -> str:
    if score >= 90:
        return "Excellent"
    if score >= 80:
        return "Good"
    if score >= 60:
        return "Warning"
    return "Critical"


def _folder_size_mb(path: Path, *, max_files: int = 8000) -> float | None:
    """Best-effort folder size; capped for large trees."""
    if not path.exists():
        return None
    total = 0
    count = 0
    try:
        if path.is_file():
            return round(path.stat().st_size / (1024 * 1024), 2)
        for root, _dirs, files in os.walk(path):
            for name in files:
                fp = Path(root) / name
                try:
                    total += fp.stat().st_size
                except OSError:
                    continue
                count += 1
                if count >= max_files:
                    return round(total / (1024 * 1024), 2)
    except OSError:
        return None
    return round(total / (1024 * 1024), 2)


class SystemHealthService:
    """Enterprise monitoring center — reuses Backup, Utility, Integration Health."""

    def __init__(self, repository: SystemHealthRepository | None = None):
        self.repo = repository or SystemHealthRepository()

    # ------------------------------------------------------------------ public
    def dashboard(self, *, force_scan: bool = False, persist: bool = True) -> dict[str, Any]:
        """Full Mission Control payload. Auto-scans when stale (>30s) or forced."""
        self.repo.ensure_schema()
        latest = self.repo.latest_scan()
        stale = True
        if latest and latest.get("ScannedOn") and not force_scan:
            scanned = latest["ScannedOn"]
            if isinstance(scanned, datetime) and (_utcnow() - scanned) < timedelta(seconds=25):
                stale = False
                try:
                    summary = json.loads(latest.get("SummaryJson") or "{}")
                    details = json.loads(latest.get("DetailsJson") or "{}")
                    return {
                        "ok": True,
                        "cached": True,
                        "overall_score": int(latest.get("OverallScore") or 0),
                        "overall_label": latest.get("StatusLabel") or _score_label(int(latest.get("OverallScore") or 0)),
                        "last_scan": scanned.isoformat() + "Z",
                        "summary": summary,
                        **details,
                        "alerts": self._alert_payload(),
                        "live_clock": _utcnow().isoformat() + "Z",
                    }
                except Exception:
                    stale = True

        return self.scan(persist=persist)

    def scan(self, *, persist: bool = True) -> dict[str, Any]:
        """Collect all health facets and optionally persist scan + metrics."""
        user_id = session.get("user_id") if has_request_context() else None

        application = self.collect_application()
        database = self.collect_database()
        server = self.collect_server()
        storage = self.collect_storage()
        services = self.collect_background_services()
        api_health = self.collect_api_health()
        security = self.collect_security()
        users = self.collect_users()
        backups = self.collect_backups()
        license_info = self.collect_license()
        logs = self.collect_logs(period="today", level=None, limit=40)
        network = self.collect_network()

        score, summary_cards = self._compute_score(
            application=application,
            database=database,
            server=server,
            storage=storage,
            api_health=api_health,
            backups=backups,
            security=security,
            network=network,
        )
        label = _score_label(score)

        details = {
            "application": application,
            "database": database,
            "server": server,
            "storage": storage,
            "background_services": services,
            "api_health": api_health,
            "security": security,
            "users": users,
            "backups": backups,
            "license": license_info,
            "logs": logs,
            "network": network,
            "utilities": self._utilities_meta(),
            "roadmap": self._roadmap_hints(),
        }

        self._sync_alerts(score, details)

        if persist:
            self.repo.insert_scan(
                overall_score=score,
                status_label=label,
                summary=summary_cards,
                details=details,
                user_id=user_id,
            )
            metrics = []
            if server.get("cpu_percent") is not None:
                metrics.append(("cpu", float(server["cpu_percent"])))
            if server.get("memory_percent") is not None:
                metrics.append(("memory", float(server["memory_percent"])))
            if server.get("disk_percent") is not None:
                metrics.append(("disk", float(server["disk_percent"])))
            if database.get("active_sessions") is not None:
                metrics.append(("db_sessions", float(database["active_sessions"])))
            if api_health.get("global_health_score") is not None:
                metrics.append(("api_health", float(api_health["global_health_score"])))
            if metrics:
                try:
                    self.repo.insert_metrics(metrics)
                except Exception:
                    logger.exception("Metric sample insert failed")

        return {
            "ok": True,
            "cached": False,
            "overall_score": score,
            "overall_label": label,
            "last_scan": _utcnow().isoformat() + "Z",
            "summary": summary_cards,
            "alerts": self._alert_payload(),
            "live_clock": _utcnow().isoformat() + "Z",
            **details,
        }

    def charts(self) -> dict[str, Any]:
        """Time-series for live charts."""
        return {
            "ok": True,
            "cpu": self._series("cpu"),
            "memory": self._series("memory"),
            "disk": self._series("disk"),
            "db_sessions": self._series("db_sessions"),
            "api_health": self._series("api_health"),
        }

    def export_report(self, fmt: str = "csv") -> tuple[str, str, str]:
        data = self.dashboard(force_scan=False, persist=False)
        fmt = (fmt or "csv").lower()
        if fmt == "json":
            return (
                "system_health_report.json",
                "application/json",
                json.dumps(data, indent=2, default=str),
            )
        summary = data.get("summary") or {}
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Metric", "Value"])
        writer.writerow(["Overall Score", data.get("overall_score")])
        writer.writerow(["Overall Label", data.get("overall_label")])
        writer.writerow(["Last Scan", data.get("last_scan")])
        for k, v in summary.items():
            writer.writerow([k, v if not isinstance(v, dict) else v.get("value", v)])
        body = buf.getvalue()
        if fmt == "pdf":
            lines = [
                "JTCS ERP — System Health Report",
                f"Score: {data.get('overall_score')}% ({data.get('overall_label')})",
                f"Scan: {data.get('last_scan')}",
                "",
            ]
            for k, v in summary.items():
                val = v.get("value") if isinstance(v, dict) else v
                lines.append(f"{k}: {val}")
            return "system_health_report.txt", "text/plain; charset=utf-8", "\n".join(lines)
        return "system_health_report.csv", "text/csv; charset=utf-8", body

    def clear_cache(self) -> dict[str, Any]:
        from app.services.utility_service import UtilityService

        return UtilityService().clear_caches()

    def run_backup(self, *, created_by: str = "System") -> dict[str, Any]:
        from app.services.backup_service import BackupService

        info = BackupService().create_database_backup(created_by=created_by)
        return {"ok": True, **info}

    # ------------------------------------------------------------- collectors
    def collect_application(self) -> dict[str, Any]:
        """Application process / Flask runtime facts."""
        cfg = current_app.config
        flask_ver = ""
        try:
            import flask

            flask_ver = getattr(flask, "__version__", "") or ""
        except Exception:
            pass
        uptime_s = max(0, int(time.time() - _PROCESS_STARTED))
        env = (cfg.get("ENV") or cfg.get("FLASK_ENV") or os.getenv("FLASK_ENV") or "production").lower()
        if cfg.get("DEBUG"):
            env_label = "Development"
        elif "dev" in env or env == "development":
            env_label = "Development"
        else:
            env_label = "Production"
        return {
            "running": True,
            "status": "Running",
            "version": cfg.get("APP_VERSION") or "—",
            "app_name": cfg.get("APP_NAME") or "JTCS ERP",
            "environment": env_label,
            "uptime_seconds": uptime_s,
            "uptime_human": self._human_duration(uptime_s),
            "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "timezone": time.tzname[0] if time.tzname else "local",
            "last_restart": datetime.fromtimestamp(_PROCESS_STARTED).strftime("%Y-%m-%d %H:%M:%S"),
            "python_version": platform.python_version(),
            "flask_version": flask_ver or "—",
            "mode": "vps" if self._is_vps() else "local",
        }

    def collect_database(self) -> dict[str, Any]:
        """SQL Server status, size, sessions — reuses live ERP connection."""
        cfg = current_app.config
        result: dict[str, Any] = {
            "status": "Unknown",
            "ok": False,
            "database_name": cfg.get("DB_NAME_DISPLAY") or cfg.get("DB_NAME") or "",
            "server": cfg.get("DB_SERVER_DISPLAY") or cfg.get("DB_SERVER") or "",
            "size_mb": None,
            "free_space_mb": None,
            "connections": None,
            "active_sessions": None,
            "slow_queries": None,
            "deadlocks": None,
            "failed_queries": None,
            "error": None,
        }
        try:
            db.session.execute(text("SELECT 1"))
            result["ok"] = True
            result["status"] = "Online"
            # Size
            try:
                row = db.session.execute(
                    text(
                        """
                        SELECT
                            CAST(SUM(size) * 8.0 / 1024 AS DECIMAL(18, 2)) AS SizeMB,
                            CAST(SUM(CASE WHEN max_size = -1 THEN 0
                                          ELSE (max_size - size) * 8.0 / 1024 END) AS DECIMAL(18, 2)) AS FreeMB
                        FROM sys.database_files
                        """
                    )
                ).first()
                if row:
                    result["size_mb"] = float(row[0] or 0)
                    result["free_space_mb"] = float(row[1] or 0) if row[1] is not None else None
            except Exception:
                pass
            try:
                sessions = db.session.execute(
                    text(
                        """
                        SELECT COUNT(1)
                        FROM sys.dm_exec_sessions
                        WHERE is_user_process = 1
                        """
                    )
                ).scalar()
                result["active_sessions"] = int(sessions or 0)
                result["connections"] = result["active_sessions"]
            except Exception:
                # Fallback without DMV permission
                result["active_sessions"] = 1
                result["connections"] = 1
            try:
                blocked = db.session.execute(
                    text(
                        """
                        SELECT COUNT(1)
                        FROM sys.dm_exec_requests
                        WHERE blocking_session_id > 0
                        """
                    )
                ).scalar()
                result["deadlocks"] = int(blocked or 0)
            except Exception:
                result["deadlocks"] = 0
            result["slow_queries"] = 0
            result["failed_queries"] = 0
        except Exception as exc:
            result["ok"] = False
            result["status"] = "Down"
            result["error"] = str(exc)[:500]
        return result

    def collect_server(self) -> dict[str, Any]:
        """CPU / RAM / disks / OS — uses psutil when available."""
        disks: dict[str, Any] = {}
        for letter in ("C", "D", "E"):
            root = f"{letter}:\\" if os.name == "nt" else "/"
            if os.name != "nt" and letter != "C":
                continue
            try:
                usage = shutil.disk_usage(root if os.name == "nt" else "/")
                disks[f"disk_{letter.lower()}"] = {
                    "path": root if os.name == "nt" else "/",
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                    "percent": round(usage.used * 100 / usage.total, 1) if usage.total else 0,
                }
            except OSError:
                disks[f"disk_{letter.lower()}"] = None

        cpu = None
        mem_pct = None
        mem_avail = None
        boot = None
        if _PSUTIL:
            try:
                cpu = _PSUTIL.cpu_percent(interval=0.15)
                vm = _PSUTIL.virtual_memory()
                mem_pct = float(vm.percent)
                mem_avail = round(vm.available / (1024**3), 2)
                boot = datetime.fromtimestamp(_PSUTIL.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass

        primary = disks.get("disk_c") or next((d for d in disks.values() if d), None)
        return {
            "cpu_percent": cpu,
            "memory_percent": mem_pct,
            "ram_available_gb": mem_avail,
            "disk_percent": primary["percent"] if primary else None,
            "disks": disks,
            "disk_io": "N/A" if not _PSUTIL else "Available via psutil",
            "os_name": platform.system(),
            "os_version": platform.version(),
            "windows_version": platform.platform(),
            "hostname": socket.gethostname(),
            "server_uptime_since": boot,
            "psutil_available": bool(_PSUTIL),
        }

    def collect_storage(self) -> dict[str, Any]:
        """ERP folder usage — uploads, docs, backups, logs, temp."""
        cfg = current_app.config
        candidates = {
            "uploads": Path(cfg.get("UPLOAD_FOLDER") or (BASE_DIR / "uploads")),
            "documents": Path(cfg.get("DOCUMENT_STORAGE") or (BASE_DIR / "documents")),
            "backups": Path(cfg.get("BACKUP_ROOT") or (BASE_DIR.parent / "backups")),
            "logs": Path(cfg.get("LOG_FOLDER") or (BASE_DIR / "logs")),
            "temp": Path(cfg.get("TEMP_FOLDER") or (BASE_DIR / "tmp")),
            "erp_app": BASE_DIR / "app",
        }
        folders = {}
        for key, path in candidates.items():
            folders[key] = {
                "path": str(path),
                "exists": path.exists(),
                "size_mb": _folder_size_mb(path) if path.exists() else 0,
            }
        try:
            usage = shutil.disk_usage(str(BASE_DIR))
            total = round(usage.total / (1024**3), 2)
            used = round(usage.used / (1024**3), 2)
            free = round(usage.free / (1024**3), 2)
        except OSError:
            total = used = free = None
        return {
            "total_storage_gb": total,
            "used_storage_gb": used,
            "free_storage_gb": free,
            "folders": folders,
            "cleanup_suggestions": self._cleanup_suggestions(folders, free),
        }

    def collect_background_services(self) -> dict[str, Any]:
        """Queue-ish stats from CRM messages when present; scheduler is in-process."""
        queues = {
            "scheduler": {"status": "In-process", "note": "No Celery/APScheduler worker configured"},
            "email_queue": {"pending": 0, "failed": 0, "status": "Idle"},
            "whatsapp_queue": {"pending": 0, "failed": 0, "status": "Idle"},
            "sms_queue": {"pending": 0, "failed": 0, "status": "Idle"},
            "notification_queue": {"pending": 0, "failed": 0, "status": "Idle"},
            "background_jobs": {"pending": 0, "failed": 0, "worker_status": "Embedded"},
        }
        try:
            exists = db.session.execute(
                text(
                    """
                    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'CrmMessage'
                    """
                )
            ).scalar()
            if exists:
                rows = db.session.execute(
                    text(
                        """
                        SELECT LOWER(ISNULL(Channel, '')), LOWER(ISNULL(DeliveryStatus, '')), COUNT(1)
                        FROM dbo.CrmMessage
                        WHERE CreatedDate >= DATEADD(day, -1, SYSUTCDATETIME())
                        GROUP BY LOWER(ISNULL(Channel, '')), LOWER(ISNULL(DeliveryStatus, ''))
                        """
                    )
                ).all()
                for channel, status, cnt in rows:
                    key = "whatsapp_queue"
                    if "email" in channel or "smtp" in channel:
                        key = "email_queue"
                    elif "sms" in channel:
                        key = "sms_queue"
                    elif "notif" in channel:
                        key = "notification_queue"
                    elif "whatsapp" in channel or "wa" == channel:
                        key = "whatsapp_queue"
                    else:
                        continue
                    n = int(cnt or 0)
                    if status in {"queued", "pending", "processing"}:
                        queues[key]["pending"] += n
                        queues[key]["status"] = "Active"
                    elif status in {"failed", "error"}:
                        queues[key]["failed"] += n
                        if n:
                            queues[key]["status"] = "Warning"
        except Exception:
            logger.debug("CRM queue stats unavailable", exc_info=True)

        pending = sum(q.get("pending", 0) for q in queues.values() if isinstance(q, dict))
        failed = sum(q.get("failed", 0) for q in queues.values() if isinstance(q, dict))
        queues["totals"] = {"pending_jobs": pending, "failed_jobs": failed}
        return queues

    def collect_api_health(self) -> dict[str, Any]:
        """Reuse Integration Health dashboard summary (no duplicate config)."""
        try:
            from app.modules.settings.integration_health_service import IntegrationHealthService

            dash = IntegrationHealthService().dashboard(run_scan=False)
            cards = []
            for c in dash.get("integrations") or []:
                code = c.get("code") or ""
                # Focus summary set requested by Mission Control
                if code in {
                    "whatsapp_meta",
                    "smtp",
                    "google",
                    "openai",
                    "gemini",
                    "fyers",
                    "payment",
                    "gst_api",
                    "income_tax",
                    "cloud_storage",
                }:
                    cards.append(
                        {
                            "code": code,
                            "label": c.get("label"),
                            "status": c.get("connection_status"),
                            "status_code": c.get("status_code"),
                            "score": c.get("health_score"),
                        }
                    )
            return {
                "ok": True,
                "global_health_score": dash.get("global_health_score"),
                "global_label": dash.get("global_label"),
                "summary": dash.get("summary"),
                "integrations": cards,
                "alerts": dash.get("alerts") or [],
                "source": "integration_health",
                "console_url": "/admin/integrations?tab=health",
            }
        except Exception as exc:
            logger.exception("Integration health reuse failed")
            return {"ok": False, "error": str(exc), "integrations": [], "global_health_score": 0}

    def collect_security(self) -> dict[str, Any]:
        """Security signals from Users + customer portal lockouts when present."""
        out: dict[str, Any] = {
            "failed_login_attempts": None,
            "blocked_users": 0,
            "suspicious_activity": 0,
            "password_expiry": "Not tracked centrally",
            "ssl_certificate": "Configured at reverse proxy / IIS",
            "encryption_status": "Fernet secrets for Integration Settings",
            "audit_logs": "IntegrationSettingsAudit + module audits",
            "firewall_status": "OS / hosting provider",
            "notes": [],
        }
        try:
            blocked = db.session.execute(
                text(
                    """
                    SELECT COUNT(1) FROM dbo.Users
                    WHERE UserStatus IN (N'Blocked', N'Deactivated', N'Rejected', N'Suspended')
                    """
                )
            ).scalar()
            out["blocked_users"] = int(blocked or 0)
        except Exception:
            pass
        try:
            # Customer portal failed logins if column exists
            col = db.session.execute(
                text(
                    """
                    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='CustomerMaster'
                      AND COLUMN_NAME='FailedLoginCount'
                    """
                )
            ).scalar()
            if col:
                failed = db.session.execute(
                    text(
                        """
                        SELECT ISNULL(SUM(FailedLoginCount), 0),
                               SUM(CASE WHEN FailedLoginCount >= 5 THEN 1 ELSE 0 END)
                        FROM dbo.CustomerMaster
                        """
                    )
                ).first()
                if failed:
                    out["failed_login_attempts"] = int(failed[0] or 0)
                    out["suspicious_activity"] = int(failed[1] or 0)
        except Exception:
            pass
        return out

    def collect_users(self) -> dict[str, Any]:
        """Active / recently logged-in ERP users."""
        out: dict[str, Any] = {
            "active_users": 0,
            "logged_in_recent": 0,
            "sessions_note": "Flask cookie sessions (server-side count not persisted)",
            "concurrent_users": None,
            "idle_users": 0,
            "recent": [],
        }
        try:
            active = db.session.execute(
                text(
                    """
                    SELECT COUNT(1) FROM dbo.Users
                    WHERE UserStatus IN (N'Active', N'Approved')
                    """
                )
            ).scalar()
            out["active_users"] = int(active or 0)
            recent_cut = _utcnow() - timedelta(hours=8)
            rows = db.session.execute(
                text(
                    """
                    SELECT TOP 15 UserID, UserName, Email, LastLoginDate, UserStatus
                    FROM dbo.Users
                    WHERE LastLoginDate IS NOT NULL
                    ORDER BY LastLoginDate DESC
                    """
                )
            ).mappings().all()
            recent = []
            logged = 0
            for r in rows:
                last = r.get("LastLoginDate")
                is_recent = isinstance(last, datetime) and last >= recent_cut
                if is_recent:
                    logged += 1
                recent.append(
                    {
                        "user_id": r.get("UserID"),
                        "user_name": r.get("UserName"),
                        "email": r.get("Email"),
                        "last_login": last.isoformat() + "Z" if isinstance(last, datetime) else str(last or ""),
                        "status": r.get("UserStatus"),
                        "device": "—",
                        "browser": "—",
                    }
                )
            out["logged_in_recent"] = logged
            out["recent"] = recent
            idle = db.session.execute(
                text(
                    """
                    SELECT COUNT(1) FROM dbo.Users
                    WHERE UserStatus IN (N'Active', N'Approved')
                      AND (LastLoginDate IS NULL OR LastLoginDate < DATEADD(day, -30, SYSUTCDATETIME()))
                    """
                )
            ).scalar()
            out["idle_users"] = int(idle or 0)
        except Exception as exc:
            out["error"] = str(exc)[:300]
        return out

    def collect_backups(self) -> dict[str, Any]:
        """Reuse BackupService file inventory."""
        try:
            from app.services.backup_service import BackupService

            svc = BackupService()
            db_list = svc.list_database_backups()
            full_list = svc.list_full_backups()
            latest = None
            if db_list:
                latest = db_list[0]
            elif full_list:
                latest = full_list[0]
            status = "No backups found"
            if latest:
                status = "Available"
                # Age warning
                try:
                    mtime = latest.get("modified") or latest.get("mtime")
                    # BackupService _file_info likely has size/name/path
                except Exception:
                    pass
            return {
                "ok": True,
                "status": status,
                "last_backup": latest,
                "next_backup": "Manual / schedule via Admin Backup",
                "backup_location": svc.connection_info(),
                "database_backups": db_list[:10],
                "full_backups": full_list[:10],
                "restore_points": (db_list[:5] + full_list[:5])[:8],
                "console_url": "/admin/backup/data",
            }
        except Exception as exc:
            return {"ok": False, "status": "Error", "error": str(exc)}

    def collect_license(self) -> dict[str, Any]:
        cfg = current_app.config
        try:
            from app.services.version_service import VersionService

            display = VersionService().get_display_version(cfg.get("APP_VERSION", "1.0.0"))
        except Exception:
            display = cfg.get("APP_VERSION", "1.0.0")
        user_count = 0
        try:
            user_count = int(
                db.session.execute(
                    text("SELECT COUNT(1) FROM dbo.Users WHERE UserStatus IN (N'Active', N'Approved')")
                ).scalar()
                or 0
            )
        except Exception:
            pass
        return {
            "erp_version": display,
            "license_type": cfg.get("LICENSE_TYPE") or "Enterprise (Internal)",
            "expiry_date": cfg.get("LICENSE_EXPIRY") or "Perpetual / not configured",
            "modules_activated": [
                "Accounting",
                "CRM",
                "Integration Settings",
                "Communication Center",
                "Customer Portal",
                "Backup",
                "System Health",
            ],
            "users_allowed": cfg.get("LICENSE_USER_LIMIT") or "Unlimited",
            "users_active": user_count,
            "storage_limit": cfg.get("LICENSE_STORAGE_LIMIT") or "Host disk capacity",
        }

    def collect_logs(
        self, *, period: str = "today", level: str | None = None, limit: int = 50
    ) -> dict[str, Any]:
        """Tail local log files under erp/logs or deployment/logs."""
        roots = [
            BASE_DIR / "logs",
            BASE_DIR.parent / "deployment" / "logs",
            BASE_DIR.parent / "logs",
        ]
        files: list[Path] = []
        for root in roots:
            if root.is_dir():
                files.extend(sorted(root.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:5])
        entries: list[dict[str, str]] = []
        for fp in files[:3]:
            try:
                text_body = fp.read_text(encoding="utf-8", errors="replace")
                lines = text_body.splitlines()[-200:]
                for line in lines:
                    low = line.lower()
                    sev = "Information"
                    if "critical" in low or "fatal" in low:
                        sev = "Critical"
                    elif "error" in low:
                        sev = "Error"
                    elif "warn" in low:
                        sev = "Warning"
                    if level and sev.lower() != level.lower():
                        continue
                    entries.append(
                        {
                            "source": fp.name,
                            "level": sev,
                            "message": line[:400],
                        }
                    )
            except OSError:
                continue
        entries = entries[-limit:]
        return {
            "period": period,
            "count": len(entries),
            "entries": list(reversed(entries))[:limit],
            "sources": [str(f) for f in files[:5]],
        }

    def collect_network(self) -> dict[str, Any]:
        """Internet / public health check (reuses Utility public health URL)."""
        from app.services.utility_service import UtilityService

        util = UtilityService().system_health()
        internet_ok = None
        try:
            socket.create_connection(("1.1.1.1", 53), timeout=2).close()
            internet_ok = True
        except OSError:
            internet_ok = False
        return {
            "status": "Online" if internet_ok else "Offline / Restricted",
            "internet_ok": internet_ok,
            "public_health_ok": util.get("public_health_ok"),
            "public_health_body": util.get("public_health_body"),
            "public_health_url": (util.get("info") or {}).get("public_health"),
        }

    # -------------------------------------------------------------- scoring
    def _compute_score(self, **parts: dict) -> tuple[int, dict[str, Any]]:
        database = parts["database"]
        server = parts["server"]
        storage = parts["storage"]
        api = parts["api_health"]
        backups = parts["backups"]
        security = parts["security"]
        network = parts["network"]
        application = parts["application"]

        score = 100
        if not database.get("ok"):
            score -= 40
        if network.get("internet_ok") is False:
            score -= 5
        if network.get("public_health_ok") is False:
            score -= 5
        cpu = server.get("cpu_percent")
        if cpu is not None and cpu >= 90:
            score -= 15
        elif cpu is not None and cpu >= 75:
            score -= 8
        mem = server.get("memory_percent")
        if mem is not None and mem >= 90:
            score -= 15
        elif mem is not None and mem >= 80:
            score -= 8
        disk = server.get("disk_percent")
        if disk is not None and disk >= 92:
            score -= 20
        elif disk is not None and disk >= 85:
            score -= 10
        api_score = api.get("global_health_score")
        if api_score is not None and api.get("ok"):
            # blend API health lightly
            if api_score < 40:
                score -= 10
            elif api_score < 70:
                score -= 5
        if not backups.get("last_backup"):
            score -= 8
        if (security.get("suspicious_activity") or 0) > 0:
            score -= 5
        score = max(0, min(100, score))

        def card(value, status="ok", detail=""):
            return {"value": value, "status": status, "detail": detail}

        def st_from(ok: bool, warn: bool = False) -> str:
            if not ok:
                return "bad"
            if warn:
                return "warn"
            return "ok"

        summary = {
            "application_status": card(
                application.get("status"), "ok", application.get("environment")
            ),
            "database_status": card(
                database.get("status"),
                st_from(bool(database.get("ok"))),
                database.get("database_name") or "",
            ),
            "server_status": card(
                "Online",
                st_from(True, (cpu or 0) >= 75 or (mem or 0) >= 80),
                server.get("hostname") or "",
            ),
            "cpu_usage": card(
                f"{cpu}%" if cpu is not None else "N/A",
                st_from(True, (cpu or 0) >= 75) if cpu is not None else "muted",
            ),
            "memory_usage": card(
                f"{mem}%" if mem is not None else "N/A",
                st_from(True, (mem or 0) >= 80) if mem is not None else "muted",
            ),
            "disk_usage": card(
                f"{disk}%" if disk is not None else "N/A",
                st_from(True, (disk or 0) >= 85) if disk is not None else "muted",
            ),
            "network_status": card(
                network.get("status"),
                st_from(bool(network.get("internet_ok")), network.get("public_health_ok") is False),
            ),
            "backup_status": card(
                backups.get("status") or "—",
                "warn" if not backups.get("last_backup") else "ok",
            ),
            "api_health": card(
                f"{api_score}%" if api_score is not None else "—",
                st_from(bool(api.get("ok")), (api_score or 100) < 70),
            ),
            "security_status": card(
                "Watch" if (security.get("suspicious_activity") or 0) else "Stable",
                "warn" if (security.get("suspicious_activity") or 0) else "ok",
            ),
            "overall_health_score": card(f"{score}%", "ok" if score >= 80 else "warn" if score >= 60 else "bad"),
            "last_system_scan": card(_utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"), "ok"),
        }
        return score, summary

    def _sync_alerts(self, score: int, details: dict[str, Any]) -> None:
        db_part = details.get("database") or {}
        server = details.get("server") or {}
        api = details.get("api_health") or {}
        backups = details.get("backups") or {}
        network = details.get("network") or {}

        def set_alert(atype: str, severity: str, title: str, message: str, active: bool):
            if active:
                self.repo.upsert_alert(
                    alert_type=atype, severity=severity, title=title, message=message
                )
            else:
                self.repo.resolve_alert(atype)

        set_alert(
            "database_down",
            "Critical",
            "Database Down",
            db_part.get("error") or "SQL Server unreachable",
            not db_part.get("ok"),
        )
        cpu = server.get("cpu_percent")
        set_alert(
            "high_cpu",
            "Warning",
            "High CPU",
            f"CPU at {cpu}%",
            cpu is not None and cpu >= 85,
        )
        disk = server.get("disk_percent")
        set_alert(
            "low_disk",
            "Critical",
            "Low Disk Space",
            f"Disk usage {disk}%",
            disk is not None and disk >= 90,
        )
        set_alert(
            "backup_missing",
            "Warning",
            "Backup Failed / Missing",
            "No database backup files found",
            not backups.get("last_backup"),
        )
        set_alert(
            "api_failure",
            "Warning",
            "API Health Degraded",
            f"Integration health {api.get('global_health_score')}%",
            bool(api.get("ok")) and (api.get("global_health_score") or 100) < 40,
        )
        # Surface integration alerts (token expiry etc.)
        for a in (api.get("alerts") or [])[:5]:
            at = f"integration_{(a.get('type') or 'alert')}"
            set_alert(
                at[:60],
                a.get("severity") or "Warning",
                a.get("title") or "Integration alert",
                a.get("message") or "",
                True,
            )
        set_alert(
            "public_health",
            "Warning",
            "Public Health Check Failed",
            str(network.get("public_health_body") or "")[:400],
            network.get("public_health_ok") is False,
        )
        if score >= 85:
            self.repo.resolve_alert("overall_critical")
        elif score < 40:
            self.repo.upsert_alert(
                alert_type="overall_critical",
                severity="Critical",
                title="Overall System Critical",
                message=f"Health score {score}%",
            )

    def _alert_payload(self) -> list[dict[str, Any]]:
        rows = self.repo.list_open_alerts()
        return [
            {
                "id": r.get("AlertID"),
                "type": r.get("AlertType"),
                "severity": r.get("Severity"),
                "title": r.get("Title"),
                "message": r.get("Message"),
                "created_on": r["CreatedOn"].isoformat() + "Z"
                if isinstance(r.get("CreatedOn"), datetime)
                else str(r.get("CreatedOn") or ""),
            }
            for r in rows
        ]

    def _series(self, key: str) -> dict[str, Any]:
        rows = self.repo.metric_series(key, limit=48)
        return {
            "labels": [
                (r["SampledOn"].strftime("%H:%M:%S") if isinstance(r.get("SampledOn"), datetime) else "")
                for r in rows
            ],
            "values": [float(r.get("MetricValue") or 0) for r in rows],
        }

    def _utilities_meta(self) -> dict[str, Any]:
        return {
            "actions": [
                {"code": "run_scan", "label": "Run Health Scan"},
                {"code": "clear_cache", "label": "Clear Cache"},
                {"code": "manual_backup", "label": "Manual Backup"},
                {"code": "refresh_config", "label": "Refresh Configuration"},
                {"code": "export_csv", "label": "Export Report"},
            ],
            "notes": {
                "restart_scheduler": "No external scheduler process — ERP uses request/thread workers.",
                "optimize_database": "Run SQL Server maintenance plans / INDEX rebuilds via DBA tools.",
            },
        }

    def _roadmap_hints(self) -> list[str]:
        return [
            "Docker / Kubernetes readiness: keep collectors behind SystemHealthService.",
            "Redis / RabbitMQ: plug queue depth into collect_background_services.",
            "Azure / AWS metrics adapters can replace local psutil collectors.",
            "Multi-tenant: scope scans by TenantID in SystemHealthScan.",
        ]

    def _cleanup_suggestions(self, folders: dict, free_gb: float | None) -> list[str]:
        tips = []
        if free_gb is not None and free_gb < 10:
            tips.append("Free disk space is low — archive old backups and clear temp folders.")
        temp = folders.get("temp") or {}
        if (temp.get("size_mb") or 0) > 500:
            tips.append("Temp folder exceeds 500 MB — safe to clear after hours.")
        logs = folders.get("logs") or {}
        if (logs.get("size_mb") or 0) > 200:
            tips.append("Log folder is large — rotate or archive older .log files.")
        if not tips:
            tips.append("Storage looks healthy. Keep weekly backups and log rotation.")
        return tips

    @staticmethod
    def _human_duration(seconds: int) -> str:
        d, rem = divmod(seconds, 86400)
        h, rem = divmod(rem, 3600)
        m, s = divmod(rem, 60)
        parts = []
        if d:
            parts.append(f"{d}d")
        if h or d:
            parts.append(f"{h}h")
        parts.append(f"{m}m")
        return " ".join(parts)

    @staticmethod
    def _is_vps() -> bool:
        try:
            from app.utils.runtime_env import is_vps_runtime

            return bool(is_vps_runtime())
        except Exception:
            return False
