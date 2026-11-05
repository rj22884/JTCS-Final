"""System Maintenance / Storage Cleanup — safe scan + selectable cleanup + audit."""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from flask import current_app
from sqlalchemy import text

from app.config import BASE_DIR
from app.extensions import db

# Categories users may select. Never includes backups/uploads/DB/source/.env.
CLEANUP_CATEGORIES: dict[str, dict[str, str]] = {
    "python_cache": {
        "label": "Python cache (__pycache__, *.pyc)",
        "description": "Bytecode and tool caches under the ERP folder only.",
    },
    "temp_files": {
        "label": "Application temp folder",
        "description": "Files inside the configured ERP temp/tmp folder only.",
    },
    "old_logs": {
        "label": "Old log files (30+ days)",
        "description": ".log files older than 30 days inside the ERP logs folder only.",
    },
}

PROTECTED_DIR_NAMES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        ".env",
        "backups",
        "uploads",
        "documents",
        "database",
        "docker",
        "var",  # often holds volumes / persistent data
    }
)

CACHE_DIR_NAMES = frozenset(
    {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".webassets-cache"}
)

OLD_LOG_DAYS = 30


class SystemMaintenanceService:
    def ensure_schema(self) -> None:
        db.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.SystemMaintenanceAudit', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.SystemMaintenanceAudit (
                        AuditID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                        ActionType NVARCHAR(40) NOT NULL,
                        Categories NVARCHAR(200) NULL,
                        DryRun BIT NOT NULL CONSTRAINT DF_SysMaint_DryRun DEFAULT (0),
                        BytesFreed BIGINT NOT NULL CONSTRAINT DF_SysMaint_Bytes DEFAULT (0),
                        ItemsRemoved INT NOT NULL CONSTRAINT DF_SysMaint_Items DEFAULT (0),
                        Details NVARCHAR(MAX) NULL,
                        Actor NVARCHAR(120) NULL,
                        CreatedAt DATETIME2 NOT NULL CONSTRAINT DF_SysMaint_Created DEFAULT (SYSUTCDATETIME())
                    );
                    CREATE INDEX IX_SystemMaintenanceAudit_Created
                        ON dbo.SystemMaintenanceAudit (CreatedAt DESC);
                END
                """
            )
        )
        db.session.commit()

    def _cfg_path(self, key: str, default: Path) -> Path:
        raw = current_app.config.get(key)
        try:
            return Path(raw) if raw else default
        except TypeError:
            return default

    def protected_roots(self) -> list[Path]:
        cfg = current_app.config
        roots = [
            self._cfg_path("BACKUP_ROOT", BASE_DIR / "backups"),
            self._cfg_path("BACKUP_DATABASE_DIR", BASE_DIR / "backups" / "database"),
            self._cfg_path("BACKUP_FULL_DIR", BASE_DIR / "backups" / "full"),
            self._cfg_path("UPLOAD_FOLDER", BASE_DIR / "app" / "static" / "uploads"),
            self._cfg_path("CRM_DOCUMENT_FOLDER", BASE_DIR / "app" / "static" / "uploads" / "crm_documents"),
            self._cfg_path("DOCUMENT_STORAGE", BASE_DIR / "documents"),
            BASE_DIR / ".env",
            BASE_DIR / ".git",
            BASE_DIR / ".venv",
            BASE_DIR / "venv",
            BASE_DIR / "database",
            BASE_DIR / "app",  # source — only caches under app may be cleared
        ]
        sql_dir = cfg.get("SQL_SERVER_BACKUP_DIR")
        if sql_dir:
            roots.append(Path(sql_dir))
        rec = cfg.get("RECRUITMENT_UPLOAD_DIR")
        if rec:
            roots.append(Path(rec))
        return [p.resolve() for p in roots if p]

    def temp_dir(self) -> Path:
        return self._cfg_path("TEMP_FOLDER", BASE_DIR / "tmp").resolve()

    def logs_dir(self) -> Path:
        return self._cfg_path("LOG_FOLDER", BASE_DIR / "logs").resolve()

    def disk_summary(self) -> dict[str, Any]:
        try:
            usage = shutil.disk_usage(str(BASE_DIR))
            total = usage.total
            used = usage.used
            free = usage.free
        except OSError:
            return {
                "ok": False,
                "error": "Unable to read disk usage.",
                "path": str(BASE_DIR),
            }
        return {
            "ok": True,
            "path": str(BASE_DIR.resolve()),
            "total_bytes": total,
            "used_bytes": used,
            "free_bytes": free,
            "total_label": self._fmt_bytes(total),
            "used_label": self._fmt_bytes(used),
            "free_label": self._fmt_bytes(free),
            "used_percent": round((used / total) * 100, 1) if total else 0,
        }

    def folder_overview(self) -> list[dict[str, Any]]:
        rows = [
            ("ERP root", BASE_DIR, True),
            ("Backups (protected)", self._cfg_path("BACKUP_ROOT", BASE_DIR / "backups"), True),
            ("Uploads (protected)", self._cfg_path("UPLOAD_FOLDER", BASE_DIR / "app" / "static" / "uploads"), True),
            ("Documents (protected)", self._cfg_path("DOCUMENT_STORAGE", BASE_DIR / "documents"), True),
            ("Logs (cleanup eligible)", self.logs_dir(), False),
            ("Temp (cleanup eligible)", self.temp_dir(), False),
            ("App source (protected; caches only)", BASE_DIR / "app", True),
        ]
        out = []
        for label, path, protected in rows:
            exists = path.exists()
            size = self._folder_size(path) if exists and path.is_dir() else (path.stat().st_size if exists and path.is_file() else 0)
            out.append(
                {
                    "label": label,
                    "path": str(path),
                    "exists": exists,
                    "protected": protected,
                    "size_bytes": size,
                    "size_label": self._fmt_bytes(size),
                }
            )
        return out

    def scan(self, categories: list[str] | None = None) -> dict[str, Any]:
        selected = self._normalize_categories(categories)
        category_results = []
        total_bytes = 0
        total_items = 0
        for key in selected:
            result = self._scan_category(key)
            category_results.append(result)
            total_bytes += int(result.get("bytes") or 0)
            total_items += int(result.get("items") or 0)
        return {
            "ok": True,
            "scanned_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "disk": self.disk_summary(),
            "folders": self.folder_overview(),
            "categories": category_results,
            "catalog": [
                {"key": k, "label": v["label"], "description": v["description"]}
                for k, v in CLEANUP_CATEGORIES.items()
            ],
            "totals": {
                "bytes": total_bytes,
                "bytes_label": self._fmt_bytes(total_bytes),
                "items": total_items,
            },
            "protections": [
                "Database / SQL Server files",
                "Backup folders (.bak / full ZIP)",
                "Uploads and documents",
                ".env and secrets",
                "Docker / volume directories",
                "Application source (.py) and virtualenvs",
            ],
        }

    def cleanup(
        self,
        categories: list[str] | None = None,
        *,
        dry_run: bool = True,
        actor: str = "System",
    ) -> dict[str, Any]:
        selected = self._normalize_categories(categories)
        if not selected:
            raise ValueError("Select at least one cleanup category.")

        details: list[dict[str, Any]] = []
        freed = 0
        removed = 0
        for key in selected:
            part = self._cleanup_category(key, dry_run=dry_run)
            details.append(part)
            freed += int(part.get("bytes") or 0)
            removed += int(part.get("items") or 0)

        action = "scan" if dry_run else "cleanup"
        self._write_audit(
            action_type=action,
            categories=",".join(selected),
            dry_run=dry_run,
            bytes_freed=freed,
            items_removed=removed,
            details=details,
            actor=actor,
        )
        return {
            "ok": True,
            "dry_run": dry_run,
            "categories": details,
            "bytes_freed": freed,
            "bytes_freed_label": self._fmt_bytes(freed),
            "items_removed": removed,
            "message": (
                f"Dry run: {removed} item(s) / {self._fmt_bytes(freed)} would be cleared."
                if dry_run
                else f"Cleanup complete: removed {removed} item(s), freed {self._fmt_bytes(freed)}."
            ),
        }

    def recent_audit(self, *, limit: int = 20) -> list[dict[str, Any]]:
        self.ensure_schema()
        lim = max(1, min(int(limit or 20), 100))
        rows = db.session.execute(
            text(
                f"""
                SELECT TOP ({lim})
                    AuditID, ActionType, Categories, DryRun, BytesFreed, ItemsRemoved,
                    Details, Actor, CreatedAt
                FROM dbo.SystemMaintenanceAudit
                ORDER BY CreatedAt DESC, AuditID DESC
                """
            )
        ).mappings().all()
        out = []
        for row in rows:
            out.append(
                {
                    "audit_id": int(row["AuditID"]),
                    "action_type": row["ActionType"],
                    "categories": row["Categories"] or "",
                    "dry_run": bool(row["DryRun"]),
                    "bytes_freed": int(row["BytesFreed"] or 0),
                    "bytes_freed_label": self._fmt_bytes(int(row["BytesFreed"] or 0)),
                    "items_removed": int(row["ItemsRemoved"] or 0),
                    "actor": row["Actor"] or "",
                    "created_at": row["CreatedAt"].isoformat(timespec="seconds")
                    if row["CreatedAt"]
                    else "",
                }
            )
        return out

    def _normalize_categories(self, categories: list[str] | None) -> list[str]:
        if not categories:
            return list(CLEANUP_CATEGORIES.keys())
        out = []
        for raw in categories:
            key = (raw or "").strip().lower()
            if key in CLEANUP_CATEGORIES and key not in out:
                out.append(key)
        return out

    def _scan_category(self, key: str) -> dict[str, Any]:
        return self._cleanup_category(key, dry_run=True)

    def _cleanup_category(self, key: str, *, dry_run: bool) -> dict[str, Any]:
        meta = CLEANUP_CATEGORIES[key]
        if key == "python_cache":
            return self._cleanup_python_cache(dry_run=dry_run, meta=meta)
        if key == "temp_files":
            return self._cleanup_temp(dry_run=dry_run, meta=meta)
        if key == "old_logs":
            return self._cleanup_old_logs(dry_run=dry_run, meta=meta)
        raise ValueError(f"Unknown cleanup category: {key}")

    def _cleanup_python_cache(self, *, dry_run: bool, meta: dict[str, str]) -> dict[str, Any]:
        bytes_total = 0
        items = 0
        samples: list[str] = []
        skip = set(PROTECTED_DIR_NAMES) | {"backups"}
        for root, dirs, files in os.walk(BASE_DIR):
            root_path = Path(root)
            # Never walk into protected directory names.
            dirs[:] = [d for d in dirs if d not in skip]
            # Drop cache dirs
            for d in list(dirs):
                if d not in CACHE_DIR_NAMES:
                    continue
                path = root_path / d
                if not self._is_safe_cleanup_target(path):
                    continue
                size = self._folder_size(path)
                bytes_total += size
                items += 1
                if len(samples) < 8:
                    samples.append(str(path))
                if not dry_run:
                    shutil.rmtree(path, ignore_errors=True)
                dirs.remove(d)
            for name in files:
                if not name.endswith((".pyc", ".pyo")):
                    continue
                path = root_path / name
                if not self._is_safe_cleanup_target(path):
                    continue
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                bytes_total += size
                items += 1
                if len(samples) < 8:
                    samples.append(str(path))
                if not dry_run:
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        pass
        return {
            "key": "python_cache",
            "label": meta["label"],
            "bytes": bytes_total,
            "bytes_label": self._fmt_bytes(bytes_total),
            "items": items,
            "samples": samples,
            "dry_run": dry_run,
        }

    def _cleanup_temp(self, *, dry_run: bool, meta: dict[str, str]) -> dict[str, Any]:
        temp = self.temp_dir()
        bytes_total = 0
        items = 0
        samples: list[str] = []
        if not temp.exists() or not temp.is_dir():
            return {
                "key": "temp_files",
                "label": meta["label"],
                "bytes": 0,
                "bytes_label": self._fmt_bytes(0),
                "items": 0,
                "samples": [],
                "dry_run": dry_run,
                "note": "Temp folder not found.",
            }
        if not self._is_under(temp, BASE_DIR.resolve()) and not self._is_configured_temp(temp):
            raise ValueError("Temp folder is outside the allowed cleanup roots.")

        for path in sorted(temp.rglob("*"), reverse=True):
            if not self._is_safe_cleanup_target(path):
                continue
            if path.is_dir():
                # Remove empty dirs after files; skip non-empty until emptied.
                try:
                    if any(path.iterdir()):
                        continue
                except OSError:
                    continue
                items += 1
                if len(samples) < 8:
                    samples.append(str(path))
                if not dry_run:
                    shutil.rmtree(path, ignore_errors=True)
                continue
            if not path.is_file():
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            bytes_total += size
            items += 1
            if len(samples) < 8:
                samples.append(str(path))
            if not dry_run:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
        return {
            "key": "temp_files",
            "label": meta["label"],
            "bytes": bytes_total,
            "bytes_label": self._fmt_bytes(bytes_total),
            "items": items,
            "samples": samples,
            "dry_run": dry_run,
        }

    def _cleanup_old_logs(self, *, dry_run: bool, meta: dict[str, str]) -> dict[str, Any]:
        logs = self.logs_dir()
        bytes_total = 0
        items = 0
        samples: list[str] = []
        if not logs.exists() or not logs.is_dir():
            return {
                "key": "old_logs",
                "label": meta["label"],
                "bytes": 0,
                "bytes_label": self._fmt_bytes(0),
                "items": 0,
                "samples": [],
                "dry_run": dry_run,
                "note": "Logs folder not found.",
            }
        if not self._is_under(logs, BASE_DIR.resolve()) and not self._is_configured_logs(logs):
            raise ValueError("Logs folder is outside the allowed cleanup roots.")

        cutoff = datetime.now() - timedelta(days=OLD_LOG_DAYS)
        for path in logs.rglob("*.log"):
            if not path.is_file():
                continue
            if not self._is_safe_cleanup_target(path):
                continue
            try:
                stat = path.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime)
                if mtime > cutoff:
                    continue
                size = stat.st_size
            except OSError:
                continue
            bytes_total += size
            items += 1
            if len(samples) < 8:
                samples.append(str(path))
            if not dry_run:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
        return {
            "key": "old_logs",
            "label": meta["label"],
            "bytes": bytes_total,
            "bytes_label": self._fmt_bytes(bytes_total),
            "items": items,
            "samples": samples,
            "dry_run": dry_run,
            "note": f"Only .log files older than {OLD_LOG_DAYS} days.",
        }

    def _is_configured_temp(self, path: Path) -> bool:
        try:
            return path.resolve() == self.temp_dir()
        except OSError:
            return False

    def _is_configured_logs(self, path: Path) -> bool:
        try:
            return path.resolve() == self.logs_dir()
        except OSError:
            return False

    def _is_safe_cleanup_target(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
        except OSError:
            return False
        name = resolved.name.lower()
        if name in {".env", ".git", "docker-compose.yml", "dockerfile"}:
            return False
        if resolved.suffix.lower() in {".bak", ".env"}:
            return False
        # Block anything under protected roots except cache dirs under app/
        for root in self.protected_roots():
            if root.is_file() and resolved == root:
                return False
            if root.is_dir() and self._is_under(resolved, root):
                # Allow only cache folders / .pyc under app/
                if root == (BASE_DIR / "app").resolve():
                    if any(part in CACHE_DIR_NAMES for part in resolved.parts):
                        return True
                    if resolved.suffix.lower() in {".pyc", ".pyo"}:
                        return True
                    return False
                return False
        # Must stay under BASE_DIR for python_cache walk results
        if not self._is_under(resolved, BASE_DIR.resolve()):
            # Allow exact configured temp/logs roots only
            if self._is_configured_temp(resolved) or self._is_under(resolved, self.temp_dir()):
                return True
            if self._is_configured_logs(resolved) or self._is_under(resolved, self.logs_dir()):
                return True
            return False
        # Block protected directory name anywhere in path
        for part in resolved.parts:
            if part in PROTECTED_DIR_NAMES and part not in {"app"}:
                # allow walking past 'app' — already handled
                if part == "app":
                    continue
                # tmp/logs are eligible
                if part in {"tmp", "temp", "logs"}:
                    continue
                return False
        return True

    def _write_audit(
        self,
        *,
        action_type: str,
        categories: str,
        dry_run: bool,
        bytes_freed: int,
        items_removed: int,
        details: list[dict[str, Any]],
        actor: str,
    ) -> None:
        self.ensure_schema()
        import json

        db.session.execute(
            text(
                """
                INSERT INTO dbo.SystemMaintenanceAudit (
                    ActionType, Categories, DryRun, BytesFreed, ItemsRemoved,
                    Details, Actor, CreatedAt
                )
                VALUES (
                    :action_type, :categories, :dry_run, :bytes_freed, :items_removed,
                    :details, :actor, SYSUTCDATETIME()
                )
                """
            ),
            {
                "action_type": action_type[:40],
                "categories": (categories or "")[:200],
                "dry_run": 1 if dry_run else 0,
                "bytes_freed": int(bytes_freed),
                "items_removed": int(items_removed),
                "details": json.dumps(details, default=str)[:8000],
                "actor": (actor or "System")[:120],
            },
        )
        db.session.commit()

    @staticmethod
    def _is_under(path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except (ValueError, OSError):
            return False

    @staticmethod
    def _folder_size(path: Path) -> int:
        total = 0
        try:
            if path.is_file():
                return path.stat().st_size
            for p in path.rglob("*"):
                if p.is_file():
                    try:
                        total += p.stat().st_size
                    except OSError:
                        pass
        except OSError:
            return 0
        return total

    @staticmethod
    def _fmt_bytes(num: int) -> str:
        value = float(num or 0)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                if unit == "B":
                    return f"{int(value)} {unit}"
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{num} B"
