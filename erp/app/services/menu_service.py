from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models.menu_master import MenuMaster
from app.repositories.menu_repository import MenuRepository
from app.repositories.user_repository import UserRepository
from app.utils.fps_access import (
    FPS_DISABLED_MASTER_PATHS,
    FPS_ENABLED_MASTER_PATHS,
    FPS_HOME_PATH,
    fps_nav_menu_disabled,
)
from app.utils.roles import (
    format_roles_display,
    has_admin_role,
    has_data_backup_role,
    has_fps_user_role,
    join_roles,
    roles_intersect,
)


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
    font_color: str | None = None
    font_name: str | None = None
    background_color: str | None = None
    disabled: bool = False

    @property
    def inline_style(self) -> str:
        parts: list[str] = []
        if self.font_color:
            parts.append(f"color: {self.font_color}")
        if self.font_name:
            parts.append(f"font-family: {self.font_name}")
        if self.background_color:
            parts.append(f"background-color: {self.background_color}")
        return "; ".join(parts)


@dataclass
class MenuAdminNode:
    menu: MenuMaster
    children: list[MenuAdminNode] = field(default_factory=list)


class MenuService:
    ADMIN_ROLES = {"Administrator", "Admin"}
    INVALID_MENU_URLS = frozenset({"none", "/none", "/others/income/none", "/others/expense/none"})
    HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
    ALLOWED_FONT_NAMES = frozenset(
        {
            "Source Sans 3, Segoe UI, Arial, sans-serif",
            "Segoe UI, Tahoma, sans-serif",
            "Arial, Helvetica, sans-serif",
            "Tahoma, Geneva, sans-serif",
            "Verdana, Geneva, sans-serif",
            "Georgia, Times New Roman, serif",
            "Times New Roman, Times, serif",
            "Courier New, Courier, monospace",
            "Trebuchet MS, Helvetica, sans-serif",
            "Comic Sans MS, Comic Sans, cursive",
        }
    )

    def __init__(self, repository: MenuRepository | None = None):
        self.repository = repository or MenuRepository()
        self._allowed_users_cache: dict[int, set[int]] | None = None

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

    @classmethod
    def _is_admin_role_root(cls, menu) -> bool:
        name = (getattr(menu, "MenuName", None) or "").strip().lower()
        return name == cls.ADMIN_ROLE_MENU_NAME and not getattr(menu, "ParentMenuID", None)

    @classmethod
    def _is_data_backup_menu(cls, menu) -> bool:
        name = (getattr(menu, "MenuName", None) or "").strip().lower()
        url = (cls.normalize_menu_url(getattr(menu, "MenuURL", None)) or "").rstrip("/").lower()
        return name == cls.DATA_BACKUP_MENU_NAME or url in cls.DATA_BACKUP_URLS

    @classmethod
    def _is_help_menu(cls, menu) -> bool:
        name = (getattr(menu, "MenuName", None) or "").strip().lower()
        url = (cls.normalize_menu_url(getattr(menu, "MenuURL", None)) or "").rstrip("/").lower()
        return name == cls.HELP_MENU_NAME or url in cls.HELP_URLS or url.startswith("/help/")

    def _menu_allowed_users(self) -> dict[int, set[int]]:
        if self._allowed_users_cache is None:
            self._allowed_users_cache = self.repository.list_allowed_users_map()
        return self._allowed_users_cache

    def _allowed_user_ids_for(self, menu_id: int) -> set[int]:
        return self._menu_allowed_users().get(menu_id, set())

    def _invalidate_allow_cache(self) -> None:
        self._allowed_users_cache = None

    def _is_all_users_menu(self, menu) -> bool:
        if self._is_help_menu(menu):
            return True
        return bool(getattr(menu, "AllowAllUsers", False))

    def _user_is_explicitly_allowed(self, menu, user_id: int | None) -> bool:
        if user_id is None:
            return False
        return int(user_id) in self._allowed_user_ids_for(menu.MenuID)

    def _is_staff_shared_menu(self, menu, user_id: int | None) -> bool:
        """Menus a non-admin staff user may see even under Admin Role."""
        return self._is_all_users_menu(menu) or self._user_is_explicitly_allowed(menu, user_id)

    def _users_label(self, menu: MenuMaster) -> str:
        if bool(getattr(menu, "AllowAllUsers", False)) or self._is_help_menu(menu):
            return "All users"
        allowed = self._allowed_user_ids_for(menu.MenuID)
        if allowed:
            count = len(allowed)
            return f"{count} user" + ("" if count == 1 else "s")
        return format_roles_display(menu.RoleName)

    def can_access_menu(
        self,
        menu: MenuMaster,
        role: str | None,
        user_id: int | None = None,
    ) -> bool:
        if not menu.IsActive:
            return False
        if has_admin_role(role):
            return True
        if has_fps_user_role(role):
            return self._is_fps_user_menu(menu)
        if self._is_all_users_menu(menu):
            return True
        allowed_ids = self._allowed_user_ids_for(menu.MenuID)
        if allowed_ids:
            return bool(user_id and int(user_id) in allowed_ids)
        if has_data_backup_role(role) and (
            self._is_admin_role_root(menu) or self._is_data_backup_menu(menu)
        ):
            return True
        return roles_intersect(role, menu.RoleName)

    def _is_fps_user_menu(self, menu) -> bool:
        url = (self.normalize_menu_url(getattr(menu, "MenuURL", None)) or "").rstrip("/").lower()
        name = (getattr(menu, "MenuName", None) or "").strip().lower()
        if url == FPS_HOME_PATH:
            return True
        if url in FPS_ENABLED_MASTER_PATHS or url in FPS_DISABLED_MASTER_PATHS:
            return True
        if url:
            return False
        return name in {"public report", "ration card report"}

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
                    font_color=getattr(menu, "FontColor", None) or None,
                    font_name=getattr(menu, "FontName", None) or None,
                    background_color=getattr(menu, "BackgroundColor", None) or None,
                )
            )
        return nodes

    # Default ERP top bar (seed). Customization may add more active top-level menus.
    CORE_TOP_LEVEL_MENUS = frozenset(
        {
            "admin role",
            "dashboard",
            "activities",
            "reports and analysis",
            "masters",
            "accounting",
            "crm",
            "public report",
            "hr",
        }
    )

    # Permanently blocked legacy top modules (never re-show via customization).
    LEGACY_HIDDEN_TOP_LEVEL = frozenset(
        {
            "itr",
            "others",
            "gst",
            "dsc",
            "tds",
            "payroll",
            "transactions",
            "employee",
            "stock",
            "exceptional report",
            "settings",
            "menu management",
            "menu admin",
        }
    )

    # Protected from delete/remove in Menu Customization.
    PROTECTED_MAIN_MENUS = frozenset({"admin role", "dashboard"})
    ADMIN_ROLE_MENU_NAME = "admin role"
    DATA_BACKUP_MENU_NAME = "data backup"
    DATA_BACKUP_URLS = frozenset({"/admin/backup/data"})
    HELP_MENU_NAME = "help"
    HELP_URLS = frozenset({"/help"})

    # Old Menu Management page — keep out of ribbon (new page is Menu Customization).
    HIDDEN_MENU_NAMES = frozenset(
        {
            "settings",
            "menu management",
            "menu admin",
        }
    )
    HIDDEN_MENU_URLS = frozenset(
        {
            "/admin/menus",
            "/admin/menus/",
            "/settings",
            "/settings/",
        }
    )

    def get_navigation(self, role: str | None, user_id: int | None = None) -> list[MenuNode]:
        try:
            from app.routes.admin_import_export import ensure_import_export_menus

            ensure_import_export_menus()
        except Exception:
            from app.extensions import db

            db.session.rollback()
        try:
            from app.routes.help import ensure_help_menus

            ensure_help_menus()
        except Exception:
            from app.extensions import db

            db.session.rollback()
        menus = [m for m in self.repository.get_all() if self.can_access_menu(m, role, user_id)]
        # Hidden from app nav (CRM / Exceptional / Settings / non-core modules).
        menus = [m for m in menus if not self._is_hidden_nav_menu(m)]
        # Drop children of ITR/GST/Payroll/… so _include_parent_chain cannot
        # bring those top modules back into the ribbon.
        menus = [m for m in menus if self._is_under_core_nav(m)]
        if has_admin_role(role):
            allowed_ids = {menu.MenuID for menu in menus}
            menus = self._include_parent_chain(menus, allowed_ids)
            menus = [m for m in menus if not self._is_hidden_nav_menu(m) and self._is_under_core_nav(m)]
        else:
            menus = self._menus_with_accessible_ancestors(menus, role, user_id)
            menus = [m for m in menus if not self._is_hidden_nav_menu(m) and self._is_under_core_nav(m)]
            if has_fps_user_role(role):
                menus = [m for m in menus if self._is_fps_user_menu(m)]
            elif has_data_backup_role(role):
                menus = self._restrict_admin_role_to_data_backup(menus, user_id)
        tree = self.build_tree(menus, None)
        if has_fps_user_role(role):
            self._mark_fps_disabled_menus(tree)
        return tree

    def _mark_fps_disabled_menus(self, nodes: list[MenuNode]) -> None:
        for node in nodes:
            if fps_nav_menu_disabled(node.url, node.name):
                node.disabled = True
            if node.children:
                self._mark_fps_disabled_menus(node.children)

    def _is_under_admin_role(self, menu: MenuMaster) -> bool:
        current: MenuMaster | None = menu
        seen: set[int] = set()
        while current is not None:
            if current.MenuID in seen:
                return False
            seen.add(current.MenuID)
            if self._is_admin_role_root(current):
                return True
            if not current.ParentMenuID:
                return False
            current = self.repository.get_by_id(current.ParentMenuID)
        return False

    def _restrict_admin_role_to_data_backup(
        self,
        menus: list[MenuMaster],
        user_id: int | None = None,
    ) -> list[MenuMaster]:
        """Manager / Operator / Viewer: Admin Role shows shared staff menus only."""
        kept: list[MenuMaster] = []
        for menu in menus:
            if not self._is_under_admin_role(menu):
                kept.append(menu)
                continue
            if (
                self._is_admin_role_root(menu)
                or self._is_data_backup_menu(menu)
                or self._is_staff_shared_menu(menu, user_id)
            ):
                kept.append(menu)
        if not any(
            self._is_data_backup_menu(menu) or self._is_staff_shared_menu(menu, user_id)
            for menu in kept
        ):
            kept = [menu for menu in kept if not self._is_admin_role_root(menu)]
        return kept

    def _top_level_ancestor(self, menu: MenuMaster) -> MenuMaster | None:
        current: MenuMaster | None = menu
        seen: set[int] = set()
        while current is not None:
            if current.MenuID in seen:
                return None
            seen.add(current.MenuID)
            if not current.ParentMenuID:
                return current
            current = self.repository.get_by_id(current.ParentMenuID)
        return None

    def _is_under_core_nav(self, menu: MenuMaster) -> bool:
        """True when menu sits under an allowed (non-legacy) top-level item."""
        root = self._top_level_ancestor(menu)
        if root is None:
            return False
        name = (root.MenuName or "").strip().lower()
        if name in self.LEGACY_HIDDEN_TOP_LEVEL or name in self.HIDDEN_MENU_NAMES:
            return False
        return True

    @classmethod
    def _is_hidden_nav_menu(cls, menu) -> bool:
        name = (getattr(menu, "MenuName", None) or "").strip().lower()
        url = (getattr(menu, "MenuURL", None) or "").strip().lower()
        parent_id = getattr(menu, "ParentMenuID", None)

        # Parent "Exceptional Report" stays hidden; Stamp / e-Court Exception
        # are shown under Reports and Analysis (existing module URLs kept).
        # CRM is an active top-level module (Communication Center).
        if name in {"exceptional report", "logout", "log out"}:
            return True
        if name in cls.HIDDEN_MENU_NAMES:
            return True
        if url.rstrip("/") in {u.rstrip("/") for u in cls.HIDDEN_MENU_URLS} or url.startswith(
            "/admin/menus"
        ):
            return True
        allowed_exception_urls = {
            "/exceptional-report/stamp-certificate",
            "/exceptional-report/ecourt-exception",
        }
        if url in allowed_exception_urls:
            return False
        if url.startswith("/exceptional-report/") or url == "/exceptional-report":
            return True
        if url in {"/logout", "/auth/logout"}:
            return True
        # Top-level: hide only blocked legacy modules (customization can add others).
        if parent_id is None and name and name in cls.LEGACY_HIDDEN_TOP_LEVEL:
            return True
        return False

    def _ancestors_accessible(
        self,
        menu: MenuMaster,
        role: str | None,
        user_id: int | None = None,
    ) -> bool:
        """True only if this menu and every parent allow the user's role."""
        if self._is_staff_shared_menu(menu, user_id):
            # Help / All users / selected users sit under Admin Role (admin-only
            # parent) but are granted to the chosen staff. FPS_USER stays excluded.
            if has_fps_user_role(role):
                return False
            return True
        current: MenuMaster | None = menu
        seen: set[int] = set()
        while current is not None:
            if current.MenuID in seen:
                return False
            seen.add(current.MenuID)
            if not self.can_access_menu(current, role, user_id):
                return False
            if not current.ParentMenuID:
                return True
            current = self.repository.get_by_id(current.ParentMenuID)
        return False

    def _menus_with_accessible_ancestors(
        self,
        menus: list[MenuMaster],
        role: str | None,
        user_id: int | None = None,
    ) -> list[MenuMaster]:
        """Keep role-allowed menus only when their full parent chain is also allowed.

        Prevents Admin Role from appearing for Operators when a child row has
        RoleName NULL (legacy "all roles") under an admin-only parent.
        All-users / selected-user menus are the exception (same as Help).
        """
        by_id: dict[int, MenuMaster] = {}
        kept_ids: set[int] = set()

        for menu in menus:
            if not self._ancestors_accessible(menu, role, user_id):
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
                parent = self.repository.get_by_id(current.ParentMenuID)
                if parent is None or self._is_hidden_nav_menu(parent):
                    break
                root_name = ""
                root = parent
                walk = parent
                seen: set[int] = set()
                while walk is not None and walk.MenuID not in seen:
                    seen.add(walk.MenuID)
                    if not walk.ParentMenuID:
                        root = walk
                        break
                    nxt = self.repository.get_by_id(walk.ParentMenuID)
                    if nxt is None:
                        break
                    walk = nxt
                root_name = (root.MenuName or "").strip().lower()
                if root_name and (
                    root_name in self.LEGACY_HIDDEN_TOP_LEVEL
                    or root_name in self.HIDDEN_MENU_NAMES
                ):
                    break
                expanded_ids.add(parent.MenuID)
                by_id[parent.MenuID] = parent
                current = parent

        return [by_id[menu_id] for menu_id in expanded_ids if menu_id in by_id]

    def get_breadcrumb(
        self,
        menu_url: str,
        role: str | None,
        user_id: int | None = None,
    ) -> list[MenuMaster]:
        menu = self.repository.find_by_url(menu_url)
        if menu is None or not self.can_access_menu(menu, role, user_id):
            return []

        return self._breadcrumb_from_menu(menu, role, user_id)

    def get_breadcrumb_for_work_type(
        self,
        work_type: str | None,
        role: str | None,
        *,
        fallback_url: str = "/transactions/new",
        user_id: int | None = None,
    ) -> list[MenuMaster]:
        if work_type:
            module = self.repository.find_top_level_by_name(work_type.strip())
            if module is not None and self.can_access_menu(module, role, user_id):
                return self._breadcrumb_from_menu(module, role, user_id)

        return self.get_breadcrumb(fallback_url, role, user_id) or self.get_breadcrumb(
            "/transactions/new",
            role,
            user_id,
        )

    def _breadcrumb_from_menu(
        self,
        menu: MenuMaster,
        role: str | None,
        user_id: int | None = None,
    ) -> list[MenuMaster]:
        trail: list[MenuMaster] = [menu]
        current = menu
        while current.ParentMenuID:
            parent = self.repository.get_by_id(current.ParentMenuID)
            if parent is None:
                break
            if not self.can_access_menu(parent, role, user_id):
                if self._is_staff_shared_menu(menu, user_id) and self._is_admin_role_root(parent):
                    trail.insert(0, parent)
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

        raw_parent = data.get("ParentMenuID")
        if raw_parent not in (None, "", "None") and str(raw_parent).strip() == str(menu_id):
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

    def _descendant_ids(self, root_id: int, menus: list[MenuMaster] | None = None) -> set[int]:
        """All MenuIDs under root_id (not including root_id)."""
        rows = menus if menus is not None else self.repository.get_all(include_inactive=True)
        by_parent: dict[int | None, list[int]] = {}
        for menu in rows:
            by_parent.setdefault(menu.ParentMenuID, []).append(menu.MenuID)
        found: set[int] = set()
        stack = list(by_parent.get(root_id, []))
        while stack:
            menu_id = stack.pop()
            if menu_id in found:
                continue
            found.add(menu_id)
            stack.extend(by_parent.get(menu_id, []))
        return found

    def flat_menu_options(self, exclude_id: int | None = None) -> list[tuple[int, str]]:
        menus = self.repository.get_all(include_inactive=True)
        if exclude_id is not None:
            blocked = {exclude_id} | self._descendant_ids(exclude_id, menus)
            menus = [menu for menu in menus if menu.MenuID not in blocked]
        tree = self.build_tree(menus, None)
        options: list[tuple[int, str]] = []

        def walk(nodes: list[MenuNode], depth: int = 0) -> None:
            for node in nodes:
                prefix = ("— " * depth) if depth else ""
                options.append((node.id, f"{prefix}{node.name}"))
                walk(node.children, depth + 1)

        walk(tree)
        return options

    def _normalize_color(self, value: object) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        if not text.startswith("#") and re.fullmatch(r"[0-9a-fA-F]{3}|[0-9a-fA-F]{6}", text):
            text = f"#{text}"
        if not self.HEX_COLOR_RE.fullmatch(text):
            return None
        return text.upper() if len(text) == 7 else text.lower()

    def _normalize_font_name(self, value: object) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        if text in self.ALLOWED_FONT_NAMES:
            return text
        return None

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
            "FontColor": self._normalize_color(data.get("FontColor")),
            "FontName": self._normalize_font_name(data.get("FontName")),
            "BackgroundColor": self._normalize_color(data.get("BackgroundColor")),
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
            if current_id and self._is_under_ancestor(current_id, int(parent_id)):
                return "Cannot set a child (or nested) menu as parent — that would break the sub-menu tree."

        font_raw = str(data.get("FontName") or "").strip()
        if font_raw and font_raw not in self.ALLOWED_FONT_NAMES:
            return "Selected font name is not allowed."

        for field_name, label in (("FontColor", "Font colour"), ("BackgroundColor", "Background colour")):
            raw = str(data.get(field_name) or "").strip()
            if raw and self._normalize_color(raw) is None:
                return f"{label} must be a valid hex colour (e.g. #243B7B)."

        return None

    # -------------------------------------------------------------------------
    # Menu Customization (Admin Role) — main menus + submenus
    # -------------------------------------------------------------------------
    def _customization_child_count(self, parent_id: int) -> int:
        children = [
            c
            for c in self.repository.get_children(parent_id)
            if c.IsActive and not self._is_hidden_nav_menu(c)
        ]
        return len(children)

    def list_menus_for_customization(self, parent_id: int | None = None) -> dict:
        """List siblings under parent_id (None = main / top-level ribbon)."""
        parent = None
        breadcrumb: list[dict] = []
        if parent_id is not None:
            parent = self.repository.get_by_id(parent_id)
            if parent is None:
                return {"ok": False, "error": "Parent menu not found.", "items": [], "breadcrumb": []}
            # Build breadcrumb root → parent
            chain: list[MenuMaster] = []
            current: MenuMaster | None = parent
            seen: set[int] = set()
            while current is not None and current.MenuID not in seen:
                seen.add(current.MenuID)
                chain.insert(0, current)
                if not current.ParentMenuID:
                    break
                current = self.repository.get_by_id(current.ParentMenuID)
            breadcrumb = [
                {
                    "menu_id": m.MenuID,
                    "name": m.MenuName,
                }
                for m in chain
            ]

        menus = self.repository.get_all(include_inactive=False)
        siblings = [m for m in menus if m.ParentMenuID == parent_id]
        if parent_id is None:
            siblings = [
                m
                for m in siblings
                if (m.MenuName or "").strip().lower() not in self.LEGACY_HIDDEN_TOP_LEVEL
                and (m.MenuName or "").strip().lower() not in self.HIDDEN_MENU_NAMES
            ]
        else:
            siblings = [m for m in siblings if not self._is_hidden_nav_menu(m)]

        siblings.sort(key=lambda item: (item.DisplayOrder, item.MenuID))
        items = []
        for m in siblings:
            name_key = (m.MenuName or "").strip().lower()
            protected = parent_id is None and name_key in self.PROTECTED_MAIN_MENUS
            child_count = self._customization_child_count(m.MenuID)
            allow_all = bool(getattr(m, "AllowAllUsers", False))
            allowed_ids = sorted(self._allowed_user_ids_for(m.MenuID))
            items.append(
                {
                    "menu_id": m.MenuID,
                    "name": m.MenuName,
                    "icon": m.MenuIcon or "bi-circle",
                    "url": m.MenuURL or "",
                    "display_order": m.DisplayOrder,
                    "protected": protected,
                    "has_children": child_count > 0,
                    "child_count": child_count,
                    "parent_menu_id": m.ParentMenuID,
                    "allow_all_users": allow_all,
                    "allowed_user_ids": allowed_ids,
                    "users_label": self._users_label(m),
                }
            )

        parent_url = ""
        if parent is not None:
            parent_url = (self.normalize_menu_url(parent.MenuURL) or "").strip()
            if not parent_url:
                # Fallback: /masters from "Masters"
                slug = re.sub(r"[^a-z0-9]+", "_", (parent.MenuName or "").strip().lower())
                slug = slug.strip("_")
                parent_url = f"/{slug}" if slug else ""

        users = [
            {
                "user_id": user.UserID,
                "name": user.FullName,
                "role": user.Role,
            }
            for user in UserRepository().list_for_menu_allow()
        ]
        return {
            "ok": True,
            "parent_id": parent_id,
            "parent_name": parent.MenuName if parent else None,
            "parent_url": parent_url.rstrip("/") if parent_url else "",
            "breadcrumb": breadcrumb,
            "items": items,
            "users": users,
        }

    def list_main_menus_for_customization(self) -> list[dict]:
        return self.list_menus_for_customization(None).get("items") or []

    def move_customization_menu(
        self,
        menu_id: int,
        direction: str,
        parent_id: int | None = None,
    ) -> tuple[bool, str | None]:
        direction = (direction or "").strip().lower()
        if direction not in {"up", "down"}:
            return False, "Direction must be up or down."

        payload = self.list_menus_for_customization(parent_id)
        items = payload.get("items") or []
        index = next((i for i, row in enumerate(items) if row["menu_id"] == menu_id), -1)
        if index < 0:
            return False, "Menu not found at this level."
        swap_with = index - 1 if direction == "up" else index + 1
        if swap_with < 0 or swap_with >= len(items):
            return False, "Already at the edge."

        a = self.repository.get_by_id(items[index]["menu_id"])
        b = self.repository.get_by_id(items[swap_with]["menu_id"])
        if a is None or b is None:
            return False, "Menu not found."
        if a.ParentMenuID != b.ParentMenuID:
            return False, "Menus are not siblings."

        a_order, b_order = a.DisplayOrder, b.DisplayOrder
        if a_order == b_order:
            for i, row in enumerate(items):
                menu = self.repository.get_by_id(row["menu_id"])
                if menu is not None:
                    menu.DisplayOrder = (i + 1) * 10
            self.repository.session.commit()
            a = self.repository.get_by_id(menu_id)
            b = self.repository.get_by_id(items[swap_with]["menu_id"])
            if a is None or b is None:
                return False, "Menu not found."
            a_order, b_order = a.DisplayOrder, b.DisplayOrder

        a.DisplayOrder, b.DisplayOrder = b_order, a_order
        self.repository.session.commit()
        return True, None

    def move_main_menu(self, menu_id: int, direction: str) -> tuple[bool, str | None]:
        return self.move_customization_menu(menu_id, direction, parent_id=None)

    def _apply_user_allow(
        self,
        menu: MenuMaster,
        *,
        allow_all_users: bool,
        allowed_user_ids: list[int] | None,
    ) -> None:
        menu.AllowAllUsers = bool(allow_all_users)
        if menu.AllowAllUsers:
            menu.RoleName = None
            self.repository.replace_allowed_users(menu.MenuID, [])
        elif allowed_user_ids is not None:
            self.repository.replace_allowed_users(menu.MenuID, allowed_user_ids)
        self._invalidate_allow_cache()

    def add_customization_menu(
        self,
        name: str,
        *,
        parent_id: int | None = None,
        url: str | None = None,
        icon: str | None = None,
        allow_all_users: bool = False,
        allowed_user_ids: list[int] | None = None,
    ) -> tuple[MenuMaster | None, str | None]:
        clean_name = (name or "").strip()
        if not clean_name:
            return None, "Menu name is required."
        key = clean_name.lower()
        if parent_id is None:
            if key in self.LEGACY_HIDDEN_TOP_LEVEL or key in self.HIDDEN_MENU_NAMES:
                return None, "This menu name is reserved / blocked."
            if self.repository.find_top_level_by_name(clean_name) is not None:
                return None, "A main menu with this name already exists."
        else:
            parent = self.repository.get_by_id(parent_id)
            if parent is None:
                return None, "Parent menu not found."
            for child in self.repository.get_children(parent_id):
                if child.IsActive and (child.MenuName or "").strip().lower() == key:
                    return None, "A submenu with this name already exists here."

        payload = self.list_menus_for_customization(parent_id)
        items = payload.get("items") or []
        next_order = (max((row["display_order"] for row in items), default=0) or 0) + 10
        menu = self.repository.create(
            {
                "ParentMenuID": parent_id,
                "MenuName": clean_name,
                "MenuIcon": (icon or "").strip() or ("bi-folder" if parent_id is None else "bi-circle"),
                "MenuURL": self.normalize_menu_url(url),
                "DisplayOrder": next_order,
                "IsActive": True,
                "Description": "Added via Menu Customization",
                "RoleName": None,
                "AllowAllUsers": bool(allow_all_users),
                "FontColor": None,
                "FontName": None,
                "BackgroundColor": None,
            }
        )
        self._apply_user_allow(
            menu,
            allow_all_users=allow_all_users,
            allowed_user_ids=allowed_user_ids or [],
        )
        self.repository.session.commit()
        return menu, None

    def add_main_menu(
        self,
        name: str,
        url: str | None = None,
        icon: str | None = None,
    ) -> tuple[MenuMaster | None, str | None]:
        return self.add_customization_menu(name, parent_id=None, url=url, icon=icon)

    def remove_customization_menu(self, menu_id: int) -> tuple[bool, str | None]:
        menu = self.repository.get_by_id(menu_id)
        if menu is None:
            return False, "Menu not found."
        name = (menu.MenuName or "").strip().lower()
        if menu.ParentMenuID is None:
            if name in self.PROTECTED_MAIN_MENUS:
                return False, "Admin Role and Dashboard cannot be removed."
            if name in self.LEGACY_HIDDEN_TOP_LEVEL:
                return False, "This menu is already blocked."
        # Soft-remove from nav (keeps children in DB).
        self.repository.deactivate(menu)
        return True, None

    def remove_main_menu(self, menu_id: int) -> tuple[bool, str | None]:
        return self.remove_customization_menu(menu_id)

    def update_customization_menu(
        self,
        menu_id: int,
        *,
        name: str,
        url: str | None = None,
        icon: str | None = None,
        allow_all_users: bool | None = None,
        allowed_user_ids: list[int] | None = None,
    ) -> tuple[MenuMaster | None, str | None]:
        menu = self.repository.get_by_id(menu_id)
        if menu is None or not menu.IsActive:
            return None, "Menu not found."

        clean_name = (name or "").strip()
        if not clean_name:
            return None, "Menu name is required."
        key = clean_name.lower()
        parent_id = menu.ParentMenuID

        if parent_id is None:
            if key in self.LEGACY_HIDDEN_TOP_LEVEL or key in self.HIDDEN_MENU_NAMES:
                return None, "This menu name is reserved / blocked."
            existing = self.repository.find_top_level_by_name(clean_name)
            if existing is not None and existing.MenuID != menu_id:
                return None, "A main menu with this name already exists."
        else:
            for child in self.repository.get_children(parent_id):
                if (
                    child.IsActive
                    and child.MenuID != menu_id
                    and (child.MenuName or "").strip().lower() == key
                ):
                    return None, "A submenu with this name already exists here."

        # Keep parent + order; only edit label / link / icon / user allow.
        menu.MenuName = clean_name
        menu.MenuURL = self.normalize_menu_url(url)
        menu.MenuIcon = (icon or "").strip() or menu.MenuIcon or "bi-circle"
        if allow_all_users is not None:
            self._apply_user_allow(
                menu,
                allow_all_users=allow_all_users,
                allowed_user_ids=allowed_user_ids,
            )
        self.repository.session.commit()
        return menu, None
