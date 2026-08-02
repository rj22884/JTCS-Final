"""Meta Graph API / OAuth HTTP client for Integration Settings only."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

import urllib.error
import urllib.request
import json

logger = logging.getLogger(__name__)

DEFAULT_GRAPH_VERSION = "v21.0"
GRAPH_BASE = "https://graph.facebook.com"
OAUTH_DIALOG = "https://www.facebook.com"


class MetaGraphError(Exception):
    def __init__(self, message: str, *, status: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


class WhatsAppMetaClient:
    """Lightweight urllib client — no CRM dependency."""

    def __init__(self, *, access_token: str, graph_api_version: str | None = None):
        self.access_token = (access_token or "").strip()
        ver = (graph_api_version or DEFAULT_GRAPH_VERSION).strip()
        if not ver.startswith("v"):
            ver = f"v{ver}"
        self.version = ver

    @staticmethod
    def oauth_authorize_url(
        *,
        app_id: str,
        redirect_uri: str,
        state: str,
        scopes: str | None = None,
    ) -> str:
        scope = scopes or (
            "business_management,whatsapp_business_management,whatsapp_business_messaging"
        )
        params = {
            "client_id": app_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": scope,
            "response_type": "code",
        }
        return f"{OAUTH_DIALOG}/{DEFAULT_GRAPH_VERSION}/dialog/oauth?{urlencode(params)}"

    @classmethod
    def exchange_code(
        cls,
        *,
        app_id: str,
        app_secret: str,
        redirect_uri: str,
        code: str,
        graph_api_version: str | None = None,
    ) -> dict[str, Any]:
        ver = (graph_api_version or DEFAULT_GRAPH_VERSION).strip()
        if not ver.startswith("v"):
            ver = f"v{ver}"
        params = {
            "client_id": app_id,
            "client_secret": app_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        }
        url = f"{GRAPH_BASE}/{ver}/oauth/access_token?{urlencode(params)}"
        return cls._http_get_json(url)

    def _auth_params(self, extra: dict | None = None) -> dict:
        params = {"access_token": self.access_token}
        if extra:
            params.update(extra)
        return params

    def get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        clean = path if path.startswith("/") else f"/{path}"
        url = f"{GRAPH_BASE}/{self.version}{clean}?{urlencode(self._auth_params(params))}"
        return self._http_get_json(url)

    def post(self, path: str, body: dict | None = None, params: dict | None = None) -> dict[str, Any]:
        clean = path if path.startswith("/") else f"/{path}"
        url = f"{GRAPH_BASE}/{self.version}{clean}?{urlencode(self._auth_params(params))}"
        return self._http_post_json(url, body or {})

    def list_businesses(self) -> list[dict[str, Any]]:
        data = self.get("/me/businesses", {"fields": "id,name"})
        return list(data.get("data") or [])

    def list_owned_wabas(self, business_id: str) -> list[dict[str, Any]]:
        data = self.get(
            f"/{business_id}/owned_whatsapp_business_accounts",
            {"fields": "id,name,currency,account_review_status"},
        )
        return list(data.get("data") or [])

    def list_phone_numbers(self, waba_id: str) -> list[dict[str, Any]]:
        data = self.get(
            f"/{waba_id}/phone_numbers",
            {
                "fields": (
                    "id,display_phone_number,verified_name,quality_rating,"
                    "code_verification_status,platform_type"
                )
            },
        )
        return list(data.get("data") or [])

    def get_business(self, business_id: str) -> dict[str, Any]:
        return self.get(f"/{business_id}", {"fields": "id,name"})

    def get_waba(self, waba_id: str) -> dict[str, Any]:
        return self.get(f"/{waba_id}", {"fields": "id,name,account_review_status"})

    def get_phone(self, phone_number_id: str) -> dict[str, Any]:
        return self.get(
            f"/{phone_number_id}",
            {
                "fields": (
                    "id,display_phone_number,verified_name,quality_rating,"
                    "code_verification_status"
                )
            },
        )

    def debug_token(self, app_id: str, app_secret: str, input_token: str) -> dict[str, Any]:
        app_token = f"{app_id}|{app_secret}"
        url = (
            f"{GRAPH_BASE}/{self.version}/debug_token?"
            + urlencode({"input_token": input_token, "access_token": app_token})
        )
        return self._http_get_json(url)

    def send_test_text(self, phone_number_id: str, to_e164: str, body: str) -> dict[str, Any]:
        return self.post(
            f"/{phone_number_id}/messages",
            {
                "messaging_product": "whatsapp",
                "to": to_e164,
                "type": "text",
                "text": {"body": body},
            },
        )

    @staticmethod
    def _http_get_json(url: str) -> dict[str, Any]:
        req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(body) if body else {}
            except json.JSONDecodeError:
                payload = {"raw": body}
            err = (payload.get("error") or {})
            msg = err.get("message") or body or str(exc)
            logger.warning("Meta Graph GET failed: %s", msg)
            raise MetaGraphError(msg, status=exc.code, payload=payload) from exc
        except urllib.error.URLError as exc:
            raise MetaGraphError(f"Network error reaching Meta Graph API: {exc.reason}") from exc

    @staticmethod
    def _http_post_json(url: str, body: dict) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            body_txt = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(body_txt) if body_txt else {}
            except json.JSONDecodeError:
                payload = {"raw": body_txt}
            err = (payload.get("error") or {})
            msg = err.get("message") or body_txt or str(exc)
            logger.warning("Meta Graph POST failed: %s", msg)
            raise MetaGraphError(msg, status=exc.code, payload=payload) from exc
        except urllib.error.URLError as exc:
            raise MetaGraphError(f"Network error reaching Meta Graph API: {exc.reason}") from exc
