"""
KDK Software ITR status sync via Playwright (sync API — safe in Flask threads).

Exact flow (ITR Followup Sync):
1. Login (Mobile Number + Password) → Spectrum Cloud dashboard
2. Click ITR → Go
3. Client Master → All tab
4. Search by PAN (unique id)
5. Click Client Name link
6. ITR Summary: match A.Y. == JTCS Period AND File Type == Return Type (e.g. Original)
7. Sync Filing Date + Return Filing Status
"""
from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote


KDK_LOGIN_URL = "https://app.kdksoftware.com/login"
KDK_ITR_URL = "https://app.kdksoftware.com/itr"
KDK_ITR_CLIENTS_URL = "https://app.kdksoftware.com/itr/client/all"
NAV_TIMEOUT_MS = 45_000
FAST_TIMEOUT_MS = 4_000
STEP_TIMEOUT_MS = 15_000
LOGIN_WAIT_MS = 60_000


@dataclass
class SyncClientInput:
    entry_id: int
    customer: str
    pan: str
    period: str
    return_type: str = "Original"


ProgressCallback = Callable[[dict[str, Any]], None]


def parse_portal_date(raw: str | None) -> date | None:
    text = (raw or "").strip()
    if not text or text in {"-", "—", "–", "n/a", "na", "null"}:
        return None
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def normalize_period(value: str | None) -> str:
    """Normalize JTCS Period / KDK A.Y. → e.g. 2026-27 (handles '2026 - 27')."""
    text = (value or "").strip().upper().replace("AY", "").strip()
    text = re.sub(r"\s+", "", text)
    text = text.replace("/", "-")
    # Collapse "2026--27" style
    text = re.sub(r"-+", "-", text)
    return text


def periods_match(left: str | None, right: str | None) -> bool:
    a = normalize_period(left)
    b = normalize_period(right)
    if not a or not b:
        return False
    if a == b:
        return True
    # Also allow 2026-2027 vs 2026-27
    def expand(p: str) -> str:
        m = re.match(r"^(\d{4})-(\d{2})$", p)
        if m:
            return f"{m.group(1)}-{m.group(1)[:2]}{m.group(2)}"
        return p

    return expand(a) == expand(b) or a in b or b in a


def normalize_pan(value: str | None) -> str:
    return re.sub(r"\s+", "", (value or "")).upper()


def normalize_mobile(value: str | None) -> str:
    digits = re.sub(r"\D+", "", value or "")
    if len(digits) > 10 and digits.startswith("91"):
        digits = digits[-10:]
    return digits


def _ensure_browsers_path() -> None:
    if not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        local = os.environ.get("LOCALAPPDATA") or ""
        if local:
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(Path(local) / "ms-playwright")


def _capture_preview(page) -> str | None:
    """JPEG screenshot as data-URL for JTCS progress modal live view."""
    if page is None:
        return None
    try:
        raw = page.screenshot(type="jpeg", quality=42, full_page=False, timeout=5_000)
        if not raw:
            return None
        return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")
    except Exception:
        return None


def _click_first(page, selectors: list[str], *, timeout: int = FAST_TIMEOUT_MS) -> bool:
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            loc.wait_for(state="visible", timeout=timeout)
            loc.click(timeout=timeout)
            return True
        except Exception:
            continue
    return False


def _fill_first(page, selectors: list[str], value: str, *, timeout: int = FAST_TIMEOUT_MS) -> bool:
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            loc.wait_for(state="visible", timeout=timeout)
            loc.click(timeout=timeout)
            loc.fill("")
            loc.fill(value, timeout=timeout)
            return True
        except Exception:
            continue
    return False


def _launch_browser(playwright, *, headless: bool = True):
    _ensure_browsers_path()
    launch_errors: list[str] = []
    attempts = [
        {"headless": headless, "channel": "chrome"},
        {"headless": headless, "channel": "msedge"},
        {"headless": headless},
    ]
    for kwargs in attempts:
        try:
            return playwright.chromium.launch(**kwargs)
        except Exception as exc:
            launch_errors.append(str(exc))
            continue
    detail = launch_errors[-1] if launch_errors else "Unknown browser launch error."
    if "Executable doesn't exist" in detail or "playwright install" in detail.lower():
        raise RuntimeError(
            "Playwright browser missing. Run once in erp folder: "
            ".venv\\Scripts\\python.exe -m playwright install chromium"
        )
    raise RuntimeError(detail)


