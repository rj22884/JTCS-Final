import logging
import smtplib
import time
from datetime import datetime
from email.utils import make_msgid

from flask import current_app, render_template
from flask_mail import Message

from app.extensions import mail
from app.utils.smtp_health import (
    TRANSIENT_SMTP_ERRORS,
    mail_domain_hostname,
    mask_email,
    open_smtp_connection,
    smtp_settings_from_config,
)

logger = logging.getLogger(__name__)

SMTP_NOT_CONFIGURED = "SMTP mail is not configured."
SMTP_USER_MESSAGE = "Unable to send email. Please contact Administrator."
SMTP_SEND_MAX_ATTEMPTS = 2
SMTP_RETRY_DELAY_SECONDS = 1.0
# Registration verification: more retries + VPS-first SMTP (587/insecure before slow 465).
REGISTRATION_SMTP_MAX_ATTEMPTS = 3
REGISTRATION_SMTP_TIMEOUT = 15.0


class EmailService:
    def _env_mail_config(self) -> dict:
        """Flask .env MAIL_* mapping (always available as a fallback)."""
        return current_app.config

    def _mail_config(self) -> dict:
        """Prefer Integration Settings SMTP (encrypted DB) when fully configured; else .env."""
        try:
            from app.modules.settings.services import IntegrationSettingsService

            overlay = IntegrationSettingsService().smtp_runtime_config()
            if overlay:
                return overlay
        except Exception:
            logger.debug("[EMAIL] Integration Settings SMTP unavailable; using .env MAIL_*", exc_info=True)
        return self._env_mail_config()

    def _mail_config_candidates(self) -> list[tuple[str, dict]]:
        """Ordered SMTP configs: Integration Settings first (if any), then .env."""
        candidates: list[tuple[str, dict]] = []
        seen: set[tuple] = set()

        def _key(cfg: dict) -> tuple:
            return (
                (cfg.get("MAIL_SERVER") or "").strip().lower(),
                int(cfg.get("MAIL_PORT") or 0),
                (cfg.get("MAIL_USERNAME") or "").strip().lower(),
                cfg.get("MAIL_PASSWORD") or "",
            )

        try:
            from app.modules.settings.services import IntegrationSettingsService

            overlay = IntegrationSettingsService().smtp_runtime_config()
            if overlay:
                candidates.append(("integration_settings", overlay))
                seen.add(_key(overlay))
        except Exception:
            logger.debug("[EMAIL] Integration Settings SMTP unavailable", exc_info=True)

        env_cfg = self._env_mail_config()
        env_key = _key(env_cfg)
        if env_cfg.get("MAIL_PASSWORD") and env_key not in seen:
            candidates.append(("env", env_cfg))

        if not candidates and env_cfg.get("MAIL_SERVER"):
            candidates.append(("env", env_cfg))
        return candidates

    def is_configured(self) -> bool:
        for _, cfg in self._mail_config_candidates():
            if (
                cfg.get("MAIL_SERVER")
                and cfg.get("MAIL_USERNAME")
                and cfg.get("MAIL_PASSWORD")
                and cfg.get("MAIL_DEFAULT_SENDER")
            ):
                return True
        return False

    @staticmethod
    def _prepare_message_headers(message: Message, cfg: dict) -> None:
        """Set Date + Message-ID with real mail domain (avoid @localhost spam filtering)."""
        if message.date is None:
            message.date = time.time()
        domain = mail_domain_hostname(cfg.get("MAIL_USERNAME")) or mail_domain_hostname(
            str(cfg.get("MAIL_DEFAULT_SENDER") or "")
        )
        # Flask-Mail defaults to make_msgid() → often @localhost on VPS hostnames.
        if domain and (
            not message.msgId
            or message.msgId.endswith("@localhost>")
            or "@localhost" in message.msgId
        ):
            message.msgId = make_msgid(domain=domain)

    def _context(self) -> dict:
        from app.repositories.user_repository import CompanyRepository

        support = current_app.config.get("SUPPORT_EMAIL") or current_app.config.get("MAIL_USERNAME", "")
        company = current_app.config.get("COMPANY_DISPLAY_NAME", "Joshi Tax Consultancy & Services")
        logo_path = None
        try:
            profile = CompanyRepository().get_profile()
            if profile and profile.LogoPath:
                logo_path = profile.LogoPath
        except Exception:
            logger.exception("[EMAIL] Failed to load company profile for email context")
        from app.utils.url_helpers import public_base_url

        base = public_base_url()
        logo_url = f"{base}/static/{logo_path.lstrip('/')}" if logo_path else None
        return {
            "app_name": current_app.config["APP_NAME"],
            "company_name": company,
            "support_email": support,
            "current_year": datetime.now().year,
            "logo_url": logo_url,
        }

    def _send_message(self, message: Message) -> None:
        logger.info("[EMAIL] Sending via Flask-Mail")
        mail.send(message)

    def _send_message_direct(
        self,
        message: Message,
        *,
        cfg: dict | None = None,
        prefer_vps: bool = False,
        timeout: float | None = None,
    ) -> None:
        """Primary SMTP send with VPS-friendly SSL/port fallbacks."""
        from flask_mail import sanitize_address, sanitize_addresses

        cfg = cfg or self._mail_config()
        self._prepare_message_headers(message, cfg)
        settings = smtp_settings_from_config(cfg)
        if timeout is not None:
            settings["timeout"] = float(timeout)
        settings["prefer_vps"] = prefer_vps
        settings["local_hostname"] = mail_domain_hostname(settings.get("username"))
        # Titan/GoDaddy requires envelope MAIL FROM = authenticated mailbox.
        envelope_from = sanitize_address(
            settings.get("username") or message.sender
        )
        logger.info(
            "[EMAIL] Sending via direct SMTP to %s prefer_vps=%s ehlo=%s from=%s",
            settings["server"],
            prefer_vps,
            settings.get("local_hostname"),
            mask_email(str(envelope_from)),
        )
        with open_smtp_connection(**settings) as smtp:
            smtp.sendmail(
                envelope_from,
                list(sanitize_addresses(message.recipients)),
                message.as_bytes(),
            )

    def _should_retry(self, exc: Exception, attempt: int, max_attempts: int) -> bool:
        if attempt >= max_attempts:
            return False
        if isinstance(exc, smtplib.SMTPAuthenticationError):
            return False
        if isinstance(exc, TRANSIENT_SMTP_ERRORS):
            return True
        if isinstance(exc, smtplib.SMTPException):
            code = getattr(exc, "smtp_code", None)
            if code in {421, 450, 451, 452}:
                return True
        return False

    @staticmethod
    def _normalize_sender(cfg: dict) -> str:
        sender = cfg.get("MAIL_DEFAULT_SENDER") or ""
        username = (cfg.get("MAIL_USERNAME") or "").strip()
        # Keep display name, but force mailbox address = authenticated user (GoDaddy).
        if username and "<" not in str(sender) and str(sender).lower() != username.lower():
            return f"Joshi Tax Consultancy & Services <{username}>"
        if username and "<" in str(sender) and username.lower() not in str(sender).lower():
            return f"Joshi Tax Consultancy & Services <{username}>"
        return str(sender)

    def send_html(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str | None = None,
        *,
        prefer_vps: bool = False,
        max_attempts: int | None = None,
        timeout: float | None = None,
        reply_to: str | None = None,
        attachments: list[tuple[str, bytes, str]] | None = None,
    ) -> tuple[bool, str | None]:
        candidates = self._mail_config_candidates()
        if not candidates:
            logger.error(
                "[EMAIL] SMTP not fully configured — cannot send email to %s",
                mask_email(to_email),
            )
            return False, SMTP_NOT_CONFIGURED

        attempts = max_attempts or SMTP_SEND_MAX_ATTEMPTS
        last_error: Exception | None = None

        for source, cfg in candidates:
            if not (
                cfg.get("MAIL_SERVER")
                and cfg.get("MAIL_USERNAME")
                and cfg.get("MAIL_PASSWORD")
                and cfg.get("MAIL_DEFAULT_SENDER")
            ):
                logger.warning("[EMAIL] Skipping incomplete SMTP source=%s", source)
                continue

            logger.info(
                "[EMAIL] Preparing email to=%s subject=%s sender=%s prefer_vps=%s source=%s",
                mask_email(to_email),
                subject,
                cfg.get("MAIL_DEFAULT_SENDER"),
                prefer_vps,
                source,
            )

            message = Message(
                subject=subject,
                recipients=[to_email],
                body=text_body or "Please view this message in an HTML-capable email client.",
                html=html_body,
                sender=self._normalize_sender(cfg),
            )
            if reply_to:
                message.reply_to = reply_to
            for filename, data, mime in attachments or []:
                message.attach(filename, mime or "application/octet-stream", data)

            self._prepare_message_headers(message, cfg)
            self._log_smtp_config_for(cfg, source=source)

            for attempt in range(1, attempts + 1):
                try:
                    try:
                        # Prefer direct SMTP (SSL/587 fallbacks for VPS).
                        self._send_message_direct(
                            message,
                            cfg=cfg,
                            prefer_vps=prefer_vps,
                            timeout=timeout,
                        )
                    except Exception as direct_exc:
                        logger.warning(
                            "[EMAIL] Direct SMTP send failed (attempt %s/%s source=%s): %s",
                            attempt,
                            attempts,
                            source,
                            direct_exc,
                            exc_info=True,
                        )
                        # Final attempt on this config: also try Flask-Mail (.env-backed).
                        if attempt >= attempts and source == "env":
                            self._send_message(message)
                        elif prefer_vps and attempt < attempts:
                            raise
                        elif not prefer_vps:
                            self._send_message(message)
                        else:
                            raise

                    logger.info(
                        "[EMAIL] Email sent successfully to %s via %s: %s",
                        mask_email(to_email),
                        source,
                        subject,
                    )
                    return True, None
                except smtplib.SMTPAuthenticationError as exc:
                    last_error = exc
                    logger.error(
                        "[EMAIL] SMTP authentication failed for %s (source=%s): %s",
                        mask_email(cfg.get("MAIL_USERNAME")),
                        source,
                        exc,
                        exc_info=True,
                    )
                    # Try next SMTP source (e.g. .env after bad Integration Settings).
                    break
                except smtplib.SMTPException as exc:
                    last_error = exc
                    logger.error(
                        "[EMAIL] SMTP error sending to %s (attempt %s/%s source=%s): %s",
                        mask_email(to_email),
                        attempt,
                        attempts,
                        source,
                        exc,
                        exc_info=True,
                    )
                    if attempt >= attempts:
                        break
                    if not prefer_vps and not self._should_retry(exc, attempt, attempts):
                        break
                except TRANSIENT_SMTP_ERRORS as exc:
                    last_error = exc
                    logger.error(
                        "[EMAIL] SMTP connection error sending to %s (attempt %s/%s source=%s): %s",
                        mask_email(to_email),
                        attempt,
                        attempts,
                        source,
                        exc,
                        exc_info=True,
                    )
                    if attempt >= attempts:
                        break
                    if not prefer_vps and not self._should_retry(exc, attempt, attempts):
                        break
                except Exception as exc:
                    last_error = exc
                    logger.error(
                        "[EMAIL] Unexpected email error sending to %s (source=%s): %s",
                        mask_email(to_email),
                        source,
                        exc,
                        exc_info=True,
                    )
                    break

                time.sleep(SMTP_RETRY_DELAY_SECONDS)

        if last_error is not None:
            logger.error(
                "[EMAIL] SMTP send failed for all configs to %s: %s",
                mask_email(to_email),
                last_error,
                exc_info=True,
            )
        return False, SMTP_USER_MESSAGE

    def _log_smtp_config_for(self, cfg: dict, *, source: str = "unknown") -> None:
        logger.info(
            "[EMAIL] Connecting SMTP source=%s server=%s port=%s ssl=%s tls=%s sender=%s",
            source,
            cfg.get("MAIL_SERVER"),
            cfg.get("MAIL_PORT"),
            cfg.get("MAIL_USE_SSL"),
            cfg.get("MAIL_USE_TLS"),
            cfg.get("MAIL_DEFAULT_SENDER"),
        )

    def send_verification_email(self, to_email: str, full_name: str, verify_url: str) -> tuple[bool, str | None]:
        """Registration verification mail — VPS-hardened SMTP path only."""
        logger.info("[EMAIL] Preparing verification email for %s", mask_email(to_email))
        logger.info("[EMAIL] Verification URL: %s", verify_url)
        if "localhost" in (verify_url or "").lower() or "127.0.0.1" in (verify_url or ""):
            logger.error(
                "[EMAIL] Verification URL still points at localhost — set APP_BASE_URL on VPS "
                "to the public site URL (e.g. http://app.jtcsexpert.com)."
            )
        ctx = self._context()
        logger.info("[EMAIL] Rendering template email/verify_email.html")
        html = render_template(
            "email/verify_email.html",
            full_name=full_name,
            verify_url=verify_url,
            expiry_minutes=current_app.config.get("AUTH_TOKEN_EXPIRY_MINUTES", 30),
            **ctx,
        )
        text = (
            f"Hello {full_name},\n\n"
            f"Verify your email:\n{verify_url}\n\n"
            f"Support: {ctx['support_email']}"
        )
        support = (ctx.get("support_email") or current_app.config.get("MAIL_USERNAME") or "").strip()
        return self.send_html(
            to_email,
            "Verify your Email",
            html,
            text,
            prefer_vps=True,
            max_attempts=REGISTRATION_SMTP_MAX_ATTEMPTS,
            timeout=REGISTRATION_SMTP_TIMEOUT,
            reply_to=support or None,
        )

    def send_password_reset_email(self, to_email: str, full_name: str, reset_url: str) -> tuple[bool, str | None]:
        ctx = self._context()
        html = render_template(
            "email/password_reset.html",
            full_name=full_name,
            reset_url=reset_url,
            expiry_minutes=current_app.config.get("AUTH_TOKEN_EXPIRY_MINUTES", 30),
            **ctx,
        )
        text = (
            f"Hello {full_name},\n\n"
            f"Reset your password:\n{reset_url}\n\n"
            f"This link expires in 30 minutes.\n\n"
            f"Support: {ctx['support_email']}"
        )
        support = (ctx.get("support_email") or current_app.config.get("MAIL_USERNAME") or "").strip()
        return self.send_html(
            to_email,
            "Reset your Password",
            html,
            text,
            prefer_vps=True,
            max_attempts=REGISTRATION_SMTP_MAX_ATTEMPTS,
            timeout=REGISTRATION_SMTP_TIMEOUT,
            reply_to=support or None,
        )

    def send_set_password_email(self, to_email: str, full_name: str, reset_url: str) -> tuple[bool, str | None]:
        """Registration invite — user sets password via emailed link (also verifies email)."""
        logger.info("[EMAIL] Preparing set-password email for %s", mask_email(to_email))
        logger.info("[EMAIL] Set-password URL: %s", reset_url)
        if "localhost" in (reset_url or "").lower() or "127.0.0.1" in (reset_url or ""):
            logger.error(
                "[EMAIL] Set-password URL still points at localhost — set APP_BASE_URL on VPS "
                "to the public site URL (e.g. http://app.jtcsexpert.com)."
            )
        ctx = self._context()
        html = render_template(
            "email/set_password.html",
            full_name=full_name,
            reset_url=reset_url,
            expiry_minutes=current_app.config.get("AUTH_TOKEN_EXPIRY_MINUTES", 30),
            **ctx,
        )
        text = (
            f"Hello {full_name},\n\n"
            f"Set your password and verify your email:\n{reset_url}\n\n"
            f"Password must be at least 8 characters with uppercase, lowercase, and a number.\n"
            f"This link expires in {current_app.config.get('AUTH_TOKEN_EXPIRY_MINUTES', 30)} minutes.\n\n"
            f"Support: {ctx['support_email']}"
        )
        support = (ctx.get("support_email") or current_app.config.get("MAIL_USERNAME") or "").strip()
        return self.send_html(
            to_email,
            "Set your Password",
            html,
            text,
            prefer_vps=True,
            max_attempts=REGISTRATION_SMTP_MAX_ATTEMPTS,
            timeout=REGISTRATION_SMTP_TIMEOUT,
            reply_to=support or None,
        )

    def send_user_id_recovery_email(self, to_email: str, user_ids: list[str]) -> tuple[bool, str | None]:
        ctx = self._context()
        html = render_template(
            "email/forgot_user_id.html",
            user_ids=user_ids,
            **ctx,
        )
        text = "Your JTCS ERP User ID(s):\n\n" + "\n".join(user_ids)
        return self.send_html(to_email, "Your JTCS ERP User ID", html, text)

    def send_admin_new_user_notification(
        self,
        admin_email: str,
        user_name: str,
        user_email: str,
        pending_url: str,
    ) -> tuple[bool, str | None]:
        ctx = self._context()
        html = render_template(
            "email/admin_new_user.html",
            user_name=user_name,
            user_email=user_email,
            pending_url=pending_url,
            **ctx,
        )
        text = f"New user {user_name} ({user_email}) awaits approval: {pending_url}"
        return self.send_html(admin_email, f"New user pending — {ctx['app_name']}", html, text)
