"""Quick replies and message templates for Communication Center."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text

from app.extensions import db
from app.modules.shared.schema import ensure_crm_schema


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
                       LanguageCode, CreatedDate
                FROM dbo.CrmMessageTemplate
                WHERE {where}
                ORDER BY Name
                """
            ),
            params,
        ).mappings().all()
        return [dict(r) for r in rows]

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
