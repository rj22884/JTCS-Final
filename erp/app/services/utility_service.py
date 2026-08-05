"""Admin Utility: Upload VPS (local) and Download Local (VPS) package helpers."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from flask import current_app

from app.config import BASE_DIR
from app.services.backup_service import BackupService
from app.utils.runtime_env import is_vps_runtime

REPO_ROOT = BASE_DIR.parent


class UtilityService:
    def __init__(self) -> None:
        self.repo_root = REPO_ROOT
        self.vps = self._load_vps_env()

    def _load_vps_env(self) -> dict[str, str]:
        defaults = {
            "VPS_HOST": "200.141.5.68",
            "VPS_USER": "root",
            "VPS_PORT": "22",
            "VPS_PATH": "/root/JTCS-final",
            "PUBLIC_HEALTH_URL": "https://app.jtcsxpert.com/health",
            "GIT_REPO_URL": "https://github.com/rj22884/JTCS-Final.git",
        }
        path = self.repo_root / "deploy_vps.env"
        if not path.is_file():
            return defaults
        data = dict(defaults)
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key:
                data[key] = val
        return data

    def app_info(self) -> dict:
        cfg = current_app.config
        return {
            "mode": "vps" if is_vps_runtime() else "local",
            "sync_label": "Download Local" if is_vps_runtime() else "Upload VPS",
            "app_name": cfg.get("APP_NAME") or "JTCS ERP",
            "app_base_url": cfg.get("APP_BASE_URL") or "",
            "db_server": cfg.get("DB_SERVER_DISPLAY") or cfg.get("DB_SERVER") or "",
            "db_name": cfg.get("DB_NAME_DISPLAY") or cfg.get("DB_NAME") or "",
            "erp_dir": str(BASE_DIR),
            "repo_root": str(self.repo_root),
            "vps_host": self.vps.get("VPS_HOST", ""),
            "vps_path": self.vps.get("VPS_PATH", ""),
            "public_health": self.vps.get("PUBLIC_HEALTH_URL", ""),
            "os_name": os.name,
        }

    def system_health(self) -> dict:
        info = self.app_info()
        db_ok = False
        db_error = ""
        try:
            from app.extensions import db
            from sqlalchemy import text

            db.session.execute(text("SELECT 1"))
            db_ok = True
        except Exception as exc:  # pragma: no cover
            db_error = str(exc)

        public_ok = None
        public_body = ""
        try:
            import urllib.request

            url = info["public_health"] or "https://app.jtcsxpert.com/health"
            with urllib.request.urlopen(url, timeout=15) as resp:
                public_ok = resp.status == 200
                public_body = resp.read().decode("utf-8", errors="replace")[:200]
        except Exception as exc:
            public_ok = False
            public_body = str(exc)

        return {
            "ok": db_ok,
            "database_ok": db_ok,
            "database_error": db_error,
            "public_health_ok": public_ok,
            "public_health_body": public_body,
            "info": info,
        }

    def clear_caches(self) -> dict:
        removed_dirs = 0
        removed_files = 0
        skip_names = {".venv", "venv", "node_modules", ".git"}
        for root, dirs, files in os.walk(BASE_DIR):
            dirs[:] = [d for d in dirs if d not in skip_names]
            for d in list(dirs):
                if d in {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".webassets-cache"}:
                    path = Path(root) / d
                    shutil.rmtree(path, ignore_errors=True)
                    removed_dirs += 1
                    dirs.remove(d)
            for name in files:
                if name.endswith((".pyc", ".pyo")):
                    try:
                        (Path(root) / name).unlink(missing_ok=True)
                        removed_files += 1
                    except OSError:
                        pass
        return {
            "ok": True,
            "removed_dirs": removed_dirs,
            "removed_files": removed_files,
            "message": f"Cleared {removed_dirs} cache folder(s) and {removed_files} bytecode file(s).",
        }

    def create_download_package(self, *, created_by: str = "System") -> dict:
        """VPS: full app + database ZIP (same layout as Backup Full)."""
        if not is_vps_runtime():
            raise RuntimeError("Download Local is only available on the VPS.")
        info = BackupService().create_full_backup(created_by=created_by)
        info["sync_action"] = "download_local"
        return info

    def resolve_download_package(self, file_name: str) -> Path:
        return BackupService().resolve_download("full", file_name)

    def deploy_to_vps(
        self,
        *,
        password: str,
        commit_message: str = "",
        created_by: str = "System",
    ) -> dict:
        """Local Windows: git push current branch, then SSH run deployment/deploy.sh."""
        if is_vps_runtime():
            raise RuntimeError("Upload VPS is only available on the local PC.")
        if os.name != "nt":
            raise RuntimeError("Upload VPS deploy is intended from the Windows local PC.")
        password = (password or "").strip()
        if not password:
            raise ValueError("VPS password is required.")

        try:
            import paramiko
        except ImportError as exc:
            raise RuntimeError(
                "paramiko is not installed. Run: pip install paramiko"
            ) from exc

        branch = self._git_current_branch()
        push_info = self._git_commit_push(commit_message=commit_message or f"deploy {created_by}")
        host = self.vps["VPS_HOST"]
        user = self.vps["VPS_USER"]
        port = int(self.vps.get("VPS_PORT") or "22")
        app_dir = self.vps["VPS_PATH"]
        repo = self.vps.get("GIT_REPO_URL") or "https://github.com/rj22884/JTCS-Final.git"

        remote_cmd = (
            f"cd {app_dir} && "
            f"git remote set-url origin {repo} && "
            f"git fetch --all --prune && "
            f"git checkout -B {branch} origin/{branch} && "
            f"git reset --hard origin/{branch} && "
            f"export BRANCH={branch} && "
            f"export VPS_APP_DIR={app_dir} && "
            f"export GIT_BRANCH={branch} && "
            "bash deployment/deploy.sh && "
            "echo ===DEPLOY_RESULT:SUCCESS==="
        )

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        log_chunks: list[str] = []
        try:
            client.connect(
                host,
                port=port,
                username=user,
                password=password,
                timeout=45,
                allow_agent=False,
                look_for_keys=False,
            )
            _stdin, stdout, stderr = client.exec_command(remote_cmd, get_pty=True)
            while True:
                line = stdout.readline()
                if not line:
                    break
                log_chunks.append(line)
            err = stderr.read().decode("utf-8", errors="replace")
            if err:
                log_chunks.append(err)
            rc = stdout.channel.recv_exit_status()
        finally:
            client.close()

        log_text = "".join(log_chunks)
        log_dir = self.repo_root / "deployment" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"utility_deploy_{int(time.time())}.log"
        log_path.write_text(log_text, encoding="utf-8", errors="replace")

        success = rc == 0 and (
            "DEPLOY_RESULT:SUCCESS" in log_text or "DEPLOYMENT SUCCESS" in log_text
        )
        health_ok = self._check_public_health()
        if not success:
            raise RuntimeError(
                f"VPS deploy failed (exit {rc}). See log: {log_path.name}. "
                f"Last lines: {log_text[-800:]}"
            )

        return {
            "ok": True,
            "sync_action": "upload_vps",
            "branch": branch,
            "push": push_info,
            "remote_exit": rc,
            "health_ok": health_ok,
            "log_file": str(log_path),
            "message": (
                f"Deployed branch {branch} to VPS. "
                f"Health={'OK' if health_ok else 'check pending'}."
            ),
        }

    def _check_public_health(self) -> bool:
        try:
            import urllib.request

            url = self.vps.get("PUBLIC_HEALTH_URL") or "https://app.jtcsxpert.com/health"
            with urllib.request.urlopen(url, timeout=25) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _run_git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo_root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def _git_current_branch(self) -> str:
        proc = self._run_git("branch", "--show-current")
        branch = (proc.stdout or "").strip()
        if not branch:
            proc = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
            branch = (proc.stdout or "").strip()
        if not branch or branch == "HEAD":
            raise RuntimeError("Cannot determine git branch. Checkout a branch first.")
        return branch

    def _git_commit_push(self, *, commit_message: str) -> dict:
        status = self._run_git("status", "--porcelain")
        if status.returncode != 0:
            raise RuntimeError(status.stderr or "git status failed")

        if (status.stdout or "").strip():
            add = self._run_git("add", "-A")
            if add.returncode != 0:
                raise RuntimeError(add.stderr or "git add failed")
            commit = self._run_git("commit", "-m", commit_message)
            if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr):
                raise RuntimeError(commit.stderr or commit.stdout or "git commit failed")

        push = self._run_git("push", "-u", "origin", "HEAD")
        if push.returncode != 0:
            raise RuntimeError(push.stderr or push.stdout or "git push failed")

        head = self._run_git("rev-parse", "--short", "HEAD")
        return {
            "commit": (head.stdout or "").strip(),
            "pushed": True,
            "message": commit_message,
        }
