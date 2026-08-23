"""Open the official SHCIL e-Stamp login and wait until the user finishes captcha + OTP."""

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

from app.services.website_estamp_articles import article_shcil_hint

SHCIL_LOGIN_URL = (
    "https://www.shcilestamp.com/eStampIndia/useradmin/UserAdminLoginServlet"
    "?rDoAction=LoadLoginPage"
)
SHCIL_CREATE_URL = (
    "https://www.shcilestamp.com/eStampIndia/submission/SubmissionServlet"
    "?rDoAction=LoadStampDuty"
)

POI_HINTS = {
    "aadhaar": "Aadhaar",
    "pan": "PAN",
    "driving_licence": "Driving",
    "voter_id": "Voter",
    "passport": "Passport",
    "ration_card": "Ration",
    "govt_photo_id": "Government",
    "bank_passbook": "Passbook",
    "pension_card": "Pension",
    "nrega_job_card": "NREGA",
}

_ACTIVE_SESSIONS: list[Any] = []
_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()
_CDP_PORT_FILE = Path(tempfile.gettempdir()) / "jtcs-shcil-cdp-port.txt"
_CDP_PORTS = (9361, 9222, 9333, 9362)

_STEALTH_INIT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'languages', { get: () => ['en-IN', 'en-GB', 'en'] });
"""


class ShcilLoginService:
    """Fill JTCS SHCIL credentials. User types captcha and OTP on the official site."""

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
    def _remember_cdp_port(port: int) -> None:
        try:
            _CDP_PORT_FILE.write_text(str(int(port)), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def _saved_cdp_port() -> int | None:
        try:
            raw = _CDP_PORT_FILE.read_text(encoding="utf-8").strip()
            port = int(raw)
            if 1 <= port <= 65535:
                return port
        except Exception:
            return None
        return None

    @staticmethod
    def _registry_browser_exe() -> tuple[str | None, str | None]:
        if os.name != "nt":
            return None, None
        try:
            import winreg
        except ImportError:
            return None, None
        keys = (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe", "chrome"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe", "chrome"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe", "chrome"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe", "msedge"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe", "msedge"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe", "msedge"),
        )
        for hive, path, channel in keys:
            try:
                with winreg.OpenKey(hive, path) as key:
                    value, _ = winreg.QueryValueEx(key, "")
                if value and Path(value).is_file():
                    return value, channel
            except OSError:
                continue
        return None, None

    @staticmethod
    def _find_browser_exe() -> tuple[str | None, str | None]:
        candidates = [
            (
                "chrome",
                [
                    os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                    os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
                    os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                    "/usr/bin/google-chrome",
                    "/usr/bin/google-chrome-stable",
                    "/usr/bin/chromium",
                    "/usr/bin/chromium-browser",
                ],
            ),
            (
                "msedge",
                [
                    os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
                    os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
                    os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
                    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                ],
            ),
        ]
        for channel, paths in candidates:
            for path in paths:
                if path and Path(path).is_file():
                    return path, channel
        users = Path(r"C:\Users")
        if users.is_dir():
            for chrome in users.glob(r"*\AppData\Local\Google\Chrome\Application\chrome.exe"):
                if chrome.is_file():
                    return str(chrome), "chrome"
            for edge in users.glob(r"*\AppData\Local\Microsoft\Edge\Application\msedge.exe"):
                if edge.is_file():
                    return str(edge), "msedge"
        from_reg = ShcilLoginService._registry_browser_exe()
        if from_reg[0]:
            return from_reg
        which_chrome = shutil.which("chrome") or shutil.which("google-chrome") or shutil.which("chromium")
        if which_chrome:
            return which_chrome, "chrome"
        which_edge = shutil.which("msedge") or shutil.which("microsoft-edge")
        if which_edge:
            return which_edge, "msedge"
        return None, None

    def _pick_shcil_page(self, context):
        pages = list(context.pages) if context is not None else []
        for page in pages:
            try:
                url = (page.url or "").lower()
            except Exception:
                continue
            if "shcilestamp" in url or "estampindia" in url:
                return page
        if pages:
            return pages[0]
        return context.new_page()

    def _session_from_browser(self, playwright, browser, proc=None):
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = self._pick_shcil_page(context)
        try:
            page.add_init_script(_STEALTH_INIT)
        except Exception:
            pass
        return {
            "playwright": playwright,
            "browser": browser,
            "context": context,
            "page": page,
            "proc": proc,
        }

    def _reuse_live_session(self):
        with _LOCK:
            sessions = list(_ACTIVE_SESSIONS)
        for session in reversed(sessions):
            try:
                page = session.get("page")
                browser = session.get("browser")
                if page is None:
                    continue
                if browser is not None and hasattr(browser, "is_connected") and not browser.is_connected():
                    continue
                _ = page.url
                return session
            except Exception:
                continue
        return None

    def _connect_existing_chrome(self, playwright):
        ports: list[int] = []
        saved = self._saved_cdp_port()
        if saved:
            ports.append(saved)
        for port in _CDP_PORTS:
            if port not in ports:
                ports.append(port)
        for port in ports:
            try:
                browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            except Exception:
                continue
            session = self._session_from_browser(playwright, browser, None)
            url = ""
            try:
                url = ((session.get("page") and session["page"].url) or "").lower()
            except Exception:
                url = ""
            if port == 9361 or "shcilestamp" in url or "estampindia" in url:
                self._remember_cdp_port(port)
                return session
        return None

    def _attach_browser(self, playwright):
        live = self._reuse_live_session()
        if live is not None:
            return live

        existing = self._connect_existing_chrome(playwright)
        if existing is not None:
            return existing

        exe, _channel = self._find_browser_exe()
        profile_dir = Path(tempfile.gettempdir()) / "jtcs-shcil-estamp-profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        port = 9361
        last_err: BaseException | None = None

        if exe:
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
                except Exception as err:  # noqa: BLE001
                    last_err = err
                    if proc.poll() is not None:
                        break
            if browser is not None:
                self._remember_cdp_port(port)
                return self._session_from_browser(playwright, browser, proc)
            try:
                proc.terminate()
            except Exception:
                pass

        try:
            context = playwright.chromium.launch_persistent_context(
                str(profile_dir),
                headless=False,
                args=[f"--remote-debugging-port={port}", "--no-first-run", "--no-default-browser-check"],
            )
            page = self._pick_shcil_page(context)
            try:
                page.add_init_script(_STEALTH_INIT)
            except Exception:
                pass
            self._remember_cdp_port(port)
            return {
                "playwright": playwright,
                "browser": context,
                "context": context,
                "page": page,
                "proc": None,
            }
        except Exception as exc:
            last_err = exc

        raise RuntimeError(
            "Could not use the already-open SHCIL window, and Chrome/Edge was not found on this computer. "
            "Run Generate Stamp on the same PC where the SHCIL Chrome window is open."
        ) from last_err

    @staticmethod
    def _page_text(page) -> str:
        try:
            return page.inner_text("body") or ""
        except Exception:
            try:
                return page.content() or ""
            except Exception:
                return ""

    def _page_phase(self, page) -> str:
        try:
            url = (page.url or "").lower()
        except Exception:
            url = ""
        text = self._page_text(page).lower()
        try:
            has_password = bool(page.locator('input[name="userPwd"], input[type="password"]').count())
        except Exception:
            has_password = "userpwd" in text
        try:
            has_captcha = bool(page.locator('input[name="searchjcaptcha"]').count())
        except Exception:
            has_captcha = "captcha" in text
        otp_hint = bool(
            re.search(r"\botp\b|one time password|enter otp|otp has been sent|verification code", text)
        )
        try:
            has_otp_field = bool(
                page.locator(
                    'input[name*="otp" i], input[id*="otp" i], input[placeholder*="otp" i]'
                ).count()
            )
        except Exception:
            has_otp_field = False
        logged_in = bool(
            re.search(r"\blog.?out\b|\bsign.?off\b|\bsign.?out\b", text)
            or ("welcome" in text and "login" not in url)
        )
        if has_otp_field or (otp_hint and not has_captcha):
            return "otp"
        if has_password or has_captcha or "loadloginpage" in url or "validatelogin" in url:
            if re.search(r"invalid captcha|incorrect captcha|captcha mismatch", text):
                return "captcha_error"
            if re.search(r"invalid (user|password|login)|login failed|authentication failed", text):
                return "login_error"
            return "login"
        if (
            logged_in
            or ("estampindia" in url and "login" not in url)
            or "loadstampduty" in url
            or "list of submissions" in text
            or re.search(r"\bcreate submission\b", text)
        ):
            return "success"
        if otp_hint:
            return "otp"
        return "unknown"

    def _bind_dialogs(self, page, job_id: str) -> None:
        def handle(dialog) -> None:
            text = (dialog.message or "").strip()
            low = text.lower()
            if re.search(r"captcha", low):
                self._set_job(
                    job_id,
                    phase="captcha",
                    message=text or "Captcha did not match. Type the new captcha and click Login.",
                )
            elif text:
                self._set_job(job_id, message=text)
            try:
                dialog.accept()
            except Exception:
                pass

        try:
            page.on("dialog", handle)
        except Exception:
            pass

    def _fill_credentials(self, page, user_id: str, password: str) -> None:
        page.goto(SHCIL_LOGIN_URL, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(800)
        user_fields = page.locator('input[name="userId"]')
        user_fields.first.wait_for(state="visible", timeout=45_000)
        count = user_fields.count()
        for index in range(count):
            field = user_fields.nth(index)
            try:
                field.click(timeout=2000)
                field.fill("")
                field.type(user_id, delay=25)
            except Exception:
                continue
        pwd = page.locator('input[name="userPwd"], input[type="password"]').first
        pwd.wait_for(state="visible", timeout=20_000)
        pwd.click()
        pwd.fill("")
        pwd.type(password, delay=25)
        captcha = page.locator('input[name="searchjcaptcha"]').first
        try:
            captcha.fill("")
            captcha.click(timeout=3000)
        except Exception:
            pass

    def _dismiss_messages(self, page, rounds: int = 4) -> bool:
        clicked = False
        for _ in range(rounds):
            round_hit = False
            for sel in (
                'input[type="button"][value="OK"]',
                'input[type="submit"][value="OK"]',
                'input[value="Ok"]',
                'input[value="ok"]',
                'button:has-text("OK")',
                'a:has-text("OK")',
                'input[type="button"][value="Yes"]',
                'input[type="submit"][value="Yes"]',
                'button:has-text("Yes")',
            ):
                try:
                    loc = page.locator(sel)
                    count = loc.count()
                    for index in range(min(count, 4)):
                        btn = loc.nth(index)
                        if btn.is_visible():
                            btn.click(timeout=1500)
                            clicked = True
                            round_hit = True
                            page.wait_for_timeout(350)
                except Exception:
                    continue
            if not round_hit:
                break
        return clicked

    def _wait_for_any_text(self, page, needles: tuple[str, ...], timeout_ms: int = 20_000) -> bool:
        deadline = time.time() + (timeout_ms / 1000.0)
        wanted = tuple(item.lower() for item in needles)
        while time.time() < deadline:
            self._dismiss_messages(page, rounds=1)
            text = self._page_text(page).lower()
            if any(item in text for item in wanted):
                return True
            page.wait_for_timeout(400)
        return False

    def _open_create_submission(self, page) -> None:
        self._wait_for_any_text(
            page,
            ("create submission", "select stamp duty type", "purchased by", "list of submissions"),
            timeout_ms=20_000,
        )
        text = self._page_text(page).lower()
        if "select stamp duty type" in text or "purchased by" in text:
            return
        clicked = False
        for sel in (
            "a:has-text('Create Submission')",
            "td:has-text('Create Submission')",
            "text=Create Submission",
        ):
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=5000)
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            clicked = bool(
                page.evaluate(
                    """() => {
                        const nodes = Array.from(document.querySelectorAll('a, td, span, font, b'));
                        const node = nodes.find((el) => {
                            const t = (el.textContent || '').replace(/\\s+/g, ' ').trim();
                            return /^create submission$/i.test(t);
                        });
                        if (!node) return false;
                        (node.closest('a') || node).click();
                        return true;
                    }"""
                )
            )
        if not clicked:
            page.goto(SHCIL_CREATE_URL, wait_until="domcontentloaded", timeout=90_000)
        self._dismiss_messages(page)
        if not self._wait_for_any_text(page, ("select stamp duty type", "purchased by"), timeout_ms=25_000):
            raise RuntimeError("Create Submission page did not open. Click Create Submission in the SHCIL menu.")

    def _select_registerable_and_article(self, page, order: dict) -> None:
        code = str((order or {}).get("article_code") or "").strip()
        hint = article_shcil_hint(code) or str((order or {}).get("article_label") or "").strip()
        page.evaluate(
            """() => {
                const nodes = Array.from(document.querySelectorAll('td, label, span, div, font, b'));
                const node = nodes.find((el) => {
                    const t = (el.textContent || '').replace(/\\s+/g, ' ').trim();
                    return /registerable stamp duty/i.test(t) && t.length < 80;
                });
                if (!node) return false;
                const row = node.closest('tr') || node.parentElement;
                const radio = row && row.querySelector('input[type="radio"]');
                if (radio) {
                    radio.checked = true;
                    radio.click();
                    radio.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }
                node.click();
                return true;
            }"""
        )
        page.wait_for_timeout(500)
        selected = page.evaluate(
            """({ code, hint }) => {
                const needle = code ? '[' + code + ']' : '';
                const selects = Array.from(document.querySelectorAll('select')).filter((sel) => !sel.disabled);
                for (const sel of selects) {
                    const opts = Array.from(sel.options || []);
                    const opt = opts.find((o) => {
                        const text = o.text || '';
                        if (needle && text.includes(needle)) return true;
                        if (code && String(o.value || '').trim() === String(code)) return true;
                        if (hint && text.toLowerCase().includes(String(hint).toLowerCase()) && /\\[/.test(text)) return true;
                        return false;
                    });
                    if (opt) {
                        sel.selectedIndex = opt.index;
                        sel.value = opt.value;
                        sel.dispatchEvent(new Event('input', { bubbles: true }));
                        sel.dispatchEvent(new Event('change', { bubbles: true }));
                        if (typeof sel.onchange === 'function') sel.onchange();
                        return opt.text || '';
                    }
                }
                return '';
            }""",
            {"code": code, "hint": hint},
        )
        if not selected and code and code != "other":
            raise RuntimeError(f"Could not select article {code} on SHCIL.")
        page.wait_for_timeout(400)
        clicked_next = bool(
            page.evaluate(
                """() => {
                    const nodes = Array.from(document.querySelectorAll('input, button, a'));
                    const el = nodes.find((node) => {
                        const v = String(node.value || node.innerText || node.textContent || '')
                            .replace(/\\s+/g, ' ').trim();
                        return /^next$/i.test(v);
                    });
                    if (!el) return false;
                    el.disabled = false;
                    el.removeAttribute('disabled');
                    el.click();
                    return true;
                }"""
            )
        )
        if not clicked_next:
            for sel in (
                'input[value*="Next" i]',
                'button:has-text("Next")',
                'a:has-text("Next")',
            ):
                try:
                    loc = page.locator(sel).first
                    if loc.count():
                        loc.click(timeout=4000, force=True)
                        clicked_next = True
                        break
                except Exception:
                    continue
        if not clicked_next:
            raise RuntimeError("Could not click Next on stamp duty type page.")
        self._dismiss_messages(page, rounds=8)
        if not self._wait_for_any_text(page, ("purchased by",), timeout_ms=25_000):
            raise RuntimeError("Submission form did not open after Next.")

    def _fill_submission_form(self, page, order: dict) -> None:
        from app.services.website_estamp_service import stamp_party_line

        first = stamp_party_line(
            str((order or {}).get("full_name") or ""),
            str((order or {}).get("first_party_relation") or ""),
            str((order or {}).get("father_or_husband_name") or ""),
        )
        second = stamp_party_line(
            str((order or {}).get("second_party_name") or ""),
            str((order or {}).get("second_party_relation") or ""),
            str((order or {}).get("second_party_father_or_husband_name") or ""),
        )
        mobile = str((order or {}).get("mobile") or "").strip()
        consideration = (order or {}).get("consideration_price")
        amount = (order or {}).get("amount")
        poi_code = str((order or {}).get("poi_document_code") or "").strip().lower()
        poi_hint = POI_HINTS.get(poi_code) or str((order or {}).get("poi_document_type") or "").strip()
        property_desc = "NA"
        article_code = str((order or {}).get("article_code") or "").strip()
        article_hint = article_shcil_hint(article_code)
        document_desc = (
            f"Article {article_code} {article_hint}".strip()
            if article_code and article_code != "other" and article_hint
            else str((order or {}).get("article_label") or "").strip()
        )
        consideration_text = "0.00" if consideration in (None, "") else str(consideration)
        amount_text = "0" if amount in (None, "") else str(amount)
        address = "NA"
        second_address = "NA"

        filled = page.evaluate(
            """(data) => {
                function ownText(el) {
                    let text = '';
                    for (const node of el.childNodes) {
                        if (node.nodeType === 3) text += node.textContent || '';
                        else if (node.nodeType === 1 && !/^(INPUT|SELECT|TEXTAREA|OPTION)$/i.test(node.tagName)) {
                            if ((node.tagName || '') === 'FONT' || (node.tagName || '') === 'SPAN' || (node.tagName || '') === 'B') {
                                text += node.textContent || '';
                            }
                        }
                    }
                    return String(text || '').replace(/\\*/g, ' ').replace(/[:：]/g, ' ').replace(/\\s+/g, ' ').trim().toLowerCase();
                }
                function setValue(input, value, selectHint) {
                    if (!input || value == null || value === '') return false;
                    if (input.tagName === 'SELECT') {
                        const hint = String(selectHint || value).toLowerCase();
                        const opt = Array.from(input.options).find((o) => {
                            const t = (o.text || '').toLowerCase();
                            return t === hint || t.includes(hint) || t.includes('first party');
                        });
                        if (!opt) return false;
                        input.value = opt.value;
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }
                    input.removeAttribute('readonly');
                    input.disabled = false;
                    input.focus();
                    input.value = value;
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }
                function controlFor(labelEl) {
                    const row = labelEl.closest('tr');
                    if (row) {
                        const inRow = row.querySelector('input[type="text"], input[type="tel"], input:not([type]), textarea, select');
                        if (inRow) return inRow;
                        const next = row.nextElementSibling;
                        if (next) {
                            const inNext = next.querySelector('input[type="text"], input[type="tel"], input:not([type]), textarea, select');
                            if (inNext) return inNext;
                        }
                    }
                    let el = labelEl.nextElementSibling;
                    while (el) {
                        if (/^(INPUT|SELECT|TEXTAREA)$/i.test(el.tagName)) return el;
                        const found = el.querySelector('input[type="text"], input[type="tel"], input:not([type]), textarea, select');
                        if (found) return found;
                        el = el.nextElementSibling;
                    }
                    return null;
                }
                function fillLabel(matchFn, value, selectHint) {
                    const nodes = Array.from(document.querySelectorAll('td, th, label, span, font, b'));
                    for (const node of nodes) {
                        const text = ownText(node);
                        if (!text || text.length > 70) continue;
                        if (!matchFn(text)) continue;
                        if (setValue(controlFor(node), value, selectHint)) return true;
                    }
                    return false;
                }
                function fillAttr(names, value, selectHint) {
                    for (const name of names) {
                        const el = document.querySelector(
                            'input[name*="' + name + '" i], textarea[name*="' + name + '" i], select[name*="' + name + '" i], input[id*="' + name + '" i], textarea[id*="' + name + '" i], select[id*="' + name + '" i]'
                        );
                        if (el && setValue(el, value, selectHint)) return true;
                    }
                    return false;
                }
                const result = {};
                result.purchased = fillAttr(['purchasedBy', 'purchased_by', 'purchaser'], data.first)
                    || fillLabel((t) => t === 'purchased by' || t.startsWith('purchased by'), data.first);
                result.first = fillAttr(['firstPartyName', 'firstParty', 'first_party'], data.first)
                    || fillLabel((t) => t === 'first party', data.first);
                result.second = fillAttr(['secondPartyName', 'secondParty', 'second_party'], data.second)
                    || fillLabel((t) => t === 'second party', data.second);
                result.property = fillAttr(['propertyDescription', 'propertyDesc', 'property_description'], data.property_desc)
                    || fillLabel((t) => t.indexOf('property description') === 0, data.property_desc);
                result.consideration = fillAttr(['considerationPrice', 'consideration', 'saleAmount'], data.consideration)
                    || fillLabel((t) => t.indexOf('consideration price') === 0, data.consideration);
                result.paidBy = fillAttr(['stampDutyPaidBy', 'paidBy', 'dutyPaidBy'], data.first, 'first party')
                    || fillLabel((t) => t.indexOf('stamp duty paid by') === 0, data.first, 'first party');
                result.amount = fillAttr(['stampDutyAmount', 'stampAmount', 'dutyAmount'], data.amount)
                    || fillLabel((t) => t.indexOf('stamp duty amount') === 0, data.amount);
                result.mobile = fillAttr(['firstPartyMobile', 'firstMobile'], data.mobile)
                    || fillLabel((t) => t.indexOf('first party mobile') === 0, data.mobile);
                result.document = fillAttr(['documentDescription', 'documentDesc'], data.document_desc)
                    || fillLabel((t) => t.indexOf('description of document') === 0, data.document_desc);
                const addrRows = Array.from(document.querySelectorAll('tr')).filter((row) => ownText(row).indexOf('address line 1') === 0 || ownText(row.querySelector('td,th,label') || row).indexOf('address line 1') >= 0);
                if (addrRows[0]) setValue(addrRows[0].querySelector('input, textarea'), data.address);
                if (addrRows[1]) setValue(addrRows[1].querySelector('input, textarea'), data.second_address);
                if (data.poi_hint) {
                    fillLabel((t) => t === 'proof of identity' || t.indexOf('proof of identity') === 0, data.poi_hint, data.poi_hint);
                }
                return result;
            }""",
            {
                "first": first,
                "second": second,
                "mobile": mobile,
                "document_desc": document_desc[:80],
                "property_desc": "NA",
                "consideration": consideration_text,
                "amount": amount_text,
                "address": address,
                "second_address": second_address,
                "poi_hint": poi_hint,
            },
        )
        self._fill_visible_fallbacks(page, first, second, amount_text, consideration_text, mobile)
        page.wait_for_timeout(400)
        return filled

    def _fill_visible_fallbacks(self, page, first: str, second: str, amount: str, consideration: str, mobile: str) -> None:
        rows = (
            ("Purchased by", first, False),
            ("First Party *", first, False),
            ("Second Party *", second, False),
            ("Property Description", "NA", False),
            ("Consideration Price", consideration, False),
            ("Stamp Duty Paid By", first, True),
            ("Stamp Duty Amount", amount, False),
            ("First Party Mobile", mobile, False),
        )
        for label, value, is_paid_by in rows:
            if not value:
                continue
            try:
                box = page.locator(f'tr:has-text("{label}")').locator("input, textarea, select").first
                if not box.count():
                    continue
                tag = (box.evaluate("el => (el.tagName || '').toLowerCase()") or "")
                if tag == "select" or is_paid_by:
                    try:
                        box.select_option(label=re.compile(r"first party", re.I))
                        continue
                    except Exception:
                        try:
                            box.select_option(label=re.compile(re.escape(value), re.I))
                            continue
                        except Exception:
                            if tag == "select":
                                continue
                box.fill(str(value), force=True)
            except Exception:
                continue

    def _click_save(self, page) -> None:
        for sel in (
            'input[type="button"][value="Save"]',
            'input[type="submit"][value="Save"]',
            'button:has-text("Save")',
        ):
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=4000)
                    page.wait_for_timeout(600)
                    self._dismiss_messages(page, rounds=8)
                    return
            except Exception:
                continue
        raise RuntimeError("Could not click Save on the SHCIL form.")

    def _fill_and_save(self, page, order: dict, job_id: str) -> None:
        last_err: BaseException | None = None
        for attempt in range(1, 6):
            try:
                self._dismiss_messages(page, rounds=3)
                self._set_job(
                    job_id,
                    phase="selecting",
                    message=f"Opening Create Submission (attempt {attempt}/5)...",
                )
                self._open_create_submission(page)
                text = self._page_text(page).lower()
                if "purchased by" not in text:
                    self._set_job(
                        job_id,
                        phase="selecting",
                        message="Selecting Registerable Stamp Duty and article, then Next...",
                    )
                    self._select_registerable_and_article(page, order or {})
                    text = self._page_text(page).lower()
                if "purchased by" not in text:
                    raise RuntimeError("Submission form did not open after Next.")
                self._set_job(job_id, phase="filling", message="Filling SHCIL form from ERP order data...")
                self._fill_submission_form(page, order or {})
                self._set_job(job_id, phase="saving", message="Clicking Save...")
                self._click_save(page)
                page.wait_for_timeout(800)
                self._dismiss_messages(page, rounds=8)
                self._set_job(
                    job_id,
                    status="done",
                    phase="saved",
                    message="SHCIL form saved. Stamp print / next steps are not started.",
                )
                return
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                self._set_job(
                    job_id,
                    phase="selecting",
                    message=f"Attempt {attempt}/5 failed: {exc}. Retrying...",
                )
                try:
                    page.evaluate(
                        """() => {
                            const nodes = Array.from(document.querySelectorAll('a, td, span, font, b'));
                            const node = nodes.find((el) => /^create submission$/i.test((el.textContent || '').trim()));
                            if (node) (node.closest('a') || node).click();
                        }"""
                    )
                except Exception:
                    pass
                page.wait_for_timeout(1000)
        raise RuntimeError(str(last_err) if last_err else "Could not save the SHCIL form.")

    def launch(self, user_id: str, password: str, *, reference_no: str = "", order: dict | None = None) -> dict:
        user_id = (user_id or "").strip()
        password = password or ""
        if not user_id:
            raise ValueError("SHCIL User ID is missing in Credentials Master.")
        if not password:
            raise ValueError("SHCIL password is missing in Credentials Master.")

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ValueError("Playwright not installed. Run: pip install playwright") from exc

        job_id = uuid.uuid4().hex
        self._set_job(
            job_id,
            status="running",
            phase="opening",
            message="Opening SHCIL e-Stamp login...",
            user_id=user_id,
            reference_no=reference_no,
        )
        order_data = dict(order or {})

        started = threading.Event()
        error_box: list[BaseException] = []

        def worker() -> None:
            playwright = None
            session = None
            try:
                session = self._reuse_live_session()
                if session is None:
                    playwright = sync_playwright().start()
                    session = self._attach_browser(playwright)
                page = session["page"]
                self._bind_dialogs(page, job_id)
                with _LOCK:
                    if session not in _ACTIVE_SESSIONS:
                        _ACTIVE_SESSIONS.append(session)

                already_in = self._page_phase(page) == "success"
                if already_in:
                    self._set_job(
                        job_id,
                        phase="filling",
                        message="Already logged in. Reusing SHCIL window — no OTP again.",
                    )
                    started.set()
                    try:
                        self._fill_and_save(page, order_data, job_id)
                    except Exception as fill_exc:  # noqa: BLE001
                        self._set_job(
                            job_id,
                            status="error",
                            phase="error",
                            message=f"Login OK, but form fill/save failed: {fill_exc}",
                        )
                    already_in = True

                if not already_in:
                    self._set_job(job_id, phase="opening", message="Opening SHCIL login page...")
                    self._fill_credentials(page, user_id, password)
                    self._set_job(
                        job_id,
                        phase="captcha",
                        message=(
                            "User ID and password filled. Waiting for you: type the captcha "
                            "(case sensitive) and click LOGIN yourself. The app will not click Login."
                        ),
                    )
                    started.set()

                deadline = time.time() + 900
                last_phase = "captcha"
                while time.time() < deadline:
                    if already_in:
                        break
                    phase = self._page_phase(page)
                    if phase == "success":
                        self._set_job(
                            job_id,
                            phase="filling",
                            message="SHCIL login successful. Filling stamp form from ERP...",
                        )
                        try:
                            self._fill_and_save(page, order_data, job_id)
                        except Exception as fill_exc:  # noqa: BLE001
                            self._set_job(
                                job_id,
                                status="error",
                                phase="error",
                                message=f"Login OK, but form fill/save failed: {fill_exc}",
                            )
                        break
                    if phase == "otp":
                        self._set_job(
                            job_id,
                            phase="otp",
                            message="OTP sent. Type the OTP in the SHCIL window to finish login.",
                        )
                    elif phase == "captcha_error":
                        if last_phase != "captcha_error":
                            self._fill_credentials(page, user_id, password)
                            self._set_job(
                                job_id,
                                phase="captcha",
                                message=(
                                    "Captcha was wrong. User ID and password filled again. "
                                    "Type the new captcha and click LOGIN yourself."
                                ),
                            )
                    elif phase == "login_error":
                        self._set_job(
                            job_id,
                            status="error",
                            phase="error",
                            message="SHCIL rejected the login. Check User ID / password in Credentials Master.",
                        )
                        break
                    elif phase == "login" and last_phase != "login":
                        self._set_job(
                            job_id,
                            phase="captcha",
                            message=(
                                "Waiting on the login page. Type captcha and click LOGIN yourself. "
                                "The app will not click Login."
                            ),
                        )
                    last_phase = phase
                    page.wait_for_timeout(1000)
                else:
                    self._set_job(
                        job_id,
                        status="error",
                        phase="error",
                        message="Login not completed in time. Finish captcha and OTP on the SHCIL window.",
                    )

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
                self._set_job(job_id, status="error", phase="error", message=str(exc))
                started.set()
                launched_new = bool(session and session.get("proc"))
                if launched_new:
                    try:
                        if session.get("browser") is not None:
                            session["browser"].close()
                    except Exception:
                        pass
                    try:
                        session["proc"].terminate()
                    except Exception:
                        pass
                if playwright is not None and (launched_new or session is None):
                    try:
                        playwright.stop()
                    except Exception:
                        pass

        threading.Thread(target=worker, name=f"shcil-login-{job_id[:8]}", daemon=True).start()
        if not started.wait(timeout=90):
            self._set_job(job_id, status="error", phase="error", message="SHCIL login window timed out.")
            raise ValueError("SHCIL login is taking too long to open. Try again.")
        if error_box:
            raise ValueError(str(error_box[0]))

        job = self.get_job(job_id) or {}
        return {
            "ok": True,
            "job_id": job_id,
            "user_id": user_id,
            "phase": job.get("phase") or "captcha",
            "message": job.get("message")
            or "SHCIL login opened. Type captcha, then OTP.",
        }
