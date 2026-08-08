"""SMTP send + IMAP sync into unified CrmConversation / CrmMessage."""

from __future__ import annotations

import email
import imaplib
import logging
import re
from datetime import datetime
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

from flask import current_app
from flask_mail import Message

from app.extensions import mail
from app.modules.communication.customer_link_service import CustomerLinkService
from app.modules.communication.services import CommunicationService
from app.modules.notification.services import NotificationService
from app.modules.shared.timeline_service import TimelineService

logger = logging.getLogger(__name__)


def _decode_mime_header(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            out.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(chunk)
    return "".join(out)


class EmailChannelService:
    def send_reply(
        self,
        *,
        to_email: str,
        body: str,
        subject: str | None = None,
        conversation_id: int | None = None,
    ) -> dict:
        to_email = (to_email or "").strip()
        if not to_email or "@" not in to_email:
            return {"ok": False, "error": "Valid recipient email required"}
        if not (body or "").strip():
            return {"ok": False, "error": "Message body required"}
        try:
            sender = current_app.config.get("MAIL_DEFAULT_SENDER") or current_app.config.get("MAIL_USERNAME")
            msg = Message(
                subject=subject or f"Re: Conversation #{conversation_id or ''}",
                recipients=[to_email],
                body=body,
                sender=sender,
            )
            mail.send(msg)
            return {"ok": True, "external_message_id": f"smtp:{conversation_id}:{datetime.utcnow().timestamp()}"}
        except Exception as exc:
            logger.exception("SMTP send failed")
            return {"ok": False, "error": str(exc)}

    def sync_inbox(self, *, limit: int = 30) -> dict:
        """Pull recent unseen (or recent) IMAP messages into CRM."""
        server = current_app.config.get("IMAP_SERVER") or ""
        user = current_app.config.get("IMAP_USERNAME") or ""
        password = current_app.config.get("IMAP_PASSWORD") or ""
        port = int(current_app.config.get("IMAP_PORT") or 993)
        use_ssl = bool(current_app.config.get("IMAP_USE_SSL", True))
        folder = current_app.config.get("IMAP_FOLDER") or "INBOX"

        if not server or not user or not password:
            return {"ok": False, "error": "IMAP not configured (IMAP_SERVER / IMAP_USERNAME / IMAP_PASSWORD)"}

        imported = 0
        skipped = 0
        errors: list[str] = []
        try:
            client = imaplib.IMAP4_SSL(server, port) if use_ssl else imaplib.IMAP4(server, port)
            client.login(user, password)
            client.select(folder)
            typ, data = client.search(None, "UNSEEN")
            if typ != "OK":
                typ, data = client.search(None, "ALL")
            ids = (data[0] or b"").split()
            ids = ids[-limit:]
            for mid in ids:
                try:
                    typ, msg_data = client.fetch(mid, "(RFC822)")
                    if typ != "OK" or not msg_data or not msg_data[0]:
                        continue
                    raw = msg_data[0][1]
                    if self._import_raw_email(raw):
                        imported += 1
                        client.store(mid, "+FLAGS", "\\Seen")
                    else:
                        skipped += 1
                except Exception as exc:
                    errors.append(str(exc))
            client.logout()
        except Exception as exc:
            logger.exception("IMAP sync failed")
            return {"ok": False, "error": str(exc), "imported": imported, "skipped": skipped}

        return {"ok": True, "imported": imported, "skipped": skipped, "errors": errors}

    def _import_raw_email(self, raw: bytes) -> bool:
        msg = email.message_from_bytes(raw)
        message_id = (msg.get("Message-ID") or "").strip() or None
        if message_id and CommunicationService().message_exists_by_external_id(message_id[:128]):
            return False

        from_name, from_addr = parseaddr(msg.get("From") or "")
        subject = _decode_mime_header(msg.get("Subject"))
        body = self._extract_body(msg)
        attachments = self._save_attachments(msg)

        linked = CustomerLinkService().resolve_email(
            from_addr,
            display_name=from_name or from_addr,
            source="Email",
            message=(body or "")[:500],
        )
        conversation_id = CommunicationService().find_or_open_conversation(
            channel="Email",
            subject=subject or f"Email from {from_addr}",
            customer_id=linked.get("customer_id"),
            lead_id=linked.get("lead_id"),
            contact_email=from_addr,
            external_thread_key=from_addr.lower() if from_addr else None,
        )

        first_att = attachments[0] if attachments else None
        msg_id = CommunicationService().add_message(
            conversation_id,
            body=body or "(no body)",
            channel="Email",
            direction="Inbound",
            attachment_path=(first_att or {}).get("path"),
            attachment_name=(first_att or {}).get("name"),
            attachment_mime_type=(first_att or {}).get("mime"),
            media_type="email",
            external_message_id=(message_id or "")[:128] or None,
            delivery_status="Delivered",
            bump_unread=True,
        )
        TimelineService().add_event(
            event_type="EmailReceived",
            title=subject or f"Email from {from_addr}",
            description=(body or "")[:500],
            customer_id=linked.get("customer_id"),
            lead_id=linked.get("lead_id"),
            entity_type="CrmMessage",
            entity_id=msg_id,
        )
        NotificationService().notify_roles_or_all(
            notification_type="Email",
            title=f"Email: {subject or from_addr}",
            message=(body or "")[:300],
            link_url=f"/crm/inbox?channel=Email&c={conversation_id}",
            customer_id=linked.get("customer_id"),
            lead_id=linked.get("lead_id"),
            entity_type="CrmConversation",
            entity_id=conversation_id,
        )
        return True

    def _extract_body(self, msg) -> str:
        if msg.is_multipart():
            plain = None
            html = None
            for part in msg.walk():
                ctype = part.get_content_type()
                disp = str(part.get("Content-Disposition") or "")
                if "attachment" in disp:
                    continue
                try:
                    payload = part.get_payload(decode=True) or b""
                    text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                except Exception:
                    continue
                if ctype == "text/plain" and plain is None:
                    plain = text
                elif ctype == "text/html" and html is None:
                    html = text
            if plain:
                return plain.strip()
            if html:
                return re.sub(r"<[^>]+>", " ", html).strip()
            return ""
        try:
            payload = msg.get_payload(decode=True) or b""
            return payload.decode(msg.get_content_charset() or "utf-8", errors="replace").strip()
        except Exception:
            return str(msg.get_payload() or "")

    def _save_attachments(self, msg) -> list[dict]:
        saved: list[dict] = []
        if not msg.is_multipart():
            return saved
        folder = Path(
            current_app.config.get("CRM_EMAIL_ATTACHMENTS_FOLDER")
            or (Path(current_app.config["UPLOAD_FOLDER"]) / "email_attachments")
        )
        folder.mkdir(parents=True, exist_ok=True)
        for part in msg.walk():
            disp = str(part.get("Content-Disposition") or "")
            filename = part.get_filename()
            if not filename and "attachment" not in disp:
                continue
            filename = _decode_mime_header(filename) or "attachment.bin"
            try:
                data = part.get_payload(decode=True) or b""
            except Exception:
                continue
            if not data:
                continue
            safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)[:180]
            stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
            dest = folder / f"{stamp}_{safe}"
            dest.write_bytes(data)
            try:
                rel = dest.relative_to(Path(current_app.config["UPLOAD_FOLDER"]))
                store_path = f"uploads/{rel.as_posix()}"
            except ValueError:
                store_path = str(dest)
            saved.append(
                {
                    "path": store_path,
                    "name": safe,
                    "mime": part.get_content_type(),
                }
            )
        return saved
