"""CRM role matrix mapped onto existing JTCS ERP roles."""

from __future__ import annotations

from functools import wraps

from flask import jsonify, session

from app.utils.roles import has_admin_role, parse_roles, roles_intersect

# Product roles → ERP role names (lowercase)
ROLE_ALIASES = {
    "super admin": {"administrator", "admin"},
    "administrator": {"administrator", "admin"},
    "admin": {"administrator", "admin"},
    "manager": {"manager", "administrator", "admin"},
    "executive": {"operator", "manager", "administrator", "admin"},
    "support": {"reception", "operator", "manager", "administrator", "admin"},
    "sales": {"operator", "reception", "manager", "administrator", "admin"},
    "accounts": {"accountant", "ca", "manager", "administrator", "admin"},
}

# Capability → minimum product roles allowed
CAPABILITIES = {
    "crm.view": {"support", "sales", "executive", "accounts", "manager", "super admin", "admin"},
    "crm.reply": {"support", "sales", "executive", "manager", "super admin", "admin", "accounts"},
    "crm.assign": {"manager", "super admin", "admin"},
    "crm.close": {"executive", "manager", "super admin", "admin"},
    "crm.templates": {"manager", "super admin", "admin"},
    "crm.email_sync": {"manager", "super admin", "admin"},
    "crm.call_logs": {"support", "sales", "executive", "manager", "super admin", "admin"},
    "crm.leads_convert": {"manager", "super admin", "admin"},
    "crm.admin": {"super admin", "admin"},
    "whatsapp.view": {"support", "sales", "executive", "accounts", "manager", "super admin", "admin"},
    "whatsapp.send": {"support", "sales", "executive", "manager", "super admin", "admin", "accounts"},
    "whatsapp.assign": {"manager", "super admin", "admin"},
    "whatsapp.templates": {"manager", "super admin", "admin"},
    "whatsapp.configure": {"super admin", "admin"},
    "whatsapp.audit": {"manager", "super admin", "admin"},
}


def _user_role_tokens() -> set[str]:
    return {r.lower() for r in parse_roles(session.get("role"))}


def user_has_capability(capability: str) -> bool:
    if has_admin_role(session.get("role")):
        return True
    # Logged-in staff: view/reply/call_logs allowed for common operational roles
    user_roles = _user_role_tokens()
    if not user_roles:
        return False
    open_caps = {
        "crm.view",
        "crm.reply",
        "crm.call_logs",
        "whatsapp.view",
        "whatsapp.send",
    }
    operational = {
        "operator",
        "reception",
        "manager",
        "administrator",
        "admin",
        "ca",
        "accountant",
        "dataentry",
    }
    if capability in open_caps and (user_roles & operational):
        return True
    allowed_product = CAPABILITIES.get(capability) or set()
    needed: set[str] = set()
    for prod in allowed_product:
        needed |= ROLE_ALIASES.get(prod, {prod})
    if user_roles & needed:
        return True
    needed_title = {
        "Administrator" if n == "administrator" else n.title() for n in needed
    }
    needed_title |= {
        "Admin",
        "Administrator",
        "Manager",
        "Operator",
        "Reception",
        "Accountant",
        "CA",
        "DataEntry",
    }
    return roles_intersect(session.get("role"), ",".join(sorted(needed_title)))


def require_crm_capability(capability: str):
    """Decorator for CRM JSON APIs — returns 403 JSON when denied."""

    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                return jsonify({"ok": False, "error": "Authentication required"}), 401
            if not user_has_capability(capability):
                return jsonify({"ok": False, "error": "Permission denied"}), 403
            return fn(*args, **kwargs)

        return wrapped

    return decorator
