#!/usr/bin/env python3
"""Unit tests for registration email link helpers (no live SMTP / full app required)."""

from __future__ import annotations

import importlib.util
import smtplib
import sys
import types
from pathlib import Path
from unittest.mock import patch

from flask import Blueprint, Flask
from flask_mail import Mail, Message

ROOT = Path(__file__).resolve().parent.parent
# Add erp root only after third-party imports so `app` package is not pulled in early.
sys.path.insert(0, str(ROOT))


def _load(name: str, rel: str, *, inject: dict | None = None):
    """Load a module by file path without executing app/__init__.py."""
    path = ROOT / rel
    # Ensure parent packages exist as lightweight stubs.
    parts = name.split(".")
    for i in range(1, len(parts)):
        pkg = ".".join(parts[:i])
        if pkg not in sys.modules:
            mod = types.ModuleType(pkg)
            mod.__path__ = [str(ROOT / "/".join(parts[:i]))]
            sys.modules[pkg] = mod
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    if inject:
        for key, value in inject.items():
            setattr(module, key, value)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Lightweight stubs for email_service imports.
ext = types.ModuleType("app.extensions")
ext.mail = Mail()
sys.modules["app.extensions"] = ext

smtp_health = _load("app.utils.smtp_health", "app/utils/smtp_health.py")
url_helpers = _load("app.utils.url_helpers", "app/utils/url_helpers.py")
email_service = _load(
    "app.services.email_service",
    "app/services/email_service.py",
)

EmailService = email_service.EmailService
SMTP_NOT_CONFIGURED = email_service.SMTP_NOT_CONFIGURED
mail_domain_hostname = smtp_health.mail_domain_hostname
external_url_for = url_helpers.external_url_for
public_base_url = url_helpers.public_base_url


def _app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="test-secret",
        APP_NAME="JTCS ERP",
        APP_BASE_URL="http://app.jtcsxpert.com",
        MAIL_SERVER="smtpout.secureserver.net",
        MAIL_PORT=465,
        MAIL_USE_SSL=True,
        MAIL_USE_TLS=False,
        MAIL_USERNAME="admin@jtcsxpert.com",
        MAIL_PASSWORD="secret",
        MAIL_DEFAULT_SENDER="Joshi Tax Consultancy & Services <admin@jtcsxpert.com>",
        SUPPORT_EMAIL="admin@jtcsxpert.com",
        AUTH_TOKEN_EXPIRY_MINUTES=30,
        SERVER_NAME=None,
        PREFERRED_URL_SCHEME="http",
        PORT=8000,
    )
    Mail(app)
    ext.mail.init_app(app)

    bp = Blueprint("auth", __name__)

    @bp.route("/reset-password", methods=["GET", "POST"])
    @bp.route("/reset-password/<path:token>", methods=["GET", "POST"])
    def reset_password(token=None):  # noqa: ARG001
        return "ok"

    app.register_blueprint(bp)
    return app


def test_mail_domain_from_display_sender() -> None:
    assert mail_domain_hostname("admin@jtcsxpert.com") == "jtcsxpert.com"
    assert mail_domain_hostname("Joshi Tax <admin@jtcsxpert.com>") == "jtcsxpert.com"


def test_message_id_uses_mail_domain() -> None:
    app = _app()
    with app.app_context():
        msg = Message(
            subject="Set your Password",
            recipients=["user@example.com"],
            body="hi",
            html="<p>hi</p>",
            sender=app.config["MAIL_DEFAULT_SENDER"],
        )
        assert "@localhost" in msg.msgId
        EmailService._prepare_message_headers(msg, app.config)
        assert msg.date is not None
        assert msg.msgId.endswith("@jtcsxpert.com>")
        assert "@localhost" not in msg.msgId
        raw = msg.as_bytes().decode("utf-8", errors="replace")
        assert "Message-ID:" in raw
        assert "@jtcsxpert.com" in raw


def test_reset_password_email_link_uses_query_token() -> None:
    app = _app()
    token = "abc.def.ghi_signed_token_value"
    with app.app_context():
        url = external_url_for("auth.reset_password", token=token)
    assert url.startswith("http://app.jtcsxpert.com/reset-password?token=")
    assert "abc.def.ghi_signed_token_value" in url
    assert "/reset-password/abc" not in url


def test_public_base_url_prefers_configured() -> None:
    app = _app()
    with app.app_context():
        assert public_base_url() == "http://app.jtcsxpert.com"


def test_send_html_reports_not_configured() -> None:
    app = _app()
    app.config["MAIL_PASSWORD"] = ""
    with app.app_context():
        with patch.object(
            EmailService,
            "_mail_config_candidates",
            return_value=[],
        ):
            ok, err = EmailService().send_html("a@b.com", "Hi", "<p>x</p>", "x")
    assert ok is False
    assert err == SMTP_NOT_CONFIGURED


def test_send_html_falls_back_to_env_when_integration_auth_fails() -> None:
    app = _app()
    overlay = {
        "MAIL_SERVER": "smtp.bad.example",
        "MAIL_PORT": 465,
        "MAIL_USERNAME": "bad@example.com",
        "MAIL_PASSWORD": "wrong",
        "MAIL_DEFAULT_SENDER": "bad@example.com",
        "MAIL_USE_SSL": True,
        "MAIL_USE_TLS": False,
        "MAIL_TIMEOUT": 5.0,
    }
    with app.app_context():
        svc = EmailService()
        calls: list[str] = []

        def fake_direct(message, *, cfg=None, prefer_vps=False, timeout=None):
            source_user = (cfg or {}).get("MAIL_USERNAME")
            calls.append(source_user)
            if source_user == "bad@example.com":
                raise smtplib.SMTPAuthenticationError(535, b"auth failed")
            return None

        with patch.object(
            EmailService,
            "_mail_config_candidates",
            return_value=[
                ("integration_settings", overlay),
                ("env", dict(app.config)),
            ],
        ), patch.object(EmailService, "_send_message_direct", side_effect=fake_direct):
            ok, err = svc.send_html(
                "user@example.com",
                "Set your Password",
                "<p>x</p>",
                "x",
                prefer_vps=True,
                max_attempts=1,
            )
    assert ok is True
    assert err is None
    assert calls == ["bad@example.com", "admin@jtcsxpert.com"]


def main() -> int:
    tests = [
        test_mail_domain_from_display_sender,
        test_message_id_uses_mail_domain,
        test_reset_password_email_link_uses_query_token,
        test_public_base_url_prefers_configured,
        test_send_html_reports_not_configured,
        test_send_html_falls_back_to_env_when_integration_auth_fails,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  OK  {fn.__name__}")
        except Exception as exc:
            failed += 1
            print(f"  FAIL {fn.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
