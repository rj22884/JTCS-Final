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
    """Mask an email address for safe logging / user-facing conflict messages."""
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


def mask_mobile(number: str | None) -> str:
    """Mask a mobile number for user-facing conflict messages (e.g. 98****3210)."""
    if not number:
        return "***"
    digits = "".join(ch for ch in str(number).strip() if ch.isdigit())
    if len(digits) < 4:
        return "***"
    if len(digits) <= 6:
        return f"{digits[:1]}***{digits[-1]}"
    return f"{digits[:2]}****{digits[-4:]}"


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


def mail_domain_hostname(username: str | None) -> str | None:
    """FQDN for SMTP EHLO/HELO — VPS hostnames like 'ubuntu' are often rejected by Titan."""
    value = (username or "").strip()
    if "@" not in value:
        return None
    domain = value.split("@", 1)[1].strip().lower()
    if not domain or "." not in domain:
        return None
    return domain


def _build_smtp_client(
    *,
    server: str,
    port: int,
    use_ssl: bool,
    use_tls: bool,
    timeout: float,
    ssl_context: ssl.SSLContext | None,
    local_hostname: str | None = None,
) -> smtplib.SMTP | smtplib.SMTP_SSL:
    host_kw: dict[str, Any] = {}
    if local_hostname:
        host_kw["local_hostname"] = local_hostname

    if use_ssl:
        if ssl_context is None:
            # Flask-Mail style — works on Windows with GoDaddy.
            return smtplib.SMTP_SSL(server, port, timeout=timeout, **host_kw)
        return smtplib.SMTP_SSL(
            server, port, timeout=timeout, context=ssl_context, **host_kw
        )

    client = smtplib.SMTP(server, port, timeout=timeout, **host_kw)
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
    prefer_vps: bool = False,
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

    # Alternate port when primary is SSL 465 (common VPS outbound block).
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

    if prefer_vps:
        # Linux VPS: verified SSL / blocked 465 often hangs — try insecure + 587 first.
        def _rank(item: dict[str, Any]) -> tuple[int, str]:
            label = str(item.get("label") or "")
            if "insecure" in label and "587" in label:
                return (0, label)
            if "insecure" in label and "SSL" in label:
                return (1, label)
            if "587" in label:
                return (2, label)
            if "insecure" in label:
                return (3, label)
            return (4, label)

        attempts.sort(key=_rank)

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
    local_hostname: str | None = None,
    prefer_vps: bool = False,
) -> Iterator[smtplib.SMTP | smtplib.SMTP_SSL]:
    """
    Open an authenticated SMTP connection with VPS-friendly fallbacks.

    Tries Flask-Mail style SSL first, then unverified SSL (Linux/GoDaddy),
    then STARTTLS on port 587 when the primary port is 465.
    """
    client: smtplib.SMTP | smtplib.SMTP_SSL | None = None
    last_error: Exception | None = None
    ehlo_host = local_hostname or mail_domain_hostname(username)

    for attempt in _connection_attempts(
        use_ssl=use_ssl, use_tls=use_tls, port=port, prefer_vps=prefer_vps
    ):
        try:
            logger.debug(
                "SMTP connect attempt %s -> %s:%s",
                attempt["label"],
                server,
                attempt["port"],
            )
            client = _build_smtp_client(
                server=server,
                port=attempt["port"],
                use_ssl=attempt["use_ssl"],
                use_tls=attempt["use_tls"],
                timeout=timeout,
                ssl_context=attempt["ssl_context"],
                local_hostname=ehlo_host,
            )
            if username and password:
                client.login(username, password)
            logger.info(
                "SMTP connected via %s (%s:%s)",
                attempt["label"],
                server,
                attempt["port"],
            )
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
    prefer_vps: bool = False,
) -> tuple[bool, str | None]:
    """Connect to SMTP and authenticate. Never logs passwords."""
    if not server:
        return False, "SMTP Host is not configured."
    if not username:
        return False, "SMTP Username is not configured."
    if not password:
        return False, "SMTP Password is not configured."

    masked_user = mask_email(username)
    logger.debug(
        "SMTP health check: server=%s port=%s ssl=%s tls=%s user=%s prefer_vps=%s",
        server,
        port,
        use_ssl,
        use_tls,
        masked_user,
        prefer_vps,
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
            prefer_vps=prefer_vps,
        ):
            return True, f"SMTP login succeeded for {masked_user} via {server}:{port}"
    except smtplib.SMTPAuthenticationError as exc:
        return (
            False,
            f"SMTP authentication failed for {masked_user}. "
            "Check the Titan mailbox password (same as webmail login).",
        )
    except smtplib.SMTPException as exc:
        return False, f"SMTP error for {server}:{port}: {exc}"
    except TRANSIENT_SMTP_ERRORS as exc:
        return (
            False,
            f"SMTP connection error for {server}:{port}: {exc}. "
            "Try port 587 with TLS if 465/SSL is blocked.",
        )
    except Exception as exc:
        logger.exception("Unexpected SMTP check failure for %s", masked_user)
        return False, f"SMTP check failed ({exc.__class__.__name__})."


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
        "[MAIL CONFIG] server=%s port=%s ssl=%s tls=%s user=%s sender=%s "
        "password_set=%s app_base_url=%s",
        config.get("MAIL_SERVER"),
        config.get("MAIL_PORT"),
        config.get("MAIL_USE_SSL"),
        config.get("MAIL_USE_TLS"),
        mask_email(config.get("MAIL_USERNAME")),
        config.get("MAIL_DEFAULT_SENDER"),
        bool(config.get("MAIL_PASSWORD")),
        config.get("APP_BASE_URL"),
    )