def _login(page, user_id: str, password: str, emit: ProgressCallback | None = None) -> None:
    """KDK Spectrum Cloud login uses Mobile Number + Password."""

    def _emit(msg: str) -> None:
        if emit:
            emit({"phase": "login", "message": msg})

    mobile = normalize_mobile(user_id) or (user_id or "").strip()
    _emit("Opening KDK login...")
    try:
        page.goto(KDK_LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    except Exception as exc:
        raise RuntimeError(f"Unable to open KDK login page: {exc}") from exc
    page.wait_for_timeout(800)

    url_now = (page.url or "").lower()
    if any(token in url_now for token in ("/itr", "/dashboard", "/client")) and "login" not in url_now:
        _emit("Login Successfully")
        if emit:
            emit({"phase": "login", "message": "Login Successfully", "login_ok": True})
        return

    _emit("Entering Mobile Number...")
    filled_user = _fill_first(
        page,
        [
            'input[placeholder*="Enter mobile number" i]',
            'input[placeholder*="mobile number" i]',
            'input[placeholder*="Mobile" i]',
            'input[name*="mobile" i]',
            'input[id*="mobile" i]',
            'input[type="tel"]',
            'input[autocomplete="tel"]',
            'input[autocomplete="username"]',
        ],
        mobile,
        timeout=STEP_TIMEOUT_MS,
    )
    if not filled_user:
        raise RuntimeError("Login Failed")

    _emit("Entering Password...")
    filled_pass = _fill_first(
        page,
        [
            'input[placeholder*="Enter password" i]',
            'input[placeholder*="Password" i]',
            'input[name="password"]',
            'input[type="password"]',
            'input[autocomplete="current-password"]',
        ],
        password,
        timeout=STEP_TIMEOUT_MS,
    )
    if not filled_pass:
        raise RuntimeError("Login Failed")

    _emit("Clicking Login to Dashboard...")
    clicked = _click_first(
        page,
        [
            'button:has-text("Login to Dashboard")',
            'button:has-text("Login")',
            'button[type="submit"]',
            'input[type="submit"]',
        ],
        timeout=STEP_TIMEOUT_MS,
    )
    if not clicked:
        page.keyboard.press("Enter")

    # Wait until we leave the login page.
    left_login = False
    deadline = datetime.utcnow().timestamp() + (LOGIN_WAIT_MS / 1000.0)
    while datetime.utcnow().timestamp() < deadline:
        url_now = (page.url or "").lower()
        if "login" not in url_now and any(
            token in url_now for token in ("/itr", "/dashboard", "/client", "kdksoftware")
        ):
            left_login = True
            break
        # Some KDK builds land on a non-login home path without those tokens.
        if "login" not in url_now and url_now.startswith("https://app.kdksoftware.com"):
            # Confirm login form is gone.
            try:
                still_form = page.locator('input[placeholder*="mobile number" i], input[type="password"]').count()
            except Exception:
                still_form = 1
            if still_form == 0:
                left_login = True
                break
        page.wait_for_timeout(500)

    try:
        page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT_MS)
    except Exception:
        pass
    page.wait_for_timeout(1200)

    body_text = ""
    try:
        body_text = (page.locator("body").inner_text(timeout=FAST_TIMEOUT_MS) or "").lower()
    except Exception:
        body_text = ""

    if "otp" in body_text and ("enter otp" in body_text or "verify otp" in body_text):
        raise RuntimeError("Login Failed: OTP required on KDK. Complete OTP once in browser, then retry Sync.")

    still_on_login = "login" in (page.url or "").lower()
    fail_markers = (
        "invalid",
        "incorrect",
        "login failed",
        "authentication failed",
        "wrong password",
        "not registered",
    )
    if still_on_login and any(m in body_text for m in fail_markers):
        raise RuntimeError("Login Failed")
    if still_on_login and not left_login:
        raise RuntimeError("Login Failed")

    _emit("Login Successfully")
    if emit:
        emit({"phase": "login", "message": "Login Successfully", "login_ok": True})


def normalize_return_type(value: str | None) -> str:
    text = (value or "Original").strip()
    if not text:
        return "Original"
    low = text.lower()
    if low.startswith("revised"):
        # Keep Revised / Revised1 / Revised2 as-is for matching File Type
        return text[0].upper() + text[1:] if text else "Revised"
    if low == "original":
        return "Original"
    return text


