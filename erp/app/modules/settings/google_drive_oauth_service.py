"""Google Drive OAuth 2.0 for backup upload — reuses IntegrationSettings encryption."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from flask import current_app, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.modules.settings.crypto import encrypt_value
from app.modules.settings.repositories import IntegrationSettingsRepository
from app.modules.settings.services import IntegrationSettingsService

logger = logging.getLogger(__name__)

PROVIDER = "google_drive"
GOOGLE_PROVIDER = "google"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
FOLDER_NAME = "JTCS Backup"

SESSION_OAUTH_STATE = "gdrive_oauth_state"
SESSION_RETURN_TO = "gdrive_oauth_return_to"

_OAUTH_STATE_SALT = "jtcs-gdrive-oauth-state"
_OAUTH_STATE_MAX_AGE = 15 * 60

STATUS_CONNECTED = "Connected"
STATUS_NOT_CONFIGURED = "Not Configured"
STATUS_DISCONNECTED = "Disconnected"


class GoogleDriveOAuthService:
    def __init__(
        self,
        settings: IntegrationSettingsService | None = None,
        repository: IntegrationSettingsRepository | None = None,
    ):
        self.settings = settings or IntegrationSettingsService()
        self.repository = repository or IntegrationSettingsRepository()

    def _cfg(self) -> dict[str, str]:
        return self.settings.get_provider_config_decrypted(PROVIDER)

    def _google_cfg(self) -> dict[str, str]:
        return self.settings.get_provider_config_decrypted(GOOGLE_PROVIDER)

    def resolve_oauth_client(self) -> tuple[str, str]:
        """Resolve OAuth Web Client ID/Secret from google_drive (preferred) or google.

        Legacy google_drive GENERIC fields stored Client ID/Secret as api_key/api_secret.
        """
        cfg = self._cfg()
        google = self._google_cfg()
        client_id = (
            (cfg.get("client_id") or "").strip()
            or (cfg.get("api_key") or "").strip()
            or (google.get("client_id") or "").strip()
        )
        client_secret = (
            (cfg.get("client_secret") or "").strip()
            or (cfg.get("api_secret") or "").strip()
            or (google.get("client_secret") or "").strip()
        )
        return client_id, client_secret

    def default_oauth_redirect_uri(self) -> str:
        return url_for("integration_settings.api_google_drive_oauth_callback", _external=True)

    @staticmethod
    def _oauth_serializer() -> URLSafeTimedSerializer:
        return URLSafeTimedSerializer(current_app.secret_key, salt=_OAUTH_STATE_SALT)

    def _issue_oauth_state(self) -> str:
        state = self._oauth_serializer().dumps(
            {"uid": session.get("user_id"), "n": secrets.token_urlsafe(12)}
        )
        session[SESSION_OAUTH_STATE] = state
        session.modified = True
        return state

    def _oauth_state_ok(self, state: str | None) -> bool:
        incoming = (state or "").strip()
        if not incoming:
            return False
        expected = (session.get(SESSION_OAUTH_STATE) or "").strip()
        if expected and incoming == expected:
            return True
        try:
            data = self._oauth_serializer().loads(incoming, max_age=_OAUTH_STATE_MAX_AGE)
        except (BadSignature, SignatureExpired, TypeError, ValueError):
            return False
        return str(data.get("uid") or "") == str(session.get("user_id") or "")

    def is_connected(self) -> bool:
        cfg = self._cfg()
        refresh = (cfg.get("refresh_token") or "").strip()
        status = (cfg.get("connection_status") or "").strip().lower()
        return bool(refresh) and status == STATUS_CONNECTED.lower()

    def connection_info(self, *, return_to: str | None = None) -> dict[str, Any]:
        cfg = self._cfg()
        client_id, client_secret = self.resolve_oauth_client()
        connected = self.is_connected()
        info: dict[str, Any] = {
            "ok": True,
            "provider": PROVIDER,
            "connected": connected,
            "connection_status": (cfg.get("connection_status") or STATUS_NOT_CONFIGURED).strip(),
            "connected_email": (cfg.get("connected_email") or "").strip(),
            "folder_name": (cfg.get("folder_name") or FOLDER_NAME).strip() or FOLDER_NAME,
            "has_client": bool(client_id and client_secret),
            "oauth_redirect_uri": (cfg.get("oauth_redirect_uri") or "").strip()
            or self.default_oauth_redirect_uri(),
        }
        if not connected:
            if client_id and client_secret:
                params = {"return_to": return_to} if return_to else {}
                info["authorize_url"] = url_for(
                    "integration_settings.api_google_drive_connect",
                    **params,
                )
            else:
                info["authorize_url"] = None
                info["connect_error"] = (
                    "Save Google Drive OAuth Client ID and Client Secret under "
                    "Admin → Integrations → Google Drive (or Google OAuth) before connecting."
                )
        return info

    def start_connect(self, *, return_to: str | None = None) -> dict[str, Any]:
        client_id, client_secret = self.resolve_oauth_client()
        if not client_id or not client_secret:
            raise ValueError(
                "Save Google Drive OAuth Client ID and Client Secret under "
                "Admin → Integrations → Google Drive (or Google OAuth) before connecting."
            )

        redirect_uri = (self._cfg().get("oauth_redirect_uri") or "").strip() or self.default_oauth_redirect_uri()
        state = self._issue_oauth_state()
        if return_to:
            session[SESSION_RETURN_TO] = return_to
            session.modified = True

        # Persist non-secret OAuth metadata under google_drive.
        if not (self._cfg().get("client_id") or "").strip() and "apps.googleusercontent.com" in client_id:
            self._upsert_plain("client_id", client_id)
        self._upsert_plain("oauth_redirect_uri", redirect_uri)
        self._upsert_plain("folder_name", FOLDER_NAME)

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": DRIVE_SCOPE,
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
        }
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
        return {"ok": True, "authorize_url": url, "redirect_uri": redirect_uri}

    def handle_callback(self, *, code: str | None, state: str | None, error: str | None) -> dict[str, Any]:
        if error:
            raise ValueError(f"Google OAuth error: {error}")
        if not code:
            raise ValueError("Missing OAuth authorization code.")
        if not self._oauth_state_ok(state):
            raise ValueError(
                "Google Drive login session expired. Click Connect Google Drive again "
                "and finish within 15 minutes in the same browser tab."
            )

        client_id, client_secret = self.resolve_oauth_client()
        redirect_uri = (self._cfg().get("oauth_redirect_uri") or "").strip() or self.default_oauth_redirect_uri()

        from app.modules.settings.google_drive_client import GoogleDriveClient

        token_payload = GoogleDriveClient.exchange_code(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            code=code,
        )
        refresh_token = (token_payload.get("refresh_token") or "").strip()
        access_token = (token_payload.get("access_token") or "").strip()
        expires_in = int(token_payload.get("expires_in") or 3600)
        if not access_token:
            raise ValueError("Google did not return an access token.")
        if not refresh_token:
            # May happen on re-consent without prompt=consent; keep prior refresh if present.
            refresh_token = (self._cfg().get("refresh_token") or "").strip()
        if not refresh_token:
            raise ValueError(
                "Google did not return a refresh token. Revoke app access in Google Account "
                "and connect again with consent."
            )

        self._upsert_secret("refresh_token", refresh_token)
        self._upsert_secret("access_token", access_token)
        expires_at = (datetime.utcnow() + timedelta(seconds=max(expires_in - 60, 60))).isoformat(
            timespec="seconds"
        )
        self._upsert_plain("token_expires_at", expires_at)

        email = ""
        try:
            client = GoogleDriveClient(access_token=access_token)
            about = client.about_user()
            email = (about.get("user") or {}).get("emailAddress") or ""
        except Exception:
            logger.exception("Google Drive about() failed after OAuth")

        if email:
            self._upsert_plain("connected_email", email)
        self._upsert_plain("connection_status", STATUS_CONNECTED)
        self._upsert_plain("folder_name", FOLDER_NAME)

        # Ensure JTCS Backup folder exists once after connect.
        try:
            client = GoogleDriveClient(access_token=access_token)
            folder_id = client.ensure_folder(FOLDER_NAME, existing_id=(self._cfg().get("folder_id") or "").strip())
            self._upsert_plain("folder_id", folder_id)
        except Exception:
            logger.exception("Could not create JTCS Backup folder after OAuth")

        session.pop(SESSION_OAUTH_STATE, None)
        return_to = (session.pop(SESSION_RETURN_TO, None) or "").strip()
        return {
            "ok": True,
            "message": "Google Drive connected.",
            "connected_email": email,
            "return_to": return_to,
        }

    def pop_return_to(self) -> str:
        return (session.pop(SESSION_RETURN_TO, None) or "").strip()

    def _upsert_plain(self, key: str, value: str) -> None:
        from app.modules.settings.audit_service import IntegrationSettingsAuditService

        if key in {"refresh_token", "access_token", "client_secret", "api_secret", "api_key"}:
            logger.error("Refused plain upsert for secret key %s", key)
            return
        old = self.repository.get_encrypted_value(PROVIDER, key)
        stored = encrypt_value(value or "")
        self.repository.upsert(
            provider=PROVIDER,
            setting_key=key,
            value_encrypted=stored,
            description=f"{PROVIDER}.{key}",
        )
        try:
            IntegrationSettingsAuditService(self.repository).log_change(
                provider=PROVIDER,
                setting_key=key,
                old_cipher=old,
                new_cipher=stored,
            )
        except Exception:
            logger.exception("Integration audit log failed for %s", key)

    def _upsert_secret(self, key: str, value: str) -> None:
        from app.modules.settings.audit_service import IntegrationSettingsAuditService

        if key not in {"refresh_token", "access_token", "client_secret", "api_secret"}:
            raise ValueError(f"Unsupported secret key: {key}")
        plain = (value or "").strip()
        if not plain:
            raise ValueError(f"{key} cannot be empty.")
        old = self.repository.get_encrypted_value(PROVIDER, key)
        stored = encrypt_value(plain)
        self.repository.upsert(
            provider=PROVIDER,
            setting_key=key,
            value_encrypted=stored,
            description=f"{PROVIDER}.{key}",
        )
        try:
            IntegrationSettingsAuditService(self.repository).log_change(
                provider=PROVIDER,
                setting_key=key,
                old_cipher=old,
                new_cipher=stored,
            )
        except Exception:
            logger.exception("Integration audit log failed for %s", key)
