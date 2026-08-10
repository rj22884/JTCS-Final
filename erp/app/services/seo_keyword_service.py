"""SEO keyword management — admin CRUD and public active-keyword helpers."""

from __future__ import annotations

import json
import re
from datetime import datetime

from sqlalchemy import func, text

from app.extensions import db
from app.models.seo_keyword import SeoKeyword

PRELOAD_KEYWORDS: tuple[str, ...] = (
    "income tax consultant",
    "GST services",
    "TDS return filing",
    "ITR filing India",
    "web app developer",
    "ERP software",
    "stamp vendor near me",
    "CSC services",
    "government forms",
    "banking services",
    "digital signature DSC",
    "certificate services",
    "annexure forms",
    "online application",
    "accounting services Haldwani",
    "Uttarakhand",
    "India",
    "Uttar Pradesh",
    "Almora",
    "Kumaon",
    "Garhwal",
    "Nainital",
    "Pithoragarh",
    "Ramnagar",
    "Rudrapur",
    "Udham Singh Nagar",
    "Sitarganj",
    "Khatima",
    "Banbasa",
    "Pilibhit",
    "Rampur",
    "Moradabad",
    "Delhi",
    "New Delhi",
    "Ranikhet",
    "Dwarahat",
    "Karnaprayag",
    "Haridwar",
    "Dehradun",
    "Rishikesh",
    "Himachal",
    "Mandi",
    "Punjab",
    "Kharar",
)

META_KEYWORDS_MAX_LEN = 280


def get_active_keywords() -> list[str]:
    """Fetch all active keywords as a list (ordered by id)."""
    try:
        rows = (
            db.session.query(SeoKeyword.keyword)
            .filter(SeoKeyword.is_active.is_(True))
            .order_by(SeoKeyword.id.asc())
            .all()
        )
        return [str(row[0]).strip() for row in rows if row and row[0] and str(row[0]).strip()]
    except Exception:
        db.session.rollback()
        return []


def normalize_keyword(raw: str | None) -> str:
    value = re.sub(r"\s+", " ", (raw or "").strip())
    return value[:255]


def split_bulk_keywords(raw: str | None) -> list[str]:
    """Split comma / newline / semicolon separated keywords."""
    if not raw:
        return []
    parts = re.split(r"[,;\n]+", raw)
    seen: set[str] = set()
    result: list[str] = []
    for part in parts:
        keyword = normalize_keyword(part)
        if not keyword:
            continue
        key = keyword.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(keyword)
    return result


def build_meta_keywords(keywords: list[str] | None = None, max_len: int = META_KEYWORDS_MAX_LEN) -> str:
    """Comma-separated keywords capped near 200–300 characters."""
    items = keywords if keywords is not None else get_active_keywords()
    if not items:
        return ""
    parts: list[str] = []
    current = 0
    for item in items:
        addition = len(item) if not parts else len(item) + 2
        if current + addition > max_len:
            break
        parts.append(item)
        current += addition
    return ", ".join(parts)


def build_schema_description(keywords: list[str] | None = None) -> str:
    items = keywords if keywords is not None else get_active_keywords()
    sample = ", ".join(items[:8]) if items else "tax, GST, and compliance services"
    return (
        f"JTCS Expert in Haldwani, Uttarakhand offers {sample} "
        f"and related professional services across Kumaon and nearby regions."
    )


def build_schema_payload(keywords: list[str] | None = None) -> dict:
    items = keywords if keywords is not None else get_active_keywords()
    return {
        "@context": "https://schema.org",
        "@type": "ProfessionalService",
        "name": "JTCS Expert",
        "description": build_schema_description(items),
        "keywords": ", ".join(items) if items else "JTCS Expert, Haldwani, Uttarakhand",
        "areaServed": "Haldwani, Uttarakhand, India",
        "address": {
            "@type": "PostalAddress",
            "addressLocality": "Haldwani",
            "addressRegion": "Uttarakhand",
            "addressCountry": "IN",
        },
    }


def build_json_ld(keywords: list[str] | None = None) -> str:
    return json.dumps(build_schema_payload(keywords), ensure_ascii=True)


