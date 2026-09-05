"""Build absolute URLs for emails without requiring SERVER_NAME routing."""

from __future__ import annotations

from urllib.parse import urlencode, urlparse

from flask import current_app, has_request_context, request, url_for


def _is_local_base(base: str) -> bool:
    host = (urlparse(base).hostname or "").lower()
    return host in {"", "localhost", "127.0.0.1", "::1"}


def public_base_url() -> str:
    """Absolute site origin for email links (never prefer localhost on a public VPS host)."""
    configured = (current_app.config.get("APP_BASE_URL") or "").rstrip("/")
    if configured and not _is_local_base(configured):
        return configured

    if has_request_context() and request.host:
        host = (request.host.split(":")[0] or "").lower()
        if host and host not in {"localhost", "127.0.0.1", "::1"}:
            scheme = (
                request.headers.get("X-Forwarded-Proto")
                or request.scheme
                or current_app.config.get("PREFERRED_URL_SCHEME")
                or "http"
            )
            return f"{scheme}://{request.host}".rstrip("/")

    if configured:
        return configured

    return f"http://localhost:{current_app.config.get('PORT', 8000)}"


def external_url_for(endpoint: str, **values) -> str:
    """Prefer public APP_BASE_URL / request host so VPS emails never point at localhost.

    Long auth tokens for password setup/reset are placed in the query string (not the
    path) so email clients are less likely to wrap/break the link mid-token.
    """
    base = public_base_url()
    token = values.get("token")
    with current_app.test_request_context(base_url=f"{base}/"):
        # Password reset / set-password: prefer ?token= query form.
        if token is not None and endpoint == "auth.reset_password":
            values = {k: v for k, v in values.items() if k != "token"}
            path = url_for(endpoint, _external=False, **values)
            return f"{base}{path}?{urlencode({'token': token})}"
        path = url_for(endpoint, _external=False, **values)
    return f"{base}{path}"
