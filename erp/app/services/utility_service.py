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
DEPLOY_TARGETS = ("app", "web", "both")


class UtilityService:
    def __init__(self) -> None:
        self.repo_root = REPO_ROOT
        self.vps = self._load_vps_env()
        self.web = self._load_web_env()

    def _load_vps_env(self) -> dict[str, str]:
        defaults = {
            "VPS_HOST": "200.234.41.220",
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

    def _load_web_env(self) -> dict[str, str]:
        """Website (jtcsxpert.com) paths. Host/user/port follow App so one password works."""
        data = {
            "WEB_PATH": r"D:\JTCS Web Page",
            "VPS_WEB_DIR": "/var/www/jtcsxpert.com",
            "VPS_GIT_DIR": "/var/repos/jtcsxpert.git",
            "LIVE_URL": "https://jtcsxpert.com",
        }
        for key in ("WEB_PATH", "VPS_WEB_DIR", "VPS_WEB_GIT_DIR", "PUBLIC_WEB_URL"):
            val = (self.vps.get(key) or "").strip()
            if not val:
                continue
            if key == "VPS_WEB_GIT_DIR":
                data["VPS_GIT_DIR"] = val
            elif key == "PUBLIC_WEB_URL":
                data["LIVE_URL"] = val
            else:
                data[key] = val
        bat = Path(data["WEB_PATH"]) / "deploy.config.bat"
        if bat.is_file():
            for raw in bat.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw.strip()
                if not line.lower().startswith("set "):
                    continue
                body = line[4:].strip().strip('"')
                if "=" not in body:
                    continue
                key, val = body.split("=", 1)
                key = key.strip().strip('"')
                val = val.strip().strip('"')
                if key in {"VPS_GIT_DIR", "VPS_WEB_DIR", "LIVE_URL"} and val:
                    data[key] = val
                if key == "WEB_PATH" and val:
                    data["WEB_PATH"] = val
        env_web = (os.getenv("JTCS_WEB_PATH") or "").strip()
        if env_web:
            data["WEB_PATH"] = env_web
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
            "vps_web_dir": self.web.get("VPS_WEB_DIR", "/var/www/jtcsxpert.com"),
            "web_path": self.web.get("WEB_PATH", ""),
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

    def iter_deploy_to_vps(
        self,
        *,
        password: str,
        commit_message: str = "",
        created_by: str = "System",
        target: str = "app",
    ):
        """Yield NDJSON-friendly events while deploying (log / done / error)."""
        def emit(line: str, *, level: str = "info"):
            text = (line or "").rstrip("\r\n")
            if text:
                return {"type": "log", "level": level, "line": text}
            return None

        try:
            if is_vps_runtime():
                raise RuntimeError("Upload VPS is only available on the local PC.")
            if os.name != "nt":
                raise RuntimeError("Upload VPS deploy is intended from the Windows local PC.")
            password = (password or "").strip()
            if not password:
                raise ValueError("VPS password is required.")
            mode = (target or "app").strip().lower()
            if mode not in DEPLOY_TARGETS:
                raise ValueError("Invalid upload target. Use App, Web, or Both.")

            try:
                import paramiko
            except ImportError as exc:
                raise RuntimeError(
                    "paramiko is not installed. Run: pip install paramiko"
                ) from exc

            labels = {"app": "App", "web": "Web", "both": "App + Web"}
            yield {
                "type": "log",
                "level": "info",
                "line": f"=== JTCS Utility Upload ({labels[mode]}) ===",
            }
            commit_message = commit_message or f"deploy {created_by}"
            push_info = None
            health_ok = None
            web_ok = None
            log_path = None
            rc = 0

            if mode in {"app", "both"}:
                branch = self._git_current_branch()
                yield {"type": "log", "level": "info", "line": f"App branch: {branch}"}
                yield {"type": "log", "level": "info", "line": "--- App: Git commit / push ---"}
                for event in self._iter_git_commit_push(commit_message=commit_message):
                    if event.get("type") == "push_done":
                        push_info = event.get("push") or {}
                    else:
                        yield event

                host = self.vps["VPS_HOST"]
                user = self.vps["VPS_USER"]
                port = int(self.vps.get("VPS_PORT") or "22")
                app_dir = self.vps["VPS_PATH"]
                repo = self.vps.get("GIT_REPO_URL") or "https://github.com/rj22884/JTCS-Final.git"
                yield {
                    "type": "log",
                    "level": "info",
                    "line": f"--- App SSH {user}@{host}:{app_dir} ---",
                }
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
                    yield {"type": "log", "level": "info", "line": "Connecting to VPS (App)…"}
                    client.connect(
                        host,
                        port=port,
                        username=user,
                        password=password,
                        timeout=45,
                        allow_agent=False,
                        look_for_keys=False,
                    )
                    yield {"type": "log", "level": "info", "line": "Connected. Running deploy.sh…"}
                    _stdin, stdout, stderr = client.exec_command(remote_cmd, get_pty=True)
                    while True:
                        line = stdout.readline()
                        if not line:
                            break
                        log_chunks.append(line)
                        evt = emit(line)
                        if evt:
                            yield evt
                    err = stderr.read().decode("utf-8", errors="replace")
                    if err:
                        for part in err.splitlines():
                            log_chunks.append(part + "\n")
                            evt = emit(part, level="warn")
                            if evt:
                                yield evt
                    rc = stdout.channel.recv_exit_status()
                finally:
                    client.close()

                log_text = "".join(log_chunks)
                log_dir = self.repo_root / "deployment" / "logs"
                log_dir.mkdir(parents=True, exist_ok=True)
                log_path = log_dir / f"utility_deploy_{int(time.time())}.log"
                log_path.write_text(log_text, encoding="utf-8", errors="replace")
                yield {"type": "log", "level": "info", "line": f"App log saved: {log_path.name}"}
                success = rc == 0 and (
                    "DEPLOY_RESULT:SUCCESS" in log_text or "DEPLOYMENT SUCCESS" in log_text
                )
                yield {"type": "log", "level": "info", "line": "Checking App public health…"}
                health_ok = self._check_public_health()
                yield {
                    "type": "log",
                    "level": "info" if health_ok else "warn",
                    "line": f"App health: {'OK' if health_ok else 'FAIL / pending'}",
                }
                if not success:
                    yield {
                        "type": "error",
                        "ok": False,
                        "error": f"App deploy failed (exit {rc}). See {log_path.name}.",
                        "remote_exit": rc,
                        "log_file": str(log_path),
                    }
                    return

            if mode in {"web", "both"}:
                for event in self._iter_deploy_website(
                    password=password,
                    commit_message=commit_message,
                ):
                    if event.get("type") == "web_done":
                        web_ok = bool(event.get("ok"))
                    else:
                        yield event
                if web_ok is False:
                    yield {
                        "type": "error",
                        "ok": False,
                        "error": "Web upload failed. Live log check karo.",
                    }
                    return

            parts = []
            if mode in {"app", "both"}:
                parts.append(
                    f"App deployed (health={'OK' if health_ok else 'check pending'})"
                )
            if mode in {"web", "both"}:
                parts.append("Web uploaded")
            message = ". ".join(parts) + "."
            yield {"type": "log", "level": "info", "line": message}
            yield {
                "type": "done",
                "ok": True,
                "sync_action": f"upload_{mode}",
                "target": mode,
                "push": push_info or {},
                "remote_exit": rc,
                "health_ok": health_ok,
                "log_file": str(log_path) if log_path else "",
                "message": message,
            }
        except Exception as exc:
            yield {"type": "error", "ok": False, "error": str(exc)}

    def _iter_deploy_website(self, *, password: str, commit_message: str):
        """Commit local website repo, upload git bundle, checkout on VPS (same SSH password)."""
        import tempfile

        import paramiko

        web_root = Path(self.web.get("WEB_PATH") or r"D:\JTCS Web Page")
        git_dir = self.web.get("VPS_GIT_DIR") or "/var/repos/jtcsxpert.git"
        web_dir = self.web.get("VPS_WEB_DIR") or "/var/www/jtcsxpert.com"
        live_url = self.web.get("LIVE_URL") or "https://jtcsxpert.com"
        host = self.vps["VPS_HOST"]
        user = self.vps["VPS_USER"]
        port = int(self.vps.get("VPS_PORT") or "22")

        yield {"type": "log", "level": "info", "line": "--- Web: jtcsxpert.com ---"}
        yield {"type": "log", "level": "info", "line": f"Local: {web_root}"}
        yield {"type": "log", "level": "info", "line": f"VPS: {user}@{host}:{web_dir}"}

        if not web_root.is_dir():
            yield {
                "type": "log",
                "level": "error",
                "line": f"Website folder not found: {web_root}",
            }
            yield {"type": "web_done", "ok": False}
            return
        if not (web_root / ".git").exists():
            yield {
                "type": "log",
                "level": "error",
                "line": f"Website is not a git repo: {web_root}",
            }
            yield {"type": "web_done", "ok": False}
            return

        yield {"type": "log", "level": "info", "line": "Web: Git commit (if needed)…"}
        for event in self._iter_git_commit_only(
            repo=web_root, commit_message=commit_message or "Update website"
        ):
            yield event

        bundle_name = f"jtcs-web-{int(time.time())}.bundle"
        local_bundle = Path(tempfile.gettempdir()) / bundle_name
        remote_bundle = f"/tmp/{bundle_name}"
        yield {"type": "log", "level": "info", "line": "Web: Creating git bundle…"}
        bundle = self._run_git("bundle", "create", str(local_bundle), "HEAD", repo=web_root)
        if bundle.returncode != 0:
            yield {
                "type": "log",
                "level": "error",
                "line": (bundle.stderr or bundle.stdout or "git bundle failed").strip(),
            }
            yield {"type": "web_done", "ok": False}
            return

        remote_cmd = (
            f"set -e; "
            f"GIT_DIR='{git_dir}'; WEB_DIR='{web_dir}'; "
            f"mkdir -p \"$GIT_DIR\" \"$WEB_DIR\"; "
            f"if [ ! -f \"$GIT_DIR/HEAD\" ]; then git init --bare \"$GIT_DIR\"; fi; "
            f"git --git-dir=\"$GIT_DIR\" fetch '{remote_bundle}' '+HEAD:refs/heads/main'; "
            f"git --git-dir=\"$GIT_DIR\" symbolic-ref HEAD refs/heads/main; "
            f"git --work-tree=\"$WEB_DIR\" --git-dir=\"$GIT_DIR\" checkout -f main; "
            f"chown -R www-data:www-data \"$WEB_DIR\" 2>/dev/null || true; "
            f"if systemctl list-unit-files 2>/dev/null | grep -q '^jtcs-recruitment.service'; then "
            f"systemctl restart jtcs-recruitment || true; fi; "
            f"rm -f '{remote_bundle}'; "
            f"echo ===WEB_DEPLOY_SUCCESS===; "
            f"echo Deploy complete -\> $WEB_DIR"
        )

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        rc = 1
        try:
            yield {"type": "log", "level": "info", "line": "Connecting to VPS (Web)…"}
            client.connect(
                host,
                port=port,
                username=user,
                password=password,
                timeout=45,
                allow_agent=False,
                look_for_keys=False,
            )
            yield {"type": "log", "level": "info", "line": f"Uploading bundle ({local_bundle.name})…"}
            sftp = client.open_sftp()
            try:
                sftp.put(str(local_bundle), remote_bundle)
            finally:
                sftp.close()
            yield {"type": "log", "level": "info", "line": "Checkout website on VPS…"}
            _stdin, stdout, stderr = client.exec_command(remote_cmd, get_pty=True)
            while True:
                line = stdout.readline()
                if not line:
                    break
                text = line.rstrip("\r\n")
                if text:
                    yield {"type": "log", "level": "info", "line": text}
            err = stderr.read().decode("utf-8", errors="replace")
            if err:
                for part in err.splitlines():
                    if part.strip():
                        yield {"type": "log", "level": "warn", "line": part}
            rc = stdout.channel.recv_exit_status()
        finally:
            client.close()
            try:
                local_bundle.unlink(missing_ok=True)
            except OSError:
                pass

        if rc != 0:
            yield {"type": "log", "level": "error", "line": f"Web deploy failed (exit {rc})."}
            yield {"type": "web_done", "ok": False}
            return

        yield {"type": "log", "level": "info", "line": f"Checking {live_url}…"}
        web_health = self._check_url(live_url)
        yield {
            "type": "log",
            "level": "info" if web_health else "warn",
            "line": f"Web live: {'OK' if web_health else 'FAIL / pending'} ({live_url})",
        }
        yield {"type": "web_done", "ok": True}

    def _iter_git_commit_only(self, *, repo: Path, commit_message: str):
        status = self._run_git("status", "--porcelain", repo=repo)
        if status.returncode != 0:
            raise RuntimeError(status.stderr or f"git status failed in {repo}")
        porcelain = (status.stdout or "").strip()
        if porcelain:
            yield {"type": "log", "level": "info", "line": f"Web changes detected — staging ({repo.name})…"}
            for event in self._iter_git("add", "-A", repo=repo):
                if event.get("type") == "git_rc" and event.get("returncode"):
                    raise RuntimeError("git add failed (website)")
                if event.get("type") == "log":
                    yield event
            for event in self._iter_git("commit", "-m", commit_message, repo=repo):
                if event.get("type") == "git_rc":
                    continue
                yield event
        else:
            yield {"type": "log", "level": "info", "line": "Web: nothing new to commit."}

    def deploy_to_vps(
        self,
        *,
        password: str,
        commit_message: str = "",
        created_by: str = "System",
        target: str = "app",
    ) -> dict:
        """Non-streaming wrapper (collects iter_deploy_to_vps)."""
        final: dict = {"ok": False, "error": "Deploy produced no result."}
        for event in self.iter_deploy_to_vps(
            password=password,
            commit_message=commit_message,
            created_by=created_by,
            target=target,
        ):
            if event.get("type") in {"done", "error"}:
                final = event
        if final.get("type") == "error" or not final.get("ok"):
            raise RuntimeError(final.get("error") or "Deploy failed.")
        return final

    def _check_public_health(self) -> bool:
        url = self.vps.get("PUBLIC_HEALTH_URL") or "https://app.jtcsxpert.com/health"
        return self._check_url(url)

    def _check_url(self, url: str) -> bool:
        try:
            import urllib.request

            with urllib.request.urlopen(url, timeout=25) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _run_git(self, *args: str, repo: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(repo or self.repo_root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def _iter_git(self, *args: str, repo: Path | None = None):
        """Run git and yield log events for stdout/stderr lines."""
        root = str(repo or self.repo_root)
        cmd = ["git", "-C", root, *args]
        yield {"type": "log", "level": "info", "line": "$ " + " ".join(args)}
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            text = line.rstrip("\r\n")
            if text:
                yield {"type": "log", "level": "info", "line": text}
        rc = proc.wait()
        yield {"type": "git_rc", "args": list(args), "returncode": rc}

    def _git_current_branch(self) -> str:
        proc = self._run_git("branch", "--show-current")
        branch = (proc.stdout or "").strip()
        if not branch:
            proc = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
            branch = (proc.stdout or "").strip()
        if not branch or branch == "HEAD":
            raise RuntimeError("Cannot determine git branch. Checkout a branch first.")
        return branch

    def _iter_git_commit_push(self, *, commit_message: str):
        status = self._run_git("status", "--porcelain")
        if status.returncode != 0:
            raise RuntimeError(status.stderr or "git status failed")
        porcelain = (status.stdout or "").strip()
        if porcelain:
            yield {"type": "log", "level": "info", "line": "Changes detected — staging…"}
            for event in self._iter_git("add", "-A"):
                if event.get("type") == "git_rc" and event.get("returncode"):
                    raise RuntimeError("git add failed")
                if event.get("type") == "log":
                    yield event
            for event in self._iter_git("commit", "-m", commit_message):
                if event.get("type") == "git_rc":
                    # allow "nothing to commit" race
                    continue
                yield event
        else:
            yield {"type": "log", "level": "info", "line": "Nothing new to commit."}

        for event in self._iter_git("push", "-u", "origin", "HEAD"):
            if event.get("type") == "git_rc" and event.get("returncode"):
                raise RuntimeError("git push failed — check GitHub auth / network")
            if event.get("type") == "log":
                yield event

        head = self._run_git("rev-parse", "--short", "HEAD")
        push = {
            "commit": (head.stdout or "").strip(),
            "pushed": True,
            "message": commit_message,
        }
        yield {
            "type": "log",
            "level": "info",
            "line": f"Push OK — commit {push['commit']}",
        }
        yield {"type": "push_done", "push": push}

    def _git_commit_push(self, *, commit_message: str) -> dict:
        push = {"commit": "", "pushed": True, "message": commit_message}
        for event in self._iter_git_commit_push(commit_message=commit_message):
            if event.get("type") == "push_done":
                push = event.get("push") or push
        return push