def file_types_match(kdk_file_type: str | None, jtcs_return_type: str | None) -> bool:
    """Match KDK File Type to JTCS Return Type (default Original)."""
    want = normalize_return_type(jtcs_return_type).lower()
    got = re.sub(r"\s+", "", (kdk_file_type or "").strip().lower())
    if not got or got in {"-", "—", "–"}:
        # Empty file type: only accept when JTCS wants Original
        return want == "original"
    if want == "original":
        return got == "original"
    # Revised / Revised1 → match if KDK contains revised
    if want.startswith("revised"):
        if "revised" not in got:
            return False
        # If JTCS is exact Revised2 etc., require same when KDK has a number
        m_want = re.search(r"(\d+)", want)
        m_got = re.search(r"(\d+)", got)
        if m_want and m_got:
            return m_want.group(1) == m_got.group(1)
        return True
    return got == want or want in got or got in want


def _dismiss_kdk_popups(page) -> None:
    _click_first(
        page,
        [
            'button:has-text("×")',
            'button[aria-label="Close"]',
            'button.close',
            '[class*="modal"] button:has-text("Close")',
            'div:has-text("CREATE CLIENTS BY Auto Scan") button',
        ],
        timeout=800,
    )


def _click_all_tab(page) -> None:
    """Click the Client Master 'All (N)' tab — not unrelated All buttons."""
    selectors = [
        'a:has-text("All (")',
        'button:has-text("All (")',
        '[role="tab"]:has-text("All (")',
        'div[role="tab"]:has-text("All (")',
        'span:has-text("All (")',
        '[role="tab"]:has-text("All")',
        'button:has-text("All")',
        'a:has-text("All")',
    ]
    _click_first(page, selectors, timeout=STEP_TIMEOUT_MS)
    page.wait_for_timeout(800)


