"""Meta WhatsApp Cloud API webhook → CrmConversation / CrmMessage."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from flask import current_app

from app.modules.communication.customer_link_service import CustomerLinkService, normalize_phone
from app.modules.communication.services import CommunicationService
from app.modules.communication.whatsapp_provider import WhatsAppCloudApiProvider, is_cloud_api_configured
from app.modules.notification.services import NotificationService
from app.modules.shared.timeline_service import TimelineService

logger = logging.getLogger(__name__)


class WhatsAppWebhookService:
    def __init__(self):
        self.comm = CommunicationService()
        self.link = CustomerLinkService()
        self.timeline = TimelineService()
        self.notifications = NotificationService()

    def process_payload(self, payload: dict[str, Any], *, raw_body: bytes | None = None) -> dict:
        """Process Meta webhook JSON. Always returns quickly with counts."""
        if (payload.get("object") or "") != "whatsapp_business_account":
            return {"ok": True, "ignored": True, "reason": "not_whatsapp_business_account"}

        messages_in = 0
        statuses_in = 0
        errors: list[str] = []

        for entry in payload.get("entry") or []:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                for status in value.get("statuses") or []:
                    try:
                        if self._handle_status(status):
                            statuses_in += 1
                    except Exception as exc:
                        logger.exception("WhatsApp status handler failed")
                        errors.append(str(exc))
                contacts = {
                    (c.get("wa_id") or ""): (c.get("profile") or {}).get("name")
                    for c in (value.get("contacts") or [])
                }
                for msg in value.get("messages") or []:
                    try:
                        if self._handle_message(msg, contacts):
                            messages_in += 1
                    except Exception as exc:
                        logger.exception("WhatsApp message handler failed")
                        errors.append(str(exc))

        return {
            "ok": True,
            "messages": messages_in,
            "statuses": statuses_in,
            "errors": errors,
        }

    def _handle_status(self, status: dict) -> bool:
        wamid = status.get("id")
        st = status.get("status")
        if not wamid or not st:
            return False
        err = None
        errors = status.get("errors") or []
        if errors:
            err = str((errors[0] or {}).get("title") or errors[0])[:500]
        return self.comm.update_delivery_status(
            external_message_id=wamid,
            status=st,
            error_detail=err,
        )

    def _handle_message(self, msg: dict, contacts: dict[str, str | None]) -> bool:
        wamid = msg.get("id")
        if not wamid:
            return False
        if self.comm.message_exists_by_external_id(wamid):
            return False

        from_wa = msg.get("from") or ""
        mobile = normalize_phone(from_wa)
        display_name = contacts.get(from_wa) or contacts.get(mobile)

        body, media_type, media_id, mime_hint, filename = self._extract_content(msg)
        attachment_path = None
        attachment_name = None
        attachment_mime = None
        attachment_size = None

        if media_id:
            saved = self._download_and_store(media_id, filename_hint=filename)
            if saved.get("ok"):
                attachment_path = saved.get("path")
                attachment_name = saved.get("filename")
                attachment_mime = saved.get("mime_type") or mime_hint
                attachment_size = saved.get("size")
            else:
                body = (body or "") + f"\n[Media unavailable: {saved.get('error')}]"

        linked = self.link.resolve_mobile(
            mobile,
            display_name=display_name,
            source="WhatsApp",
            message=(body or "")[:500],
        )
        subject = display_name or f"WhatsApp {mobile[-10:] if mobile else ''}"
        conversation_id = self.comm.find_or_open_conversation(
            channel="WhatsApp",
            subject=subject,
            customer_id=linked.get("customer_id"),
            lead_id=linked.get("lead_id"),
            contact_mobile=mobile,
            external_thread_key=mobile,
        )

        msg_id = self.comm.add_message(
            conversation_id,
            body=body or f"[{media_type or 'message'}]",
            channel="WhatsApp",
            direction="Inbound",
            attachment_path=attachment_path,
            attachment_name=attachment_name,
            attachment_mime_type=attachment_mime,
            attachment_size_bytes=attachment_size,
            media_type=media_type or "text",
            external_message_id=wamid,
            delivery_status="Delivered",
            bump_unread=True,
        )

        self.timeline.add_event(
            event_type="WhatsAppMessage",
            title=f"WhatsApp from {subject}",
            description=(body or "")[:500],
            customer_id=linked.get("customer_id"),
            lead_id=linked.get("lead_id"),
            entity_type="CrmMessage",
            entity_id=msg_id,
        )

        self.notifications.notify_roles_or_all(
            notification_type="WhatsApp",
            title=f"WhatsApp: {subject}",
            message=(body or "")[:300],
            link_url=f"/crm/inbox?channel=WhatsApp&c={conversation_id}",
            priority="Normal",
            customer_id=linked.get("customer_id"),
            lead_id=linked.get("lead_id"),
            entity_type="CrmConversation",
            entity_id=conversation_id,
        )

        # Best-effort mark read on Meta (optional)
        try:
            if is_cloud_api_configured():
                from app.modules.settings.services import IntegrationSettingsService

                cfg = IntegrationSettingsService().get_provider_config_decrypted("whatsapp_meta")
                WhatsAppCloudApiProvider(cfg).mark_as_read(wamid)
        except Exception:
            pass

        return True

    def _extract_content(self, msg: dict) -> tuple[str, str | None, str | None, str | None, str | None]:
        mtype = msg.get("type") or "text"
        if mtype == "text":
            return (msg.get("text") or {}).get("body") or "", "text", None, None, None
        if mtype in {"image", "document", "audio", "video", "sticker"}:
            media = msg.get(mtype) or {}
            caption = media.get("caption") or ""
            fname = media.get("filename")
            mime = media.get("mime_type")
            return caption or f"[{mtype}]", mtype, media.get("id"), mime, fname
        if mtype == "location":
            loc = msg.get("location") or {}
            return (
                f"Location: {loc.get('latitude')}, {loc.get('longitude')} {loc.get('name') or ''}".strip(),
                "location",
                None,
                None,
                None,
            )
        if mtype == "contacts":
            return "[Contact card]", "contacts", None, None, None
        if mtype == "button":
            return (msg.get("button") or {}).get("text") or "[Button]", "button", None, None, None
        if mtype == "interactive":
            interactive = msg.get("interactive") or {}
            reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
            return reply.get("title") or "[Interactive]", "interactive", None, None, None
        return f"[{mtype}]", mtype, None, None, None

    def _download_and_store(self, media_id: str, *, filename_hint: str | None = None) -> dict:
        try:
            from app.modules.settings.services import IntegrationSettingsService

            cfg = IntegrationSettingsService().get_provider_config_decrypted("whatsapp_meta")
            if not is_cloud_api_configured(cfg):
                return {"ok": False, "error": "Cloud API not configured"}
            result = WhatsAppCloudApiProvider(cfg).download_media(media_id)
            if not result.get("ok"):
                return result
            folder = Path(current_app.config.get("CRM_WHATSAPP_MEDIA_FOLDER")
                          or (Path(current_app.config["UPLOAD_FOLDER"]) / "whatsapp_media"))
            folder.mkdir(parents=True, exist_ok=True)
            fname = filename_hint or result.get("filename") or f"{media_id}.bin"
            # Sanitize filename
            safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in fname)[:180]
            dest = folder / f"{media_id}_{safe}"
            dest.write_bytes(result["content"])
            # Store path relative to static/uploads when possible
            try:
                rel = dest.relative_to(Path(current_app.config["UPLOAD_FOLDER"]))
                store_path = f"uploads/{rel.as_posix()}"
            except ValueError:
                store_path = str(dest)
            return {
                "ok": True,
                "path": store_path,
                "filename": safe,
                "mime_type": result.get("mime_type"),
                "size": result.get("size"),
            }
        except Exception as exc:
            logger.exception("Media download failed for %s", media_id)
            return {"ok": False, "error": str(exc)}
