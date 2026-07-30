"""SMTP connectivity helpers — matches Flask-Mail connection behaviour."""

from __future__ import annotations

import logging
import smtplib
import ssl
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger(__name__)

TRANSIENT_SMTP_ERRORS = (
    smtplib.SMTPConnectError,
    smtplib.SMTPServerDisconnected,
    smtplib.SMTPHeloError,
    TimeoutError,
    OSError,
    ssl.SSLError,
)

# GoDaddy / Titan often accept SSL on 465; many VPS networks also need STARTTLS on 587.
SMTP_FALLBACK_PORT = 587


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


def _insecure_ssl_context() -> ssl.SSLContext:
    """GoDaddy secureserver certs often fail hostname checks on Linux VPS."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _build_smtp_client(
    *,
    server: str,
    port: int,
    use_ssl: bool,
    use_tls: bool,
    timeout: float,
    ssl_context: ssl.SSLContext | None,
) -> smtplib.SMTP | smtplib.SMTP_SSL:
    if use_ssl:
        if ssl_context is None:
            # Flask-Mail style — works on Windows with GoDaddy.
            return smtplib.SMTP_SSL(server, port, timeout=timeout)
        return smtplib.SMTP_SSL(server, port, timeout=timeout, context=ssl_context)

    client = smtplib.SMTP(server, port, timeout=timeout)
    if use_tls:
        if ssl_context is None:
            client.starttls()
        else:
            client.starttls(context=ssl_context)
    return client


def _connection_attempts(
    *,
    use_ssl: bool,
    use_tls: bool,
    port: int,
) -> list[dict[str, Any]]:
    """Ordered connect strategies: primary config, then VPS-friendly fallbacks."""
    attempts: list[dict[str, Any]] = []

    if use_ssl:
        attempts.append(
            {
                "label": f"SSL:{port}/default",
                "port": port,
                "use_ssl": True,
                "use_tls": False,
                "ssl_context": None,
            }
        )
        attempts.append(
            {
                "label": f"SSL:{port}/insecure",
                "port": port,
                "use_ssl": True,
                "use_tls": False,
                "ssl_context": _insecure_ssl_context(),
            }
        )
    else:
        attempts.append(
            {
                "label": f"SMTP:{port}/tls={use_tls}/default",
                "port": port,
                "use_ssl": False,
                "use_tls": use_tls,
                "ssl_context": None,
            }
        )
        if use_tls:
            attempts.append(
                {
                    "label": f"SMTP:{port}/tls/insecure",
                    "port": port,
                    "use_ssl": False,
                    "use_tls": True,
                    "ssl_context": _insecure_ssl_context(),
                }
            )

    # Alternate port when primary is SSL 465 (common VPS outbound block / Titan).
    if use_ssl and port != SMTP_FALLBACK_PORT:
        attempts.append(
            {
                "label": f"STARTTLS:{SMTP_FALLBACK_PORT}/default",
                "port": SMTP_FALLBACK_PORT,
                "use_ssl": False,
                "use_tls": True,
                "ssl_context": None,
            }
        )
        attempts.append(
            {
                "label": f"STARTTLS:{SMTP_FALLBACK_PORT}/insecure",
                "port": SMTP_FALLBACK_PORT,
                "use_ssl": False,
                "use_tls": True,
                "ssl_context": _insecure_ssl_context(),
            }
        )

    return attempts


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
    Open an authenticated SMTP connection with VPS-friendly fallbacks.

    Tries Flask-Mail style SSL first, then unverified SSL (Linux/GoDaddy),
    then STARTTLS on port 587 when the primary port is 465.
    """
    client: smtplib.SMTP | smtplib.SMTP_SSL | None = None
    last_error: Exception | None = None

    for attempt in _connection_attempts(use_ssl=use_ssl, use_tls=use_tls, port=port):
        try:
            logger.debug("SMTP connect attempt %s -> %s:%s", attempt["label"], server, attempt["port"])
            client = _build_smtp_client(
                server=server,
                port=attempt["port"],
                use_ssl=attempt["use_ssl"],
                use_tls=attempt["use_tls"],
                timeout=timeout,
                ssl_context=attempt["ssl_context"],
            )
            if username and password:
                client.login(username, password)
            logger.info("SMTP connected via %s (%s:%s)", attempt["label"], server, attempt["port"])
            try:
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
            return
        except smtplib.SMTPAuthenticationError:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
                client = None
            raise
        except (TRANSIENT_SMTP_ERRORS, smtplib.SMTPException) as exc:
            last_error = exc
            logger.warning(
                "SMTP attempt %s failed for %s:%s: %s",
                attempt["label"],
                server,
                attempt["port"],
                exc,
            )
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
                client = None

    if last_error is not None:
        raise last_error
    raise smtplib.SMTPConnectError(-1, f"Unable to connect to {server}:{port}")


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
        return (
            False,
            f"SMTP connection error for {server}:{port}: {exc}. "
            "On VPS, allow outbound TCP 465 and 587, and confirm MAIL_* in erp/.env.",
        )


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
        "[MAIL CONFIG] server=%s port=%s ssl=%s tls=%s user=%s sender=%s password_set=%s app_base_url=%s",
        config.get("MAIL_SERVER"),
        config.get("MAIL_PORT"),
        config.get("MAIL_USE_SSL"),
        config.get("MAIL_USE_TLS"),
        mask_email(config.get("MAIL_USERNAME")),
        config.get("MAIL_DEFAULT_SENDER"),
        bool(config.get("MAIL_PASSWORD")),
        config.get("APP_BASE_URL"),
    )
