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

    def _find_browser_exe(self, kind: str) -> str | None:
        if kind == "edge":
            return self._first_existing(_EDGE_PATHS, ("msedge", "microsoft-edge"))
        return self._first_existing(_CHROME_PATHS, ("chrome", "google-chrome", "chromium"))

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
        return self._saved_kind(other)

    def _pick_browser_kind(self, playwright, role: str) -> str:
        other_kind = self._other_browser_kind(playwright, role)
        if other_kind == "chrome":
            return "edge"
        if other_kind == "edge":
            return "chrome"
        return "chrome" if role == "deo" else "edge"

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
        port = _ROLE_KIND_PORTS[(role, kind)]
        existing = self._connect_cdp(playwright, port, kind)
        if existing is not None and (existing.get("browser_kind") or kind) == kind:
            existing["browser_kind"] = kind
            self._remember_kind(role, kind)
            return existing

        exe = self._find_browser_exe(kind)
        if not exe:
            other = "Edge" if kind == "chrome" else "Chrome"
            raise RuntimeError(
                f"{role.upper()} must open in {kind.title()} because the other SHCIL login is already in {other}. "
                f"{kind.title()} was not found on this PC."
            )

        profile_dir = Path(tempfile.gettempdir()) / f"jtcs-shcil-{role}-{kind}-profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        last_err: BaseException | None = None
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
            except Exception as err:
                last_err = err
                if proc.poll() is not None:
                    break
        if browser is not None:
            session = self._session(playwright, browser, proc, exe, kind)
            self._remember_kind(role, session.get("browser_kind") or kind)
            return session
        try:
            proc.terminate()
        except Exception:
            pass
        raise RuntimeError(
            f"Could not open {kind.title()} for SHCIL {role.upper()} login. "
            "Run Stamp Activity on the same PC where Chrome and Edge are installed."
        ) from last_err

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

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ValueError("Playwright is not installed. Run: pip install playwright") from exc

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
                            "role": wanted,
                            "user_id": user_id,
                            "browser": kind,
                            "already_logged_in": True,
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
                            "role": wanted,
                            "user_id": user_id,
                            "browser": kind,
                            "already_logged_in": False,
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
            raise ValueError(str(error_box[0]))
        return result_box[0] if result_box else {"ok": True, "role": wanted, "user_id": user_id}
