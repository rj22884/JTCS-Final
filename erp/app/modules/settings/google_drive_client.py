"""Google Drive API v3 client — OAuth token + resumable .bak upload (stdlib urllib)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_ABOUT_URL = "https://www.googleapis.com/drive/v3/about"
CHUNK_SIZE = 8 * 1024 * 1024  # 8 MiB resumable chunks


class GoogleDriveError(RuntimeError):
    pass


class GoogleDriveClient:
    def __init__(self, *, access_token: str):
        self.access_token = (access_token or "").strip()
        if not self.access_token:
            raise GoogleDriveError("Access token is required.")

    @staticmethod
    def exchange_code(
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code: str,
    ) -> dict[str, Any]:
        body = urlencode(
            {
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            }
        ).encode("utf-8")
        return GoogleDriveClient._token_request(body)

    @staticmethod
    def refresh_access_token(
        *,
        client_id: str,
        client_secret: str,
        refresh_token: str,
    ) -> dict[str, Any]:
        body = urlencode(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode("utf-8")
        return GoogleDriveClient._token_request(body)

    @staticmethod
    def _token_request(body: bytes) -> dict[str, Any]:
        req = Request(
            TOKEN_URL,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8") or "{}")
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            detail = GoogleDriveClient._safe_oauth_error(raw)
            raise GoogleDriveError(f"Google token endpoint HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise GoogleDriveError(f"Google token endpoint unreachable: {exc.reason}") from exc
        if not isinstance(payload, dict):
            raise GoogleDriveError("Unexpected token response from Google.")
        return payload

    @staticmethod
    def _safe_oauth_error(raw: str) -> str:
        try:
            data = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return "OAuth request failed."
        err = str(data.get("error") or "")
        desc = str(data.get("error_description") or "")
        # Never echo tokens if Google somehow returned them in an error body.
        text = " ".join(part for part in (err, desc) if part).strip()
        return text or "OAuth request failed."

    def _auth_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def _json_request(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        data: bytes | None = None,
        timeout: int = 120,
    ) -> dict[str, Any]:
        req = Request(url, data=data, method=method, headers=headers or self._auth_headers())
        try:
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8") or "{}"
                if not raw.strip():
                    return {}
                payload = json.loads(raw)
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise GoogleDriveError(self._safe_drive_error(exc.code, raw)) from exc
        except URLError as exc:
            raise GoogleDriveError(f"Google Drive unreachable: {exc.reason}") from exc
        if not isinstance(payload, dict):
            raise GoogleDriveError("Unexpected Google Drive response.")
        return payload

    @staticmethod
    def _safe_drive_error(status: int, raw: str) -> str:
        message = ""
        try:
            data = json.loads(raw or "{}")
            err = data.get("error") if isinstance(data, dict) else None
            if isinstance(err, dict):
                message = str(err.get("message") or "")
        except json.JSONDecodeError:
            message = ""
        return f"Google Drive API HTTP {status}" + (f": {message}" if message else "")

    def about_user(self) -> dict[str, Any]:
        return self._json_request(f"{DRIVE_ABOUT_URL}?fields=user")

    def ensure_folder(self, name: str, *, existing_id: str = "") -> str:
        folder_name = (name or "JTCS Backup").strip() or "JTCS Backup"
        existing = (existing_id or "").strip()
        if existing:
            try:
                meta = self._json_request(
                    f"{DRIVE_FILES_URL}/{existing}?fields=id,name,mimeType,trashed"
                )
                if (
                    meta.get("id")
                    and meta.get("mimeType") == "application/vnd.google-apps.folder"
                    and not meta.get("trashed")
                ):
                    return str(meta["id"])
            except GoogleDriveError:
                pass

        # Search for an existing app-owned folder with this name (drive.file scope).
        query = (
            "mimeType='application/vnd.google-apps.folder' "
            f"and name='{folder_name.replace(chr(39), chr(92) + chr(39))}' "
            "and trashed=false"
        )
        listed = self._json_request(
            f"{DRIVE_FILES_URL}?{urlencode({'q': query, 'spaces': 'drive', 'fields': 'files(id,name)'})}"
        )
        files = listed.get("files") or []
        if files and isinstance(files[0], dict) and files[0].get("id"):
            return str(files[0]["id"])

        meta = json.dumps(
            {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
        ).encode("utf-8")
        created = self._json_request(
            f"{DRIVE_FILES_URL}?fields=id,name",
            method="POST",
            headers=self._auth_headers({"Content-Type": "application/json; charset=UTF-8"}),
            data=meta,
        )
        folder_id = str(created.get("id") or "").strip()
        if not folder_id:
            raise GoogleDriveError("Google Drive did not return a folder id.")
        return folder_id

    def resumable_upload(
        self,
        path: Path,
        *,
        folder_id: str,
        mime_type: str = "application/octet-stream",
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        if not path.is_file():
            raise GoogleDriveError("Backup file not found for upload.")
        size = path.stat().st_size
        if size <= 0:
            raise GoogleDriveError("Backup file is empty.")

        metadata = json.dumps(
            {
                "name": path.name,
                "parents": [folder_id],
            }
        ).encode("utf-8")
        init_url = f"{DRIVE_UPLOAD_URL}?uploadType=resumable&fields=id,name,webViewLink,size"
        init_req = Request(
            init_url,
            data=metadata,
            method="POST",
            headers=self._auth_headers(
                {
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Type": mime_type,
                    "X-Upload-Content-Length": str(size),
                }
            ),
        )
        try:
            with urlopen(init_req, timeout=60) as resp:
                session_url = resp.headers.get("Location") or ""
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise GoogleDriveError(self._safe_drive_error(exc.code, raw)) from exc
        except URLError as exc:
            raise GoogleDriveError(f"Google Drive upload session failed: {exc.reason}") from exc
        if not session_url:
            raise GoogleDriveError("Google Drive did not return a resumable upload URL.")

        uploaded = 0
        final_payload: dict[str, Any] = {}
        with open(path, "rb") as fh:
            while uploaded < size:
                chunk = fh.read(CHUNK_SIZE)
                if not chunk:
                    break
                start = uploaded
                end = uploaded + len(chunk) - 1
                chunk_req = Request(
                    session_url,
                    data=chunk,
                    method="PUT",
                    headers={
                        "Content-Length": str(len(chunk)),
                        "Content-Type": mime_type,
                        "Content-Range": f"bytes {start}-{end}/{size}",
                    },
                )
                try:
                    with urlopen(chunk_req, timeout=300) as resp:
                        status = getattr(resp, "status", None) or resp.getcode()
                        body = resp.read().decode("utf-8") or ""
                        if status in {200, 201} and body.strip():
                            final_payload = json.loads(body)
                except HTTPError as exc:
                    # 308 Resume Incomplete is expected between chunks.
                    if exc.code not in {308, 200, 201}:
                        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
                        raise GoogleDriveError(self._safe_drive_error(exc.code, raw)) from exc
                    if exc.code in {200, 201}:
                        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
                        if raw.strip():
                            final_payload = json.loads(raw)
                uploaded = end + 1
                if progress_cb:
                    progress_cb(uploaded, size)

        file_id = str(final_payload.get("id") or "").strip()
        if not file_id:
            raise GoogleDriveError("Upload finished but Google Drive did not return a file id.")
        return {
            "id": file_id,
            "name": final_payload.get("name") or path.name,
            "webViewLink": final_payload.get("webViewLink") or "",
            "size": final_payload.get("size") or str(size),
        }
