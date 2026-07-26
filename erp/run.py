"""JTCS ERP entrypoint — binds port immediately with a boot waiting page."""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback
from pathlib import Path

from werkzeug.serving import run_simple

BOOT_STATUS_PATH = "/__boot_status"
BOOT_BG_PATH = "/__boot_bg.png"
ROOT = Path(__file__).resolve().parent
BOOT_BG_FILE = ROOT / "boot_assets" / "boot-solar-system-bg.png"


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass


def _port() -> int:
    return int(os.getenv("FLASK_RUN_PORT", os.getenv("PORT", "8000")))


def _debug() -> bool:
    return (os.getenv("FLASK_DEBUG") or "1").strip() == "1"


WAITING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="8">
  <title>Starting · JTCS ERP</title>
  <style>
    :root {
      --jtcs-navy: #243b7b;
      --jtcs-navy-deep: #1a2d5c;
      --jtcs-muted: #475569;
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body {
      margin: 0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: "Segoe UI", system-ui, sans-serif;
      color: #0f172a;
      overflow: hidden;
      position: relative;
      background-color: #050816;
      background-image:
        linear-gradient(180deg, rgba(5, 8, 22, 0.28) 0%, rgba(5, 8, 22, 0.45) 100%),
        url("__BOOT_BG__");
      background-position: center center;
      background-size: cover;
      background-repeat: no-repeat;
    }
    .card {
      position: relative;
      z-index: 2;
      width: min(26rem, 92vw);
      padding: 2rem 1.75rem 1.6rem;
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.92);
      border: 1px solid rgba(255, 255, 255, 0.55);
      box-shadow:
        0 22px 55px rgba(0, 0, 0, 0.45),
        0 0 0 1px rgba(120, 90, 200, 0.12);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      text-align: center;
    }
    .mark {
      width: 3.25rem;
      height: 3.25rem;
      margin: 0 auto 1rem;
      border-radius: 12px;
      background: linear-gradient(145deg, var(--jtcs-navy), var(--jtcs-navy-deep));
      display: grid;
      place-items: center;
      color: #fff;
      font-weight: 700;
      font-size: 0.95rem;
      letter-spacing: 0.02em;
      box-shadow: 0 6px 16px rgba(36, 59, 123, 0.4);
    }
    h1 {
      margin: 0 0 0.35rem;
      font-size: 1.15rem;
      font-weight: 700;
      color: var(--jtcs-navy-deep);
    }
    p {
      margin: 0;
      font-size: 0.92rem;
      color: var(--jtcs-muted);
      line-height: 1.45;
    }
    .spinner {
      width: 2.1rem;
      height: 2.1rem;
      margin: 1.35rem auto 0.9rem;
      border: 3px solid #d5e4f4;
      border-top-color: var(--jtcs-navy);
      border-radius: 50%;
      animation: spin 0.85s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .status {
      font-size: 0.78rem;
      font-weight: 600;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--jtcs-navy);
    }
    .hint {
      margin-top: 1rem;
      font-size: 0.75rem;
      color: #64748b;
    }
  </style>
</head>
<body>
  <div class="card" role="status" aria-live="polite">
    <div class="mark">JTCS</div>
    <h1>Joshi Tax Consultancy &amp; Services</h1>
    <p>Application is starting. Login page will open automatically.</p>
    <div class="spinner" aria-hidden="true"></div>
    <div class="status" id="status">Please wait…</div>
    <p class="hint">Mail / database checks can take a few seconds.</p>
  </div>
  <script>
    (function () {
      var statusEl = document.getElementById("status");
      var ticks = 0;
      function check() {
        ticks += 1;
        statusEl.textContent = "Starting" + ".".repeat((ticks % 3) + 1);
        fetch("__BOOT_STATUS__", { cache: "no-store" })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (data && data.ready) {
              statusEl.textContent = "Opening login…";
              window.location.replace("/login");
              return;
            }
            if (data && data.error) {
              statusEl.textContent = "Startup error — check server window";
              return;
            }
            setTimeout(check, 800);
          })
          .catch(function () { setTimeout(check, 1000); });
      }
      check();
    })();
  </script>
