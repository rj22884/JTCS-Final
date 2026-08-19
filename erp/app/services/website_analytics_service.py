"""Website visitor analytics — ingest + admin summaries.

Completely separate from GST/ITR/accounting/customer tables.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
import threading
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import text

from app.extensions import db

logger = logging.getLogger(__name__)

_SCHEMA_READY = False
ACTIVE_WINDOW_MINUTES = 5
DEDUP_SECONDS = 8
MAX_EVENTS_PER_MINUTE = 80
MAX_URL_LEN = 400
MAX_TITLE_LEN = 200

_rate_lock = threading.Lock()
_rate_buckets: dict[str, deque[float]] = defaultdict(deque)


def _clip(value: str | None, length: int) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:length]


def _parse_ua(user_agent: str) -> tuple[str, str, str]:
    ua = (user_agent or "").lower()
    if "ipad" in ua or "tablet" in ua or ("android" in ua and "mobile" not in ua):
        device = "Tablet"
    elif "mobi" in ua or "iphone" in ua or "android" in ua:
        device = "Mobile"
    else:
        device = "Desktop"

    if "edg/" in ua or "edge/" in ua:
        browser = "Edge"
    elif "chrome" in ua and "edg" not in ua:
        browser = "Chrome"
    elif "firefox" in ua:
        browser = "Firefox"
    elif "safari" in ua and "chrome" not in ua:
        browser = "Safari"
    else:
        browser = "Other"

    if "windows" in ua:
        os_name = "Windows"
    elif "android" in ua:
        os_name = "Android"
    elif "iphone" in ua or "ipad" in ua or "ios" in ua:
        os_name = "iOS"
    elif "mac os" in ua or "macintosh" in ua:
        os_name = "macOS"
    elif "linux" in ua:
        os_name = "Linux"
    else:
        os_name = "Other"
    return device, browser, os_name


def _referrer_source(referrer: str, page_host: str) -> str:
    raw = (referrer or "").strip()
    if not raw:
        return "Direct"
    try:
        host = (urlparse(raw).hostname or "").lower().removeprefix("www.")
    except Exception:
        return "Other Websites"
    if not host:
        return "Direct"
    page = (page_host or "").lower().removeprefix("www.")
    if page and (host == page or host.endswith("." + page)):
        return "Direct"
    if "google." in host or host == "google":
        return "Google"
    if "facebook." in host or host in {"fb.com", "fb.me", "m.facebook.com"}:
        return "Facebook"
    if "instagram." in host:
        return "Instagram"
    if "whatsapp." in host or host in {"wa.me", "web.whatsapp.com"}:
        return "WhatsApp"
    return "Other Websites"


def _page_path(page_url: str) -> str:
    raw = (page_url or "").strip()
    if not raw:
        return "/"
    try:
        parsed = urlparse(raw)
        path = parsed.path or "/"
    except Exception:
        path = raw.split("?", 1)[0] or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or "/"
    return path[:300]


def _hash_ip(ip: str, secret: str) -> str:
    raw = f"{(ip or '').strip()}|{(secret or '')[:12]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def allow_rate(ip_hash: str) -> bool:
    now = time.time()
    with _rate_lock:
        bucket = _rate_buckets[ip_hash]
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= MAX_EVENTS_PER_MINUTE:
            return False
        bucket.append(now)
        return True


class WebsiteAnalyticsService:
    def ensure_schema(self) -> None:
        global _SCHEMA_READY
        if _SCHEMA_READY:
            return
        db.session.execute(
            text(
                """
                IF OBJECT_ID(N'dbo.WebsiteVisitorLog', N'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.WebsiteVisitorLog (
                        LogID           INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                        VisitorId       NVARCHAR(48)  NOT NULL,
                        SessionId       NVARCHAR(48)  NOT NULL,
                        EventType       NVARCHAR(12)  NOT NULL
                            CONSTRAINT DF_WebsiteVisitorLog_Event DEFAULT (N'view'),
                        PageUrl         NVARCHAR(400) NULL,
                        PagePath        NVARCHAR(300) NOT NULL,
                        PageTitle       NVARCHAR(200) NULL,
                        VisitDateTime   DATETIME      NOT NULL
                            CONSTRAINT DF_WebsiteVisitorLog_Visit DEFAULT (GETDATE()),
                        ReferrerHost    NVARCHAR(120) NULL,
                        TrafficSource   NVARCHAR(40)  NULL,
                        DeviceType      NVARCHAR(20)  NULL,
                        Browser         NVARCHAR(40)  NULL,
                        OperatingSystem NVARCHAR(40)  NULL,
                        IpHash          NVARCHAR(32)  NULL
                    );
                    CREATE INDEX IX_WebsiteVisitorLog_Visit
                        ON dbo.WebsiteVisitorLog (VisitDateTime DESC);
                    CREATE INDEX IX_WebsiteVisitorLog_Visitor
                        ON dbo.WebsiteVisitorLog (VisitorId, VisitDateTime DESC);
                    CREATE INDEX IX_WebsiteVisitorLog_Path
                        ON dbo.WebsiteVisitorLog (PagePath, VisitDateTime DESC);
                    CREATE INDEX IX_WebsiteVisitorLog_Event
                        ON dbo.WebsiteVisitorLog (EventType, VisitDateTime DESC);
                END;
                """
            )
        )
        db.session.commit()
        self.ensure_menu()
        _SCHEMA_READY = True

    def ensure_menu(self) -> None:
        db.session.execute(
            text(
                """
                DECLARE @ParentID INT;
                DECLARE @AdminRoles NVARCHAR(100) = N'Administrator,Admin';

                SELECT TOP 1 @ParentID = MenuID
                FROM dbo.MenuMaster
                WHERE ParentMenuID IS NULL
                  AND MenuName IN (N'Admin Role', N'Admin')
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
                    SELECT 1 FROM dbo.MenuMaster WHERE MenuURL = N'/admin/website-analytics'
                )
                    UPDATE dbo.MenuMaster
                    SET ParentMenuID = @ParentID,
                        MenuName = N'Website Analytics',
                        MenuIcon = N'bi-graph-up-arrow',
                        DisplayOrder = 66,
                        Description = N'Public website visitor statistics',
                        IsActive = 1,
                        RoleName = @AdminRoles
                    WHERE MenuURL = N'/admin/website-analytics';
                ELSE IF EXISTS (
                    SELECT 1 FROM dbo.MenuMaster
                    WHERE ParentMenuID = @ParentID AND MenuName = N'Website Analytics'
                )
                    UPDATE dbo.MenuMaster
                    SET MenuURL = N'/admin/website-analytics',
                        MenuIcon = N'bi-graph-up-arrow',
                        DisplayOrder = 66,
                        Description = N'Public website visitor statistics',
                        IsActive = 1,
                        RoleName = @AdminRoles
                    WHERE ParentMenuID = @ParentID AND MenuName = N'Website Analytics';
                ELSE
                    INSERT INTO dbo.MenuMaster (
                        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                        Description, IsActive, RoleName
                    )
                    VALUES (
                        @ParentID, N'Website Analytics', N'bi-graph-up-arrow',
                        N'/admin/website-analytics', 66,
                        N'Public website visitor statistics', 1, @AdminRoles
                    );
                """
            )
        )
        db.session.commit()

    def ingest(self, payload: dict[str, Any], *, ip: str, user_agent: str, secret: str) -> None:
        self.ensure_schema()
        ip_hash = _hash_ip(ip, secret)
        if not allow_rate(ip_hash):
            logger.warning("Website analytics rate-limited ip_hash=%s", ip_hash)
            return

        visitor_id = _clip(payload.get("visitor_id") or payload.get("visitorId"), 48)
        session_id = _clip(payload.get("session_id") or payload.get("sessionId"), 48)
        if not visitor_id or not session_id:
            return
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,48}", visitor_id):
            return
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,48}", session_id):
            return

        event_type = _clip(payload.get("event_type") or payload.get("eventType") or "view", 12).lower()
        if event_type not in {"view", "ping"}:
            event_type = "view"

        page_url = _clip(payload.get("page_url") or payload.get("pageUrl"), MAX_URL_LEN)
        page_path = _page_path(page_url or payload.get("page_path") or "/")
        page_title = _clip(payload.get("page_title") or payload.get("pageTitle"), MAX_TITLE_LEN)
        referrer = _clip(payload.get("referrer"), 300)
        try:
            page_host = (urlparse(page_url).hostname or "") if page_url else ""
        except Exception:
            page_host = ""
        source = _referrer_source(referrer, page_host)
        try:
            ref_host = (urlparse(referrer).hostname or "")[:120] if referrer else ""
        except Exception:
            ref_host = ""
        device, browser, os_name = _parse_ua(user_agent)

        now = datetime.now()
        if event_type == "view":
            dup = db.session.execute(
                text(
                    """
                    SELECT TOP 1 LogID
                    FROM dbo.WebsiteVisitorLog
                    WHERE VisitorId = :vid
                      AND PagePath = :path
                      AND EventType = N'view'
                      AND VisitDateTime >= :since
                    """
                ),
                {
                    "vid": visitor_id,
                    "path": page_path,
                    "since": now - timedelta(seconds=DEDUP_SECONDS),
                },
            ).first()
            if dup:
                return

        db.session.execute(
            text(
                """
                INSERT INTO dbo.WebsiteVisitorLog (
                    VisitorId, SessionId, EventType, PageUrl, PagePath, PageTitle,
                    VisitDateTime, ReferrerHost, TrafficSource, DeviceType, Browser,
                    OperatingSystem, IpHash
                )
                VALUES (
                    :visitor_id, :session_id, :event_type, :page_url, :page_path, :page_title,
                    :visit_dt, :referrer_host, :traffic_source, :device_type, :browser,
                    :os_name, :ip_hash
                )
                """
            ),
            {
                "visitor_id": visitor_id,
                "session_id": session_id,
                "event_type": event_type,
                "page_url": page_url or None,
                "page_path": page_path,
                "page_title": page_title or None,
                "visit_dt": now,
                "referrer_host": ref_host or None,
                "traffic_source": source,
                "device_type": device,
                "browser": browser,
                "os_name": os_name,
                "ip_hash": ip_hash,
            },
        )
        db.session.commit()

    @staticmethod
    def resolve_period(
        preset: str | None,
        date_from: date | None,
        date_to: date | None,
    ) -> tuple[date, date, str]:
        today = date.today()
        key = (preset or "last30").strip().lower()
        if key == "custom" and date_from and date_to:
            if date_from > date_to:
                date_from, date_to = date_to, date_from
            return date_from, date_to, "custom"
        mapping = {
            "today": (today, today),
            "yesterday": (today - timedelta(days=1), today - timedelta(days=1)),
            "last7": (today - timedelta(days=6), today),
            "last30": (today - timedelta(days=29), today),
            "last90": (today - timedelta(days=89), today),
            "this_month": (today.replace(day=1), today),
            "last_month": (
                (today.replace(day=1) - timedelta(days=1)).replace(day=1),
                today.replace(day=1) - timedelta(days=1),
            ),
            "this_year": (date(today.year, 1, 1), today),
        }
        if key not in mapping:
            key = "last30"
        start, end = mapping[key]
        return start, end, key

    def dashboard(self, *, date_from: date, date_to: date) -> dict[str, Any]:
        self.ensure_schema()
        today = date.today()
        yesterday = today - timedelta(days=1)
        week_from = today - timedelta(days=6)
        month_from = today.replace(day=1)
        active_since = datetime.now() - timedelta(minutes=ACTIVE_WINDOW_MINUTES)

        def _count_visitors(start: date, end: date) -> int:
            return int(
                db.session.execute(
                    text(
                        """
                        SELECT COUNT(DISTINCT VisitorId)
                        FROM dbo.WebsiteVisitorLog
                        WHERE CAST(VisitDateTime AS DATE) >= :d1
                          AND CAST(VisitDateTime AS DATE) <= :d2
                        """
                    ),
                    {"d1": start, "d2": end},
                ).scalar()
                or 0
            )

        def _count_views(start: date, end: date) -> int:
            return int(
                db.session.execute(
                    text(
                        """
                        SELECT COUNT(1)
                        FROM dbo.WebsiteVisitorLog
                        WHERE EventType = N'view'
                          AND CAST(VisitDateTime AS DATE) >= :d1
                          AND CAST(VisitDateTime AS DATE) <= :d2
                        """
                    ),
                    {"d1": start, "d2": end},
                ).scalar()
                or 0
            )

        range_visitors = _count_visitors(date_from, date_to)
        returning = int(
            db.session.execute(
                text(
                    """
                    SELECT COUNT(DISTINCT l.VisitorId)
                    FROM dbo.WebsiteVisitorLog l
                    WHERE CAST(l.VisitDateTime AS DATE) >= :d1
                      AND CAST(l.VisitDateTime AS DATE) <= :d2
                      AND EXISTS (
                            SELECT 1
                            FROM dbo.WebsiteVisitorLog p
                            WHERE p.VisitorId = l.VisitorId
                              AND CAST(p.VisitDateTime AS DATE) < :d1
                      )
                    """
                ),
                {"d1": date_from, "d2": date_to},
            ).scalar()
            or 0
        )
        new_visitors = max(range_visitors - returning, 0)
        active = int(
            db.session.execute(
                text(
                    """
                    SELECT COUNT(DISTINCT VisitorId)
                    FROM dbo.WebsiteVisitorLog
                    WHERE VisitDateTime >= :since
                    """
                ),
                {"since": active_since},
            ).scalar()
            or 0
        )

        trend_rows = db.session.execute(
            text(
                """
                SELECT
                    CAST(VisitDateTime AS DATE) AS d,
                    COUNT(DISTINCT VisitorId) AS visitors,
                    SUM(CASE WHEN EventType = N'view' THEN 1 ELSE 0 END) AS views
                FROM dbo.WebsiteVisitorLog
                WHERE CAST(VisitDateTime AS DATE) >= :d1
                  AND CAST(VisitDateTime AS DATE) <= :d2
                GROUP BY CAST(VisitDateTime AS DATE)
                ORDER BY d
                """
            ),
            {"d1": date_from, "d2": date_to},
        ).mappings().all()
        trend_map = {
            row["d"]: {"visitors": int(row["visitors"] or 0), "views": int(row["views"] or 0)}
            for row in trend_rows
        }
        trend = []
        cursor = date_from
        while cursor <= date_to:
            bucket = trend_map.get(cursor) or {"visitors": 0, "views": 0}
            trend.append(
                {
                    "date": cursor.isoformat(),
                    "label": cursor.strftime("%d/%m"),
                    "visitors": bucket["visitors"],
                    "views": bucket["views"],
                }
            )
            cursor += timedelta(days=1)

        def _breakdown(column: str) -> list[dict[str, Any]]:
            allowed = {"DeviceType", "Browser", "OperatingSystem", "TrafficSource"}
            if column not in allowed:
                return []
            rows = db.session.execute(
                text(
                    f"""
                    SELECT ISNULL({column}, N'Other') AS label, COUNT(DISTINCT VisitorId) AS n
                    FROM dbo.WebsiteVisitorLog
                    WHERE CAST(VisitDateTime AS DATE) >= :d1
                      AND CAST(VisitDateTime AS DATE) <= :d2
                    GROUP BY ISNULL({column}, N'Other')
                    ORDER BY n DESC
                    """
                ),
                {"d1": date_from, "d2": date_to},
            ).mappings().all()
            total = sum(int(r["n"] or 0) for r in rows) or 1
            return [
                {
                    "label": str(r["label"] or "Other"),
                    "count": int(r["n"] or 0),
                    "pct": round(100.0 * int(r["n"] or 0) / total, 1),
                }
                for r in rows
            ]

        pages = db.session.execute(
            text(
                """
                SELECT TOP 20
                    PagePath,
                    MAX(PageTitle) AS PageTitle,
                    SUM(CASE WHEN EventType = N'view' THEN 1 ELSE 0 END) AS views
                FROM dbo.WebsiteVisitorLog
                WHERE CAST(VisitDateTime AS DATE) >= :d1
                  AND CAST(VisitDateTime AS DATE) <= :d2
                GROUP BY PagePath
                ORDER BY views DESC
                """
            ),
            {"d1": date_from, "d2": date_to},
        ).mappings().all()

        recent = db.session.execute(
            text(
                """
                SELECT TOP 40
                    VisitDateTime, PagePath, PageTitle, DeviceType, TrafficSource
                FROM dbo.WebsiteVisitorLog
                WHERE EventType = N'view'
                  AND CAST(VisitDateTime AS DATE) >= :d1
                  AND CAST(VisitDateTime AS DATE) <= :d2
                ORDER BY VisitDateTime DESC, LogID DESC
                """
            ),
            {"d1": date_from, "d2": date_to},
        ).mappings().all()

        return {
            "cards": {
                "total_visitors": _count_visitors(date(2000, 1, 1), today),
                "today_visitors": _count_visitors(today, today),
                "yesterday_visitors": _count_visitors(yesterday, yesterday),
                "week_visitors": _count_visitors(week_from, today),
                "month_visitors": _count_visitors(month_from, today),
                "total_page_views": _count_views(date(2000, 1, 1), today),
                "today_page_views": _count_views(today, today),
                "active_visitors": active,
                "new_visitors": new_visitors,
                "returning_visitors": returning,
                "range_visitors": range_visitors,
                "range_page_views": _count_views(date_from, date_to),
            },
            "trend": trend,
            "devices": _breakdown("DeviceType"),
            "browsers": _breakdown("Browser"),
            "operating_systems": _breakdown("OperatingSystem"),
            "sources": _breakdown("TrafficSource"),
            "pages": [
                {
                    "path": row["PagePath"],
                    "title": row["PageTitle"] or row["PagePath"],
                    "views": int(row["views"] or 0),
                }
                for row in pages
            ],
            "recent": [
                {
                    "time": row["VisitDateTime"].strftime("%d/%m/%Y %H:%M")
                    if row["VisitDateTime"]
                    else "",
                    "page": row["PageTitle"] or row["PagePath"],
                    "path": row["PagePath"],
                    "device": row["DeviceType"] or "—",
                    "source": row["TrafficSource"] or "Direct",
                }
                for row in recent
            ],
            "active_window_minutes": ACTIVE_WINDOW_MINUTES,
        }

    def export(self, *, fmt: str, date_from: date, date_to: date) -> tuple[bytes, str, str]:
        data = self.dashboard(date_from=date_from, date_to=date_to)
        fmt_key = (fmt or "csv").strip().lower()
        stamp = datetime.now().strftime("%Y%m%d")
        rows = [["Page", "Path", "Views"]]
        for p in data["pages"]:
            rows.append([p["title"], p["path"], p["views"]])
        rows.append([])
        rows.append(["Recent Time", "Page", "Device", "Source"])
        for r in data["recent"]:
            rows.append([r["time"], r["page"], r["device"], r["source"]])

        if fmt_key == "xlsx":
            wb = Workbook()
            ws = wb.active
            ws.title = "Website Analytics"
            ws.append(["Metric", "Value"])
            for k, v in data["cards"].items():
                ws.append([k, v])
            ws.append([])
            for row in rows:
                ws.append(row)
            buf = io.BytesIO()
            wb.save(buf)
            return (
                buf.getvalue(),
                f"website_analytics_{stamp}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        if fmt_key == "pdf":
            buf = io.BytesIO()
            doc = SimpleDocTemplate(
                buf, pagesize=A4, leftMargin=18, rightMargin=18, topMargin=22, bottomMargin=22
            )
            styles = getSampleStyleSheet()
            story = [
                Paragraph("JTCS — Website Analytics", styles["Heading2"]),
                Paragraph(
                    f"Period {date_from.strftime('%d/%m/%Y')} to {date_to.strftime('%d/%m/%Y')}",
                    styles["Normal"],
                ),
                Spacer(1, 10),
            ]
            card_table = [["Metric", "Value"]]
            labels = {
                "total_visitors": "Total Visitors",
                "today_visitors": "Today Visitors",
                "yesterday_visitors": "Yesterday Visitors",
                "week_visitors": "This Week Visitors",
                "month_visitors": "This Month Visitors",
                "total_page_views": "Total Page Views",
                "today_page_views": "Today Page Views",
                "range_page_views": "Page Views (range)",
                "active_visitors": "Active Visitors",
                "new_visitors": "New Visitors",
                "returning_visitors": "Returning Visitors",
            }
            for key, label in labels.items():
                card_table.append([label, data["cards"].get(key, 0)])
            table = Table(card_table, colWidths=[280, 140])
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F4C81")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ]
                )
            )
            story.append(table)
            doc.build(story)
            return buf.getvalue(), f"website_analytics_{stamp}.pdf", "application/pdf"

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Website Analytics", f"{date_from} to {date_to}"])
        for k, v in data["cards"].items():
            writer.writerow([k, v])
        writer.writerow([])
        writer.writerows(rows)
        return (
            buf.getvalue().encode("utf-8-sig"),
            f"website_analytics_{stamp}.csv",
            "text/csv; charset=utf-8",
        )
