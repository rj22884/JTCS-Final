"""Meta Graph API / OAuth HTTP client for Integration Settings and Communication Center."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import mimetypes
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import urllib.error
import urllib.request

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

    def __init__(
        self,
        *,
        access_token: str,
        graph_api_version: str | None = None,
        timeout: int = 30,
    ):
        self.access_token = (access_token or "").strip()
        ver = (graph_api_version or DEFAULT_GRAPH_VERSION).strip()
        if not ver.startswith("v"):
            ver = f"v{ver}"
        self.version = ver
        self.timeout = max(5, int(timeout or 30))

    @staticmethod
    def oauth_authorize_url(
        *,
        app_id: str,
        redirect_uri: str,
        state: str,
        scopes: str | None = None,
        display_popup: bool = False,
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
        if display_popup:
            params["display"] = "popup"
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
        return self._http_get_json(url, timeout=self.timeout)

    def post(self, path: str, body: dict | None = None, params: dict | None = None) -> dict[str, Any]:
        clean = path if path.startswith("/") else f"/{path}"
        url = f"{GRAPH_BASE}/{self.version}{clean}?{urlencode(self._auth_params(params))}"
        return self._http_post_json(url, body or {}, timeout=self.timeout)

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
                    "code_verification_status,platform_type,throughput,"
                    "messaging_limit_tier,name_status,new_name_status,"
                    "is_official_business_account,account_mode"
                )
            },
        )

    def exchange_for_long_lived_token(
        self,
        *,
        app_id: str,
        app_secret: str,
        short_lived_token: str,
        graph_api_version: str | None = None,
    ) -> dict[str, Any]:
        """Exchange short-lived user token for ~60-day long-lived token."""
        ver = (graph_api_version or self.version or DEFAULT_GRAPH_VERSION).strip()
        if not ver.startswith("v"):
            ver = f"v{ver}"
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_lived_token,
        }
        url = f"{GRAPH_BASE}/{ver}/oauth/access_token?{urlencode(params)}"
        return self._http_get_json(url, timeout=self.timeout)

    def subscribe_app_to_waba(self, waba_id: str) -> dict[str, Any]:
        """POST /{WABA-ID}/subscribed_apps — Bearer token, no query-string secret."""
        return self._subscribed_apps_http("POST", waba_id, body={})

    def unsubscribe_app_from_waba(self, waba_id: str) -> dict[str, Any]:
        return self._subscribed_apps_http("DELETE", waba_id)

    def list_subscribed_apps(self, waba_id: str) -> list[dict[str, Any]]:
        data = self._subscribed_apps_http("GET", waba_id)
        rows = list(data.get("data") or [])
        normalized: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            inner = row.get("whatsapp_business_api_data")
            if isinstance(inner, dict):
                merged = dict(inner)
                for key, value in row.items():
                    if key != "whatsapp_business_api_data" and key not in merged:
                        merged[key] = value
                normalized.append(merged)
            else:
                normalized.append(row)
        return normalized

    def _subscribed_apps_http(
        self,
        method: str,
        waba_id: str,
        *,
        body: dict | None = None,
    ) -> dict[str, Any]:
        """Cloud API subscribed_apps: Bearer header, token never in the URL."""
        method = (method or "GET").upper()
        waba = (waba_id or "").strip()
        if not waba:
            raise MetaGraphError("WABA ID is required for subscribed_apps.")
        if not self.access_token:
            raise MetaGraphError("Access token is required for subscribed_apps.")
        path = f"/{self.version}/{waba}/subscribed_apps"
        url = f"{GRAPH_BASE}{path}"
        # This WhatsApp edge is slower than node GETs used by other Test checks.
        wait = max(30, int(self.timeout or 30))
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": "JTCS-ERP-WhatsApp/1.0",
        }
        data = None
        if method == "POST":
            headers["Content-Type"] = "application/json"
            data = json.dumps(body if body is not None else {}).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        req.add_unredirected_header("Authorization", f"Bearer {self.access_token}")
        logger.info(
            "WhatsApp subscribed_apps request method=%s url=%s version=%s waba_id=%s "
            "timeout_s=%s token_present=%s auth=Bearer",
            method,
            url,
            self.version,
            waba,
            wait,
            True,
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=wait) as resp:
                raw = resp.read().decode("utf-8")
                status = getattr(resp, "status", None) or resp.getcode()
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                logger.info(
                    "WhatsApp subscribed_apps response method=%s status=%s elapsed_ms=%s body=%s",
                    method,
                    status,
                    elapsed_ms,
                    self._redact_log_text(raw)[:2000],
                )
                return json.loads(raw) if raw else {"success": True}
        except urllib.error.HTTPError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            body_txt = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(body_txt) if body_txt else {}
            except json.JSONDecodeError:
                payload = {"raw": body_txt}
            err = payload.get("error") or {}
            msg = err.get("message") or body_txt or str(exc)
            logger.warning(
                "WhatsApp subscribed_apps http_error method=%s url=%s status=%s elapsed_ms=%s body=%s",
                method,
                url,
                exc.code,
                elapsed_ms,
                self._redact_log_text(body_txt)[:2000],
            )
            raise MetaGraphError(msg, status=exc.code, payload=payload) from exc
        except TimeoutError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "WhatsApp subscribed_apps timeout method=%s url=%s timeout_s=%s elapsed_ms=%s reason=%s",
                method,
                url,
                wait,
                elapsed_ms,
                exc,
            )
            raise MetaGraphError(
                f"Meta Graph API timed out on {method} {path} after {wait}s."
            ) from exc
        except urllib.error.URLError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            reason = exc.reason
            timed_out = isinstance(reason, TimeoutError) or "timed out" in str(reason).lower()
            logger.warning(
                "WhatsApp subscribed_apps network_error method=%s url=%s elapsed_ms=%s timeout=%s reason=%s",
                method,
                url,
                elapsed_ms,
                timed_out,
                self._redact_log_text(str(reason)),
            )
            if timed_out:
                raise MetaGraphError(
                    f"Meta Graph API timed out on {method} {path} after {wait}s."
                ) from exc
            raise MetaGraphError(f"Network error reaching Meta Graph API: {reason}") from exc

    @staticmethod
    def _redact_log_text(text: str | None) -> str:
        value = text or ""
        value = re.sub(r"EAA[A-Za-z0-9]+", "EAA***", value)
        value = re.sub(r"(access_token=)[^&\s]+", r"\1REDACTED", value, flags=re.I)
        value = re.sub(r"(Bearer\s+)\S+", r"\1REDACTED", value, flags=re.I)
        return value

    def debug_token(self, app_id: str, app_secret: str, input_token: str) -> dict[str, Any]:
        app_token = f"{app_id}|{app_secret}"
        url = (
            f"{GRAPH_BASE}/{self.version}/debug_token?"
            + urlencode({"input_token": input_token, "access_token": app_token})
        )
        return self._http_get_json(url, timeout=self.timeout)

    def send_test_text(self, phone_number_id: str, to_e164: str, body: str) -> dict[str, Any]:
        return self.send_text(phone_number_id, to_e164, body)

    def send_text(self, phone_number_id: str, to_e164: str, body: str) -> dict[str, Any]:
        return self.post(
            f"/{phone_number_id}/messages",
            {
                "messaging_product": "whatsapp",
                "to": to_e164,
                "type": "text",
                "text": {"body": body},
            },
        )

    def send_media(
        self,
        phone_number_id: str,
        to_e164: str,
        *,
        media_type: str,
        link: str | None = None,
        media_id: str | None = None,
        caption: str | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        """media_type: image | document | audio | video | sticker"""
        mtype = (media_type or "document").lower()
        if mtype not in {"image", "document", "audio", "video", "sticker"}:
            mtype = "document"
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to_e164,
            "type": mtype,
        }
        media_obj: dict[str, Any] = {}
        if media_id:
            media_obj["id"] = media_id
        elif link:
            media_obj["link"] = link
        else:
            raise MetaGraphError("send_media requires media_id or link")
        if caption and mtype in {"image", "document", "video"}:
            media_obj["caption"] = caption
        if filename and mtype == "document":
            media_obj["filename"] = filename
        payload[mtype] = media_obj
        return self.post(f"/{phone_number_id}/messages", payload)

    def send_template(
        self,
        phone_number_id: str,
        to_e164: str,
        *,
        template_name: str,
        language_code: str = "en",
        components: list | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to_e164,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code or "en"},
            },
        }
        if components:
            payload["template"]["components"] = components
        return self.post(f"/{phone_number_id}/messages", payload)

    def mark_as_read(self, phone_number_id: str, message_id: str) -> dict[str, Any]:
        return self.post(
            f"/{phone_number_id}/messages",
            {
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id,
            },
        )

    def get_media_url(self, media_id: str) -> dict[str, Any]:
        return self.get(f"/{media_id}")

    def download_media(self, media_id: str) -> dict[str, Any]:
        """Fetch media binary from Graph. Returns {ok, content, mime_type, filename}."""
        meta = self.get_media_url(media_id)
        url = meta.get("url")
        mime = meta.get("mime_type") or "application/octet-stream"
        if not url:
            return {"ok": False, "error": "No media URL in Graph response"}
        # Media URL requires Authorization header (not query token alone on some versions)
        req = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "*/*",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                content = resp.read()
                ctype = resp.headers.get("Content-Type") or mime
            ext = mimetypes.guess_extension(ctype.split(";")[0].strip()) or ""
            return {
                "ok": True,
                "content": content,
                "mime_type": ctype,
                "filename": f"{media_id}{ext}",
                "size": len(content),
            }
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise MetaGraphError(body or str(exc), status=exc.code) from exc

    def upload_media(
        self,
        phone_number_id: str,
        file_path: str | Path,
        *,
        mime_type: str | None = None,
    ) -> dict[str, Any]:
        """Upload local file to WhatsApp media endpoint (multipart)."""
        path = Path(file_path)
        mime = mime_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        boundary = "----JTCSFormBoundary7MA4YWxkTrZu0gW"
        file_bytes = path.read_bytes()
        body = b""
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="messaging_product"\r\n\r\n'
        body += b"whatsapp\r\n"
        body += f"--{boundary}\r\n".encode()
        body += (
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode()
        body += file_bytes + b"\r\n"
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="type"\r\n\r\n'
        body += mime.encode() + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        url = (
            f"{GRAPH_BASE}/{self.version}/{phone_number_id}/media?"
            + urlencode({"access_token": self.access_token})
        )
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            body_txt = exc.read().decode("utf-8", errors="replace")
            raise MetaGraphError(body_txt or str(exc), status=exc.code) from exc

    @staticmethod
    def verify_signature(app_secret: str, raw_body: bytes, signature_header: str | None) -> bool:
        """Validate X-Hub-Signature-256 from Meta webhooks."""
        if not app_secret or not signature_header:
            return False
        expected = signature_header.strip()
        if expected.startswith("sha256="):
            expected = expected[7:]
        digest = hmac.new(
            app_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(digest, expected)

    @staticmethod
    def _http_get_json(url: str, timeout: int = 30) -> dict[str, Any]:
        wait = max(5, int(timeout or 30))
        req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=wait) as resp:
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
        except TimeoutError as exc:
            raise MetaGraphError("Meta Graph API timed out.") from exc
        except urllib.error.URLError as exc:
            raise MetaGraphError(f"Network error reaching Meta Graph API: {exc.reason}") from exc

    @staticmethod
    def _http_post_json(url: str, body: dict, timeout: int = 30) -> dict[str, Any]:
        wait = max(5, int(timeout or 30))
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=wait) as resp:
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
        except TimeoutError as exc:
            raise MetaGraphError("Meta Graph API timed out.") from exc
        except urllib.error.URLError as exc:
            raise MetaGraphError(f"Network error reaching Meta Graph API: {exc.reason}") from exc
