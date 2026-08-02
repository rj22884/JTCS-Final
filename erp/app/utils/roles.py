"""Helpers for multi-role values stored as comma-separated strings."""

from __future__ import annotations

ADMIN_ROLES = frozenset({"Administrator", "Admin"})
ASSIGNABLE_ROLES = (
    "Operator",
    "Viewer",
    "Manager",
    "Admin",
    "CA",
    "Accountant",
    "DataEntry",
    "Reception",
    "Client",
)
MENU_ROLES = (
    "Administrator",
    "Manager",
    "Operator",
    "Viewer",
    "CA",
    "Accountant",
    "DataEntry",
    "Reception",
    "Client",
)


def parse_roles(value: str | None) -> set[str]:
    if not value:
        return set()
    return {part.strip() for part in str(value).split(",") if part.strip()}


def join_roles(roles) -> str | None:
    cleaned = sorted({str(r).strip() for r in (roles or []) if str(r).strip()})
    return ",".join(cleaned) if cleaned else None


def has_admin_role(value: str | None) -> bool:
    return bool(parse_roles(value) & ADMIN_ROLES)


def roles_intersect(user_roles_value: str | None, allowed_roles_value: str | None) -> bool:
    """True if menu allows all (empty) or any user role is in the menu allow-list."""
    allowed = parse_roles(allowed_roles_value)
    if not allowed:
        return True
    return bool(parse_roles(user_roles_value) & allowed)


def format_roles_display(value: str | None, *, empty_label: str = "All roles") -> str:
    roles = parse_roles(value)
    if not roles:
        return empty_label
    return ", ".join(sorted(roles))