</body>
</html>
""".replace("__BOOT_STATUS__", BOOT_STATUS_PATH).replace("__BOOT_BG__", BOOT_BG_PATH)

ERROR_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Startup Error · JTCS ERP</title>
  <style>
    body { margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
      font-family:"Segoe UI",system-ui,sans-serif; background:#050816; color:#e2e8f0; }
    .card { width:min(32rem,92vw); padding:1.5rem; border-radius:12px; background:rgba(255,255,255,.94);
      border:1px solid #fecaca; box-shadow:0 8px 24px rgba(0,0,0,.35); color:#1e293b; }
    h1 { margin:0 0 .5rem; font-size:1.1rem; color:#b91c1c; }
    pre { white-space:pre-wrap; font-size:.78rem; background:#fef2f2; padding:.75rem;
      border-radius:8px; overflow:auto; max-height:50vh; }
  </style>
</head>
<body>
  <div class="card">
    <h1>JTCS ERP failed to start</h1>
    <p>Check the server window for details, then restart.</p>
    <pre>__ERROR__</pre>
  </div>
</body>
</html>
"""


class BootGate:
    """Serve a waiting page until the real Flask app is loaded."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._app = None
        self._ready = False
        self._error: str | None = None
        self._bg_bytes: bytes | None = None
        if BOOT_BG_FILE.is_file():
            self._bg_bytes = BOOT_BG_FILE.read_bytes()

    def set_app(self, app) -> None:
        with self._lock:
            self._app = app
            self._ready = True
            self._error = None

    def set_error(self, message: str) -> None:
        with self._lock:
            self._error = message
            self._ready = False

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO") or "/"

        # Always available during boot (and after) so the waiting page can load its art.
        if path == BOOT_BG_PATH:
            if self._bg_bytes is None:
                start_response("404 Not Found", [("Content-Type", "text/plain")])
                return [b"background missing"]
            headers = [
                ("Content-Type", "image/png"),
                ("Content-Length", str(len(self._bg_bytes))),
                ("Cache-Control", "public, max-age=86400"),
            ]
            start_response("200 OK", headers)
            return [self._bg_bytes]

        with self._lock:
            ready = self._ready
            app = self._app
            error = self._error

        if path == BOOT_STATUS_PATH:
            payload = {"ready": bool(ready and app is not None), "error": error}
            body = json.dumps(payload).encode("utf-8")
            headers = [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
            ]
            start_response("200 OK", headers)
            return [body]

        if error:
            html = ERROR_HTML.replace("__ERROR__", _html_escape(error)).encode("utf-8")
            headers = [
                ("Content-Type", "text/html; charset=utf-8"),
                ("Content-Length", str(len(html))),
                ("Cache-Control", "no-store"),
            ]
            start_response("503 Service Unavailable", headers)
            return [html]

        if not ready or app is None:
            body = WAITING_HTML.encode("utf-8")
            headers = [
                ("Content-Type", "text/html; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
            ]
            start_response("200 OK", headers)
            return [body]

        return app(environ, start_response)


def _html_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _load_app(gate: BootGate, port: int) -> None:
    try:
        from app import create_app

        app = create_app()
        gate.set_app(app)
        print(f"JTCS ERP ready — login at http://localhost:{port}/login", flush=True)
    except Exception:
        message = traceback.format_exc()
        gate.set_error(message)
        print("JTCS ERP startup failed:\n" + message, file=sys.stderr, flush=True)


def main() -> None:
    _load_env()
    port = _port()
    host = "0.0.0.0"
    gate = BootGate()

    print("JTCS ERP starting — production auth (link-based reset, CSRF enabled)", flush=True)
    print(f"Boot waiting page on http://127.0.0.1:{port}/login …", flush=True)
    if not BOOT_BG_FILE.is_file():
        print(f"WARNING: boot background missing: {BOOT_BG_FILE}", flush=True)

    loader = threading.Thread(
        target=_load_app,
        args=(gate, port),
        name="jtcs-boot",
        daemon=True,
    )
    loader.start()

    run_simple(
        hostname=host,
        port=port,
        application=gate,
        use_reloader=False,
        use_debugger=_debug(),
        threaded=True,
    )


if __name__ == "__main__":
    main()
