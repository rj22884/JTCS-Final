"""Auto What's New: new MenuMaster pages + explicit publish() calls."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from flask import has_request_context
from sqlalchemy import select, text

from app.extensions import db
from app.models.menu_master import MenuMaster
from app.models.whats_new import WhatsNewEntry

# Leaf menus older than this are ignored by auto-sync (avoids flooding old Masters).
MENU_SYNC_LOOKBACK_DAYS = 180

# Paths that should never appear as What's New.
_EXCLUDED_URLS = {
    "/",
    "/dashboard",
    "/login",
    "/logout",
    "/health",
}

# One-time seeded announcements (non-menu UI updates). Idempotent by FeatureKey.
_BUILTIN_ANNOUNCEMENTS: list[dict] = [
    {
        "feature_key": "feature:activities.followup_moved",
        "title": "Follow-up modules under Activities",
        "detail": (
            "All Follow-up modules (ITR, TDS, DSC, and others) are now grouped under "
            "Activities → Follow Up, instead of separate top-level menus."
        ),
        "url": "/itr/followup",
        "badge": "Update",
        "entry_date": date(2026, 7, 22),
    },
    {
        "feature_key": "feature:auth.login_page_colours",
        "title": "New login page with colours",
        "detail": "Login screen refreshed with a new coloured design for a clearer, modern look.",
        "url": "/login",
        "badge": "New",
        "entry_date": date(2026, 7, 22),
    },
    {
        "feature_key": "feature:credentials_master",
        "title": "Credentials Master",
        "detail": "Masters → store Activity, URL, User ID, Password, Email & Mobile with Add / Edit / Delete.",
        "url": "/masters/credentials",
        "badge": "New",
        "entry_date": date(2026, 7, 21),
    },
    {
        "feature_key": "feature:ecourt.activity_summary_cards",
        "title": "e-Court Activity Summary cards",
        "detail": "Fee Sale, Payment Received, Cash / Non-cash, and SHCILECourt deposits on one row.",
        "url": "/shcil/ecourt-activity",
        "badge": "New",
        "entry_date": date(2026, 7, 21),
    },
    {
        "feature_key": "feature:stamp.period_summary_cards",
        "title": "Stamp Activity period cards",
        "detail": "Click Period Summary cards to filter the grid and open detail popup.",
        "url": "/shcil/stamp-activity",
        "badge": "Update",
        "entry_date": date(2026, 7, 21),
    },
]


class WhatsNewService:
    _schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        db.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.WhatsNew', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.WhatsNew (
                        EntryID INT IDENTITY(1,1) NOT NULL
                            CONSTRAINT PK_WhatsNew PRIMARY KEY,
                        FeatureKey NVARCHAR(120) NOT NULL,
                        Title NVARCHAR(200) NOT NULL,
                        Detail NVARCHAR(500) NULL,
                        UrlPath NVARCHAR(250) NULL,
                        Badge NVARCHAR(20) NULL,
                        EntryDate DATE NOT NULL,
                        Source NVARCHAR(40) NOT NULL
                            CONSTRAINT DF_WhatsNew_Source DEFAULT (N'manual'),
                        IsActive BIT NOT NULL
                            CONSTRAINT DF_WhatsNew_IsActive DEFAULT (1),
                        CreatedDate DATETIME2 NOT NULL
                            CONSTRAINT DF_WhatsNew_CreatedDate DEFAULT (SYSUTCDATETIME()),
                        ModifiedDate DATETIME2 NULL
                    );
                    CREATE UNIQUE INDEX UX_WhatsNew_FeatureKey ON dbo.WhatsNew (FeatureKey);
                    CREATE INDEX IX_WhatsNew_Active_Date
                        ON dbo.WhatsNew (IsActive, EntryDate DESC, EntryID DESC);
                END
                """
            )
        )
        db.session.commit()
        self._schema_ready = True

    @staticmethod
    def normalize_url(url: str | None) -> str:
        value = (url or "").strip()
        if not value:
            return ""
        if value.startswith("http://") or value.startswith("https://"):
            return value.rstrip("/")
        if not value.startswith("/"):
            value = "/" + value
        return value.rstrip("/") or "/"

    def publish(
        self,
        *,
        feature_key: str,
        title: str,
        detail: str | None = None,
        url: str | None = None,
        badge: str | None = "New",
        entry_date: date | None = None,
        source: str = "publish",
        update_existing: bool = False,
    ) -> WhatsNewEntry | None:
        """Insert What's New once per feature_key (idempotent)."""
        self.ensure_schema()
        key = (feature_key or "").strip()
        title_clean = (title or "").strip()
        if not key or not title_clean:
            return None

        existing = db.session.execute(
            select(WhatsNewEntry).where(WhatsNewEntry.FeatureKey == key)
        ).scalar_one_or_none()

        url_path = self.normalize_url(url) or None
        badge_clean = ((badge or "").strip()[:20] or None)
        detail_clean = ((detail or "").strip()[:500] or None)
        when = entry_date or date.today()

        if existing:
            if not update_existing:
                return existing
            existing.Title = title_clean
            existing.Detail = detail_clean
            existing.UrlPath = url_path
            existing.Badge = badge_clean
            existing.EntryDate = when
            existing.Source = (source or "publish")[:40]
            existing.IsActive = True
            existing.ModifiedDate = datetime.utcnow()
            db.session.commit()
            return existing

        row = WhatsNewEntry(
            FeatureKey=key,
            Title=title_clean,
            Detail=detail_clean,
            UrlPath=url_path,
            Badge=badge_clean,
            EntryDate=when,
            Source=(source or "publish")[:40],
            IsActive=True,
            CreatedDate=datetime.utcnow(),
        )
        db.session.add(row)
        db.session.commit()
        return row

    def sync_from_menus(self, *, lookback_days: int = MENU_SYNC_LOOKBACK_DAYS) -> int:
        """Auto-add What's New rows for recently created leaf menu pages."""
        self.ensure_schema()
        cutoff = datetime.utcnow() - timedelta(days=max(1, int(lookback_days)))
        menus = (
            db.session.execute(
                select(MenuMaster).where(
                    MenuMaster.IsActive == True,  # noqa: E712
                    MenuMaster.MenuURL.isnot(None),
                    MenuMaster.CreatedDate.isnot(None),
                    MenuMaster.CreatedDate >= cutoff,
                )
            )
            .scalars()
            .all()
        )

        added = 0
        for menu in menus:
            url = self.normalize_url(menu.MenuURL)
            if not url or url.lower() in _EXCLUDED_URLS:
                continue
            # Skip parent/section rows that somehow have a URL but also children — still OK to show.
            key = f"menu:{url.lower()}"
            exists = db.session.execute(
                select(WhatsNewEntry.EntryID).where(WhatsNewEntry.FeatureKey == key)
            ).scalar_one_or_none()
            if exists:
                continue
            # Same page already announced (e.g. builtin / publish) — skip duplicate.
            url_exists = db.session.execute(
                select(WhatsNewEntry.EntryID).where(
                    WhatsNewEntry.UrlPath == url,
                    WhatsNewEntry.IsActive == True,  # noqa: E712
                )
            ).scalar_one_or_none()
            if url_exists:
                continue

            created = menu.CreatedDate
            entry_day = created.date() if isinstance(created, datetime) else date.today()
            detail = (menu.Description or "").strip() or f"New page available: {menu.MenuName}"
            self.publish(
                feature_key=key,
                title=(menu.MenuName or "").strip() or "New menu",
                detail=detail[:500],
                url=url,
                badge="New",
                entry_date=entry_day,
                source="menu_auto",
            )
            added += 1
        return added

    def seed_builtins(self) -> None:
        for item in _BUILTIN_ANNOUNCEMENTS:
            self.publish(
                feature_key=item["feature_key"],
                title=item["title"],
                detail=item.get("detail"),
                url=item.get("url"),
                badge=item.get("badge") or "New",
                entry_date=item.get("entry_date") or date.today(),
                source="builtin",
                update_existing=False,
            )

    def refresh(self) -> None:
        """Ensure schema, seed known notes, then auto-sync new menus."""
        self.ensure_schema()
        self.seed_builtins()
        self.sync_from_menus()

    def list_entries(self, *, limit: int = 8) -> list[dict]:
        self.refresh()
        stmt = (
            select(WhatsNewEntry)
            .where(WhatsNewEntry.IsActive == True)  # noqa: E712
            .order_by(WhatsNewEntry.EntryDate.desc(), WhatsNewEntry.EntryID.desc())
        )
        if limit and limit > 0:
            stmt = stmt.limit(limit)
        rows = db.session.execute(stmt).scalars().all()

        items: list[dict] = []
        for row in rows:
            href = row.UrlPath or None
            if href and has_request_context() and not href.startswith("http"):
                # Prefer absolute app path as-is (already a site path).
                href = href
            entry_day = row.EntryDate
            if isinstance(entry_day, datetime):
                entry_day = entry_day.date()
            iso = entry_day.isoformat() if entry_day else ""
            try:
                y, m, d = iso.split("-")
                date_display = f"{d}/{m}/{y}"
            except ValueError:
                date_display = iso
            items.append(
                {
                    "title": row.Title,
                    "detail": row.Detail or "",
                    "badge": row.Badge or "",
                    "href": href,
                    "date": iso,
                    "date_display": date_display,
                    "feature_key": row.FeatureKey,
                    "source": row.Source,
                }
            )
        return items


def publish_whats_new(
    feature_key: str,
    title: str,
    *,
    detail: str | None = None,
    url: str | None = None,
    badge: str | None = "New",
    entry_date: date | None = None,
    update_existing: bool = False,
) -> WhatsNewEntry | None:
    """Public helper — call once when shipping a feature (safe to call every request)."""
    return WhatsNewService().publish(
        feature_key=feature_key,
        title=title,
        detail=detail,
        url=url,
        badge=badge,
        entry_date=entry_date,
        source="publish",
        update_existing=update_existing,
    )


def list_whats_new(*, limit: int = 8) -> list[dict]:
    return WhatsNewService().list_entries(limit=limit)
