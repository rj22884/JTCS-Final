"""SMTP connectivity helpers — matches Flask-Mail connection behaviour."""

from __future__ import annotations

import logging
import smtplib
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger(__name__)

TRANSIENT_SMTP_ERRORS = (
    smtplib.SMTPConnectError,
    smtplib.SMTPServerDisconnected,
    smtplib.SMTPHeloError,
    TimeoutError,
    OSError,
)


def mask_email(address: str | None) -> str:
    """Mask an email address for safe logging."""
    if not address:
        return "(not set)"
    value = address.strip()
    if "@" not in value:
        return "***"
    local, domain = value.split("@", 1)
    if len(local) <= 2:
        masked_local = "*"
    else:
        masked_local = f"{local[0]}***{local[-1]}"
    return f"{masked_local}@{domain}"


def smtp_settings_from_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "server": (config.get("MAIL_SERVER") or "").strip(),
        "port": int(config.get("MAIL_PORT") or 465),
        "username": (config.get("MAIL_USERNAME") or "").strip(),
        "password": config.get("MAIL_PASSWORD") or "",
        "use_ssl": bool(config.get("MAIL_USE_SSL")),
        "use_tls": bool(config.get("MAIL_USE_TLS")),
        "timeout": float(config.get("MAIL_TIMEOUT", 30)),
    }


@contextmanager
def open_smtp_connection(
    *,
    server: str,
    port: int,
    username: str,
    password: str,
    use_ssl: bool = True,
    use_tls: bool = False,
    timeout: float = 30,
) -> Iterator[smtplib.SMTP | smtplib.SMTP_SSL]:
    """
    Open an authenticated SMTP connection using the same approach as Flask-Mail.

    Flask-Mail calls SMTP_SSL(host, port) without an explicit SSL context, which
    succeeds with GoDaddy secureserver on Windows where create_default_context()
    certificate verification fails.
    """
    client: smtplib.SMTP | smtplib.SMTP_SSL | None = None
    try:
        if use_ssl:
            client = smtplib.SMTP_SSL(server, port, timeout=timeout)
        else:
            client = smtplib.SMTP(server, port, timeout=timeout)
            if use_tls:
                client.starttls()

        if username and password:
            client.login(username, password)

        yield client
    finally:
        if client is not None:
            try:
                client.quit()
            except Exception:
                try:
                    client.close()
                except Exception:
                    pass


def check_smtp_connection(
    *,
    server: str,
    port: int,
    username: str,
    password: str,
    use_ssl: bool = True,
    use_tls: bool = False,
    timeout: float = 15,
) -> tuple[bool, str | None]:
    """Connect to SMTP and authenticate. Never logs passwords."""
    if not server:
        return False, "MAIL_SERVER is not configured."
    if not username:
        return False, "MAIL_USERNAME is not configured."
    if not password:
        return False, "MAIL_PASSWORD is not configured."

    masked_user = mask_email(username)
    logger.debug(
        "SMTP health check: server=%s port=%s ssl=%s tls=%s user=%s",
        server,
        port,
        use_ssl,
        use_tls,
        masked_user,
    )

    try:
        with open_smtp_connection(
            server=server,
            port=port,
            username=username,
            password=password,
            use_ssl=use_ssl,
            use_tls=use_tls,
            timeout=timeout,
        ):
            return True, f"SMTP login succeeded for {masked_user} via {server}:{port}"
    except smtplib.SMTPAuthenticationError as exc:
        return False, f"SMTP authentication failed for {masked_user}: {exc}"
    except smtplib.SMTPException as exc:
        return False, f"SMTP error for {server}:{port}: {exc}"
    except TRANSIENT_SMTP_ERRORS as exc:
        return False, f"SMTP connection error for {server}:{port}: {exc}"


def check_smtp_from_config(config: dict[str, Any] | None = None) -> tuple[bool, str | None]:
    """Run SMTP health check using Flask config or an explicit mapping."""
    if config is None:
        from flask import current_app

        config = current_app.config

    settings = smtp_settings_from_config(config)
    return check_smtp_connection(
        server=settings["server"],
        port=settings["port"],
        username=settings["username"],
        password=settings["password"],
        use_ssl=settings["use_ssl"],
        use_tls=settings["use_tls"],
        timeout=settings["timeout"],
    )


def log_mail_config(config: dict[str, Any], logger_obj: logging.Logger | None = None) -> None:
    """Log loaded mail settings with secrets masked."""
    log = logger_obj or logger
    log.info(
        "[MAIL CONFIG] server=%s port=%s ssl=%s tls=%s user=%s sender=%s password_set=%s",
        config.get("MAIL_SERVER"),
        config.get("MAIL_PORT"),
        config.get("MAIL_USE_SSL"),
        config.get("MAIL_USE_TLS"),
        mask_email(config.get("MAIL_USERNAME")),
        config.get("MAIL_DEFAULT_SENDER"),
        bool(config.get("MAIL_PASSWORD")),
    )
