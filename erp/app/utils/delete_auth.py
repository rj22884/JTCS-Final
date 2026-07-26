"""Re-auth (User ID + password) required before permanent / soft deletes."""

from __future__ import annotations

from flask import session

from app.repositories.user_repository import UserRepository
from app.utils.security import verify_password


def verify_delete_credentials(user_id_input: str, password: str) -> None:
    """Ensure credentials match the currently logged-in user.

    User ID may be EmailID or numeric UserID.
    Raises ValueError with a user-facing message on failure.
    """
    session_uid = session.get("user_id")
    if not session_uid:
        raise ValueError("Please login again to delete.")

    user = UserRepository().get_by_id(int(session_uid))
    if user is None:
        raise ValueError("Logged-in user not found. Please login again.")

    entered = (user_id_input or "").strip()
    if not entered:
        raise ValueError("User ID is required.")
    if not password:
        raise ValueError("Password is required.")

    email = (user.EmailID or "").strip().lower()
    numeric_id = str(user.UserID)
    if entered.lower() != email and entered != numeric_id:
        raise ValueError("User ID does not match the logged-in user.")

    if not verify_password(user.PasswordHash, password):
        raise ValueError("Invalid password.")


def current_login_id() -> str:
    """Default User ID (email) for the logged-in session — for UI prefills."""
    session_uid = session.get("user_id")
    if not session_uid:
        return ""
    user = UserRepository().get_by_id(int(session_uid))
    if user is None:
        return ""
    return (user.EmailID or "").strip()
