from __future__ import annotations

import os
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

import pyodbc
from flask import current_app

from app.config import BASE_DIR

SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class BackupService:
    """Admin Role backups: SQL Server database (.bak) and full application zip."""

    FULL_INCLUDE_FILES = (
        "requirements.txt",
        "requirements-dev.txt",
        "run.py",
        "wsgi.py",
        ".env.example",
        "README.md",
    )
    FULL_EXCLUDE_DIR_NAMES = {
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "backups",
        ".pytest_cache",
        ".mypy_cache",
        ".cursor",
    }
    FULL_EXCLUDE_FILE_SUFFIXES = {".pyc", ".pyo", ".bak", ".zip"}

    def __init__(self):
        cfg = current_app.config
        self.db_name = str(cfg.get("DB_NAME") or "JTCSS")
        self.db_server = str(cfg.get("DB_SERVER") or r"JTCS\JTCS")
        self.db_driver = str(cfg.get("DB_DRIVER") or "ODBC Driver 17 for SQL Server")
        self.db_trusted = bool(cfg.get("DB_TRUSTED_CONNECTION", True))
        self.db_user = str(cfg.get("DB_USER") or "")
        self.db_password = str(cfg.get("DB_PASSWORD") or "")
        self.database_dir = Path(cfg.get("BACKUP_DATABASE_DIR") or (BASE_DIR / "backups" / "database"))
        self.full_dir = Path(cfg.get("BACKUP_FULL_DIR") or (BASE_DIR / "backups" / "full"))
        self.keep_count = max(int(cfg.get("BACKUP_KEEP_COUNT") or 20), 1)
        raw_sql_dir = cfg.get("SQL_SERVER_BACKUP_DIR")
        self.sql_server_backup_dir = Path(raw_sql_dir) if raw_sql_dir else None
        self.database_dir.mkdir(parents=True, exist_ok=True)
        self.full_dir.mkdir(parents=True, exist_ok=True)

    def connection_info(self) -> dict:
        sql_disk_dir = self._resolve_sql_staging_root()
        info = {
            "server": self.db_server,
            "database": self.db_name,
            "database_backup_dir": str(self.database_dir.resolve()),
            "full_backup_dir": str(self.full_dir.resolve()),
        }
        if sql_disk_dir is not None and sql_disk_dir.resolve() != self.database_dir.resolve():
            info["sql_server_backup_dir"] = str(sql_disk_dir.resolve())
        return info

    def list_database_backups(self) -> list[dict]:
        return self._list_files(self.database_dir, {".bak"})

    def list_full_backups(self) -> list[dict]:
        return self._list_files(self.full_dir, {".zip"})

    def create_database_backup(self, *, created_by: str = "System") -> dict:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_db = SAFE_NAME_RE.sub("_", self.db_name)
        file_name = f"{safe_db}_{stamp}.bak"
        target = self.database_dir / file_name
        self._run_sql_backup(target)
        self._prune(self.database_dir, {".bak"})
        info = self._file_info(target)
        info["created_by"] = created_by
        info["kind"] = "database"
        info["message"] = f"Database backup created: {file_name}"
        return info

    def create_full_backup(self, *, created_by: str = "System") -> dict:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_db = SAFE_NAME_RE.sub("_", self.db_name)
        zip_name = f"JTCS_Full_{safe_db}_{stamp}.zip"
        zip_path = self.full_dir / zip_name

        db_info = self.create_database_backup(created_by=created_by)
        bak_path = Path(db_info["path"])

        manifest = [
            "JTCS Full Backup",
            f"Created: {datetime.now().isoformat(timespec='seconds')}",
            f"CreatedBy: {created_by}",
            f"Server: {self.db_server}",
            f"Database: {self.db_name}",
            f"DatabaseBackup: {bak_path.name}",
            "",
            "Contents:",
            f"- database/{bak_path.name}",
            "- app/ (application source, excluding caches/venv)",
            "- database/sql_scripts/ (SQL scripts)",
            "- scripts/",
            "- selected root files (requirements, wsgi, .env.example, …)",
            "",
            "Restore notes:",
            "1. Restore the .bak with SQL Server RESTORE DATABASE.",
            "2. Extract application files over the ERP folder.",
            "3. Recreate .env from .env.example and set secrets.",
        ]

        tmp_zip = zip_path.with_suffix(".partial.zip")
        try:
            with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("MANIFEST.txt", "\n".join(manifest) + "\n")
                zf.write(bak_path, arcname=f"database/{bak_path.name}")
                self._add_tree_to_zip(zf, BASE_DIR / "app", "app")
                self._add_tree_to_zip(zf, BASE_DIR / "database", "database/sql_scripts")
                self._add_tree_to_zip(zf, BASE_DIR / "scripts", "scripts")
                for name in self.FULL_INCLUDE_FILES:
                    src = BASE_DIR / name
                    if src.is_file():
                        zf.write(src, arcname=name)
            tmp_zip.replace(zip_path)
        except Exception:
            if tmp_zip.exists():
                tmp_zip.unlink(missing_ok=True)
            raise

        self._prune(self.full_dir, {".zip"})
        info = self._file_info(zip_path)
        info["created_by"] = created_by
        info["kind"] = "full"
        info["database_backup"] = bak_path.name
        info["message"] = f"Full backup created: {zip_name}"
        return info

    def resolve_download(self, kind: str, file_name: str) -> Path:
        safe = self._safe_file_name(file_name)
        if kind == "database":
            path = self.database_dir / safe
            if path.suffix.lower() != ".bak":
                raise ValueError("Invalid database backup file.")
        elif kind == "full":
            path = self.full_dir / safe
            if path.suffix.lower() != ".zip":
                raise ValueError("Invalid full backup file.")
        else:
            raise ValueError("Unknown backup kind.")
        if not path.is_file() or not self._is_under(path, path.parent):
            raise ValueError("Backup file not found.")
        return path

    def delete_backup(self, kind: str, file_name: str) -> str:
        path = self.resolve_download(kind, file_name)
        path.unlink(missing_ok=False)
        return f"Deleted {path.name}."

    def _odbc_connect_string(self) -> str:
        # Connect to master so BACKUP can run even if JTCSS is busy with app pool.
        if self.db_trusted:
            return (
                f"DRIVER={{{self.db_driver}}};"
                f"SERVER={self.db_server};"
                "DATABASE=master;"
                "Trusted_Connection=yes;"
            )
        return (
            f"DRIVER={{{self.db_driver}}};"
            f"SERVER={self.db_server};"
            "DATABASE=master;"
            f"UID={self.db_user};"
            f"PWD={self.db_password};"
        )

    def _resolve_sql_staging_root(self) -> Path | None:
        """Folder SQL Server writes .bak into (may differ from app save folder).

        On Windows, BACKUP TO DISK uses the app folder directly.
        On Linux, the mssql service account cannot write under /root, so we
        stage into SQL_SERVER_BACKUP_DIR (or a known writable default) and copy.
        """
        if self.sql_server_backup_dir is not None:
            return self.sql_server_backup_dir

        if os.name == "nt":
            return None

        for candidate in (
            Path("/var/opt/mssql/backup"),
            Path("/var/backups/jtcs-erp/sql"),
        ):
            if candidate.is_dir():
                return candidate

        return Path("/tmp/jtcs-sql-backup")

    def _sql_disk_target(self, final_target: Path) -> tuple[Path, bool]:
        """Return (path for BACKUP TO DISK, whether to copy into final_target)."""
        staging_root = self._resolve_sql_staging_root()
        if staging_root is None:
            return final_target, False

        try:
            staging_root.mkdir(parents=True, exist_ok=True)
            # World-writable + sticky so mssql can create files even if we own the dir.
            if os.name != "nt":
                os.chmod(staging_root, 0o1777)
        except OSError:
            pass

        if staging_root.resolve() == final_target.parent.resolve():
            return final_target, False
        return staging_root / final_target.name, True

    def _run_sql_backup(self, target: Path) -> None:
        disk_path, needs_copy = self._sql_disk_target(target)
        disk = str(disk_path.resolve())
        escaped = disk.replace("'", "''")
        sql = (
            f"BACKUP DATABASE [{self.db_name}] TO DISK = N'{escaped}' "
            "WITH COPY_ONLY, INIT, STATS = 5, "
            f"NAME = N'JTCS {self.db_name} backup', "
            "DESCRIPTION = N'JTCS ERP Admin Role database backup'"
        )
        try:
            conn = pyodbc.connect(self._odbc_connect_string(), autocommit=True, timeout=30)
        except Exception as exc:
            raise ValueError(f"Could not connect to SQL Server for backup: {exc}") from exc

        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            # Drain informational STATS result sets from BACKUP.
            while cursor.nextset():
                pass
            cursor.close()
        except Exception as exc:
            hint = (
                f"SQL Server must be able to write to {disk_path.parent}. "
                "On Linux set SQL_SERVER_BACKUP_DIR=/var/opt/mssql/backup "
                "(sudo mkdir -p that path && sudo chown mssql:mssql it), "
                "or use /tmp/jtcs-sql-backup."
            )
            raise ValueError(
                f"Database backup failed. {hint} Details: {exc}"
            ) from exc
        finally:
            conn.close()

        if not disk_path.is_file() or disk_path.stat().st_size <= 0:
            raise ValueError(
                "Backup command finished but the .bak file was not created. "
                f"Check SQL Server permissions on {disk_path.parent}."
            )

        if needs_copy:
            try:
                shutil.copy2(disk_path, target)
            finally:
                try:
                    disk_path.unlink(missing_ok=True)
                except OSError:
                    pass

        if not target.is_file() or target.stat().st_size <= 0:
            raise ValueError(
                "Backup was created by SQL Server but could not be copied to "
                f"{target}. Check app write permissions on {self.database_dir}."
            )

    def _add_tree_to_zip(self, zf: zipfile.ZipFile, root: Path, arc_prefix: str) -> None:
        if not root.exists():
            return
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in self.FULL_EXCLUDE_DIR_NAMES]
            current = Path(dirpath)
            for name in filenames:
                src = current / name
                if src.suffix.lower() in self.FULL_EXCLUDE_FILE_SUFFIXES:
                    continue
                if name == ".env":
                    # Never pack live secrets into downloadable zip.
                    continue
                rel = src.relative_to(root).as_posix()
                zf.write(src, arcname=f"{arc_prefix}/{rel}")

    def _list_files(self, folder: Path, suffixes: set[str]) -> list[dict]:
        rows: list[dict] = []
        if not folder.exists():
            return rows
        for path in folder.iterdir():
            if path.is_file() and path.suffix.lower() in suffixes:
                rows.append(self._file_info(path))
        rows.sort(key=lambda item: item["modified"] or "", reverse=True)
        return rows

    def _prune(self, folder: Path, suffixes: set[str]) -> None:
        rows = self._list_files(folder, suffixes)
        for item in rows[self.keep_count :]:
            try:
                Path(item["path"]).unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _file_info(path: Path) -> dict:
        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime)
        return {
            "file_name": path.name,
            "path": str(path.resolve()),
            "size_bytes": stat.st_size,
            "size_label": BackupService._format_size(stat.st_size),
            "modified": modified.isoformat(timespec="seconds"),
            "modified_label": modified.strftime("%d/%m/%Y %H:%M:%S"),
        }

    @staticmethod
    def _format_size(num: int) -> str:
        value = float(num)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                if unit == "B":
                    return f"{int(value)} {unit}"
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{num} B"

    @staticmethod
    def _safe_file_name(file_name: str) -> str:
        name = Path(file_name or "").name.strip()
        if not name or name in {".", ".."} or "/" in name or "\\" in name:
            raise ValueError("Invalid file name.")
        return name

    @staticmethod
    def _is_under(path: Path, parent: Path) -> bool:
        try:
            path.resolve().relative_to(parent.resolve())
            return True
        except ValueError:
            return False
