"""Build absolute URLs for emails without requiring SERVER_NAME routing."""

from __future__ import annotations

from flask import current_app, has_request_context, request, url_for


def external_url_for(endpoint: str, **values) -> str:
    if has_request_context() and request.host:
        return url_for(endpoint, _external=True, **values)

    base = (
        current_app.config.get("APP_BASE_URL")
        or f"http://localhost:{current_app.config.get('PORT', 8000)}"
    ).rstrip("/")

    with current_app.test_request_context(base_url=f"{base}/"):
        path = url_for(endpoint, _external=False, **values)
    return f"{base}{path}"