class SeoKeywordService:
    """Admin-facing SEO keyword operations with idempotent schema bootstrap."""

    def ensure_schema(self) -> None:
        db.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.seo_keywords', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.seo_keywords (
                        id INT IDENTITY(1,1) NOT NULL
                            CONSTRAINT PK_seo_keywords PRIMARY KEY,
                        keyword NVARCHAR(255) NOT NULL,
                        is_active BIT NOT NULL
                            CONSTRAINT DF_seo_keywords_is_active DEFAULT (1),
                        created_at DATETIME2 NOT NULL
                            CONSTRAINT DF_seo_keywords_created_at DEFAULT (SYSUTCDATETIME())
                    );
                    CREATE UNIQUE INDEX UX_seo_keywords_keyword ON dbo.seo_keywords (keyword);
                    CREATE INDEX IX_seo_keywords_active ON dbo.seo_keywords (is_active, id);
                END
                """
            )
        )
        db.session.commit()
        self.seed_preload_keywords()
        self.ensure_menu()

    def seed_preload_keywords(self) -> int:
        inserted = 0
        for keyword in PRELOAD_KEYWORDS:
            existing = (
                db.session.query(SeoKeyword.id)
                .filter(func.lower(SeoKeyword.keyword) == keyword.casefold())
                .first()
            )
            if existing:
                continue
            db.session.add(
                SeoKeyword(
                    keyword=keyword,
                    is_active=True,
                    created_at=datetime.utcnow(),
                )
            )
            inserted += 1
        if inserted:
            db.session.commit()
        return inserted

    def ensure_menu(self) -> None:
        db.session.execute(
            text(
                """
                DECLARE @ParentID INT;
                DECLARE @AdminRoles NVARCHAR(50) = N'Administrator,Admin';

                SELECT TOP 1 @ParentID = MenuID
                FROM dbo.MenuMaster
                WHERE MenuName = N'Admin Role'
                  AND ParentMenuID IS NULL
                ORDER BY MenuID;

                IF @ParentID IS NULL
                BEGIN
                    INSERT INTO dbo.MenuMaster (
                        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                        Description, IsActive, RoleName
                    )
                    VALUES (
                        NULL, N'Admin Role', N'bi-archive', NULL, 1,
                        N'Administrator tools', 1, @AdminRoles
                    );
                    SET @ParentID = SCOPE_IDENTITY();
                END;

                IF EXISTS (
                    SELECT 1 FROM dbo.MenuMaster
                    WHERE ParentMenuID = @ParentID AND MenuName = N'SEO Keywords'
                )
                BEGIN
                    UPDATE dbo.MenuMaster
                    SET MenuURL = N'/admin/seo',
                        MenuIcon = N'bi-search',
                        DisplayOrder = 65,
                        Description = N'Manage SEO keywords for meta, footer, and schema',
                        IsActive = 1,
                        RoleName = @AdminRoles
                    WHERE ParentMenuID = @ParentID AND MenuName = N'SEO Keywords';
                END
                ELSE IF EXISTS (
                    SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/seo'
                )
                BEGIN
                    UPDATE dbo.MenuMaster
                    SET ParentMenuID = @ParentID,
                        MenuName = N'SEO Keywords',
                        MenuIcon = N'bi-search',
                        DisplayOrder = 65,
                        Description = N'Manage SEO keywords for meta, footer, and schema',
                        IsActive = 1,
                        RoleName = @AdminRoles
                    WHERE MenuURL = N'/admin/seo';
                END
                ELSE
                BEGIN
                    INSERT INTO dbo.MenuMaster (
                        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                        Description, IsActive, RoleName
                    )
                    VALUES (
                        @ParentID, N'SEO Keywords', N'bi-search', N'/admin/seo', 65,
                        N'Manage SEO keywords for meta, footer, and schema', 1, @AdminRoles
                    );
                END;
                """
            )
        )
        db.session.commit()

    def list_all(self) -> list[SeoKeyword]:
        return (
            db.session.query(SeoKeyword)
            .order_by(SeoKeyword.is_active.desc(), SeoKeyword.id.asc())
            .all()
        )

    def add_keyword(self, raw: str | None) -> SeoKeyword:
        keyword = normalize_keyword(raw)
        if not keyword:
            raise ValueError("Keyword is required.")
        existing = (
            db.session.query(SeoKeyword)
            .filter(func.lower(SeoKeyword.keyword) == keyword.casefold())
            .first()
        )
        if existing:
            raise ValueError(f'Keyword "{keyword}" already exists.')
        row = SeoKeyword(keyword=keyword, is_active=True, created_at=datetime.utcnow())
        db.session.add(row)
        db.session.commit()
        return row

    def bulk_add(self, raw: str | None) -> dict:
        keywords = split_bulk_keywords(raw)
        if not keywords:
            raise ValueError("Provide at least one keyword (comma-separated).")
        added = 0
        skipped = 0
        for keyword in keywords:
            existing = (
                db.session.query(SeoKeyword.id)
                .filter(func.lower(SeoKeyword.keyword) == keyword.casefold())
                .first()
            )
            if existing:
                skipped += 1
                continue
            db.session.add(
                SeoKeyword(keyword=keyword, is_active=True, created_at=datetime.utcnow())
            )
            added += 1
        if added:
            db.session.commit()
        return {"added": added, "skipped": skipped, "total": len(keywords)}

    def toggle(self, keyword_id: int, is_active: bool | None = None) -> SeoKeyword:
        row = db.session.get(SeoKeyword, keyword_id)
        if not row:
            raise ValueError("Keyword not found.")
        if is_active is None:
            row.is_active = not bool(row.is_active)
        else:
            row.is_active = bool(is_active)
        db.session.commit()
        return row

    def delete(self, keyword_id: int) -> None:
        row = db.session.get(SeoKeyword, keyword_id)
        if not row:
            raise ValueError("Keyword not found.")
        db.session.delete(row)
        db.session.commit()

    def to_dict(self, row: SeoKeyword) -> dict:
        return {
            "id": row.id,
            "keyword": row.keyword,
            "is_active": bool(row.is_active),
            "created_at": row.created_at.isoformat(timespec="seconds") if row.created_at else None,
        }
