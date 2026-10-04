"""Auto What's New: new MenuMaster pages + explicit publish() calls."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import time

from flask import has_request_context
from sqlalchemy import func, select, text

from app.extensions import db
from app.models.menu_master import MenuMaster
from app.models.whats_new import WhatsNewEntry, WhatsNewRead
from app.utils.timezone import today_app

# Badge only items the user has not opened in this window.
UNREAD_LOOKBACK_DAYS = 7

def default_workflow(title: str, detail: str | None, url: str | None) -> str:
    """Readable steps when a feature has no hand-written workflow yet."""
    name = (title or "this page").strip()
    lines = [f"Open {name} from the menu."]
    path = (url or "").strip()
    if path:
        lines.append(f"The page address is {path}.")
    note = (detail or "").strip()
    if note:
        lines.append(note)
    lines.append("Complete the work on that screen, then save.")
    lines.append("After you have read these steps, use Open and work.")
    return "\n".join(lines)


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
        "workflow": (
            "Open Activities in the top menu.\n"
            "Open Follow Up.\n"
            "Choose the module you need: ITR, GST, TDS, DSC, or another follow-up list.\n"
            "Open the client row and tick the work stages on that screen.\n"
            "Save the entry when the stage work is done."
        ),
    },
    {
        "feature_key": "feature:auth.login_page_colours",
        "title": "New login page with colours",
        "detail": "Login screen refreshed with a new coloured design for a clearer, modern look.",
        "url": "/login",
        "badge": "New",
        "entry_date": date(2026, 7, 22),
        "workflow": (
            "Open the sign-in page.\n"
            "Enter your email and password.\n"
            "Use Login. The coloured sign-in screen is the updated login.\n"
            "Forgot Password and Forgot User ID stay on the same page."
        ),
    },
    {
        "feature_key": "feature:credentials_master",
        "title": "Credentials Master",
        "detail": "Masters → store Activity, URL, User ID, Password, Email & Mobile with Add / Edit / Delete.",
        "url": "/masters/credentials",
        "badge": "New",
        "entry_date": date(2026, 7, 21),
        "workflow": (
            "Open Masters.\n"
            "Open Credentials.\n"
            "Add a row with Activity, URL, User ID, Password, Email, and Mobile.\n"
            "Use Edit to change a saved row, or Delete to remove it.\n"
            "Save before you leave the screen."
        ),
    },
    {
        "feature_key": "feature:ecourt.activity_summary_cards",
        "title": "e-Court Activity Summary cards",
        "detail": "Fee Sale, Payment Received, Cash / Non-cash, and SHCILECourt deposits on one row.",
        "url": "/shcil/ecourt-activity",
        "badge": "New",
        "entry_date": date(2026, 7, 21),
        "workflow": (
            "Open e-Court activity.\n"
            "Read the summary row: Fee Sale, Payment Received, Cash / Non-cash, and SHCIL deposits.\n"
            "Use the card that matches the work you need to check.\n"
            "Continue the receipt or sale work from that screen."
        ),
    },
    {
        "feature_key": "feature:stamp.period_summary_cards",
        "title": "Stamp Activity period cards",
        "detail": "Click Period Summary cards to filter the grid and open detail popup.",
        "url": "/shcil/stamp-activity",
        "badge": "Update",
        "entry_date": date(2026, 7, 21),
        "workflow": (
            "Open Stamp activity.\n"
            "Click a Period Summary card.\n"
            "The grid filters to that period.\n"
            "Open the detail popup from the card and finish the stamp work there."
        ),
    },
    {
        "feature_key": "feature:header.whats_new",
        "title": "What's New beside Notifications",
        "detail": "New updates show on the What's New button, with a count, a read workflow, and a screen video.",
        "url": "/dashboard",
        "badge": "New",
        "entry_date": date(2026, 10, 4),
        "workflow": (
            "Look at the top bar, beside Notifications.\n"
            "What's New shows a red count when an update is still unread.\n"
            "Open the button and choose the new item.\n"
            "Read the workflow steps from top to bottom.\n"
            "Play the screen video and watch the same steps on the screen.\n"
            "Use Open and work to go to that page and do the work."
        ),
    },
]


class WhatsNewService:
    _schema_ready = False
    _last_refresh = 0.0
    _workflow_backfill_done = False

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
                IF COL_LENGTH(N'dbo.WhatsNew', N'Workflow') IS NULL
                    ALTER TABLE dbo.WhatsNew ADD Workflow NVARCHAR(MAX) NULL;
                IF COL_LENGTH(N'dbo.WhatsNew', N'VideoPath') IS NULL
                    ALTER TABLE dbo.WhatsNew ADD VideoPath NVARCHAR(400) NULL;
                IF OBJECT_ID(N'dbo.WhatsNewRead', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.WhatsNewRead (
                        ReadID INT IDENTITY(1,1) NOT NULL
                            CONSTRAINT PK_WhatsNewRead PRIMARY KEY,
                        UserID INT NOT NULL,
                        EntryID INT NOT NULL,
                        ReadDate DATETIME2 NOT NULL
                            CONSTRAINT DF_WhatsNewRead_ReadDate DEFAULT (SYSUTCDATETIME())
                    );
                    CREATE UNIQUE INDEX UX_WhatsNewRead_User_Entry
                        ON dbo.WhatsNewRead (UserID, EntryID);
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
        workflow: str | None = None,
        video_path: str | None = None,
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
        workflow_clean = (workflow or "").strip() or None
        video_clean = ((video_path or "").strip()[:400] or None)
        when = entry_date or date.today()

        if existing:
            changed = False
            if workflow_clean and not (existing.Workflow or "").strip():
                existing.Workflow = workflow_clean
                changed = True
            if video_clean and not (existing.VideoPath or "").strip():
                existing.VideoPath = video_clean
                changed = True
            if not update_existing:
                if changed:
                    existing.ModifiedDate = datetime.utcnow()
                    db.session.commit()
                return existing
            existing.Title = title_clean
            existing.Detail = detail_clean
            existing.UrlPath = url_path
            existing.Badge = badge_clean
            existing.EntryDate = when
            existing.Source = (source or "publish")[:40]
            existing.IsActive = True
            if workflow_clean:
                existing.Workflow = workflow_clean
            if video_clean:
                existing.VideoPath = video_clean
            existing.ModifiedDate = datetime.utcnow()
            db.session.commit()
            return existing

        row = WhatsNewEntry(
            FeatureKey=key,
            Title=title_clean,
            Detail=detail_clean,
            Workflow=workflow_clean,
            VideoPath=video_clean,
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
            title = (menu.MenuName or "").strip() or "New menu"
            self.publish(
                feature_key=key,
                title=title,
                detail=detail[:500],
                url=url,
                badge="New",
                entry_date=entry_day,
                source="menu_auto",
                workflow=default_workflow(title, detail, url),
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
                workflow=item.get("workflow"),
                video_path=item.get("video"),
            )

    def refresh(self) -> None:
        """Ensure schema, seed known notes, then auto-sync new menus."""
        self.ensure_schema()
        now = time.time()
        if now - WhatsNewService._last_refresh < 120:
            return
        self.seed_builtins()
        self.sync_from_menus()
        if not WhatsNewService._workflow_backfill_done:
            self.backfill_empty_workflows()
            WhatsNewService._workflow_backfill_done = True
        WhatsNewService._last_refresh = now

    def backfill_empty_workflows(self) -> None:
        rows = db.session.execute(
            select(WhatsNewEntry).where(WhatsNewEntry.IsActive == True)  # noqa: E712
        ).scalars().all()
        changed = False
        for row in rows:
            if (row.Workflow or "").strip():
                continue
            row.Workflow = default_workflow(row.Title, row.Detail, row.UrlPath)
            changed = True
        if changed:
            db.session.commit()

    def _read_ids(self, user_id: int) -> set[int]:
        rows = db.session.execute(
            select(WhatsNewRead.EntryID).where(WhatsNewRead.UserID == int(user_id))
        ).scalars().all()
        return {int(item) for item in rows}

    def unread_count(self, user_id: int) -> int:
        self.ensure_schema()
        cutoff = today_app() - timedelta(days=UNREAD_LOOKBACK_DAYS)
        read_ids = select(WhatsNewRead.EntryID).where(WhatsNewRead.UserID == int(user_id))
        total = db.session.execute(
            select(func.count())
            .select_from(WhatsNewEntry)
            .where(
                WhatsNewEntry.IsActive == True,  # noqa: E712
                WhatsNewEntry.EntryDate >= cutoff,
                WhatsNewEntry.EntryID.not_in(read_ids),
            )
        ).scalar_one()
        return int(total or 0)

    def mark_read(self, user_id: int, entry_id: int) -> None:
        self.ensure_schema()
        uid = int(user_id)
        eid = int(entry_id)
        exists = db.session.execute(
            select(WhatsNewRead.ReadID).where(
                WhatsNewRead.UserID == uid,
                WhatsNewRead.EntryID == eid,
            )
        ).scalar_one_or_none()
        if exists:
            return
        db.session.add(
            WhatsNewRead(UserID=uid, EntryID=eid, ReadDate=datetime.utcnow())
        )
        db.session.commit()

    def header_feed(self, user_id: int, *, limit: int = 8) -> dict:
        return {
            "items": self.list_entries(limit=limit, user_id=user_id),
            "unread_count": self.unread_count(user_id),
        }

    @staticmethod
    def _video_src(path: str | None) -> str:
        raw = (path or "").strip()
        if not raw:
            return ""
        if raw.startswith(("http://", "https://", "/")):
            return raw
        if has_request_context():
            from flask import url_for

            return url_for("static", filename=raw)
        return raw

    def list_entries(self, *, limit: int = 8, user_id: int | None = None) -> list[dict]:
        self.refresh()
        stmt = (
            select(WhatsNewEntry)
            .where(WhatsNewEntry.IsActive == True)  # noqa: E712
            .order_by(WhatsNewEntry.EntryDate.desc(), WhatsNewEntry.EntryID.desc())
        )
        if limit and limit > 0:
            stmt = stmt.limit(limit)
        rows = db.session.execute(stmt).scalars().all()
        seen = self._read_ids(user_id) if user_id else set()
        cutoff = today_app() - timedelta(days=UNREAD_LOOKBACK_DAYS)

        items: list[dict] = []
        for row in rows:
            href = row.UrlPath or ""
            entry_day = row.EntryDate
            if isinstance(entry_day, datetime):
                entry_day = entry_day.date()
            iso = entry_day.isoformat() if entry_day else ""
            try:
                y, m, d = iso.split("-")
                date_display = f"{d}/{m}/{y}"
            except ValueError:
                date_display = iso
            workflow = (row.Workflow or "").strip() or default_workflow(row.Title, row.Detail, href)
            is_unread = bool(
                user_id and entry_day and entry_day >= cutoff and int(row.EntryID) not in seen
            )
            items.append(
                {
                    "entry_id": int(row.EntryID),
                    "title": row.Title,
                    "detail": row.Detail or "",
                    "badge": row.Badge or "",
                    "href": href or "",
                    "date": iso,
                    "date_display": date_display,
                    "feature_key": row.FeatureKey,
                    "source": row.Source,
                    "workflow": workflow,
                    "video": self._video_src(row.VideoPath),
                    "is_unread": is_unread,
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
    workflow: str | None = None,
    video_path: str | None = None,
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
        workflow=workflow,
        video_path=video_path,
    )


def list_whats_new(*, limit: int = 8) -> list[dict]:
    return WhatsNewService().list_entries(limit=limit)
