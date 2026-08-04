from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
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

    def save_uploaded_backup(self, kind: str, file_name: str, data) -> dict:
        """Save a previously downloaded backup into the server backup folder.

        ``data`` may be bytes or a file-like / Werkzeug FileStorage stream.
        Streams are written in chunks so large .bak files do not fill RAM.
        """
        safe = self._safe_file_name(file_name)
        if kind == "database":
            if Path(safe).suffix.lower() != ".bak":
                raise ValueError("Database restore upload must be a .bak file.")
            target = self.database_dir / safe
        elif kind == "full":
            if Path(safe).suffix.lower() != ".zip":
                raise ValueError("Full restore upload must be a .zip file.")
            target = self.full_dir / safe
        else:
            raise ValueError("Unknown backup kind.")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".partial")
        try:
            if hasattr(data, "save") and callable(getattr(data, "save")):
                # Werkzeug FileStorage — stream to disk
                data.save(tmp)
            elif hasattr(data, "read") and callable(getattr(data, "read")):
                with open(tmp, "wb") as out:
                    shutil.copyfileobj(data, out, length=1024 * 1024)
            elif isinstance(data, (bytes, bytearray)):
                if not data:
                    raise ValueError("Uploaded file is empty.")
                tmp.write_bytes(data)
            else:
                raise ValueError("Unsupported upload payload.")
            if not tmp.is_file() or tmp.stat().st_size <= 0:
                raise ValueError("Uploaded file is empty.")
            tmp.replace(target)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        info = self._file_info(target)
        info["kind"] = kind
        info["message"] = f"Uploaded to local: {target.name} — ab Restore dabayein."
        return info

    def restore_database(self, file_name: str, *, restored_by: str = "System") -> dict:
        bak_path = self.resolve_download("database", file_name)
        return self._restore_database_from_bak(bak_path, restored_by=restored_by)

    def restore_full(self, file_name: str, *, restored_by: str = "System") -> dict:
        """Restore DB from full ZIP (+ application files). Preserves live .env / venv."""
        zip_path = self.resolve_download("full", file_name)
        if not zipfile.is_zipfile(zip_path):
            raise ValueError("Invalid full backup ZIP.")

        with tempfile.TemporaryDirectory(prefix="jtcs_restore_") as tmp:
            tmp_root = Path(tmp)
            with zipfile.ZipFile(zip_path, "r") as zf:
                bak_members = [
                    name
                    for name in zf.namelist()
                    if name.lower().endswith(".bak") and not name.endswith("/")
                ]
                if not bak_members:
                    raise ValueError("Full backup ZIP has no .bak database file.")
                bak_members.sort()
                bak_member = bak_members[0]
                zf.extract(bak_member, path=tmp_root)
                bak_path = tmp_root / bak_member
                if not bak_path.is_file():
                    raise ValueError(f"Could not extract {bak_member} from ZIP.")

                db_info = self._restore_database_from_bak(bak_path, restored_by=restored_by)

                # Application files (skip secrets / runtime dirs)
                app_restored = 0
                for member in zf.namelist():
                    if member.endswith("/"):
                        continue
                    posix = member.replace("\\", "/")
                    if posix in {"MANIFEST.txt"}:
                        continue
                    if posix.lower().endswith(".bak"):
                        continue
                    if posix == ".env" or posix.endswith("/.env"):
                        continue
                    dest = self._map_full_restore_member(posix)
                    if dest is None:
                        continue
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(dest, "wb") as out:
                        shutil.copyfileobj(src, out)
                    app_restored += 1

        return {
            "ok": True,
            "kind": "full",
            "file_name": zip_path.name,
            "database_backup": db_info.get("file_name"),
            "app_files_restored": app_restored,
            "restored_by": restored_by,
            "message": (
                f"Full restore complete from {zip_path.name}: "
                f"database restored, {app_restored} application file(s) written "
                f"(.env and venv preserved)."
            ),
        }

    def _map_full_restore_member(self, posix: str) -> Path | None:
        """Map ZIP member path → live ERP path; return None to skip."""
        parts = [p for p in posix.split("/") if p and p not in {".", ".."}]
        if not parts:
            return None
        # Skip anything under excluded runtime folders
        if any(part in self.FULL_EXCLUDE_DIR_NAMES for part in parts):
            return None
        if parts[0] == "app":
            return BASE_DIR.joinpath(*parts)
        if parts[0] == "database" and len(parts) > 1 and parts[1] == "sql_scripts":
            # ZIP layout: database/sql_scripts/... → erp/database/...
            return BASE_DIR.joinpath("database", *parts[2:])
        if parts[0] == "scripts":
            return BASE_DIR.joinpath(*parts)
        if len(parts) == 1 and parts[0] in self.FULL_INCLUDE_FILES:
            return BASE_DIR / parts[0]
        return None

    def _dispose_app_db_pool(self) -> None:
        """Drop Flask-SQLAlchemy pooled connections so RESTORE can take the DB offline."""
        try:
            from app.extensions import db

            try:
                db.session.invalidate()
            except Exception:
                pass
            try:
                db.session.remove()
            except Exception:
                pass
            try:
                db.engine.dispose()
            except Exception:
                pass
        except Exception:
            pass

    def _restore_database_from_bak(self, bak_path: Path, *, restored_by: str = "System") -> dict:
        if not bak_path.is_file() or bak_path.stat().st_size <= 0:
            raise ValueError(f"Backup file missing or empty: {bak_path}")

        # App pool holds open connections to JTCSS — RESTORE SINGLE_USER kills them
        # and later SQLAlchemy teardown raises 08S01 / pipe closed.
        self._dispose_app_db_pool()

        conn = self._connect_master()
        try:
            # Long-running RESTORE (60MB+ .bak) — do not use short query timeout.
            try:
                conn.timeout = 0
            except Exception:
                pass

            sql_disk = self._stage_bak_for_sql(conn, bak_path)
            logical_files = self._restore_filelist(conn, sql_disk)
            data_files = [f for f in logical_files if f["type"] == "D"]
            log_files = [f for f in logical_files if f["type"] == "L"]
            if not data_files:
                raise ValueError("BACKUP file list has no data file.")

            move_targets = self._current_db_file_paths(conn)
            move_clauses: list[str] = []
            default_data = self._instance_default_path(conn, "InstanceDefaultDataPath")
            default_log = self._instance_default_path(conn, "InstanceDefaultLogPath") or default_data

            for idx, item in enumerate(data_files):
                logical = item["logical"]
                if logical in move_targets:
                    physical = move_targets[logical]
                elif idx == 0 and move_targets:
                    # Fall back to first existing data file path's directory
                    sample = next(iter(move_targets.values()))
                    physical = str(Path(sample).with_name(f"{self.db_name}.mdf"))
                else:
                    root = Path(default_data or str(bak_path.parent))
                    physical = str(root / f"{self.db_name}_{idx}.mdf")
                move_clauses.append(
                    f"MOVE N'{logical.replace(chr(39), chr(39)+chr(39))}' TO N'{physical.replace(chr(39), chr(39)+chr(39))}'"
                )

            for idx, item in enumerate(log_files):
                logical = item["logical"]
                if logical in move_targets:
                    physical = move_targets[logical]
                else:
                    root = Path(default_log or default_data or str(bak_path.parent))
                    physical = str(root / f"{self.db_name}_{idx}.ldf")
                move_clauses.append(
                    f"MOVE N'{logical.replace(chr(39), chr(39)+chr(39))}' TO N'{physical.replace(chr(39), chr(39)+chr(39))}'"
                )

            disk_escaped = str(sql_disk).replace("'", "''")
            db_escaped = self.db_name.replace("'", "''")
            move_sql = ",\n         ".join(move_clauses)
            # Kick off other sessions first (app pool already disposed), then restore.
            sql = f"""
SET NOCOUNT ON;
BEGIN TRY
    IF DB_ID(N'{db_escaped}') IS NOT NULL
    BEGIN
        ALTER DATABASE [{self.db_name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    END;

    RESTORE DATABASE [{self.db_name}] FROM DISK = N'{disk_escaped}'
    WITH REPLACE, RECOVERY
         {(',' + chr(10) + '         ' + move_sql) if move_sql else ''};

    IF DB_ID(N'{db_escaped}') IS NOT NULL
    BEGIN
        ALTER DATABASE [{self.db_name}] SET MULTI_USER;
    END;
END TRY
BEGIN CATCH
    BEGIN TRY
        IF DB_ID(N'{db_escaped}') IS NOT NULL
            ALTER DATABASE [{self.db_name}] SET MULTI_USER;
    END TRY
    BEGIN CATCH
    END CATCH;
    DECLARE @msg NVARCHAR(4000) = ERROR_MESSAGE();
    RAISERROR(@msg, 16, 1);
END CATCH
"""
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
                raise ValueError(f"Database restore failed: {exc}") from exc
            finally:
                try:
                    cursor.close()
                except Exception:
                    pass

            # Clean staged copy when different from original
            try:
                if Path(sql_disk).resolve() != bak_path.resolve():
                    Path(sql_disk).unlink(missing_ok=True)
            except OSError:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
            # Drop any dead pooled handles left from before SINGLE_USER.
            self._dispose_app_db_pool()

        return {
            "ok": True,
            "kind": "database",
            "file_name": bak_path.name,
            "restored_by": restored_by,
            "message": (
                f"Database [{self.db_name}] restored from {bak_path.name}. "
                f"Page refresh / re-login recommended."
            ),
            "reload_recommended": True,
        }

    def _stage_bak_for_sql(self, conn, bak_path: Path) -> Path:
        """Place .bak where SQL Server (or Docker mssql) can read it."""
        roots = self._sql_writable_roots(conn)
        if os.name == "nt":
            roots = [bak_path.parent, *roots]

        container = None if os.name == "nt" else self._find_mssql_docker_container()

        # Prefer a root SQL can see; copy when needed.
        for root in roots:
            try:
                staged = root / bak_path.name
                if staged.resolve() == bak_path.resolve():
                    if self._sql_xp_file_exists(conn, str(staged)):
                        return staged
                staged.parent.mkdir(parents=True, exist_ok=True)
                if staged.resolve() != bak_path.resolve():
                    self._copy_bak_to_target(bak_path, staged)
                if container:
                    # Ensure file is inside container FS at the same path.
                    subprocess.run(
                        ["docker", "cp", str(staged), f"{container}:{staged}"],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=600,
                    )
                if self._sql_xp_file_exists(conn, str(staged)) or staged.is_file():
                    return staged
            except (OSError, ValueError):
                continue

        # Last resort: original path (Windows local often works)
        if self._sql_xp_file_exists(conn, str(bak_path)) or bak_path.is_file():
            return bak_path
        raise ValueError(
            f"Could not stage {bak_path.name} to a path SQL Server can read. "
            "On VPS, ensure /var/opt/mssql/backup is writable by mssql."
        )

    def _restore_filelist(self, conn, disk_path: Path) -> list[dict]:
        escaped = str(disk_path).replace("'", "''")
        cursor = conn.cursor()
        try:
            cursor.execute(f"RESTORE FILELISTONLY FROM DISK = N'{escaped}'")
            cols = [col[0] for col in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            out: list[dict] = []
            for row in rows:
                data = dict(zip(cols, row))
                logical = str(data.get("LogicalName") or "")
                ftype = str(data.get("Type") or "").strip().upper()
                if logical:
                    out.append({"logical": logical, "type": ftype or "D"})
            if not out:
                raise ValueError("RESTORE FILELISTONLY returned no files.")
            return out
        except Exception as exc:
            raise ValueError(f"Could not read backup file list: {exc}") from exc
        finally:
            try:
                cursor.close()
            except Exception:
                pass

    def _current_db_file_paths(self, conn) -> dict[str, str]:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT mf.name, mf.physical_name
                FROM sys.master_files AS mf
                INNER JOIN sys.databases AS d ON d.database_id = mf.database_id
                WHERE d.name = ?
                """,
                self.db_name,
            )
            return {str(row[0]): str(row[1]) for row in cursor.fetchall() if row and row[0]}
        except Exception:
            return {}
        finally:
            try:
                cursor.close()
            except Exception:
                pass

    def _instance_default_path(self, conn, prop: str) -> str | None:
        cursor = conn.cursor()
        try:
            cursor.execute(f"SELECT CAST(SERVERPROPERTY('{prop}') AS NVARCHAR(512))")
            row = cursor.fetchone()
            if row and row[0]:
                return str(row[0]).strip()
            return None
        except Exception:
            return None
        finally:
            try:
                cursor.close()
            except Exception:
                pass

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
        # Linux: shared mssql backup dir (prepared at runtime). Avoid /tmp and /root.
        return Path("/var/opt/mssql/backup")

    def _connect_master(self):
        try:
            return pyodbc.connect(self._odbc_connect_string(), autocommit=True, timeout=30)
        except Exception as exc:
            raise ValueError(f"Could not connect to SQL Server for backup: {exc}") from exc

    def _prepare_linux_mssql_dirs(self) -> list[Path]:
        """Ensure mssql-owned folders exist so BACKUP TO DISK can succeed on VPS."""
        prepared: list[Path] = []
        for folder in (Path("/var/opt/mssql/backup"), Path("/var/opt/mssql/data")):
            try:
                subprocess.run(["mkdir", "-p", str(folder)], capture_output=True, check=False)
                subprocess.run(["chown", "mssql:mssql", str(folder)], capture_output=True, check=False)
                subprocess.run(["chmod", "775", str(folder)], capture_output=True, check=False)
                prepared.append(folder)
            except OSError:
                continue
        return prepared

    def _find_mssql_docker_container(self) -> str | None:
        """If SQL Server runs in Docker, host paths may not see .bak files."""
        try:
            completed = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}\t{{.Image}}"],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if completed.returncode != 0:
            return None
        for line in (completed.stdout or "").splitlines():
            low = line.lower()
            if any(token in low for token in ("mssql", "azure-sql", "microsoft/mssql", "mssql/server")):
                return line.split("\t", 1)[0].strip() or None
        return None

    def _sql_xp_file_exists(self, conn, path: str) -> bool:
        cursor = conn.cursor()
        try:
            escaped = path.replace("'", "''")
            cursor.execute(
                f"""
                DECLARE @t TABLE (
                    FileExists INT NOT NULL,
                    FileIsDirectory INT NOT NULL,
                    ParentDirectoryExists INT NOT NULL
                );
                INSERT INTO @t
                EXEC master.dbo.xp_fileexist N'{escaped}';
                SELECT FileExists FROM @t;
                """
            )
            row = cursor.fetchone()
            return bool(row and int(row[0]) == 1)
        except Exception:
            return False
        finally:
            try:
                cursor.close()
            except Exception:
                pass

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

        if os.name != "nt":
            for folder in self._prepare_linux_mssql_dirs():
                add(folder)

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
            add(Path("/var/opt/mssql/backup"))
            add(Path("/var/opt/mssql/data"))

        return roots

    def _execute_backup_to_disk(self, conn, disk_path: Path) -> None:
        disk = str(disk_path)
        if os.name == "nt":
            disk = str(Path(disk))
        escaped = disk.replace("'", "''")
        # TRY/CATCH so Access Denied cannot look like a silent success.
        sql = f"""
SET NOCOUNT ON;
BEGIN TRY
    BACKUP DATABASE [{self.db_name}] TO DISK = N'{escaped}'
    WITH COPY_ONLY, INIT,
         NAME = N'JTCS {self.db_name} backup',
         DESCRIPTION = N'JTCS ERP Admin Role database backup';
END TRY
BEGIN CATCH
    DECLARE @msg NVARCHAR(4000) = ERROR_MESSAGE();
    RAISERROR(@msg, 16, 1);
END CATCH
"""
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

    def _materialize_bak(self, conn, disk_path: Path, target: Path) -> None:
        """Copy .bak into app folder; use docker cp when SQL FS is not host-visible."""
        target.parent.mkdir(parents=True, exist_ok=True)

        for _ in range(15):
            if disk_path.is_file() and disk_path.stat().st_size > 0:
                self._copy_bak_to_target(disk_path, target)
                if target.is_file() and target.stat().st_size > 0:
                    try:
                        disk_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                    return
            time.sleep(0.2)

        sql_sees = self._sql_xp_file_exists(conn, str(disk_path))
        container = None if os.name == "nt" else self._find_mssql_docker_container()

        if container:
            # SQL Server inside Docker: file exists in container FS only.
            completed = subprocess.run(
                ["docker", "cp", f"{container}:{disk_path}", str(target)],
                capture_output=True,
                text=True,
                check=False,
                timeout=600,
            )
            if completed.returncode == 0 and target.is_file() and target.stat().st_size > 0:
                subprocess.run(
                    ["docker", "exec", container, "rm", "-f", str(disk_path)],
                    capture_output=True,
                    check=False,
                )
                return
            raise ValueError(
                f"docker cp from {container}:{disk_path} failed: "
                f"{completed.stderr or completed.stdout or 'unknown error'}"
            )

        if sql_sees:
            # File exists for SQL user but not readable yet — fix perms then copy.
            subprocess.run(["chmod", "-R", "a+rX", str(disk_path.parent)], capture_output=True, check=False)
            subprocess.run(["chmod", "a+r", str(disk_path)], capture_output=True, check=False)
            if disk_path.is_file() and disk_path.stat().st_size > 0:
                self._copy_bak_to_target(disk_path, target)
                if target.is_file() and target.stat().st_size > 0:
                    try:
                        disk_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                    return

        raise ValueError(
            f"BACKUP finished but .bak not available at {disk_path} "
            f"(sql_sees_file={sql_sees}, docker={container or 'none'})."
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
                    if os.name == "nt":
                        try:
                            root.mkdir(parents=True, exist_ok=True)
                        except OSError:
                            pass
                    elif not str(root).startswith("/var/opt/mssql/"):
                        try:
                            root.mkdir(parents=True, exist_ok=True)
                        except OSError:
                            pass

                    self._execute_backup_to_disk(conn, disk_path)

                    if disk_path.resolve() == target.resolve() and target.is_file() and target.stat().st_size > 0:
                        return

                    self._materialize_bak(conn, disk_path, target)
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
                "On Linux/VPS, SQL Server must write under /var/opt/mssql/backup "
                "(mssql:mssql). If SQL runs in Docker, the app will docker-cp the .bak. "
                "Do not use /tmp or /root."
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
