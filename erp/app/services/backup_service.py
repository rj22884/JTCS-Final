from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
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
        sql_disk_dir = self._preferred_sql_staging_root()
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
        trust = ""
        if bool(current_app.config.get("DB_TRUST_SERVER_CERTIFICATE", True)):
            trust = "TrustServerCertificate=yes;"
        if self.db_trusted:
            return (
                f"DRIVER={{{self.db_driver}}};"
                f"SERVER={self.db_server};"
                "DATABASE=master;"
                "Trusted_Connection=yes;"
                f"{trust}"
            )
        return (
            f"DRIVER={{{self.db_driver}}};"
            f"SERVER={self.db_server};"
            "DATABASE=master;"
            f"UID={self.db_user};"
            f"PWD={self.db_password};"
            f"{trust}"
        )

    def _normalize_sql_backup_dir(self) -> Path | None:
        """Configured SQL_SERVER_BACKUP_DIR, ignoring OS-mismatched paths."""
        if self.sql_server_backup_dir is None:
            return None
        raw = str(self.sql_server_backup_dir).strip()
        if not raw:
            return None
        # Linux path in Windows .env (or vice versa) must be ignored.
        if os.name == "nt" and raw.startswith("/"):
            return None
        if os.name != "nt" and len(raw) >= 2 and raw[1] == ":":
            return None
        return Path(raw)

    def _windows_sql_default_backup_dirs(self) -> list[Path]:
        roots: list[Path] = []
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        mssql_root = program_files / "Microsoft SQL Server"
        if mssql_root.is_dir():
            for backup_dir in mssql_root.glob("MSSQL*/*/MSSQL/Backup"):
                if backup_dir.is_dir():
                    roots.append(backup_dir)
        return roots

    def _preferred_sql_staging_root(self) -> Path | None:
        """Best guess for UI display (actual backup uses SQL instance paths)."""
        configured = self._normalize_sql_backup_dir()
        if configured is not None:
            return configured
        if os.name == "nt":
            return None
        # Linux: mssql always owns its data dir (NOT /tmp — PrivateTmp hides files).
        return Path("/var/opt/mssql/data")

    def _connect_master(self):
        try:
            return pyodbc.connect(self._odbc_connect_string(), autocommit=True, timeout=30)
        except Exception as exc:
            raise ValueError(f"Could not connect to SQL Server for backup: {exc}") from exc

    def _sql_writable_roots(self, conn) -> list[Path]:
        """Folders the SQL Server process can actually write to."""
        roots: list[Path] = []
        seen: set[str] = set()

        def add(path: Path | None) -> None:
            if path is None:
                return
            try:
                text = str(path).strip().rstrip("\\/")
                if not text:
                    return
                root = Path(text)
                key = str(root).lower()
                if key in seen:
                    return
                seen.add(key)
                roots.append(root)
            except (OSError, TypeError, ValueError):
                return

        add(self._normalize_sql_backup_dir())

        cursor = conn.cursor()
        for prop in ("InstanceDefaultBackupPath", "InstanceDefaultDataPath"):
            try:
                cursor.execute(
                    f"SELECT CAST(SERVERPROPERTY('{prop}') AS NVARCHAR(512))"
                )
                row = cursor.fetchone()
                if row and row[0]:
                    add(Path(str(row[0]).strip()))
            except Exception:
                pass
        try:
            cursor.close()
        except Exception:
            pass

        if os.name == "nt":
            for root in self._windows_sql_default_backup_dirs():
                add(root)
        else:
            # Never use /tmp on Linux: mssql often has systemd PrivateTmp, so the
            # Flask app cannot see files SQL Server wrote under its private /tmp.
            add(Path("/var/opt/mssql/data"))
            add(Path("/var/opt/mssql/backup"))

        return roots

    def _execute_backup_to_disk(self, conn, disk_path: Path) -> None:
        # Use the exact string we send to SQL (avoid resolve() changing path).
        disk = str(disk_path)
        if os.name == "nt":
            disk = str(Path(disk))
        escaped = disk.replace("'", "''")
        sql = (
            f"BACKUP DATABASE [{self.db_name}] TO DISK = N'{escaped}' "
            "WITH COPY_ONLY, INIT, "
            f"NAME = N'JTCS {self.db_name} backup', "
            "DESCRIPTION = N'JTCS ERP Admin Role database backup'"
        )
        cursor = conn.cursor()
        try:
            cursor.execute(sql)
            while True:
                try:
                    if not cursor.nextset():
                        break
                except pyodbc.ProgrammingError:
                    break
        except Exception as exc:
            raise ValueError(str(exc)) from exc
        finally:
            try:
                cursor.close()
            except Exception:
                pass

        # Allow brief FS sync; then confirm the file SQL Server wrote.
        for _ in range(10):
            if disk_path.is_file() and disk_path.stat().st_size > 0:
                return
            time.sleep(0.2)

        raise ValueError(
            f"BACKUP reported OK but file missing at {disk_path}. "
            "SQL Server service cannot write that folder."
        )

    def _copy_bak_to_target(self, disk_path: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(disk_path, target)
        except OSError:
            completed = subprocess.run(
                ["cp", "-f", str(disk_path), str(target)],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0 or not target.is_file():
                raise ValueError(
                    f"Could not copy .bak to {target}: {completed.stderr or completed.stdout}"
                )

    def _run_sql_backup(self, target: Path) -> None:
        conn = self._connect_master()
        errors: list[str] = []
        try:
            roots = self._sql_writable_roots(conn)
            if os.name == "nt":
                # Local Windows: try the app save folder first (usually works).
                roots = [target.parent, *roots]

            seen: set[str] = set()
            for root in roots:
                key = str(root).lower()
                if key in seen:
                    continue
                seen.add(key)
                disk_path = root / target.name
                try:
                    # Do not mkdir under /var/opt/mssql/* as root with wrong owner.
                    if root not in (
                        Path("/var/opt/mssql/data"),
                        Path("/var/opt/mssql/backup"),
                    ) and not (
                        str(root).lower().startswith("/var/opt/mssql/")
                    ):
                        try:
                            root.mkdir(parents=True, exist_ok=True)
                        except OSError:
                            pass

                    self._execute_backup_to_disk(conn, disk_path)

                    if disk_path.resolve() != target.resolve():
                        self._copy_bak_to_target(disk_path, target)
                        try:
                            disk_path.unlink(missing_ok=True)
                        except OSError:
                            pass

                    if target.is_file() and target.stat().st_size > 0:
                        return

                    errors.append(f"{root}: copy to app folder failed")
                except ValueError as exc:
                    errors.append(f"{root}: {exc}")
                    continue
        finally:
            conn.close()

        detail = " | ".join(errors[-4:]) if errors else "no writable SQL folders found"
        if os.name == "nt":
            tip = (
                "On Windows, grant the SQL Server service write access to the backup "
                "folder, or set SQL_SERVER_BACKUP_DIR to the instance Backup folder."
            )
        else:
            tip = (
                "On Linux, SQL Server must write under /var/opt/mssql/data "
                "(owned by mssql). Do not use /tmp or /root. "
                "Optional: sudo mkdir -p /var/opt/mssql/backup && "
                "sudo chown mssql:mssql /var/opt/mssql/backup && "
                "set SQL_SERVER_BACKUP_DIR=/var/opt/mssql/backup"
            )
        raise ValueError(f"Database backup failed. {tip} Details: {detail}")

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
