from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.menu_master import MenuMaster


class MenuRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session

    def get_all(self, include_inactive: bool = False) -> list[MenuMaster]:
        stmt = select(MenuMaster).order_by(MenuMaster.DisplayOrder, MenuMaster.MenuID)
        if not include_inactive:
            stmt = stmt.where(MenuMaster.IsActive == True)  # noqa: E712
        return list(self.session.scalars(stmt).all())

    def get_by_id(self, menu_id: int) -> MenuMaster | None:
        return self.session.get(MenuMaster, menu_id)

    def get_active_for_role(self, role: str | None) -> list[MenuMaster]:
        from app.utils.roles import has_admin_role, roles_intersect

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
        stmt = select(MenuMaster).where(MenuMaster.MenuURL == menu_url)
        return self.session.scalars(stmt).first()

    def find_top_level_by_name(self, menu_name: str) -> MenuMaster | None:
        stmt = (
            select(MenuMaster)
            .where(MenuMaster.MenuName == menu_name, MenuMaster.ParentMenuID.is_(None))
            .order_by(MenuMaster.MenuID)
        )
        return self.session.scalars(stmt).first()

    def create(self, data: dict) -> MenuMaster:
        menu = MenuMaster(**data)
        self.session.add(menu)
        self.session.commit()
        return menu

    def update(self, menu: MenuMaster, data: dict) -> MenuMaster:
        for key, value in data.items():
            setattr(menu, key, value)
        self.session.commit()
        return menu

    def delete(self, menu: MenuMaster) -> None:
        self.session.delete(menu)
        self.session.commit()

    def deactivate(self, menu: MenuMaster) -> MenuMaster:
        menu.IsActive = False
        self.session.commit()
        return menu

    def activate(self, menu: MenuMaster) -> MenuMaster:
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
        stmt = select(MenuMaster.MenuID).where(MenuMaster.ParentMenuID == menu_id).limit(1)
        return self.session.scalars(stmt).first() is not None

    def get_children(self, menu_id: int) -> list[MenuMaster]:
        stmt = (
            select(MenuMaster)
            .where(MenuMaster.ParentMenuID == menu_id)
            .order_by(MenuMaster.DisplayOrder, MenuMaster.MenuID)
        )
        return list(self.session.scalars(stmt).all())
