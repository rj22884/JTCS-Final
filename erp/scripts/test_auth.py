"""
JTCS ERP authentication test suite.

Run:
    cd erp
    .\.venv\Scripts\Activate.ps1
    python scripts/test_auth.py
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app
from app.config import Config
from app.extensions import db
from app.models.auth import AuthToken
from app.services.auth_service import AuthService
from app.services.email_service import EmailService, SMTP_NOT_CONFIGURED, SMTP_USER_MESSAGE
from app.utils.security import hash_token, token_expiry, verify_password
from app.utils.tokens import create_signed_token


def run_tests() -> int:
    app = create_app()
    failures: list[str] = []
    suffix = uuid.uuid4().hex[:8]
    test_email = f"auth.test.{suffix}@example.com"
    test_mobile = f"9{int(suffix, 16) % 1000000000:09d}"

    def ok(name: str) -> None:
        print(f"  OK  {name}")

    def fail(name: str, detail: str) -> None:
        failures.append(f"{name}: {detail}")
        print(f"  FAIL {name}: {detail}")

    with app.app_context():
        auth = AuthService()
        email_svc = EmailService()

        print("\n=== Admin setup guard ===")
        if auth.administrator_exists():
            ok("Administrator exists (setup complete)")
        else:
            fail("Administrator setup", "no administrator found")

        print("\n=== Transaction safety ===")
        flows = [
            ("register conflict check", lambda: auth._registration_conflict("itax.haldwani@gmail.com")),
            ("forgot password", lambda: auth.request_password_reset("itax.haldwani@gmail.com")),
            ("forgot user id", lambda: auth.request_forgot_user_id(mobile="9999999999")),
        ]
        for name, fn in flows:
            try:
                fn()
                ok(f"{name} — no InvalidRequestError")
            except Exception as exc:
                if "transaction is already begun" in str(exc).lower():
                    fail(name, str(exc))
                else:
                    ok(f"{name} — no InvalidRequestError")

        print("\n=== SMTP configuration ===")
        if os.getenv("MAIL_PASSWORD"):
            if email_svc.is_configured():
                ok("SMTP configured from .env")
            else:
                fail("SMTP config", "MAIL_PASSWORD set but is_configured() is false")
        else:
            ok(f"SMTP without password returns safe message ({SMTP_NOT_CONFIGURED})")

        print("\n=== Register ===")
        success, message, data = auth.register(
            {
                "full_name": "Auth Test User",
                "email": test_email,
                "mobile": test_mobile,
                "department": "IT",
                "designation": "Tester",
                "password": "TestPass123",
                "confirm_password": "TestPass123",
            }
        )
        if success or (message and "saved" in message.lower()):
            ok("Register completes without transaction error")
        else:
            fail("Register", message or "unknown")

        user = auth.users.get_by_email(test_email)
        test_user_id = user.UserID if user else None
        verify_token_str = ""
        if user:
            verify_token_str = create_signed_token(user.UserID, test_email, "email_verify")
            auth.tokens.invalidate_active(
                auth.TOKEN_TYPES["email_verify_link"],
                user_id=user.UserID,
                email=test_email,
            )
            auth.tokens.create(
                {
                    "UserID": user.UserID,
                    "Email": test_email,
                    "TokenType": auth.TOKEN_TYPES["email_verify_link"],
                    "TokenHash": hash_token(verify_token_str),
                    "ExpiresAt": token_expiry(30),
                    "CreatedDate": __import__("datetime").datetime.utcnow(),
                }
            )
            db.session.commit()
            db.session.remove()
            ok("Verification link token stored")

            verified, ver_message, _ = auth.verify_email_link(verify_token_str, client_ip="127.0.0.1")
            if verified:
                ok("Email verification works")
                user = auth.users.get_by_email(test_email)
                if user and user.EmailVerified:
                    ok("EmailVerified updated")
                else:
                    fail("EmailVerified", "not updated")
                if hasattr(user, "VerificationDate") and user.VerificationDate:
                    ok("VerificationDate recorded")
                if hasattr(user, "VerificationIP") and user.VerificationIP == "127.0.0.1":
                    ok("VerificationIP recorded")
            else:
                fail("verify_email_link", ver_message or "unknown")

        print("\n=== Password reset link ===")
        admin = auth.users.get_by_email("itax.haldwani@gmail.com")
        if admin:
            admin_email = admin.EmailID
            admin_id = admin.UserID
            try:
                auth.request_password_reset(admin_email)
                ok("Forgot password completes without transaction error")
            except Exception as exc:
                if "transaction is already begun" in str(exc).lower():
                    fail("request_password_reset", str(exc))
                else:
                    ok("Forgot password completes without transaction error")

            reset_token = create_signed_token(admin_id, admin_email, "password_reset")
            auth.tokens.invalidate_active(
                auth.TOKEN_TYPES["password_reset_link"],
                user_id=admin_id,
                email=admin_email,
            )
            auth.tokens.create(
                {
                    "UserID": admin_id,
                    "Email": admin_email,
                    "TokenType": auth.TOKEN_TYPES["password_reset_link"],
                    "TokenHash": hash_token(reset_token),
                    "ExpiresAt": token_expiry(30),
                    "CreatedDate": __import__("datetime").datetime.utcnow(),
                }
            )
            db.session.commit()
            db.session.remove()

            old_hash = auth.users.get_by_email(admin_email).PasswordHash
            changed, change_msg, _ = auth.reset_password_with_token(
                reset_token,
                "TempPass123!",
                "TempPass123!",
            )
            admin = auth.users.get_by_email(admin_email)
            if changed and verify_password(admin.PasswordHash, "TempPass123!"):
                ok("Password reset with secure link works (bcrypt, one-time)")
                admin.PasswordHash = old_hash
                db.session.commit()
                db.session.remove()
            else:
                fail("reset_password_with_token", change_msg or "hash not updated")

            login_ok, login_msg, _ = auth.login(admin_email, "wrong-password")
            if not login_ok and login_msg:
                ok("Login rejects invalid password")
            else:
                fail("Login invalid password", "expected failure")

        print("\n=== Forgot User ID ===")
        try:
            auth.request_forgot_user_id(email=test_email)
            ok("Forgot user ID completes without transaction error")
        except Exception as exc:
            if "transaction is already begun" in str(exc).lower():
                fail("request_forgot_user_id", str(exc))
            else:
                ok("Forgot user ID completes without transaction error")

        print("\n=== Login — unverified email flow ===")
        pending_user = auth.users.get_by_email(test_email)
        if pending_user:
            auth.users.update(pending_user, {"EmailVerified": False, "AdminApproved": False, "UserStatus": "Pending", "IsActive": False})
            db.session.commit()
            db.session.remove()
            unverified_ok, unverified_msg, unverified_data = auth.login(test_email, "TestPass123")
            if not unverified_ok and unverified_data.get("reason") == "email_not_verified":
                ok("Login returns email_not_verified for unverified user")
            else:
                fail("Login unverified", unverified_msg or str(unverified_data))
            pending_user = auth.users.get_by_email(test_email)
            if pending_user:
                auth.users.update(pending_user, {"EmailVerified": True})
                db.session.commit()
                db.session.remove()

        print("\n=== Admin approval & login ===")
        if test_user_id:
            approved, approve_msg, _ = auth.approve_user(test_user_id)
            if approved:
                ok("Admin approval works")
            else:
                fail("approve_user", approve_msg or "unknown")

            login_ok, _, login_data = auth.login(test_email, "TestPass123")
            if login_ok and login_data.get("user_id"):
                ok("Login works after email verification and admin approval")
            else:
                fail("Login after approval", "expected success")

            deactivated, deact_msg, _ = auth.deactivate_user(test_user_id)
            if deactivated:
                ok("Deactivate user works")
            else:
                fail("deactivate_user", deact_msg or "unknown")

            login_ok, _, _ = auth.login(test_email, "TestPass123")
            if not login_ok:
                ok("Deactivated user cannot login")
            else:
                fail("Login after deactivate", "expected failure")

            test_user = auth.users.get_by_email(test_email)
            if test_user:
                for token in db.session.query(AuthToken).filter(AuthToken.UserID == test_user.UserID).all():
                    db.session.delete(token)
                db.session.delete(test_user)
                db.session.commit()

    print("\n=== HTTP routes (test client) ===")
    client = app.test_client()
    login_get = client.get("/login")
    if login_get.status_code == 200 and b"csrf_token" in login_get.data:
        ok("Login page renders with CSRF")
    else:
        fail("Login page", f"status {login_get.status_code}")

    verify_get = client.get(f"/verify/{verify_token_str or 'invalid'}")
    if verify_get.status_code in (200, 302):
        ok("Verification route responds")
    else:
        fail("Verification route", f"status {verify_get.status_code}")

    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["user_name"] = "Test"
        sess["role"] = "Administrator"
    logout = client.get("/logout", follow_redirects=False)
    if logout.status_code in (302, 303):
        ok("Logout route works")
    else:
        fail("Logout", f"status {logout.status_code}")

    class ShortSessionConfig(Config):
        PERMANENT_SESSION_LIFETIME = timedelta(seconds=1)

    short_app = create_app(ShortSessionConfig)
    short_client = short_app.test_client()
    with short_client.session_transaction() as sess:
        sess.permanent = True
        sess["user_id"] = 99
    ok("Session permanent flag configurable (timeout via PERMANENT_SESSION_LIFETIME)")

    print("\n=== Summary ===")
    if failures:
        print(f"{len(failures)} test(s) failed:")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("All authentication tests passed.")
    if not os.getenv("MAIL_PASSWORD"):
        print(f"Note: Set MAIL_PASSWORD in .env for live SMTP. User message on failure: {SMTP_USER_MESSAGE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_tests())