def _click_itr_go(page, emit: ProgressCallback | None = None) -> None:
    """Open ITR fast: prefer direct URL (no long waits on dashboard Go)."""
    if emit:
        emit({"phase": "navigate", "message": "Opening ITR module..."})

    url_now = (page.url or "").lower()
    if "/itr/client" in url_now:
        return
    if "/itr" in url_now and "/login" not in url_now and "/dashboard" not in url_now:
        return

    _dismiss_kdk_popups(page)

    # Fast path — same destination user reaches after ITR → Go.
    try:
        page.goto(KDK_ITR_CLIENTS_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        page.wait_for_timeout(400)
        if "/itr" in (page.url or "").lower() and "/login" not in (page.url or "").lower():
            if emit:
                emit({"phase": "navigate", "message": "ITR Client Master opened"})
            return
    except Exception:
        pass

    # Fallback: click ITR card "Go" with SHORT timeouts (do not stall 15s×N).
    if "/dashboard" not in (page.url or "").lower():
        try:
            page.goto("https://app.kdksoftware.com/dashboard", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            page.wait_for_timeout(400)
        except Exception:
            pass
    _dismiss_kdk_popups(page)

    clicked = False
    # Prefer scoped ITR card — avoid matching GST/TDS "Go" buttons.
    try:
        itr_card = page.locator("div, section, article, a, li").filter(
            has_text=re.compile(r"AI Smart Identification of ITR|Fetch AIS/26AS Automatically", re.I)
        ).first
        go_btn = itr_card.locator('a:has-text("Go"), button:has-text("Go"), text=Go').first
        go_btn.wait_for(state="visible", timeout=2_500)
        go_btn.click(timeout=2_500)
        clicked = True
    except Exception:
        clicked = _click_first(
            page,
            [
                'a[href="/itr"]',
                'a[href*="/itr/"]:not([href*="login"])',
                'a[href$="/itr"]',
            ],
            timeout=2_000,
        )

    if clicked:
        try:
            page.wait_for_url(re.compile(r".*/itr.*", re.I), timeout=12_000)
        except Exception:
            pass
        page.wait_for_timeout(400)
        # Land on Client Master All list.
        try:
            if "/client" not in (page.url or "").lower():
                page.goto(KDK_ITR_CLIENTS_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                page.wait_for_timeout(400)
        except Exception:
            pass
        if emit:
            emit({"phase": "navigate", "message": "ITR opened"})
        return

    # Last resort
    page.goto(KDK_ITR_CLIENTS_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    page.wait_for_timeout(400)
    if emit:
        emit({"phase": "navigate", "message": "ITR Client Master opened"})


def _open_client_master(page, emit: ProgressCallback | None = None) -> None:
    """Login → ITR → Client Master All tab (fast)."""
    _click_itr_go(page, emit=emit)
    if emit:
        emit({"phase": "navigate", "message": "Clicking All tab..."})
    _dismiss_kdk_popups(page)

    # Ensure Client Master URL even if ITR opened a different ITR home.
    if "/itr/client" not in (page.url or "").lower():
        try:
            page.goto(KDK_ITR_CLIENTS_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            page.wait_for_timeout(400)
        except Exception as exc:
            raise RuntimeError(f"Unable to open KDK ITR Client Master. {exc}") from exc

    _click_all_tab(page)
    search = page.locator(
        'input[placeholder*="Search by Name / PAN / Mobile" i], '
        'input[placeholder*="Name / PAN / Mobile" i], '
        'input[placeholder*="PAN" i], '
        'input[placeholder*="Search" i]'
    ).first
    try:
        search.wait_for(state="visible", timeout=STEP_TIMEOUT_MS)
    except Exception as exc:
        raise RuntimeError(f"Unable to open KDK ITR Client Master. {exc}") from exc
    if emit:
        emit({"phase": "navigate", "message": "Client Master ready"})


def _client_rows(page):
    """Return locator for client-master data rows (flexible DOM)."""
    for sel in ("table tbody tr", "table tr", '[role="row"]'):
        loc = page.locator(sel)
        try:
            if loc.count() > 0:
                return loc
        except Exception:
            continue
    return page.locator("table tbody tr")


def _row_has_pan(row, pan_norm: str) -> bool:
    try:
        text = (row.inner_text(timeout=FAST_TIMEOUT_MS) or "").strip()
    except Exception:
        return False
    if not text:
        return False
    low = text.lower()
    if any(x in low for x in ("no data", "no record", "not found", "client name")):
        return False
    return pan_norm in normalize_pan(text)


def _wait_for_pan_row(page, pan_norm: str, *, timeout_ms: int = 20_000):
    deadline = datetime.utcnow().timestamp() + (timeout_ms / 1000.0)
    while datetime.utcnow().timestamp() < deadline:
        try:
            cell = page.get_by_text(pan_norm, exact=True)
            if cell.count() > 0:
                for xpath in (
                    "xpath=ancestor::tr[1]",
                    'xpath=ancestor::*[@role="row"][1]',
                    "xpath=ancestor::div[contains(@class,'row')][1]",
                ):
                    row = cell.first.locator(xpath)
                    if row.count() > 0:
                        return row.first
                return cell.first
        except Exception:
            pass

        rows = _client_rows(page)
        try:
            count = rows.count()
        except Exception:
            count = 0
        for i in range(min(count, 40)):
            row = rows.nth(i)
            if _row_has_pan(row, pan_norm):
                return row
        page.wait_for_timeout(350)
    return None


def _ensure_client_master(page) -> None:
    if "/itr/client" in (page.url or "").lower():
        return
    page.goto(KDK_ITR_CLIENTS_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    page.wait_for_timeout(500)


def _search_by_pan(page, pan: str, emit: ProgressCallback | None = None) -> bool:
    """1) All tab  2) search PAN — do not re-click All after search."""
    pan_norm = normalize_pan(pan)
    if not pan_norm:
        return False

    _ensure_client_master(page)
    _dismiss_kdk_popups(page)
    if emit:
        emit({"phase": "client", "message": "Clicking All tab…", "pan": pan_norm})
    _click_all_tab(page)
    page.wait_for_timeout(400)

    if emit:
        emit({"phase": "client", "message": f"Searching PAN {pan_norm}…", "pan": pan_norm})

    filter_url = f"{KDK_ITR_CLIENTS_URL}?page=1&filter_company_name={quote(pan_norm)}"
    try:
        page.goto(filter_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        page.wait_for_timeout(900)
    except Exception:
        pass
    _dismiss_kdk_popups(page)

    search_selectors = [
        'input[placeholder*="Search by Name / PAN / Mobile" i]',
        'input[placeholder*="Name / PAN / Mobile" i]',
        'input[placeholder*="Mobile No" i]',
        'input[placeholder*="PAN" i]',
        'input[placeholder*="Search" i]',
        'input[type="search"]',
    ]
    filled = False
    for selector in search_selectors:
        try:
            loc = page.locator(selector).first
            loc.wait_for(state="visible", timeout=3_000)
            loc.click(timeout=2_000)
            loc.fill("")
            loc.type(pan_norm, delay=25)
            filled = True
            break
        except Exception:
            continue

    if filled:
        try:
            page.keyboard.press("Enter")
        except Exception:
            pass
        _click_first(
            page,
            [
                'button[aria-label*="Search" i]',
                'input[placeholder*="Search" i] + button',
                'input[placeholder*="Search" i] ~ button',
                ".input-group button",
            ],
            timeout=1_200,
        )
        page.wait_for_timeout(1200)

    try:
        page.get_by_text(pan_norm, exact=True).first.wait_for(state="visible", timeout=12_000)
        return True
    except Exception:
        return _wait_for_pan_row(page, pan_norm, timeout_ms=8_000) is not None


def _is_edit_or_action_link(a) -> bool:
    """True for pencil/edit/action icon links — never click these."""
    try:
        href = (a.get_attribute("href") or "").lower()
        cls = (a.get_attribute("class") or "").lower()
        title = (a.get_attribute("title") or "").lower()
        aria = (a.get_attribute("aria-label") or "").lower()
        blob = " ".join([href, cls, title, aria])
        if any(tok in blob for tok in ("edit", "pencil", "delete", "action", "trash", "modify")):
            return True
        label = (a.inner_text(timeout=600) or "").strip()
        # Icon-only anchors (SVG/i) with no real name text
        has_icon = False
        try:
            has_icon = a.locator("svg, i, img, .bi, .fa").count() > 0
        except Exception:
            has_icon = False
        if has_icon and not re.search(r"[A-Za-z]{3,}", label or ""):
            return True
        if label.lower() in {"edit", "delete", "update"}:
            return True
    except Exception:
        return False
    return False


def _is_client_name_link(a, pan_norm: str, customer: str = "") -> bool:
    """True only for the blue Client Name text link."""
    if _is_edit_or_action_link(a):
        return False
    try:
        label = (a.inner_text(timeout=800) or "").strip()
    except Exception:
        return False
    if not re.search(r"[A-Za-z]{3,}", label):
        return False
    if normalize_pan(label) == pan_norm:
        return False
    # Prefer customer name when known
    if customer:
        first = customer.strip().split()[0].lower()
        if first and len(first) >= 3 and first not in label.lower():
            # Still allow other name links if customer not exact (search result may differ)
            pass
    return True


def _js_click_client_name(page, pan_norm: str, customer: str = "") -> bool:
    """Click ONLY Client Name column link — never Actions/edit pencil."""
    try:
        return bool(
            page.evaluate(
                """([pan, customer]) => {
                  const norm = (s) => (s || '').replace(/\\s+/g, '').toUpperCase();
                  const want = norm(pan);
                  const nodes = Array.from(document.querySelectorAll('td, div, span, a, p'));
                  let panEl = nodes.find((n) => norm((n.textContent || '').trim()) === want);
                  if (!panEl) {
                    panEl = nodes.find((n) => norm(n.textContent || '').includes(want) && want.length >= 10);
                  }
                  if (!panEl) return false;
                  const row = panEl.closest('tr') || panEl.closest('[role="row"]');
                  if (!row) return false;

                  const isBad = (a) => {
                    const href = (a.getAttribute('href') || '').toLowerCase();
                    const cls = (a.getAttribute('class') || '').toLowerCase();
                    const title = (a.getAttribute('title') || '').toLowerCase();
                    const aria = (a.getAttribute('aria-label') || '').toLowerCase();
                    const blob = href + ' ' + cls + ' ' + title + ' ' + aria;
                    if (/edit|pencil|delete|trash|action|modify/.test(blob)) return true;
                    const t = (a.textContent || '').trim();
                    const hasIcon = !!a.querySelector('svg, i, img');
                    if (hasIcon && !/[A-Za-z]{3,}/.test(t)) return true;
                    if (/^(edit|delete|update)$/i.test(t)) return true;
                    return false;
                  };

                  const isName = (a) => {
                    if (isBad(a)) return false;
                    const t = (a.textContent || '').trim().replace(/\\s+/g, ' ');
                    if (!/[A-Za-z]{3,}/.test(t)) return false;
                    if (norm(t) === want) return false;
                    return true;
                  };

                  // 1) First data cell (Client Name column) — never last Actions cell
                  const cells = Array.from(row.querySelectorAll('td'));
                  if (cells.length) {
                    const firstCell = cells[0];
                    const nameLinks = Array.from(firstCell.querySelectorAll('a')).filter(isName);
                    if (nameLinks.length) {
                      nameLinks[0].click();
                      return true;
                    }
                  }

                  // 2) Prefer link matching customer name
                  const links = Array.from(row.querySelectorAll('a')).filter(isName);
                  const cust = (customer || '').trim().toLowerCase();
                  if (cust) {
                    const first = cust.split(/\\s+/)[0];
                    const hit = links.find((a) => (a.textContent || '').toLowerCase().includes(first));
                    if (hit) { hit.click(); return true; }
                  }

                  // 3) Any remaining name-like link that is NOT in the last cell
                  const lastCell = cells.length ? cells[cells.length - 1] : null;
                  const safe = links.filter((a) => !lastCell || !lastCell.contains(a));
                  if (safe.length) { safe[0].click(); return true; }
                  return false;
                }""",
                [pan_norm, customer or ""],
            )
        )
    except Exception:
        return False


def _on_assessee_dashboard(page) -> bool:
    url = (page.url or "").lower()
    if "assessee_id=" in url or "/itr/dashboard" in url:
        return True
    try:
        if page.locator("text=ITR Summary").count() > 0:
            return True
    except Exception:
        pass
    return False


def _click_client_name(
    page, pan: str, customer: str = "", emit: ProgressCallback | None = None
) -> bool:
    """Click Client Name text link only — never Actions/edit pencil."""
    pan_norm = normalize_pan(pan)
    if emit:
        emit(
            {
                "phase": "client",
                "message": f"Clicking client name for {pan_norm}…",
                "pan": pan_norm,
                "customer": customer or "",
            }
        )

    row = _wait_for_pan_row(page, pan_norm, timeout_ms=10_000)
    clicked = False

    # Highest priority: customer name link (accessible name)
    if customer and len(customer.strip()) >= 3:
        try:
            link = page.get_by_role(
                "link", name=re.compile(re.escape(customer.strip()), re.I)
            ).first
            link.wait_for(state="visible", timeout=3_000)
            if not _is_edit_or_action_link(link):
                link.scroll_into_view_if_needed(timeout=2_000)
                link.click(timeout=STEP_TIMEOUT_MS)
                clicked = True
        except Exception:
            clicked = False

    # Next: FIRST column (Client Name) only — never last Actions column
    if not clicked and row is not None:
        try:
            first_cell = row.locator("td").first
            links = first_cell.locator("a")
            for ai in range(min(links.count(), 5)):
                a = links.nth(ai)
                if not _is_client_name_link(a, pan_norm, customer):
                    continue
                a.scroll_into_view_if_needed(timeout=2_000)
                a.click(timeout=STEP_TIMEOUT_MS)
                clicked = True
                break
        except Exception:
            clicked = False

    # Row links excluding last cell / edit
    if not clicked and row is not None:
        try:
            cells = row.locator("td")
            cell_count = cells.count()
            limit = max(0, cell_count - 1)  # skip Actions column
            for ci in range(min(limit, 4)):
                links = cells.nth(ci).locator("a")
                for ai in range(min(links.count(), 5)):
                    a = links.nth(ai)
                    if not _is_client_name_link(a, pan_norm, customer):
                        continue
                    a.scroll_into_view_if_needed(timeout=2_000)
                    a.click(timeout=STEP_TIMEOUT_MS)
                    clicked = True
                    break
                if clicked:
                    break
        except Exception:
            clicked = False

    # Narrow CSS: name link near PAN, not edit
    if not clicked:
        try:
            link = page.locator(
                f'tr:has-text("{pan_norm}") td:first-child a, '
                f'[role="row"]:has-text("{pan_norm}") td:first-child a'
            ).first
            link.wait_for(state="visible", timeout=3_000)
            if not _is_edit_or_action_link(link):
                link.click(timeout=STEP_TIMEOUT_MS)
                clicked = True
        except Exception:
            clicked = False

    if not clicked:
        clicked = _js_click_client_name(page, pan_norm, customer)

    if not clicked:
        return False

    deadline = datetime.utcnow().timestamp() + 20
    while datetime.utcnow().timestamp() < deadline:
        if _on_assessee_dashboard(page):
            page.wait_for_timeout(800)
            _dismiss_kdk_popups(page)
            if emit:
                emit(
                    {
                        "phase": "client",
                        "message": "Client opened — reading ITR Summary…",
                        "pan": pan_norm,
                        "customer": customer or "",
                    }
                )
            return True
        page.wait_for_timeout(400)
    return False


def _search_and_open_by_pan(
    page, pan: str, customer: str = "", emit: ProgressCallback | None = None
) -> bool:
    if not _search_by_pan(page, pan, emit=emit):
        return False
    return _click_client_name(page, pan, customer=customer, emit=emit)


def _header_index_map(table) -> dict[str, int]:
    mapping: dict[str, int] = {}
    headers = table.locator("thead th, tr th")
    try:
        count = headers.count()
    except Exception:
        count = 0
    for i in range(count):
        try:
            label = re.sub(r"\s+", " ", (headers.nth(i).inner_text(timeout=1_000) or "").strip().lower())
        except Exception:
            continue
        if not label:
            continue
        if "a.y" in label or label in {"ay", "a.y.", "assessment year"}:
            mapping["ay"] = i
        elif "file type" in label or label == "type":
            mapping["file_type"] = i
        elif "filing date" in label:
            mapping["filing_date"] = i
        elif "return filing status" in label or "filing status" in label:
            mapping["status"] = i
    return mapping


def _extract_from_cells(cell_vals: list[str], headers: dict[str, int]) -> tuple[str | None, str | None]:
    status = None
    filing_date = None

    if "filing_date" in headers and headers["filing_date"] < len(cell_vals):
        raw = (cell_vals[headers["filing_date"]] or "").strip()
        if parse_portal_date(raw):
            filing_date = raw
        elif raw in {"-", "—", "–", ""}:
            filing_date = None

    if "status" in headers and headers["status"] < len(cell_vals):
        status = (cell_vals[headers["status"]] or "").strip() or None
        if status in {"-", "—", "–"}:
            status = None

    if status or filing_date is not None:
        return status, filing_date

    for v in cell_vals:
        if not v:
            continue
        if parse_portal_date(v) and not filing_date:
            filing_date = v.strip()
            continue
        low = v.lower()
        if any(
            token in low
            for token in (
                "filed",
                "pending",
                "refund",
                "process",
                "verified",
                "e-verif",
                "uploaded",
                "processed",
            )
        ):
            status = v.strip()
    return status, filing_date


def _ensure_itr_summary_visible(page) -> None:
    try:
        page.locator("text=ITR Summary").first.wait_for(state="visible", timeout=STEP_TIMEOUT_MS)
        return
    except Exception:
        pass
    _click_first(
        page,
        [
            'a:has-text("ITR Summary")',
            'button:has-text("ITR Summary")',
            "text=ITR Summary",
            'a:has-text("Return Register")',
            'button:has-text("Return Register")',
        ],
        timeout=FAST_TIMEOUT_MS,
    )
    page.wait_for_timeout(600)


def _read_itr_summary_row(
    page, period: str, return_type: str = "Original"
) -> tuple[str | None, str | None]:
    """Match KDK A.Y. == Period and File Type == Return Type; return status + filing date."""
    _ensure_itr_summary_visible(page)
    target = normalize_period(period)
    want_type = normalize_return_type(return_type)
    if not target:
        return None, None

    table_selectors = [
        'table:has-text("Return Filing Status")',
        'table:has-text("Filing Date")',
        'table:has-text("File Type")',
        'table:has-text("A.Y.")',
        'table:has-text("A.Y")',
        "table",
    ]
    for table_sel in table_selectors:
        tables = page.locator(table_sel)
        try:
            count = min(tables.count(), 8)
        except Exception:
            count = 0
        for i in range(count):
            table = tables.nth(i)
            headers = _header_index_map(table)
            # Must look like ITR Summary (has A.Y. or Filing Date)
            if "ay" not in headers and "filing_date" not in headers and "status" not in headers:
                # still try if table text mentions ITR Summary context
                try:
                    ttxt = (table.inner_text(timeout=1_000) or "").lower()
                except Exception:
                    ttxt = ""
                if "filing date" not in ttxt and "a.y" not in ttxt:
                    continue

            rows = table.locator("tbody tr")
            try:
                row_count = rows.count()
            except Exception:
                row_count = 0
            if row_count <= 0:
                rows = table.locator("tr")
                try:
                    row_count = rows.count()
                except Exception:
                    row_count = 0

            for r in range(row_count):
                row = rows.nth(r)
                try:
                    text = (row.inner_text(timeout=FAST_TIMEOUT_MS) or "").strip()
                except Exception:
                    continue
                if not text:
                    continue
                low = text.lower()
                if "filing date" in low and "a.y" in low:
                    continue
                cells = row.locator("td, th")
                try:
                    cell_count = cells.count()
                except Exception:
                    cell_count = 0
                cell_vals: list[str] = []
                for c in range(cell_count):
                    try:
                        cell_vals.append((cells.nth(c).inner_text(timeout=800) or "").strip())
                    except Exception:
                        cell_vals.append("")

                ay_val = ""
                if "ay" in headers and headers["ay"] < len(cell_vals):
                    ay_val = cell_vals[headers["ay"]]
                if not ay_val and cell_vals:
                    ay_val = cell_vals[0]

                if not periods_match(ay_val, target) and not any(
                    periods_match(v, target) for v in cell_vals
                ):
                    continue

                file_type = ""
                if "file_type" in headers and headers["file_type"] < len(cell_vals):
                    file_type = cell_vals[headers["file_type"]]
                else:
                    # Heuristic: Original / Revised often in early columns
                    for v in cell_vals[1:4]:
                        if re.search(r"original|revised", v or "", re.I):
                            file_type = v
                            break

                if not file_types_match(file_type, want_type):
                    continue

                return _extract_from_cells(cell_vals, headers)
    return None, None


def _back_to_client_master(page) -> None:
    try:
        page.goto(KDK_ITR_CLIENTS_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        page.wait_for_timeout(700)
        _dismiss_kdk_popups(page)
        _click_all_tab(page)
    except Exception:
        _click_first(
            page,
            [
                'a:has-text("Client Master")',
                'a[href*="/itr/client"]',
                'button:has-text("Back")',
                'a:has-text("Back")',
            ],
            timeout=FAST_TIMEOUT_MS,
        )


def sync_clients_sync(
    *,
    user_id: str,
    password: str,
    clients: list[SyncClientInput],
    progress_cb: ProgressCallback | None = None,
    headless: bool = True,
) -> list[dict[str, Any]]:
    """Run KDK sync using Playwright sync API (thread-safe for Flask)."""
    from playwright.sync_api import sync_playwright

    results: list[dict[str, Any]] = []
    total = len(clients)
    page_ref: dict[str, Any] = {"page": None}

    def emit(payload: dict[str, Any]) -> None:
        if not progress_cb:
            return
        out = dict(payload)
        preview = _capture_preview(page_ref.get("page"))
        if preview:
            out["preview_image"] = preview
        progress_cb(out)

    emit({"phase": "login", "message": "Launching browser..."})
    with sync_playwright() as p:
        browser = _launch_browser(p, headless=headless)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        page_ref["page"] = page
        page.set_default_timeout(STEP_TIMEOUT_MS)
        try:
            emit({"phase": "login", "message": "Opening KDK..."})
            _login(page, user_id, password, emit=emit)
            _open_client_master(page, emit=emit)

            for index, client in enumerate(clients, start=1):
                current = {
                    "index": index,
                    "total": total,
                    "entry_id": client.entry_id,
                    "customer": client.customer,
                    "pan": client.pan,
                    "period": client.period,
                    "message": f"Syncing PAN {client.pan} / {client.period}",
                }
                emit({**current, "phase": "client"})

                item = {
                    "entry_id": client.entry_id,
                    "customer": client.customer,
                    "pan": client.pan,
                    "period": client.period,
                    "return_filing_status": None,
                    "filing_date": None,
                    "ok": False,
                    "error": None,
                }

                try:
                    if not normalize_pan(client.pan):
                        item["return_filing_status"] = "Customer Not Found"
                        item["ok"] = True
                        results.append(item)
                        emit({**current, "phase": "result", "result": item})
                        continue

                    emit({**current, "phase": "client", "message": f"All → search PAN {client.pan}"})
                    opened = _search_and_open_by_pan(
                        page,
                        client.pan,
                        customer=client.customer or "",
                        emit=lambda payload: emit({**current, **payload}),
                    )
                    if not opened:
                        item["return_filing_status"] = "Customer Not Found"
                        item["ok"] = True
                        results.append(item)
                        emit({**current, "phase": "result", "result": item})
                        _back_to_client_master(page)
                        continue

                    emit(
                        {
                            **current,
                            "phase": "client",
                            "message": (
                                f"ITR Summary A.Y.={client.period} "
                                f"File Type={getattr(client, 'return_type', None) or 'Original'}"
                            ),
                        }
                    )
                    status, filing_raw = _read_itr_summary_row(
                        page,
                        client.period,
                        getattr(client, "return_type", None) or "Original",
                    )
                    if not status and not filing_raw:
                        item["return_filing_status"] = "AY Not Found"
                        item["filing_date"] = None
                    else:
                        item["return_filing_status"] = (status or "").strip() or "AY Not Found"
                        # Empty/dash filing date stays blank
                        item["filing_date"] = (filing_raw or "").strip() or None
                        if item["filing_date"] and not parse_portal_date(item["filing_date"]):
                            item["filing_date"] = None
                    item["ok"] = True
                except Exception as exc:
                    item["error"] = str(exc)
                    item["ok"] = False
                    if "Login Failed" in str(exc):
                        raise
                    item["return_filing_status"] = item["return_filing_status"] or "Timeout"

                results.append(item)
                emit({**current, "phase": "result", "result": item})
                _back_to_client_master(page)
                page.wait_for_timeout(300)
        finally:
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass

    return results
