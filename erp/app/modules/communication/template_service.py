"""Quick replies and message templates for Communication Center."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import text

from app.extensions import db
from app.modules.communication.whatsapp_template_catalog import (
    merge_template_rows,
    public_meta_error,
    select_inbox_templates,
)
from app.modules.shared.schema import ensure_crm_schema

logger = logging.getLogger(__name__)


class TemplateService:
    def list_quick_replies(self, *, channel: str | None = None) -> list[dict]:
        ensure_crm_schema()
        clauses = ["IsActive = 1"]
        params: dict = {}
        if channel:
            clauses.append("(Channel IS NULL OR Channel = :channel OR Channel = N'All')")
            params["channel"] = channel
        where = " AND ".join(clauses)
        rows = db.session.execute(
            text(
                f"""
                SELECT QuickReplyID, Title, Body, Channel, Shortcut, SortOrder, CreatedDate
                FROM dbo.CrmQuickReply
                WHERE {where}
                ORDER BY SortOrder, Title
                """
            ),
            params,
        ).mappings().all()
        return [dict(r) for r in rows]

    def create_quick_reply(
        self,
        *,
        title: str,
        body: str,
        channel: str | None = None,
        shortcut: str | None = None,
        sort_order: int = 0,
        user_id: int | None = None,
    ) -> int:
        ensure_crm_schema()
        if not (title or "").strip() or not (body or "").strip():
            raise ValueError("Title and body are required")
        row = db.session.execute(
            text(
                """
                INSERT INTO dbo.CrmQuickReply
                    (Title, Body, Channel, Shortcut, SortOrder, CreatedByUserID)
                OUTPUT INSERTED.QuickReplyID
                VALUES (:title, :body, :channel, :shortcut, :sort_order, :uid)
                """
            ),
            {
                "title": title.strip()[:120],
                "body": body.strip(),
                "channel": (channel or "")[:50] or None,
                "shortcut": (shortcut or "")[:40] or None,
                "sort_order": sort_order,
                "uid": user_id,
            },
        ).first()
        db.session.commit()
        return int(row[0]) if row else 0

    def delete_quick_reply(self, quick_reply_id: int) -> None:
        ensure_crm_schema()
        db.session.execute(
            text(
                """
                UPDATE dbo.CrmQuickReply
                SET IsActive = 0, ModifiedDate = :now
                WHERE QuickReplyID = :id
                """
            ),
            {"id": quick_reply_id, "now": datetime.utcnow()},
        )
        db.session.commit()

    def list_templates(self, *, channel: str | None = None) -> list[dict]:
        ensure_crm_schema()
        clauses = ["IsActive = 1"]
        params: dict = {}
        if channel:
            clauses.append("Channel = :channel")
            params["channel"] = channel
        where = " AND ".join(clauses)
        rows = db.session.execute(
            text(
                f"""
                SELECT TemplateID, Name, Channel, Subject, Body, ExternalTemplateName,
                       LanguageCode, Category, VariablesJson, TemplateStatus, IsActive,
                       CreatedDate
                FROM dbo.CrmMessageTemplate
                WHERE {where}
                ORDER BY Name
                """
            ),
            params,
        ).mappings().all()
        return [dict(r) for r in rows]

    def list_inbox_templates(self, *, channel: str | None = None) -> dict:
        """Inbox dropdown rows.

        WhatsApp (and the All tab) include usable templates from the connected
        WABA. Other channels stay on the local template table.
        """
        local_rows = self.list_templates(channel=channel or None)
        if channel and channel.strip().lower() != "whatsapp":
            return {"ok": True, "rows": local_rows, "meta_error": None, "defaults": {}}
        meta_rows, meta_error, defaults = self._fetch_meta_template_rows()
        return {
            "ok": True,
            "rows": merge_template_rows(meta_rows, local_rows),
            "meta_error": meta_error,
            "defaults": defaults,
        }

    def _fetch_meta_template_rows(self) -> tuple[list[dict], str | None, dict]:
        from app.modules.settings.services import IntegrationSettingsService
        from app.modules.settings.whatsapp_meta_client import WhatsAppMetaClient

        cfg = IntegrationSettingsService().get_provider_config_decrypted("whatsapp_meta") or {}
        waba_id = (cfg.get("waba_id") or "").strip()
        token = (cfg.get("access_token") or "").strip()
        phone_id = (cfg.get("phone_number_id") or "").strip()
        if not waba_id or not token:
            return [], "WhatsApp Business Account is not connected, so Meta templates could not be loaded.", {}
        client = WhatsAppMetaClient(
            access_token=token,
            graph_api_version=cfg.get("graph_api_version"),
        )
        try:
            raw_rows = client.list_message_templates(waba_id)
        except Exception as exc:
            logger.warning("WhatsApp template catalog fetch failed: %s", type(exc).__name__)
            return [], public_meta_error(exc), {}
        defaults: dict[str, str] = {}
        if phone_id:
            try:
                phone = client.get_phone(phone_id)
                display = str(phone.get("display_phone_number") or "").strip()
                if display:
                    defaults["business_whatsapp_number"] = display
            except Exception as exc:
                logger.warning("WhatsApp business number lookup failed: %s", type(exc).__name__)
        return select_inbox_templates(raw_rows), None, defaults

    @staticmethod
    def interpolate(body: str, values: dict | None = None) -> str:
        text_body = body or ""
        for key, val in (values or {}).items():
            text_body = text_body.replace("{{" + str(key) + "}}", str(val or ""))
        return text_body

    def create_template(
        self,
        *,
        name: str,
        body: str,
        channel: str = "WhatsApp",
        subject: str | None = None,
        external_template_name: str | None = None,
        language_code: str | None = None,
        user_id: int | None = None,
    ) -> int:
        ensure_crm_schema()
        if not (name or "").strip() or not (body or "").strip():
            raise ValueError("Name and body are required")
        row = db.session.execute(
            text(
                """
                INSERT INTO dbo.CrmMessageTemplate
                    (Name, Channel, Subject, Body, ExternalTemplateName, LanguageCode, CreatedByUserID)
                OUTPUT INSERTED.TemplateID
                VALUES (:name, :channel, :subject, :body, :ext, :lang, :uid)
                """
            ),
            {
                "name": name.strip()[:150],
                "channel": (channel or "WhatsApp")[:50],
                "subject": (subject or "")[:255] or None,
                "body": body.strip(),
                "ext": (external_template_name or "")[:150] or None,
                "lang": (language_code or "")[:20] or None,
                "uid": user_id,
            },
        ).first()
        db.session.commit()
        return int(row[0]) if row else 0

    def delete_template(self, template_id: int) -> None:
        ensure_crm_schema()
        db.session.execute(
            text(
                """
                UPDATE dbo.CrmMessageTemplate
                SET IsActive = 0, ModifiedDate = :now
                WHERE TemplateID = :id
                """
            ),
            {"id": template_id, "now": datetime.utcnow()},
        )
        db.session.commit()
