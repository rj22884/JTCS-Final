"""Runtime boot: detect app version + client device after Server Login."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, make_response, render_template, request, url_for

from app.decorators import login_required
from app.services.version_service import VersionService

bp = Blueprint("runtime", __name__)


def _safe_next(raw: str | None) -> str:
    target = (raw or "").strip()
    if target.startswith("/") and not target.startswith("//") and not target.startswith("/boot"):
        return target
    return url_for("dashboard.index")


@bp.route("/boot", methods=["GET"], strict_slashes=False)
@login_required
def boot():
    svc = VersionService()
    fallback = current_app.config.get("APP_VERSION", "1.0.0")
    version = svc.get_display_version(fallback)
    current = svc.get_current()
    return render_template(
        "runtime/boot.html",
        page_title="Starting JTCS ERP",
        app_version=version,
        build_number=current.BuildNumber if current else 1,
        next_url=_safe_next(request.args.get("next")),
        runtime_api=url_for("runtime.api_runtime"),
    )


@bp.route("/api/runtime", methods=["GET"], strict_slashes=False)
@login_required
def api_runtime():
    svc = VersionService()
    fallback = current_app.config.get("APP_VERSION", "1.0.0")
    current = svc.get_current()
    version = svc.get_display_version(fallback)
    payload = {
        "ok": True,
        "app_name": current_app.config.get("APP_NAME", "JTCS ERP"),
        "version": version,
        "build_number": current.BuildNumber if current else 1,
        "source": "database" if current else "env",
    }
    return jsonify(payload)


@bp.route("/manifest.webmanifest", methods=["GET"], strict_slashes=False)
def manifest():
    name = current_app.config.get("APP_NAME", "JTCS ERP")
    body = {
        "name": name,
        "short_name": "JTCS",
        "description": "Joshi Tax Consultancy ERP — desktop, Android, iOS and tablets",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "background_color": "#243b7b",
        "theme_color": "#243b7b",
        "lang": "en",
        "icons": [
            {
                "src": url_for("static", filename="icons/jtcs-app.svg"),
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any",
            },
            {
                "src": url_for("static", filename="icons/jtcs-app-192.png"),
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable",
            },
            {
                "src": url_for("static", filename="icons/jtcs-app-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
        ],
    }
    response = make_response(jsonify(body))
    response.mimetype = "application/manifest+json"
    return response


@bp.route("/sw.js", methods=["GET"], strict_slashes=False)
def service_worker():
    response = current_app.send_static_file("sw.js")
    response.headers["Content-Type"] = "application/javascript; charset=utf-8"
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response
