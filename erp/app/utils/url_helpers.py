"""Build absolute URLs for emails without requiring SERVER_NAME routing."""

from __future__ import annotations

from flask import current_app, has_request_context, request, url_for


def external_url_for(endpoint: str, **values) -> str:
    """Prefer APP_BASE_URL so VPS emails never point at localhost."""
    base = (current_app.config.get("APP_BASE_URL") or "").rstrip("/")
    if base:
        with current_app.test_request_context(base_url=f"{base}/"):
            path = url_for(endpoint, _external=False, **values)
        return f"{base}{path}"

    if has_request_context() and request.host:
        return url_for(endpoint, _external=True, **values)

    fallback = f"http://localhost:{current_app.config.get('PORT', 8000)}"
    with current_app.test_request_context(base_url=f"{fallback}/"):
        path = url_for(endpoint, _external=False, **values)
    return f"{fallback}{path}"
