"""Server User auth checks (validation, hashing, token). Run from erp folder:

  .venv\\Scripts\\python.exe scripts\\test_server_auth.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def test_validation_and_security() -> None:
    from app import create_app
    from app.services.auth_service import AuthService
    from app.services.server_auth_service import LOGIN_ID_RE, ServerAuthService
    from app.utils.security import hash_password, verify_password
    from app.utils.tokens import create_signed_token, load_signed_token

    app = create_app()
    with app.app_context():
        svc = ServerAuthService()
        assert svc.validate_login_id("") == "Please enter a Server User ID."
        assert svc.validate_login_id("ab") is None
        assert "letters and numbers only" in (svc.validate_login_id("good_user.1") or "")
        assert "Special characters" in (svc.validate_login_id("rajneesh-joshi") or "")
        assert svc.validate_login_id("goodUser1") is None
        assert LOGIN_ID_RE.match("ServerUser01")
        assert not LOGIN_ID_RE.match("bad id")
        assert not LOGIN_ID_RE.match("user@name")
        assert "application login ID" in (
            svc.validate_login_id("itaxhaldwani", app_email="itaxhaldwani@gmail.com") or ""
        )
        assert svc.validate_login_id("otherid", app_email="itaxhaldwani@gmail.com") is None

        auth = AuthService()
        assert auth.validate_password("short", "short")
        assert auth.validate_password("GoodPass1", "GoodPass1") is None
        assert auth.validate_password("GoodPass1", "OtherPass1")
        assert svc.validate_server_password("", "x", user_id=-1) == "Please enter a Server password."
        assert svc.validate_server_password("any", "other", user_id=-1) == "Passwords do not match."

        hashed = hash_password("GoodPass1")
        assert hashed != "GoodPass1"
        assert verify_password(hashed, "GoodPass1")
        assert not verify_password(hashed, "wrong")

        token = create_signed_token(1, "user@example.com", "server_password_reset")
        data = load_signed_token(token, "server_password_reset")
        assert data and data["uid"] == 1
        assert data["email"] == "user@example.com"

        svc.ensure_schema()
        print("schema: dbo.ServerUser + AuditLog Module/Status ready")
        print("validation, bcrypt reuse, and reset-token purpose: OK")


if __name__ == "__main__":
    test_validation_and_security()
    print("test_server_auth.py passed")
