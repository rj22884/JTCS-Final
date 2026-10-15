"""Admin Role → Help. Available to every signed-in user. Documentation only."""

from __future__ import annotations

from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import text

from app.decorators import login_required
from app.extensions import db
from app.services.help_catalog import HelpShot, HelpTopic, get_topic, search_topics, topics_by_group
from app.services.menu_service import MenuService

bp = Blueprint("help", __name__, url_prefix="/help")

_MENU_ENSURED = False
MENU_PATH = "/help"


def ensure_help_menus() -> None:
    """Admin Role → Help with RoleName NULL (all signed-in users). Idempotent."""
    global _MENU_ENSURED
    if _MENU_ENSURED:
        return
    try:
        db.session.execute(
            text(
                """
                DECLARE @ParentID INT;

                SELECT TOP 1 @ParentID = MenuID
                FROM dbo.MenuMaster
                WHERE MenuName = N'Admin Role' AND ParentMenuID IS NULL
                ORDER BY MenuID;

                IF @ParentID IS NULL
                BEGIN
                    INSERT INTO dbo.MenuMaster (
                        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                        Description, IsActive, RoleName
                    )
                    VALUES (
                        NULL, N'Admin Role', N'bi-archive', NULL, 1,
                        N'Administrator tools', 1, N'Administrator,Admin'
                    );
                    SET @ParentID = SCOPE_IDENTITY();
                END;

                IF EXISTS (
                    SELECT 1 FROM dbo.MenuMaster
                    WHERE MenuURL = N'/help' OR MenuName = N'Help'
                )
                BEGIN
                    UPDATE dbo.MenuMaster
                    SET ParentMenuID = @ParentID,
                        MenuName = N'Help',
                        MenuIcon = N'bi-question-circle',
                        MenuURL = N'/help',
                        DisplayOrder = 0,
                        Description = N'User help for every menu, screen, and calculation',
                        IsActive = 1,
                        RoleName = NULL
                    WHERE MenuURL = N'/help' OR MenuName = N'Help';
                END
                ELSE
                BEGIN
                    INSERT INTO dbo.MenuMaster (
                        ParentMenuID, MenuName, MenuIcon, MenuURL, DisplayOrder,
                        Description, IsActive, RoleName
                    )
                    VALUES (
                        @ParentID, N'Help', N'bi-question-circle', N'/help', 0,
                        N'User help for every menu, screen, and calculation',
                        1, NULL
                    );
                END;
                """
            )
        )
        db.session.commit()
        _MENU_ENSURED = True
    except Exception:
        db.session.rollback()


def _shot_image_url(topic: HelpTopic, shot: HelpShot, index: int) -> str | None:
    """Use a dropped PNG/WebP if present; otherwise the illustrated frame is shown."""
    static_folder = current_app.static_folder
    if not static_folder:
        return None
    folder = Path(static_folder) / "img" / "help"
    names: list[str] = []
    if shot.image:
        names.append(shot.image)
    names.extend(
        (
            f"{topic.slug}-{index}.png",
            f"{topic.slug}-{index}.webp",
            f"{topic.slug}-{index}.jpg",
            f"{topic.slug}.png",
        )
    )
    seen: set[str] = set()
    for name in names:
        clean = (name or "").replace("\\", "/").split("/")[-1]
        if not clean or clean in seen:
            continue
        seen.add(clean)
        if (folder / clean).is_file():
            return url_for("static", filename=f"img/help/{clean}")
    return None


def _default_shot(topic: HelpTopic) -> HelpShot:
    ribbon = tuple(part.strip() for part in topic.menu_path.split("→") if part.strip())
    return HelpShot(
        caption=f"Figure 1 — {topic.title}",
        title=topic.title,
        ribbon=ribbon or ("JTCS ERP",),
        highlights=(topic.summary[:220],),
    )


def _topic_context(topic: HelpTopic) -> dict:
    source_shots = topic.shots or (_default_shot(topic),)
    shots = []
    for i, shot in enumerate(source_shots, start=1):
        shots.append({"shot": shot, "image_url": _shot_image_url(topic, shot, i), "index": i})
    related = [get_topic(slug) for slug in topic.related]
    related = [item for item in related if item is not None]
    return {
        "topic": topic,
        "shots": shots,
        "related_topics": related,
        "open_url": topic.open_url,
    }


@bp.before_request
def _boot_menus():
    ensure_help_menus()


@bp.route("", methods=["GET"], strict_slashes=False)
@bp.route("/", methods=["GET"], strict_slashes=False)
@login_required
def index():
    menu_service = MenuService()
    query = (request.args.get("q") or "").strip()
    grouped = topics_by_group()
    results = search_topics(query) if query else None
    return render_template(
        "help/index.html",
        page_title="Help",
        breadcrumb=menu_service.get_breadcrumb(MENU_PATH, session.get("role")),
        groups=grouped,
        query=query,
        results=results,
        active_slug=None,
    )


@bp.route("/search")
@login_required
def search():
    query = (request.args.get("q") or "").strip()
    hits = search_topics(query)
    return jsonify(
        {
            "ok": True,
            "query": query,
            "results": [
                {
                    "slug": t.slug,
                    "title": t.title,
                    "menu_path": t.menu_path,
                    "url": url_for("help.topic", slug=t.slug),
                    "icon": t.icon,
                    "group": t.group,
                }
                for t in hits[:40]
            ],
        }
    )


@bp.route("/<slug>")
@login_required
def topic(slug: str):
    article = get_topic(slug)
    if article is None:
        abort(404)
    menu_service = MenuService()
    ctx = _topic_context(article)
    return render_template(
        "help/topic.html",
        page_title=article.title,
        breadcrumb=menu_service.get_breadcrumb(MENU_PATH, session.get("role")),
        groups=topics_by_group(),
        active_slug=article.slug,
        query="",
        **ctx,
    )
