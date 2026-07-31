from __future__ import annotations

from dataclasses import dataclass, field

from app.models.menu_master import MenuMaster
from app.repositories.menu_repository import MenuRepository
from app.utils.roles import has_admin_role, join_roles, roles_intersect


@dataclass
class MenuNode:
    id: int
    name: str
    icon: str
    url: str | None
    description: str | None
    role_name: str | None
    children: list[MenuNode] = field(default_factory=list)
    has_children: bool = False


@dataclass
class MenuAdminNode:
    menu: MenuMaster
    children: list[MenuAdminNode] = field(default_factory=list)


class MenuService:
    ADMIN_ROLES = {"Administrator", "Admin"}
    INVALID_MENU_URLS = frozenset({"none", "/none", "/others/income/none", "/others/expense/none"})

    def __init__(self, repository: MenuRepository | None = None):
        self.repository = repository or MenuRepository()

    @classmethod
    def normalize_menu_url(cls, menu_url: str | None) -> str | None:
        if not menu_url:
            return None
        cleaned = menu_url.strip()
        if not cleaned or cleaned.lower() in cls.INVALID_MENU_URLS:
            return None
        if cleaned.lower().endswith("/none"):
            return None
        return cleaned

    def can_access_menu(self, menu: MenuMaster, role: str | None) -> bool:
        if not menu.IsActive:
            return False
        if has_admin_role(role):
            return True
        return roles_intersect(role, menu.RoleName)

    def build_tree(
        self,
        menus: list[MenuMaster],
        parent_id: int | None = None,
    ) -> list[MenuNode]:
        nodes: list[MenuNode] = []
        children = [menu for menu in menus if menu.ParentMenuID == parent_id]
        children.sort(key=lambda item: (item.DisplayOrder, item.MenuID))

        for menu in children:
            child_nodes = self.build_tree(menus, menu.MenuID)
            nodes.append(
                MenuNode(
                    id=menu.MenuID,
                    name=menu.MenuName,
                    icon=menu.MenuIcon or "bi-circle",
                    url=self.normalize_menu_url(menu.MenuURL),
                    description=menu.Description,
                    role_name=menu.RoleName,
                    children=child_nodes,
                    has_children=bool(child_nodes),
                )
            )
        return nodes

    def get_navigation(self, role: str | None) -> list[MenuNode]:
        menus = self.repository.get_active_for_role(role)
        if has_admin_role(role):
            allowed_ids = {menu.MenuID for menu in menus}
            menus = self._include_parent_chain(menus, allowed_ids)
        else:
            menus = self._menus_with_accessible_ancestors(menus, role)
        return self.build_tree(menus, None)

    def _ancestors_accessible(self, menu: MenuMaster, role: str | None) -> bool:
        """True only if this menu and every parent allow the user's role."""
        current: MenuMaster | None = menu
        seen: set[int] = set()
        while current is not None:
            if current.MenuID in seen:
                return False
            seen.add(current.MenuID)
            if not self.can_access_menu(current, role):
                return False
            if not current.ParentMenuID:
                return True
            current = self.repository.get_by_id(current.ParentMenuID)
        return False

    def _menus_with_accessible_ancestors(
        self,
        menus: list[MenuMaster],
        role: str | None,
    ) -> list[MenuMaster]:
        """Keep role-allowed menus only when their full parent chain is also allowed.

        Prevents Admin Role from appearing for Operators when a child row has
        RoleName NULL (legacy "all roles") under an admin-only parent.
        """
        by_id: dict[int, MenuMaster] = {}
        kept_ids: set[int] = set()

        for menu in menus:
            if not self._ancestors_accessible(menu, role):
                continue
            kept_ids.add(menu.MenuID)
            by_id[menu.MenuID] = menu
            current = menu
            while current and current.ParentMenuID:
                parent = self.repository.get_by_id(current.ParentMenuID)
                if parent is None:
                    break
                kept_ids.add(parent.MenuID)
                by_id[parent.MenuID] = parent
                current = parent

        return [by_id[menu_id] for menu_id in kept_ids if menu_id in by_id]

    def _include_parent_chain(
        self,
        menus: list[MenuMaster],
        allowed_ids: set[int],
    ) -> list[MenuMaster]:
        by_id = {menu.MenuID: menu for menu in menus}
        expanded_ids = set(allowed_ids)

        for menu_id in list(allowed_ids):
            current = by_id.get(menu_id)
            while current and current.ParentMenuID:
                expanded_ids.add(current.ParentMenuID)
                parent = self.repository.get_by_id(current.ParentMenuID)
                if parent is None:
                    break
                by_id[parent.MenuID] = parent
                current = parent

        return [by_id[menu_id] for menu_id in expanded_ids if menu_id in by_id]

    def get_breadcrumb(self, menu_url: str, role: str | None) -> list[MenuMaster]:
        menu = self.repository.find_by_url(menu_url)
        if menu is None or not self.can_access_menu(menu, role):
            return []

        return self._breadcrumb_from_menu(menu, role)

    def get_breadcrumb_for_work_type(
        self,
        work_type: str | None,
        role: str | None,
        *,
        fallback_url: str = "/transactions/new",
    ) -> list[MenuMaster]:
        if work_type:
            module = self.repository.find_top_level_by_name(work_type.strip())
            if module is not None and self.can_access_menu(module, role):
                return self._breadcrumb_from_menu(module, role)

        return self.get_breadcrumb(fallback_url, role) or self.get_breadcrumb(
            "/transactions/new",
            role,
        )

    def _breadcrumb_from_menu(self, menu: MenuMaster, role: str | None) -> list[MenuMaster]:
        trail: list[MenuMaster] = [menu]
        current = menu
        while current.ParentMenuID:
            parent = self.repository.get_by_id(current.ParentMenuID)
            if parent is None or not self.can_access_menu(parent, role):
                break
            trail.insert(0, parent)
            current = parent
        return trail

    def list_all(self, include_inactive: bool = False) -> list[MenuMaster]:
        return self.repository.get_all(include_inactive=include_inactive)

    def list_tree_for_admin(self, include_inactive: bool = True) -> list[MenuAdminNode]:
        """Parent/child tree for the admin drag-and-drop list."""
        menus = self.list_all(include_inactive=include_inactive)
        by_parent: dict[int | None, list[MenuMaster]] = {}
        for menu in menus:
            by_parent.setdefault(menu.ParentMenuID, []).append(menu)
        for children in by_parent.values():
            children.sort(key=lambda item: (item.DisplayOrder, item.MenuID))

        def build(parent_id: int | None) -> list[MenuAdminNode]:
            return [
                MenuAdminNode(menu=menu, children=build(menu.MenuID))
                for menu in by_parent.get(parent_id, [])
            ]

        return build(None)

    def get(self, menu_id: int) -> MenuMaster | None:
        return self.repository.get_by_id(menu_id)

    def create_menu(self, data: dict) -> tuple[MenuMaster | None, str | None]:
        error = self._validate(data)
        if error:
            return None, error
        menu = self.repository.create(self._normalize_payload(data))
        self._hide_empty_shcil_parent()
        return menu, None

    def update_menu(
        self,
        menu_id: int,
        data: dict,
    ) -> tuple[MenuMaster | None, str | None]:
        menu = self.repository.get_by_id(menu_id)
        if menu is None:
            return None, "Menu not found."

        if data.get("ParentMenuID") == menu_id:
            return None, "A menu cannot be its own parent."

        error = self._validate(data, current_id=menu_id)
        if error:
            return None, error

        updated = self.repository.update(menu, self._normalize_payload(data))
        self._hide_empty_shcil_parent()
        return updated, None

    def delete_menu(self, menu_id: int) -> tuple[bool, str | None]:
        menu = self.repository.get_by_id(menu_id)
        if menu is None:
            return False, "Menu not found."

        for child in self.repository.get_children(menu_id):
            ok, error = self.delete_menu(child.MenuID)
            if error:
                return False, error

        self.repository.delete(menu)
        self._hide_empty_shcil_parent()
        return True, None

    def set_active(self, menu_id: int, is_active: bool) -> tuple[MenuMaster | None, str | None]:
        menu = self.repository.get_by_id(menu_id)
        if menu is None:
            return None, "Menu not found."
        if is_active:
            menu = self.repository.activate(menu)
        else:
            menu = self.repository.deactivate(menu)
        return menu, None

    def change_order(self, menu_id: int, display_order: int) -> tuple[MenuMaster | None, str | None]:
        menu = self.repository.reorder(menu_id, display_order)
        if menu is None:
            return None, "Menu not found."
        return menu, None

    def _is_under_ancestor(self, ancestor_id: int, node_id: int) -> bool:
        """True when node_id is ancestor_id or sits under it in the parent chain."""
        current = self.repository.get_by_id(node_id)
        seen: set[int] = set()
        while current is not None:
            if current.MenuID == ancestor_id:
                return True
            if current.MenuID in seen:
                break
            seen.add(current.MenuID)
            if not current.ParentMenuID:
                break
            current = self.repository.get_by_id(current.ParentMenuID)
        return False

    def reorder_batch(self, items: list[dict]) -> tuple[bool, str | None]:
        if not items:
            return False, "No menu order provided."

        omit_parent = object()
        orders: list[tuple[int, int, int | None | object]] = []
        for item in items:
            try:
                menu_id = int(item["menu_id"])
                display_order = int(item["display_order"])
            except (KeyError, TypeError, ValueError):
                return False, "Invalid reorder payload."
            if display_order < 0:
                return False, "Display order cannot be negative."

            parent_value: int | None | object = omit_parent
            if "parent_menu_id" in item:
                raw_parent = item.get("parent_menu_id")
                if raw_parent in ("", None):
                    parent_value = None
                else:
                    try:
                        parent_value = int(raw_parent)
                    except (TypeError, ValueError):
                        return False, "Invalid parent menu."
                    if parent_value == menu_id:
                        return False, "A menu cannot be its own parent."
                    if self._is_under_ancestor(menu_id, parent_value):
                        return False, "Cannot move a menu under itself or its child."
                    if self.repository.get_by_id(parent_value) is None:
                        return False, "Parent menu not found."

            orders.append((menu_id, display_order, parent_value))

        if not self.repository.reorder_many(orders):
            return False, "One or more menus not found."
        self._hide_empty_shcil_parent()
        return True, None

    def _hide_empty_shcil_parent(self) -> None:
        """Keep top-level SHCIL hidden unless it still has active children.

        Stamp / eCourt belong under Activities. An empty SHCIL root must not
        appear as a main-menu item after Menu Admin parent/reorder saves.
        """
        shcil = self.repository.find_top_level_by_name("SHCIL")
        if shcil is None:
            return
        active_children = [
            child for child in self.repository.get_children(shcil.MenuID) if child.IsActive
        ]
        if active_children:
            if not shcil.IsActive:
                self.repository.activate(shcil)
            return
        if shcil.IsActive:
            self.repository.deactivate(shcil)

    def parent_options(self, exclude_id: int | None = None) -> list[MenuMaster]:
        return self.repository.get_parent_options(exclude_id=exclude_id)

    def flat_menu_options(self, exclude_id: int | None = None) -> list[tuple[int, str]]:
        menus = self.repository.get_all(include_inactive=True)
        if exclude_id is not None:
            menus = [menu for menu in menus if menu.MenuID != exclude_id]
        tree = self.build_tree(menus, None)
        options: list[tuple[int, str]] = []

        def walk(nodes: list[MenuNode], depth: int = 0) -> None:
            for node in nodes:
                prefix = ("— " * depth) if depth else ""
                options.append((node.id, f"{prefix}{node.name}"))
                walk(node.children, depth + 1)

        walk(tree)
        return options

    def _normalize_payload(self, data: dict) -> dict:
        parent_id = data.get("ParentMenuID")
        if parent_id in ("", None, "None"):
            parent_id = None
        else:
            parent_id = int(parent_id)

        menu_url = (data.get("MenuURL") or "").strip() or None
        all_roles = str(data.get("RoleNameAll") or "").strip().lower() in {"1", "true", "on", "yes"}
        if hasattr(data, "getlist"):
            selected_roles = data.getlist("RoleName")
        else:
            raw = data.get("RoleName")
            if isinstance(raw, (list, tuple, set)):
                selected_roles = list(raw)
            elif raw:
                selected_roles = [raw]
            else:
                selected_roles = []
        role_name = None if all_roles else join_roles(selected_roles)

        return {
            "ParentMenuID": parent_id,
            "MenuName": (data.get("MenuName") or "").strip(),
            "MenuIcon": (data.get("MenuIcon") or "").strip() or "bi-circle",
            "MenuURL": menu_url,
            "DisplayOrder": int(data.get("DisplayOrder") or 0),
            "IsActive": str(data.get("IsActive", "1")) in {"1", "true", "True", "on"},
            "Description": (data.get("Description") or "").strip() or None,
            "RoleName": role_name,
        }

    def _validate(self, data: dict, current_id: int | None = None) -> str | None:
        name = (data.get("MenuName") or "").strip()
        if not name:
            return "Menu name is required."

        parent_id = data.get("ParentMenuID")
        if parent_id not in (None, "", "None"):
            parent = self.repository.get_by_id(int(parent_id))
            if parent is None:
                return "Selected parent menu does not exist."
            if current_id and int(parent_id) == current_id:
                return "A menu cannot be its own parent."

        return None
