from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

INCOME_TAX_HOME_URL = "https://eportal.incometax.gov.in/iec/foservices/"
INCOME_TAX_LOGIN_URL = "https://eportal.incometax.gov.in/iec/foservices/#/login"

PROFILE_HASHES = (
    "#/userProfile",
    "#/profile",
    "#/myProfile",
    "#/dashboard/userProfile",
    "#/services/myProfile",
    "#/taxpayerProfile",
)

# Keep references so headed browsers are not garbage-collected / closed early.
_ACTIVE_SESSIONS: list[Any] = []
_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()

_STEALTH_INIT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'languages', { get: () => ['en-IN', 'en-GB', 'en'] });
"""

_LABEL_ALIASES = {
    "customer_name": (
        "name",
        "taxpayer name",
        "assessee name",
        "full name",
        "applicant name",
        "person name",
    ),
    "pan_number": ("pan", "permanent account number", "pan number"),
    "aadhaar_number": ("aadhaar", "aadhar", "uid", "aadhaar number", "aadhar number"),
    "date_of_birth": ("date of birth", "dob", "birth date"),
    "gender": ("gender", "sex"),
    "email_id": ("email", "e-mail", "email id", "email address"),
    "mobile_number": ("mobile", "mobile number", "mobile no", "contact number", "phone"),
    "address_line1": (
        "address",
        "residential address",
        "permanent address",
        "communication address",
        "address line 1",
    ),
    "city": ("city", "town", "district"),
    "state": ("state", "state/ut", "state / ut"),
    "pincode": ("pin", "pincode", "pin code", "zip"),
    "father_husband_name": ("father", "father name", "father's name", "husband name"),
}


class CustomerPortalSyncService:
    """Customer Master only — Income Tax portal login assist + profile sync."""

    @staticmethod
    def _normalize_user_id(user_id: str) -> str:
        return re.sub(r"\s+", "", (user_id or "")).upper()

    @staticmethod
    def _set_job(job_id: str, **kwargs) -> None:
        with _LOCK:
            job = _JOBS.get(job_id) or {}
            job.update(kwargs)
            _JOBS[job_id] = job

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with _LOCK:
            job = _JOBS.get(job_id)
            return dict(job) if job else None

    @staticmethod
    def _find_browser_exe() -> tuple[str | None, str | None]:
        candidates = [
            (
                "chrome",
                [
                    os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                    os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
                    os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
                ],
            ),
            (
                "msedge",
                [
                    os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
                    os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
                ],
            ),
        ]
        for channel, paths in candidates:
            for path in paths:
                if path and Path(path).is_file():
                    return path, channel
        which_chrome = shutil.which("chrome") or shutil.which("google-chrome")
        if which_chrome:
            return which_chrome, "chrome"
        which_edge = shutil.which("msedge")
        if which_edge:
            return which_edge, "msedge"
        return None, None

    @staticmethod
    def _page_denied(page) -> bool:
        try:
            text = page.inner_text("body")
        except Exception:
            try:
                text = page.content() or ""
            except Exception:
                return False
        return "permission denied" in (text or "").lower()

    def _open_login_page(self, page) -> None:
        page.goto(INCOME_TAX_HOME_URL, wait_until="domcontentloaded", timeout=120_000)
        page.wait_for_timeout(2000)
        if self._page_denied(page):
            page.wait_for_timeout(1500)
            page.goto(INCOME_TAX_HOME_URL, wait_until="domcontentloaded", timeout=120_000)
            page.wait_for_timeout(2000)

        clicked = False
        for sel in (
            "a:has-text('Login')",
            "button:has-text('Login')",
            "text=Login",
        ):
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=3000)
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            page.goto(INCOME_TAX_LOGIN_URL, wait_until="domcontentloaded", timeout=120_000)
        page.wait_for_timeout(2000)
        if self._page_denied(page):
            raise RuntimeError(
                "Income Tax portal returned 'Permission Denied'. Close the window and retry."
            )

    @staticmethod
    def _continue_enabled(page) -> bool:
        try:
            return bool(
                page.evaluate(
                    """() => {
                        const buttons = Array.from(document.querySelectorAll('button'));
                        const btn = buttons.find((b) => /continue/i.test((b.textContent || '').trim()));
                        if (!btn) return false;
                        return !btn.disabled && btn.getAttribute('disabled') == null
                            && !btn.classList.contains('disabled');
                    }"""
                )
            )
        except Exception:
            return False

    def _click_continue(self, page) -> bool:
        try:
            page.wait_for_function(
                """() => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const btn = buttons.find((b) => /continue/i.test((b.textContent || '').trim()));
                    return !!(btn && !btn.disabled);
                }""",
                timeout=12_000,
            )
        except Exception:
            pass
        for sel in (
            "button:has-text('Continue')",
            "button:has-text('CONTINUE')",
        ):
            try:
                btn = page.locator(sel).first
                if btn.count():
                    btn.click(timeout=5_000)
                    return True
            except Exception:
                continue
        try:
            page.get_by_role("button", name=re.compile(r"Continue", re.I)).first.click(timeout=5_000)
            return True
        except Exception:
            return False

    def _dismiss_dual_login(self, page) -> bool:
        """If 'Dual Login Detected!' appears, click Login Here."""
        try:
            dual = page.get_by_text(re.compile(r"Dual Login Detected", re.I))
            if not dual.count() or not dual.first.is_visible():
                # Also check body text quickly
                try:
                    body = (page.inner_text("body") or "").lower()
                except Exception:
                    body = ""
                if "dual login" not in body:
                    return False
        except Exception:
            return False

        for sel in (
            "button:has-text('Login Here')",
            "button:has-text('LOGIN HERE')",
            "text=Login Here",
            "[role='dialog'] button:has-text('Login')",
        ):
            try:
                btn = page.locator(sel).first
                if btn.count() and btn.is_visible():
                    btn.click(timeout=4000)
                    page.wait_for_timeout(1200)
                    return True
            except Exception:
                continue
        try:
            page.get_by_role("button", name=re.compile(r"Login Here", re.I)).first.click(timeout=4000)
            page.wait_for_timeout(1200)
            return True
        except Exception:
            return False

    def _handle_interrupt_dialogs(self, page) -> None:
        """Handle common portal popups that block Continue / login."""
        for _ in range(3):
            if not self._dismiss_dual_login(page):
                break
            page.wait_for_timeout(500)

    def _check_secure_access_box(self, page) -> None:
        # Prefer clicking the label / mat-checkbox near the secure access text.
        selectors = (
            "text=/confirm your secure access message/i",
            "label:has-text('secure access message')",
            "mat-checkbox:has-text('secure access')",
            ".mat-checkbox:has-text('secure access')",
            "input[type='checkbox']",
        )
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if not loc.count():
                    continue
                loc.click(timeout=2500, force=True)
                page.wait_for_timeout(300)
                return
            except Exception:
                continue
        # JS fallback — click first unchecked checkbox on password step
        try:
            page.evaluate(
                """() => {
                    const boxes = Array.from(document.querySelectorAll('input[type=checkbox]'));
                    const box = boxes.find((b) => !b.checked);
                    if (box) {
                        box.click();
                        box.dispatchEvent(new Event('change', { bubbles: true }));
                        box.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                    const mats = Array.from(document.querySelectorAll('mat-checkbox'));
                    const mat = mats.find((m) => !m.classList.contains('mat-checkbox-checked'));
                    if (mat) mat.click();
                }"""
            )
        except Exception:
            pass

    def _force_enable_continue(self, page) -> None:
        try:
            page.evaluate(
                """() => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const btn = buttons.find((b) => /continue/i.test((b.textContent || '').trim()));
                    if (!btn) return;
                    btn.disabled = false;
                    btn.removeAttribute('disabled');
                    btn.classList.remove('disabled', 'btn-disabled');
                    btn.setAttribute('aria-disabled', 'false');
                }"""
            )
        except Exception:
            pass

    def _fill_user_id_and_continue(self, page, user_id: str) -> None:
        user_input = page.locator(
            'input[placeholder*="PAN" i], '
            'input[placeholder*="AADHAAR" i], '
            'input[placeholder*="OTHER" i], '
            'input[type="text"]:visible'
        ).first
        user_input.wait_for(state="visible", timeout=60_000)
        user_input.click()
        user_input.fill("")
        user_input.type(user_id, delay=45)
        user_input.dispatch_event("input")
        user_input.dispatch_event("change")
        user_input.press("Tab")
        page.wait_for_timeout(500)
        self._click_continue(page)
        page.wait_for_timeout(1200)
        self._handle_interrupt_dialogs(page)

    def _fill_password_step(self, page, password: str) -> None:
        """
        Fill password + tick secure-access checkbox, but do NOT auto-click Continue.

        Auto-submitting Continue on this portal often returns:
        "Error: Request is not authenticated"
        User must click Continue manually after captcha/session is valid.
        """
        if not password:
            return
        pwd = page.locator('input[type="password"]:visible').first
        pwd.wait_for(state="visible", timeout=45_000)
        pwd.click()
        pwd.fill("")
        pwd.type(password, delay=40)
        pwd.dispatch_event("input")
        pwd.dispatch_event("change")
        pwd.press("Tab")
        page.wait_for_timeout(400)

        self._check_secure_access_box(page)
        page.wait_for_timeout(400)

        if not self._continue_enabled(page):
            # Re-trigger Angular validators only — never force-enable + auto-submit.
            try:
                pwd.click()
                pwd.press("End")
                pwd.type(" ", delay=20)
                pwd.press("Backspace")
                pwd.dispatch_event("input")
                pwd.dispatch_event("change")
            except Exception:
                pass
            self._check_secure_access_box(page)
            page.wait_for_timeout(300)

        self._handle_interrupt_dialogs(page)
        # Leave Continue for the user. Forced/automated Continue causes auth errors.

    def _wait_for_login(self, page, timeout_ms: int = 180_000) -> bool:
        """Wait until URL leaves login/password, or dashboard markers appear."""
        deadline = time.time() + (timeout_ms / 1000.0)
        while time.time() < deadline:
            try:
                url = (page.url or "").lower()
                self._handle_interrupt_dialogs(page)
                if "permission denied" in (page.inner_text("body") or "").lower():
                    return False
                if "#/login" not in url and "login/password" not in url:
                    if "foservices" in url:
                        return True
                # Logged-in markers
                for marker in ("Logout", "My Profile", "Dashboard", "e-File"):
                    try:
                        if page.get_by_text(marker, exact=False).first.is_visible():
                            if "#/login" not in url:
                                return True
                    except Exception:
                        pass
            except Exception:
                pass
            page.wait_for_timeout(1000)
        return "#/login" not in (page.url or "").lower()

    @staticmethod
    def _clean_value(value: str) -> str:
        text = re.sub(r"\s+", " ", (value or "")).strip()
        if text.lower() in {"", "-", "na", "n/a", "null", "undefined"}:
            return ""
        return text

    def _scrape_profile_dict(self, page) -> dict[str, str]:
        """Extract labeled fields from whatever profile/dashboard DOM is visible."""
        raw = page.evaluate(
            """() => {
                const out = {};
                const push = (k, v) => {
                    const key = String(k || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    const val = String(v || '').replace(/\\s+/g, ' ').trim();
                    if (!key || !val || key.length > 80) return;
                    if (!(key in out)) out[key] = val;
                };
                document.querySelectorAll('tr').forEach((tr) => {
                    const cells = tr.querySelectorAll('th,td');
                    if (cells.length >= 2) push(cells[0].innerText, cells[1].innerText);
                });
                document.querySelectorAll('dl').forEach((dl) => {
                    const dts = dl.querySelectorAll('dt');
                    dts.forEach((dt) => {
                        const dd = dt.nextElementSibling;
                        if (dd && dd.tagName === 'DD') push(dt.innerText, dd.innerText);
                    });
                });
                document.querySelectorAll('label, .label, mat-label, .form-label, .field-label').forEach((lab) => {
                    const key = lab.innerText;
                    let val = '';
                    const forId = lab.getAttribute('for');
                    if (forId) {
                        const el = document.getElementById(forId);
                        if (el) val = el.value || el.innerText || '';
                    }
                    if (!val) {
                        const sib = lab.nextElementSibling;
                        if (sib) val = sib.value || sib.innerText || '';
                    }
                    if (!val && lab.parentElement) {
                        const input = lab.parentElement.querySelector('input, textarea, select, .value, span');
                        if (input) val = input.value || input.innerText || '';
                    }
                    push(key, val);
                });
                // Generic "Label : Value" lines
                const body = document.body ? document.body.innerText : '';
                body.split('\\n').forEach((line) => {
                    const m = line.match(/^\\s*([^:]{2,60})\\s*:\\s*(.+?)\\s*$/);
                    if (m) push(m[1], m[2]);
                });
                return out;
            }"""
        )
        raw = raw or {}
        mapped: dict[str, str] = {}
        for field, aliases in _LABEL_ALIASES.items():
            for alias in aliases:
                for key, value in raw.items():
                    if alias in key:
                        cleaned = self._clean_value(value)
                        if cleaned:
                            mapped[field] = cleaned
                            break
                if field in mapped:
                    break

        # Normalize PAN / Aadhaar
        if mapped.get("pan_number"):
            pan = re.sub(r"[^A-Za-z0-9]", "", mapped["pan_number"]).upper()
            if re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan):
                mapped["pan_number"] = pan
        if mapped.get("aadhaar_number"):
            aad = re.sub(r"\D", "", mapped["aadhaar_number"])
            if len(aad) >= 12:
                mapped["aadhaar_number"] = aad[:12]
        if mapped.get("mobile_number"):
            mob = re.sub(r"\D", "", mapped["mobile_number"])
            if len(mob) >= 10:
                mapped["mobile_number"] = mob[-10:]
        if mapped.get("gender"):
            g = mapped["gender"].strip().lower()
            if g.startswith("m"):
                mapped["gender"] = "Male"
            elif g.startswith("f"):
                mapped["gender"] = "Female"
            elif g:
                mapped["gender"] = "Other"
        if mapped.get("date_of_birth"):
            dob = mapped["date_of_birth"]
            # dd/mm/yyyy or dd-mm-yyyy -> yyyy-mm-dd
            m = re.search(r"(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{4})", dob)
            if m:
                d, mo, y = m.group(1).zfill(2), m.group(2).zfill(2), m.group(3)
                mapped["date_of_birth"] = f"{y}-{mo}-{d}"
        return mapped

    def _collect_profile(self, page, fallback_pan: str) -> dict[str, str]:
        collected: dict[str, str] = {}
        # Try menu click first
        for text in ("My Profile", "Profile", "Taxpayer Profile", "User Profile"):
            try:
                link = page.get_by_text(text, exact=False).first
                if link.is_visible():
                    link.click(timeout=3000)
                    page.wait_for_timeout(2000)
                    collected.update(self._scrape_profile_dict(page))
                    if collected.get("customer_name") or collected.get("pan_number"):
                        break
            except Exception:
                continue

        for hash_path in PROFILE_HASHES:
            try:
                target = "https://eportal.incometax.gov.in/iec/foservices/" + hash_path
                page.goto(target, wait_until="domcontentloaded", timeout=60_000)
            except Exception:
                try:
                    page.evaluate(f"window.location.hash = '{hash_path[1:]}'")
                except Exception:
                    continue
            page.wait_for_timeout(2000)
            part = self._scrape_profile_dict(page)
            for k, v in part.items():
                if v and k not in collected:
                    collected[k] = v
            if collected.get("customer_name") and collected.get("pan_number"):
                break

        # Always keep login PAN if portal didn't return it
        if fallback_pan and not collected.get("pan_number"):
            collected["pan_number"] = fallback_pan

        # Last resort: scrape current page once more
        if len(collected) <= 1:
            collected.update(self._scrape_profile_dict(page))
            if fallback_pan and not collected.get("pan_number"):
                collected["pan_number"] = fallback_pan
        return collected

    def _attach_browser(self, playwright):
        exe, _channel = self._find_browser_exe()
        if not exe:
            raise RuntimeError("Google Chrome / Edge not found.")

        profile_dir = Path(tempfile.gettempdir()) / "jtcs-cm-it-portal-profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        port = 9333
        for candidate in range(9333, 9360):
            port = candidate
            break

        # Do NOT pass AutomationControlled flag — it shows Chrome warning and breaks Angular Continue.
        proc = subprocess.Popen(
            [
                exe,
                f"--remote-debugging-port={port}",
                f"--user-data-dir={str(profile_dir)}",
                "--no-first-run",
                "--no-default-browser-check",
                INCOME_TAX_HOME_URL,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        browser = None
        last_err: BaseException | None = None
        for _ in range(50):
            time.sleep(0.3)
            try:
                browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
                break
            except Exception as err:  # noqa: BLE001
                last_err = err
                if proc.poll() is not None:
                    break
        if browser is None:
            try:
                proc.terminate()
            except Exception:
                pass
            raise RuntimeError(f"Could not attach to Chrome/Edge ({last_err})")

        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.add_init_script(_STEALTH_INIT)
        except Exception:
            pass
        return {"playwright": playwright, "browser": browser, "context": context, "page": page, "proc": proc}

    def launch_income_tax_login(self, user_id: str, password: str | None = None) -> dict:
        user_id = self._normalize_user_id(user_id)
        password = password or ""
        if not user_id:
            raise ValueError("Income Tax User ID (PAN) is required.")

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ValueError("Playwright not installed. Run: pip install playwright") from exc

        job_id = uuid.uuid4().hex
        self._set_job(
            job_id,
            status="running",
            message="Opening Income Tax portal...",
            data=None,
            user_id=user_id,
        )

        started = threading.Event()
        error_box: list[BaseException] = []

        def worker() -> None:
            playwright = None
            session = None
            try:
                playwright = sync_playwright().start()
                session = self._attach_browser(playwright)
                page = session["page"]

                self._set_job(job_id, message="Opening login page...")
                self._open_login_page(page)
                self._set_job(job_id, message="Filling PAN / User ID...")
                self._fill_user_id_and_continue(page, user_id)
                self._set_job(job_id, message="Filling password + secure access tick...")
                self._fill_password_step(page, password)

                with _LOCK:
                    _ACTIVE_SESSIONS.append(session)
                started.set()

                self._set_job(
                    job_id,
                    message=(
                        "PAN/password ready. Dual-login aaye to Login Here auto-click hoga. "
                        "Phir portal me Continue dabayein. Login ke baad data sync hoga..."
                    ),
                )
                logged_in = self._wait_for_login(page, timeout_ms=300_000)
                if not logged_in:
                    self._set_job(
                        job_id,
                        status="error",
                        message="Login not completed in time. Tick secure message, press Continue, finish captcha.",
                    )
                else:
                    self._set_job(job_id, message="Login OK — reading profile data...")
                    data = self._collect_profile(page, fallback_pan=user_id)
                    if not data:
                        self._set_job(
                            job_id,
                            status="done",
                            message="Logged in but no profile fields found. You can fill manually.",
                            data={"pan_number": user_id},
                        )
                    else:
                        self._set_job(
                            job_id,
                            status="done",
                            message=f"Synced {len(data)} field(s) from Income Tax portal.",
                            data=data,
                        )

                # Keep browser open for user until they close it.
                browser = session["browser"]
                try:
                    while True:
                        try:
                            if hasattr(browser, "is_connected") and not browser.is_connected():
                                break
                        except Exception:
                            break
                        page.wait_for_timeout(1000)
                except Exception:
                    pass
            except BaseException as exc:  # noqa: BLE001
                error_box.append(exc)
                self._set_job(job_id, status="error", message=str(exc), data=None)
                started.set()
                try:
                    if session and session.get("browser") is not None:
                        session["browser"].close()
                except Exception:
                    pass
                try:
                    if session and session.get("proc") is not None:
                        session["proc"].terminate()
                except Exception:
                    pass
                try:
                    if playwright is not None:
                        playwright.stop()
                except Exception:
                    pass

        threading.Thread(target=worker, name=f"cm-it-portal-{job_id[:8]}", daemon=True).start()
        if not started.wait(timeout=120):
            self._set_job(job_id, status="error", message="Portal open timed out.")
            raise ValueError("Income Tax portal is taking too long to open. Try again.")
        if error_box:
            raise ValueError(str(error_box[0]))

        return {
            "ok": True,
            "job_id": job_id,
            "user_id": user_id,
            "message": (
                f"Portal opened for {user_id}. PAN + password filled, secure tick done. "
                "Ab aap Continue dabayein (auto Continue se 'Request is not authenticated' aata hai). "
                "Login success ke baad profile data Customer Master me sync hoga."
            ),
        }
