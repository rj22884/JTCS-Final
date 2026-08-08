"""Real Meta WhatsApp Test Connection checks for Integration Settings."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.modules.settings.crypto import encrypt_value
from app.modules.settings.repositories import IntegrationSettingsRepository
from app.modules.settings.services import IntegrationSettingsService
from app.modules.settings.whatsapp_meta_client import MetaGraphError, WhatsAppMetaClient

logger = logging.getLogger(__name__)

PROVIDER = "whatsapp_meta"

LABELS = {
    "app_id": "App ID",
    "app_secret": "App Secret",
    "access_token": "Access Token",
    "business_id": "Business ID",
    "waba_id": "WhatsApp Business Account ID",
    "phone_number_id": "Phone Number ID",
    "graph_api_version": "Graph API Version",
    "webhook_url": "Webhook URL",
    "webhook_verify_token": "Webhook Verify Token",
}


class WhatsAppTestService:
    def __init__(
        self,
        settings: IntegrationSettingsService | None = None,
        repository: IntegrationSettingsRepository | None = None,
    ):
        self.settings = settings or IntegrationSettingsService()
        self.repository = repository or IntegrationSettingsRepository()

    def run(
        self,
        *,
        send_test_message: bool = False,
        test_to_number: str | None = None,
    ) -> dict[str, Any]:
        cfg = self.settings.get_provider_config_decrypted(PROVIDER)
        checks: list[dict[str, Any]] = []
        missing = self._missing_fields(cfg)

        if missing:
            status = "Not Configured"
            self._set_status(status)
            return {
                "ok": False,
                "connection_status": status,
                "status_code": "not_configured",
                "missing": missing,
                "missing_labels": [LABELS.get(m, m) for m in missing],
                "checks": [
                    {
                        "name": "Configuration completeness",
                        "ok": False,
                        "detail": "Missing: " + ", ".join(LABELS.get(m, m) for m in missing),
                    }
                ],
                "message": "Configuration incomplete.",
            }

        client = WhatsAppMetaClient(
            access_token=cfg["access_token"],
            graph_api_version=cfg.get("graph_api_version"),
        )

        # 1 Business ID
        checks.append(self._check_business(client, cfg["business_id"]))
        # 2 WABA
        checks.append(self._check_waba(client, cfg["waba_id"]))
        # 3 Phone Number
        checks.append(self._check_phone(client, cfg["phone_number_id"]))
        # 4 Graph reachability (reuse phone/waba success as reachability + explicit me)
        checks.append(self._check_graph_reachability(client))
        # 5 Webhook validation (local completeness + localhost warning)
        checks.append(self._check_webhook(cfg))
        # 6 Permission / token debug (+ persist expiry)
        checks.append(
            self._check_permissions(
                client,
                app_id=cfg["app_id"],
                app_secret=cfg["app_secret"],
                access_token=cfg["access_token"],
            )
        )
        # 7 WABA subscribed apps (webhook delivery readiness)
        checks.append(self._check_subscribed_apps(client, cfg.get("waba_id") or ""))
        # 7 Optional test message
        if send_test_message:
            checks.append(
                self._check_send_message(
                    client,
                    phone_number_id=cfg["phone_number_id"],
                    to_number=test_to_number,
                )
            )
        else:
            checks.append(
                {
                    "name": "Optional test message",
                    "ok": True,
                    "skipped": True,
                    "detail": "Skipped (enable send_test_message to send).",
                }
            )

        failed = [c for c in checks if not c.get("ok") and not c.get("skipped")]
        partial_ok = any(c.get("ok") for c in checks)
        if not failed:
            status = "Connected"
            status_code = "connected"
            ok = True
            message = "All Meta WhatsApp connection checks passed."
        elif partial_ok:
            status = "Partial Configuration"
            status_code = "partial"
            ok = False
            message = "Some checks failed. Review details below."
        else:
            status = "Not Configured"
            status_code = "not_configured"
            ok = False
            message = "Connection checks failed."

        self._set_status(status)
        return {
            "ok": ok,
            "connection_status": status,
            "status_code": status_code,
            "missing": [],
            "missing_labels": [],
            "checks": checks,
            "message": message,
            "field_values": self.settings.get_provider_settings_masked(PROVIDER)["field_values"],
        }

    def _missing_fields(self, cfg: dict[str, str]) -> list[str]:
        required = [
            "app_id",
            "app_secret",
            "access_token",
            "business_id",
            "waba_id",
            "phone_number_id",
            "graph_api_version",
        ]
        return [k for k in required if not (cfg.get(k) or "").strip()]

    def _check_business(self, client: WhatsAppMetaClient, business_id: str) -> dict[str, Any]:
        try:
            biz = client.get_business(business_id)
            return {
                "name": "Business ID validation",
                "ok": True,
                "detail": f"Business OK: {biz.get('name') or business_id}",
            }
        except MetaGraphError as exc:
            return {"name": "Business ID validation", "ok": False, "detail": str(exc)}

    def _check_waba(self, client: WhatsAppMetaClient, waba_id: str) -> dict[str, Any]:
        try:
            waba = client.get_waba(waba_id)
            return {
                "name": "WABA validation",
                "ok": True,
                "detail": f"WABA OK: {waba.get('name') or waba_id}",
            }
        except MetaGraphError as exc:
            return {"name": "WABA validation", "ok": False, "detail": str(exc)}

    def _check_phone(self, client: WhatsAppMetaClient, phone_number_id: str) -> dict[str, Any]:
        try:
            phone = client.get_phone(phone_number_id)
            return {
                "name": "Phone Number validation",
                "ok": True,
                "detail": (
                    f"Phone OK: {phone.get('display_phone_number') or phone_number_id}"
                    f" ({phone.get('verified_name') or 'no display name'})"
                ),
            }
        except MetaGraphError as exc:
            return {"name": "Phone Number validation", "ok": False, "detail": str(exc)}

    def _check_graph_reachability(self, client: WhatsAppMetaClient) -> dict[str, Any]:
        try:
            me = client.get("/me", {"fields": "id,name"})
            return {
                "name": "Graph API reachability",
                "ok": True,
                "detail": f"Graph reachable as {me.get('name') or me.get('id')}",
            }
        except MetaGraphError as exc:
            return {"name": "Graph API reachability", "ok": False, "detail": str(exc)}

    def _check_webhook(self, cfg: dict[str, str]) -> dict[str, Any]:
        url = (cfg.get("webhook_url") or "").strip()
        token = (cfg.get("webhook_verify_token") or "").strip()
        if not url:
            return {
                "name": "Webhook validation",
                "ok": False,
                "detail": "Webhook URL is empty.",
            }
        if "localhost" in url.lower() or "127.0.0.1" in url:
            return {
                "name": "Webhook validation",
                "ok": False,
                "detail": (
                    "Webhook URL is localhost — Meta cannot reach it. "
                    "Use ngrok or a public APP_BASE_URL."
                ),
            }
        if not url.startswith("https://"):
            return {
                "name": "Webhook validation",
                "ok": False,
                "detail": "Webhook URL should use https in production.",
            }
        if not token:
            return {
                "name": "Webhook validation",
                "ok": False,
                "detail": "Webhook Verify Token is missing. Use Generate Verify Token.",
            }
        return {
            "name": "Webhook validation",
            "ok": True,
            "detail": f"Webhook URL + verify token OK ({url})",
        }

    def _check_subscribed_apps(self, client: WhatsAppMetaClient, waba_id: str) -> dict[str, Any]:
        if not waba_id:
            return {
                "name": "Webhook subscription",
                "ok": False,
                "detail": "WABA ID missing — cannot check subscribed_apps.",
            }
        try:
            apps = client.list_subscribed_apps(waba_id)
            if apps:
                labels = []
                for a in apps[:5]:
                    labels.append(str(a.get("id") or a.get("name") or "app"))
                self._set_plain(
                    "webhook_subscribed_fields",
                    "messages, message_deliveries, message_reads, message_template_status_update",
                )
                return {
                    "name": "Webhook subscription",
                    "ok": True,
                    "detail": f"App subscribed on WABA ({len(apps)}): {', '.join(labels)}",
                }
            return {
                "name": "Webhook subscription",
                "ok": False,
                "detail": "No subscribed apps on WABA. Use Resubscribe Webhooks in ERP.",
            }
        except MetaGraphError as exc:
            return {
                "name": "Webhook subscription",
                "ok": False,
                "detail": str(exc),
            }

    def _check_permissions(
        self,
        client: WhatsAppMetaClient,
        *,
        app_id: str,
        app_secret: str,
        access_token: str,
    ) -> dict[str, Any]:
        try:
            from datetime import datetime

            data = client.debug_token(app_id, app_secret, access_token)
            info = (data.get("data") or {}) if isinstance(data, dict) else {}
            exp_ts = info.get("expires_at") or 0
            if exp_ts and int(exp_ts) > 0:
                self._set_plain(
                    "token_expires_at",
                    datetime.utcfromtimestamp(int(exp_ts)).strftime("%Y-%m-%d %H:%M:%S"),
                )
            if info.get("is_valid") is False:
                return {
                    "name": "Permission validation",
                    "ok": False,
                    "detail": "Access token is invalid or expired (debug_token).",
                }
            scopes = info.get("scopes") or info.get("granular_scopes") or []
            if isinstance(scopes, list) and scopes:
                scope_txt = ", ".join(
                    s if isinstance(s, str) else str(s.get("scope") or s) for s in scopes[:12]
                )
                return {
                    "name": "Permission validation",
                    "ok": True,
                    "detail": f"Token valid. Scopes: {scope_txt}",
                }
            return {
                "name": "Permission validation",
                "ok": True,
                "detail": "Token debug succeeded.",
            }
        except MetaGraphError as exc:
            return {"name": "Permission validation", "ok": False, "detail": str(exc)}

    def _set_plain(self, key: str, value: str) -> None:
        self.repository.upsert(
            provider=PROVIDER,
            setting_key=key,
            value_encrypted=encrypt_value(value or ""),
            description=f"{PROVIDER}.{key}",
        )

    def _check_send_message(
        self,
        client: WhatsAppMetaClient,
        *,
        phone_number_id: str,
        to_number: str | None,
    ) -> dict[str, Any]:
        to_raw = (to_number or "").strip()
        digits = re.sub(r"\D", "", to_raw)
        if len(digits) < 10:
            return {
                "name": "Optional test message",
                "ok": False,
                "detail": "Provide test_to_number (E.164) to send a test message.",
            }
        try:
            result = client.send_test_text(
                phone_number_id,
                digits,
                "JTCS ERP Integration Settings: WhatsApp test message.",
            )
            msg_id = ((result.get("messages") or [{}])[0] or {}).get("id")
            return {
                "name": "Optional test message",
                "ok": True,
                "detail": f"Test message accepted by Meta. id={msg_id or 'n/a'}",
            }
        except MetaGraphError as exc:
            return {"name": "Optional test message", "ok": False, "detail": str(exc)}

    def _set_status(self, status: str) -> None:
        self.repository.upsert(
            provider=PROVIDER,
            setting_key="connection_status",
            value_encrypted=encrypt_value(status),
            description=f"{PROVIDER}.connection_status",
        )
