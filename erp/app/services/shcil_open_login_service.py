"""Open official SHCIL login and fill User ID + password only. No captcha, OTP, or stamp pages."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from app.services.credentials_master_service import CredentialsMasterService

SHCIL_LOGIN_URL = (
    "https://www.shcilestamp.com/eStampIndia/useradmin/UserAdminLoginServlet"
    "?rDoAction=LoadLoginPage"
)

_ROLE_KIND_PORTS = {
    ("deo", "chrome"): 9361,
    ("deo", "edge"): 9362,
    ("admin", "chrome"): 9363,
    ("admin", "edge"): 9364,
}
_LOCK = threading.Lock()
_SESSIONS: dict[str, dict] = {}
_KIND_FILE = Path(tempfile.gettempdir()) / "jtcs-shcil-browser-kind.txt"

_CHROME_PATHS = [
    os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]
_EDGE_PATHS = [
    os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


class ShcilOpenLoginService:
    @staticmethod
    def _first_existing(paths: list[str], which_names: tuple[str, ...]) -> str | None:
        for path in paths:
            if path and Path(path).is_file():
                return path
        for name in which_names:
            found = shutil.which(name)
            if found:
                return found
        return None

    @staticmethod
    def _registry_exe(kind: str) -> str | None:
        if os.name != "nt":
            return None
        try:
            import winreg
        except ImportError:
            return None
        exe_name = "msedge.exe" if kind == "edge" else "chrome.exe"
        keys = (
            (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"),
            (winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"),
            (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"),
        )
        for hive, path in keys:
            try:
                with winreg.OpenKey(hive, path) as key:
                    value, _ = winreg.QueryValueEx(key, "")
                if value and Path(value).is_file():
                    return value
            except OSError:
                continue
        return None

    def _find_browser_exe(self, kind: str) -> str | None:
        if kind == "edge":
            found = self._first_existing(_EDGE_PATHS, ("msedge", "microsoft-edge"))
        else:
            found = self._first_existing(_CHROME_PATHS, ("chrome", "google-chrome", "chromium"))
        if found:
            return found
        found = self._registry_exe(kind)
        if found:
            return found
        users = Path(r"C:\Users")
        if users.is_dir():
            pattern = (
                r"*\AppData\Local\Microsoft\Edge\Application\msedge.exe"
                if kind == "edge"
                else r"*\AppData\Local\Google\Chrome\Application\chrome.exe"
            )
            for path in users.glob(pattern):
                if path.is_file():
                    return str(path)
        return None

    @staticmethod
    def _kind_from_ua(user_agent: str) -> str | None:
        text = (user_agent or "").lower()
        if "edg/" in text or "edgios" in text or "edge/" in text:
            return "edge"
        if "chrome/" in text or "chromium" in text:
            return "chrome"
        return None

    @staticmethod
    def _kind_from_path(path: str | None) -> str | None:
        name = Path(path or "").name.lower()
        if "msedge" in name or name == "microsoft-edge":
            return "edge"
        if "chrome" in name or "chromium" in name:
            return "chrome"
        return None

    def _remember_kind(self, role: str, kind: str) -> None:
        try:
            raw = {}
            if _KIND_FILE.is_file():
                for line in _KIND_FILE.read_text(encoding="utf-8").splitlines():
                    if "=" in line:
                        key, value = line.split("=", 1)
                        raw[key.strip()] = value.strip()
            raw[role] = kind
            _KIND_FILE.write_text("".join(f"{key}={value}\n" for key, value in raw.items()), encoding="utf-8")
        except Exception:
            pass

    def _saved_kind(self, role: str) -> str | None:
        try:
            if not _KIND_FILE.is_file():
                return None
            for line in _KIND_FILE.read_text(encoding="utf-8").splitlines():
                if line.startswith(f"{role}="):
                    kind = line.split("=", 1)[1].strip().lower()
                    if kind in {"chrome", "edge"}:
                        return kind
        except Exception:
            return None
        return None

    def _detect_kind(self, session: dict | None) -> str | None:
        if not session:
            return None
        stored = session.get("browser_kind")
        if stored in {"chrome", "edge"}:
            return stored
        from_path = self._kind_from_path(session.get("exe"))
        if from_path:
            return from_path
        try:
            page = session.get("page")
            ua = page.evaluate("() => navigator.userAgent || ''") if page is not None else ""
        except Exception:
            ua = ""
        return self._kind_from_ua(ua)

    def _other_role(self, role: str) -> str:
        return "admin" if role == "deo" else "deo"

    def _other_browser_kind(self, playwright, role: str) -> str | None:
        other = self._other_role(role)
        live = self._reuse(other)
        kind = self._detect_kind(live)
        if kind:
            return kind
        saved = self._saved_kind(other)
        if saved and live is not None:
            return saved
        for kind_guess in ("chrome", "edge"):
            port = _ROLE_KIND_PORTS[(other, kind_guess)]
            try:
                browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
                context = browser.contexts[0] if browser.contexts else None
                page = context.pages[0] if context and context.pages else None
                ua = page.evaluate("() => navigator.userAgent || ''") if page is not None else ""
                kind = self._kind_from_ua(ua) or kind_guess
                self._remember_kind(other, kind)
                return kind
            except Exception:
                continue
        return None

    def _pick_browser_kind(self, playwright, role: str) -> str:
        other_kind = self._other_browser_kind(playwright, role)
        preferred = None
        if other_kind == "chrome":
            preferred = "edge"
        elif other_kind == "edge":
            preferred = "chrome"
        else:
            preferred = "chrome" if role == "deo" else "edge"
        if self._find_browser_exe(preferred):
            return preferred
        for kind in ("chrome", "edge"):
            if kind != preferred and self._find_browser_exe(kind):
                return kind
        return preferred

    def _reuse(self, role: str):
        with _LOCK:
            session = _SESSIONS.get(role)
        if not session:
            return None
        try:
            page = session.get("page")
            browser = session.get("browser")
            if page is None:
                return None
            if browser is not None and hasattr(browser, "is_connected") and not browser.is_connected():
                return None
            _ = page.url
            return session
        except Exception:
            return None

    def _session(self, playwright, browser, proc, exe: str | None, kind: str):
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()
        detected = self._kind_from_path(exe) or kind
        try:
            detected = self._kind_from_ua(page.evaluate("() => navigator.userAgent || ''")) or detected
        except Exception:
            pass
        return {
            "playwright": playwright,
            "browser": browser,
            "context": context,
            "page": page,
            "proc": proc,
            "exe": exe,
            "browser_kind": detected,
        }

    def _connect_cdp(self, playwright, port: int, kind: str | None = None):
        try:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            return self._session(playwright, browser, None, None, kind or "chrome")
        except Exception:
            return None

    def _attach(self, playwright, role: str):
        live = self._reuse(role)
        if live is not None:
            kind = self._detect_kind(live) or self._saved_kind(role)
            if kind:
                live["browser_kind"] = kind
                self._remember_kind(role, kind)
            return live

        kind = self._pick_browser_kind(playwright, role)
        tried: list[str] = []
        for candidate in (kind, "chrome", "edge"):
            if candidate in tried:
                continue
            tried.append(candidate)
            port = _ROLE_KIND_PORTS[(role, candidate)]
            existing = self._connect_cdp(playwright, port, candidate)
            if existing is not None:
                existing["browser_kind"] = existing.get("browser_kind") or candidate
                self._remember_kind(role, existing["browser_kind"])
                return existing
            exe = self._find_browser_exe(candidate)
            if not exe:
                continue
            session = self._launch_exe(playwright, role, candidate, exe, port)
            if session is not None:
                self._remember_kind(role, session.get("browser_kind") or candidate)
                return session

        kind = tried[0] if tried else "chrome"
        port = _ROLE_KIND_PORTS[(role, kind)]
        profile_dir = Path(tempfile.gettempdir()) / f"jtcs-shcil-{role}-{kind}-profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        try:
            context = playwright.chromium.launch_persistent_context(
                str(profile_dir),
                headless=False,
                args=[f"--remote-debugging-port={port}", "--no-first-run", "--no-default-browser-check"],
            )
            page = context.pages[0] if context.pages else context.new_page()
            session = {
                "playwright": playwright,
                "browser": context,
                "context": context,
                "page": page,
                "proc": None,
                "exe": None,
                "browser_kind": kind,
            }
            self._remember_kind(role, kind)
            return session
        except Exception as exc:
            raise RuntimeError(
                f"Could not open a browser for SHCIL {role.upper()} login. "
                "Install Google Chrome or Microsoft Edge on this PC and try again."
            ) from exc

    def _launch_exe(self, playwright, role: str, kind: str, exe: str, port: int):
        profile_dir = Path(tempfile.gettempdir()) / f"jtcs-shcil-{role}-{kind}-profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen(
            [
                exe,
                f"--remote-debugging-port={port}",
                f"--user-data-dir={str(profile_dir)}",
                "--no-first-run",
                "--no-default-browser-check",
                SHCIL_LOGIN_URL,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        browser = None
        for _ in range(50):
            time.sleep(0.3)
            try:
                browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
                break
            except Exception:
                if proc.poll() is not None:
                    break
        if browser is None:
            try:
                proc.terminate()
            except Exception:
                pass
            return None
        return self._session(playwright, browser, proc, exe, kind)

    @staticmethod
    def _logged_in(page) -> bool:
        try:
            url = (page.url or "").lower()
            text = (page.inner_text("body") or "").lower()
        except Exception:
            return False
        if "loadloginpage" in url or "validatelogin" in url:
            return False
        return "logout" in text or ("welcome" in text and "login" not in url)

    def _fill_credentials(self, page, user_id: str, password: str) -> None:
        if self._logged_in(page):
            return
        page.goto(SHCIL_LOGIN_URL, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(400)
        if self._logged_in(page):
            return
        user = page.locator(
            'input[name="userId"], input[name="userid"], input[name="UserID"], '
            'input[id="userId"], input[name="userName"], input[name="username"]'
        ).first
        pwd = page.locator('input[name="userPwd"], input[name="password"], input[type="password"]').first
        user.wait_for(state="visible", timeout=15_000)
        user.fill("")
        user.fill(user_id)
        pwd.fill("")
        pwd.fill(password)

    @staticmethod
    def _use_client_browser() -> bool:
        """VPS / headless Linux cannot open a window on the operator's PC."""
        try:
            from app.utils.runtime_env import is_vps_runtime

            if is_vps_runtime():
                return True
        except Exception:
            pass
        if os.name != "nt" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            return True
        return False

    def _client_payload(self, role: str, user_id: str, password: str) -> dict:
        label = role.upper()
        return {
            "ok": True,
            "mode": "client",
            "role": role,
            "user_id": user_id,
            "password": password,
            "login_url": SHCIL_LOGIN_URL,
            "message": (
                f"SHCIL {label} login page opened in this browser. "
                "User ID and password are shown below — paste them on the SHCIL page, "
                "type the captcha, then click LOGIN."
            ),
        }

    def open_login(self, role: str) -> dict:
        wanted = "admin" if str(role or "").strip().lower() == "admin" else "deo"
        cred = CredentialsMasterService().find_shcil_login(role=wanted)
        if not cred:
            label = "Stamp Admin" if wanted == "admin" else "Stamp DEO"
            raise ValueError(f"Add {label} User ID and password in Credentials Master first.")
        user_id = (cred.get("user_id") or "").strip()
        password = cred.get("password") or ""
        if not user_id or not password:
            raise ValueError("SHCIL User ID or password is missing in Credentials Master.")

        if self._use_client_browser():
            return self._client_payload(wanted, user_id, password)

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return self._client_payload(wanted, user_id, password)

        started = threading.Event()
        error_box: list[BaseException] = []
        result_box: list[dict] = []

        def worker() -> None:
            playwright = None
            session = None
            launched_new = False
            try:
                session = self._reuse(wanted)
                if session is None:
                    playwright = sync_playwright().start()
                    session = self._attach(playwright, wanted)
                    launched_new = bool(session.get("proc"))
                page = session["page"]
                kind = self._detect_kind(session) or self._saved_kind(wanted) or "chrome"
                session["browser_kind"] = kind
                self._remember_kind(wanted, kind)
                with _LOCK:
                    _SESSIONS[wanted] = session
                browser_label = "Microsoft Edge" if kind == "edge" else "Google Chrome"
                already = self._logged_in(page)
                if already:
                    result_box.append(
                        {
                            "ok": True,
                            "mode": "desktop",
                            "role": wanted,
                            "user_id": user_id,
                            "browser": kind,
                            "already_logged_in": True,
                            "login_url": SHCIL_LOGIN_URL,
                            "message": (
                                f"SHCIL {wanted.upper()} is already open in {browser_label}. "
                                "The app will not touch stamp pages. Close that window yourself when finished."
                            ),
                        }
                    )
                else:
                    self._fill_credentials(page, user_id, password)
                    result_box.append(
                        {
                            "ok": True,
                            "mode": "desktop",
                            "role": wanted,
                            "user_id": user_id,
                            "browser": kind,
                            "already_logged_in": False,
                            "login_url": SHCIL_LOGIN_URL,
                            "message": (
                                f"SHCIL {wanted.upper()} opened in {browser_label}. "
                                "User ID and password are filled. Type the captcha and click LOGIN yourself. "
                                "Close that window yourself when finished."
                            ),
                        }
                    )
                started.set()
                browser = session.get("browser")
                while True:
                    try:
                        if hasattr(browser, "is_connected") and not browser.is_connected():
                            break
                    except Exception:
                        break
                    page.wait_for_timeout(1000)
            except BaseException as exc:
                error_box.append(exc)
                started.set()
                if launched_new and session:
                    try:
                        if session.get("browser") is not None:
                            session["browser"].close()
                    except Exception:
                        pass
                    try:
                        if session.get("proc") is not None:
                            session["proc"].terminate()
                    except Exception:
                        pass
                if playwright is not None and (launched_new or session is None):
                    try:
                        playwright.stop()
                    except Exception:
                        pass

        threading.Thread(target=worker, name=f"shcil-open-{wanted}", daemon=True).start()
        if not started.wait(timeout=90):
            raise ValueError("SHCIL login window is taking too long to open. Try again.")
        if error_box:
            return self._client_payload(wanted, user_id, password)
        return result_box[0] if result_box else self._client_payload(wanted, user_id, password)
