from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.menu_master import MenuMaster
from app.models.menu_user_allow import MenuUserAllow

_MENU_STYLE_SCHEMA_READY = False


class MenuRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session

    def ensure_style_columns(self) -> None:
        """Add style / user-allow columns if missing (VPS-safe, idempotent)."""
        global _MENU_STYLE_SCHEMA_READY
        if _MENU_STYLE_SCHEMA_READY:
            return
        for stmt in (
            """
            IF COL_LENGTH(N'dbo.MenuMaster', N'FontColor') IS NULL
                ALTER TABLE dbo.MenuMaster ADD FontColor NVARCHAR(20) NULL;
            """,
            """
            IF COL_LENGTH(N'dbo.MenuMaster', N'FontName') IS NULL
                ALTER TABLE dbo.MenuMaster ADD FontName NVARCHAR(100) NULL;
            """,
            """
            IF COL_LENGTH(N'dbo.MenuMaster', N'BackgroundColor') IS NULL
                ALTER TABLE dbo.MenuMaster ADD BackgroundColor NVARCHAR(20) NULL;
            """,
            """
            IF COL_LENGTH(N'dbo.MenuMaster', N'AllowAllUsers') IS NULL
                ALTER TABLE dbo.MenuMaster ADD AllowAllUsers BIT NOT NULL
                    CONSTRAINT DF_MenuMaster_AllowAllUsers DEFAULT (0);
            """,
            """
            IF OBJECT_ID(N'dbo.MenuUserAllow', N'U') IS NULL
            BEGIN
                CREATE TABLE dbo.MenuUserAllow (
                    MenuID INT NOT NULL,
                    UserID INT NOT NULL,
                    CONSTRAINT PK_MenuUserAllow PRIMARY KEY (MenuID, UserID),
                    CONSTRAINT FK_MenuUserAllow_Menu FOREIGN KEY (MenuID)
                        REFERENCES dbo.MenuMaster (MenuID)
                );
                CREATE INDEX IX_MenuUserAllow_UserID ON dbo.MenuUserAllow (UserID);
            END
            """,
        ):
            self.session.execute(text(stmt))
            self.session.commit()
        _MENU_STYLE_SCHEMA_READY = True

    def list_allowed_users_map(self) -> dict[int, set[int]]:
        self.ensure_style_columns()
        rows = self.session.execute(text("SELECT MenuID, UserID FROM dbo.MenuUserAllow")).all()
        mapping: dict[int, set[int]] = {}
        for menu_id, user_id in rows:
            mapping.setdefault(int(menu_id), set()).add(int(user_id))
        return mapping

    def replace_allowed_users(self, menu_id: int, user_ids: list[int]) -> None:
        self.ensure_style_columns()
        self.session.execute(
            text("DELETE FROM dbo.MenuUserAllow WHERE MenuID = :mid"),
            {"mid": menu_id},
        )
        seen: set[int] = set()
        for raw_id in user_ids:
            try:
                user_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if user_id <= 0 or user_id in seen:
                continue
            seen.add(user_id)
            self.session.add(MenuUserAllow(MenuID=menu_id, UserID=user_id))
        self.session.flush()

    def get_all(self, include_inactive: bool = False) -> list[MenuMaster]:
        self.ensure_style_columns()
        stmt = select(MenuMaster).order_by(MenuMaster.DisplayOrder, MenuMaster.MenuID)
        if not include_inactive:
            stmt = stmt.where(MenuMaster.IsActive == True)  # noqa: E712
        return list(self.session.scalars(stmt).all())

    def get_by_id(self, menu_id: int) -> MenuMaster | None:
        self.ensure_style_columns()
        return self.session.get(MenuMaster, menu_id)

    def get_active_for_role(self, role: str | None) -> list[MenuMaster]:
        from app.utils.roles import has_admin_role, roles_intersect

        self.ensure_style_columns()
        stmt = (
            select(MenuMaster)
            .where(MenuMaster.IsActive == True)  # noqa: E712
            .order_by(MenuMaster.DisplayOrder, MenuMaster.MenuID)
        )
        menus = list(self.session.scalars(stmt).all())
        if has_admin_role(role):
            return menus
        return [menu for menu in menus if roles_intersect(role, menu.RoleName)]

    def get_parent_options(self, exclude_id: int | None = None) -> list[MenuMaster]:
        self.ensure_style_columns()
        stmt = (
            select(MenuMaster)
            .where(MenuMaster.IsActive == True)  # noqa: E712
            .order_by(MenuMaster.DisplayOrder, MenuMaster.MenuID)
        )
        menus = list(self.session.scalars(stmt).all())
        if exclude_id is None:
            return menus
        return [menu for menu in menus if menu.MenuID != exclude_id]

    def find_by_url(self, menu_url: str) -> MenuMaster | None:
        self.ensure_style_columns()
        stmt = select(MenuMaster).where(MenuMaster.MenuURL == menu_url)
        return self.session.scalars(stmt).first()

    def find_top_level_by_name(self, menu_name: str) -> MenuMaster | None:
        self.ensure_style_columns()
        stmt = (
            select(MenuMaster)
            .where(MenuMaster.MenuName == menu_name, MenuMaster.ParentMenuID.is_(None))
            .order_by(MenuMaster.MenuID)
        )
        return self.session.scalars(stmt).first()

    def create(self, data: dict) -> MenuMaster:
        self.ensure_style_columns()
        menu = MenuMaster(**data)
        self.session.add(menu)
        self.session.commit()
        return menu

    def update(self, menu: MenuMaster, data: dict) -> MenuMaster:
        self.ensure_style_columns()
        for key, value in data.items():
            setattr(menu, key, value)
        self.session.commit()
        return menu

    def delete(self, menu: MenuMaster) -> None:
        self.ensure_style_columns()
        self.session.delete(menu)
        self.session.commit()

    def deactivate(self, menu: MenuMaster) -> MenuMaster:
        self.ensure_style_columns()
        menu.IsActive = False
        self.session.commit()
        return menu

    def activate(self, menu: MenuMaster) -> MenuMaster:
        self.ensure_style_columns()
        menu.IsActive = True
        self.session.commit()
        return menu

    def reorder(self, menu_id: int, display_order: int) -> MenuMaster | None:
        menu = self.get_by_id(menu_id)
        if menu is None:
            return None
        menu.DisplayOrder = display_order
        self.session.commit()
        return menu

    def reorder_many(
        self,
        orders: list[tuple[int, int, int | None | object]],
    ) -> bool:
        """Apply display order; optional third value updates ParentMenuID when not omitted."""
        self.ensure_style_columns()
        omit_parent = object()
        pending: list[tuple[MenuMaster, int, int | None | object]] = []
        for item in orders:
            menu_id = item[0]
            display_order = item[1]
            parent_menu_id = item[2] if len(item) > 2 else omit_parent
            menu = self.get_by_id(menu_id)
            if menu is None:
                return False
            pending.append((menu, display_order, parent_menu_id))
        for menu, display_order, parent_menu_id in pending:
            menu.DisplayOrder = display_order
            if parent_menu_id is not omit_parent:
                menu.ParentMenuID = parent_menu_id  # type: ignore[assignment]
        self.session.commit()
        return True

    def has_children(self, menu_id: int) -> bool:
        self.ensure_style_columns()
        stmt = select(MenuMaster.MenuID).where(MenuMaster.ParentMenuID == menu_id).limit(1)
        return self.session.scalars(stmt).first() is not None

    def get_children(self, menu_id: int) -> list[MenuMaster]:
        self.ensure_style_columns()
        stmt = (
            select(MenuMaster)
            .where(MenuMaster.ParentMenuID == menu_id)
            .order_by(MenuMaster.DisplayOrder, MenuMaster.MenuID)
        )
        return list(self.session.scalars(stmt).all())
