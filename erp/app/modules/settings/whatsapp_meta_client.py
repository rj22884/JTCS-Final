"""Meta Graph API / OAuth HTTP client for Integration Settings and Communication Center."""

from __future__ import annotations

import hashlib
import hmac
import logging
import mimetypes
from pathlib import Path
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
        return self._http_get_json(url)

    def subscribe_app_to_waba(self, waba_id: str) -> dict[str, Any]:
        """POST /{waba-id}/subscribed_apps — app receives webhooks for this WABA."""
        return self.post(f"/{waba_id}/subscribed_apps", {})

    def unsubscribe_app_from_waba(self, waba_id: str) -> dict[str, Any]:
        clean = f"/{waba_id}/subscribed_apps"
        url = f"{GRAPH_BASE}/{self.version}{clean}?{urlencode(self._auth_params())}"
        req = urllib.request.Request(url, method="DELETE", headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {"success": True}
        except urllib.error.HTTPError as exc:
            body_txt = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(body_txt) if body_txt else {}
            except json.JSONDecodeError:
                payload = {"raw": body_txt}
            err = (payload.get("error") or {})
            raise MetaGraphError(err.get("message") or body_txt or str(exc), status=exc.code, payload=payload) from exc

    def list_subscribed_apps(self, waba_id: str) -> list[dict[str, Any]]:
        data = self.get(f"/{waba_id}/subscribed_apps")
        return list(data.get("data") or [])

    def debug_token(self, app_id: str, app_secret: str, input_token: str) -> dict[str, Any]:
        app_token = f"{app_id}|{app_secret}"
        url = (
            f"{GRAPH_BASE}/{self.version}/debug_token?"
            + urlencode({"input_token": input_token, "access_token": app_token})
        )
        return self._http_get_json(url)

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
