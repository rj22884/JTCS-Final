"""SMTP send + IMAP sync into unified CrmConversation / CrmMessage."""

from __future__ import annotations

import email
import imaplib
import logging
from datetime import datetime
from email.header import decode_header
from email.utils import parseaddr
from pathlib import Path

from flask import current_app
from flask_mail import Message

from app.modules.communication.customer_link_service import CustomerLinkService
from app.modules.communication.email_html import html_to_plain, sanitize_email_html
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


def _imap_runtime() -> dict:
    """API Master IMAP first, then environment variables."""
    try:
        from app.modules.settings.services import IntegrationSettingsService

        saved = IntegrationSettingsService().imap_runtime_config()
        if saved:
            return saved
    except Exception:
        logger.debug("API Master IMAP settings unavailable; using environment", exc_info=True)
    return {
        "server": current_app.config.get("IMAP_SERVER") or "",
        "username": current_app.config.get("IMAP_USERNAME") or "",
        "password": current_app.config.get("IMAP_PASSWORD") or "",
        "port": int(current_app.config.get("IMAP_PORT") or 993),
        "use_ssl": bool(current_app.config.get("IMAP_USE_SSL", True)),
        "folder": current_app.config.get("IMAP_FOLDER") or "INBOX",
    }


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
            from app.services.email_service import EmailService

            svc = EmailService()
            if not svc.is_configured():
                return {
                    "ok": False,
                    "error": "SMTP is not configured. Set outgoing mail in Masters → API Master.",
                }
            cfg = svc._mail_config()
            sender = cfg.get("MAIL_DEFAULT_SENDER") or cfg.get("MAIL_USERNAME")
            from html import escape as html_escape

            text_body = body.replace("\r\n", "\n").replace("\r", "\n")
            html_body = "<div style=\"font-family: Calibri, Arial, sans-serif; font-size: 11pt; line-height: 1.4;\">"
            html_body += "<br>".join(html_escape(line) if line else "<br>" for line in text_body.split("\n"))
            html_body += "</div>"
            msg = Message(
                subject=subject or f"Re: Conversation #{conversation_id or ''}",
                recipients=[to_email],
                body=text_body,
                html=html_body,
                sender=sender,
            )
            svc._send_message_direct(msg)
            return {"ok": True, "external_message_id": f"smtp:{conversation_id}:{datetime.utcnow().timestamp()}"}
        except Exception as exc:
            logger.exception("SMTP send failed")
            return {"ok": False, "error": str(exc)}

    def sync_inbox(self, *, limit: int = 30) -> dict:
        """Pull recent unseen (or recent) IMAP messages into CRM."""
        imap_cfg = _imap_runtime()
        server = imap_cfg.get("server") or ""
        user = imap_cfg.get("username") or ""
        password = imap_cfg.get("password") or ""
        port = int(imap_cfg.get("port") or 993)
        use_ssl = bool(imap_cfg.get("use_ssl", True))
        folder = imap_cfg.get("folder") or "INBOX"

        if not server or not user or not password:
            return {
                "ok": False,
                "error": "IMAP not configured. Open Masters → API Master → Cloud Email and save Incoming mail (server, username, password).",
            }

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
                    raw = self._fetch_raw(client, mid)
                    if not raw:
                        continue
                    if self._import_raw_email(raw):
                        imported += 1
                        client.store(mid, "+FLAGS", "\\Seen")
                    else:
                        skipped += 1
                except Exception as exc:
                    errors.append(str(exc))
            refreshed = self._refresh_stored_html(client, limit=limit)
            client.logout()
        except Exception as exc:
            logger.exception("IMAP sync failed")
            return {"ok": False, "error": str(exc), "imported": imported, "skipped": skipped}

        return {
            "ok": True,
            "imported": imported,
            "skipped": skipped,
            "refreshed": refreshed,
            "errors": errors,
        }

    @staticmethod
    def _fetch_raw(client, mid, *, header_only: bool = False) -> bytes | None:
        spec = "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])" if header_only else "(BODY.PEEK[])"
        typ, msg_data = client.fetch(mid, spec)
        if typ != "OK" or not msg_data:
            return None
        for item in msg_data:
            if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
                return bytes(item[1])
        return None

    def _refresh_stored_html(self, client, *, limit: int) -> int:
        """Fill HTML for emails already saved from the plain-text part."""
        from app.extensions import db
        from sqlalchemy import text

        pending = {
            (row[0] or "").strip()
            for row in db.session.execute(
                text(
                    """
                    SELECT ExternalMessageID
                    FROM dbo.CrmMessage
                    WHERE Channel = N'Email'
                      AND ExternalMessageID IS NOT NULL
                      AND (BodyHtml IS NULL OR LTRIM(RTRIM(BodyHtml)) = N'')
                    """
                )
            ).all()
            if row[0]
        }
        if not pending:
            return 0
        typ, data = client.search(None, "ALL")
        if typ != "OK":
            return 0
        ids = (data[0] or b"").split()[-limit:]
        refreshed = 0
        for mid in ids:
            try:
                header = self._fetch_raw(client, mid, header_only=True)
                if not header:
                    continue
                message_id = (email.message_from_bytes(header).get("Message-ID") or "").strip()
                if message_id[:128] not in pending:
                    continue
                raw = self._fetch_raw(client, mid)
                if raw and self._refresh_email_html(raw):
                    refreshed += 1
                    pending.discard(message_id[:128])
            except Exception:
                db.session.rollback()
                logger.exception("Email HTML refresh skipped")
        return refreshed

    def _refresh_email_html(self, raw: bytes) -> bool:
        msg = email.message_from_bytes(raw)
        message_id = (msg.get("Message-ID") or "").strip()
        if not message_id or not CommunicationService().email_needs_html(message_id[:128]):
            return False
        parsed = self._parse_email(msg)
        if not parsed["html"]:
            return False
        CommunicationService().save_email_html(
            message_id[:128],
            body=parsed["plain"] or "(no body)",
            body_html=parsed["html"],
            drop_inline_image="<img" in parsed["html"].lower(),
        )
        return True

    def _import_raw_email(self, raw: bytes) -> bool:
        msg = email.message_from_bytes(raw)
        message_id = (msg.get("Message-ID") or "").strip() or None
        if message_id and CommunicationService().message_exists_by_external_id(message_id[:128]):
            self._refresh_email_html(raw)
            return False

        from_name, from_addr = parseaddr(msg.get("From") or "")
        subject = _decode_mime_header(msg.get("Subject"))
        parsed = self._parse_email(msg)
        body = parsed["plain"]
        attachments = parsed["attachments"]

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
            body_html=parsed["html"] or None,
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

    def _parse_email(self, msg) -> dict:
        """Keep the HTML part Outlook renders, and real file attachments."""
        plain = None
        html = None
        cid_map: dict[str, str] = {}
        attachments: list[dict] = []
        parts = msg.walk() if msg.is_multipart() else [msg]
        for part in parts:
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "").lower()
            if ctype == "text/plain" and plain is None and "attachment" not in disp:
                plain = self._decode_part(part)
            elif ctype == "text/html" and html is None and "attachment" not in disp:
                html = self._decode_part(part)
            elif ctype.startswith("image/") or "attachment" in disp or part.get_filename():
                if ctype in {"text/plain", "text/html", "multipart/alternative", "multipart/mixed", "multipart/related"}:
                    continue
                saved = self._store_part(part)
                if not saved:
                    continue
                cid = (part.get("Content-ID") or "").strip().strip("<>").lower()
                if cid:
                    cid_map[cid] = saved["url"]
                if "attachment" in disp and not cid:
                    attachments.append(saved)
        safe_html = sanitize_email_html(html, cid_map=cid_map) if html else ""
        if safe_html:
            plain_text = html_to_plain(safe_html)
        else:
            plain_text = (plain or "").strip()
            if not plain_text and html:
                plain_text = html_to_plain(html)
        return {"plain": plain_text, "html": safe_html, "attachments": attachments}

    @staticmethod
    def _decode_part(part) -> str:
        try:
            payload = part.get_payload(decode=True) or b""
            return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            return ""

    def _store_part(self, part) -> dict | None:
        filename = _decode_mime_header(part.get_filename()) or "inline.bin"
        try:
            data = part.get_payload(decode=True) or b""
        except Exception:
            return None
        if not data:
            return None
        folder = Path(
            current_app.config.get("CRM_EMAIL_ATTACHMENTS_FOLDER")
            or (Path(current_app.config["UPLOAD_FOLDER"]) / "email_attachments")
        )
        folder.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)[:180]
        stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        dest = folder / f"{stamp}_{safe}"
        dest.write_bytes(data)
        try:
            rel = dest.relative_to(Path(current_app.config["UPLOAD_FOLDER"]))
            store_path = f"uploads/{rel.as_posix()}"
        except ValueError:
            store_path = str(dest)
        return {
            "path": store_path,
            "url": "/static/" + store_path if store_path.startswith("uploads/") else store_path,
            "name": safe,
            "mime": part.get_content_type(),
        }
