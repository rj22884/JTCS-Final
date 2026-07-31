import logging
import smtplib
import time
from datetime import datetime

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
    def is_configured(self) -> bool:
        return bool(
            current_app.config.get("MAIL_SERVER")
            and current_app.config.get("MAIL_USERNAME")
            and current_app.config.get("MAIL_PASSWORD")
            and current_app.config.get("MAIL_DEFAULT_SENDER")
        )

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

    def _log_smtp_config(self) -> None:
        logger.info(
            "[EMAIL] Connecting SMTP server=%s port=%s ssl=%s tls=%s sender=%s",
            current_app.config.get("MAIL_SERVER"),
            current_app.config.get("MAIL_PORT"),
            current_app.config.get("MAIL_USE_SSL"),
            current_app.config.get("MAIL_USE_TLS"),
            current_app.config.get("MAIL_DEFAULT_SENDER"),
        )

    def _send_message(self, message: Message) -> None:
        logger.info("[EMAIL] Sending via Flask-Mail")
        mail.send(message)

    def _send_message_direct(
        self,
        message: Message,
        *,
        prefer_vps: bool = False,
        timeout: float | None = None,
    ) -> None:
        """Primary SMTP send with VPS-friendly SSL/port fallbacks."""
        from flask_mail import sanitize_address, sanitize_addresses

        settings = smtp_settings_from_config(current_app.config)
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

    def _should_retry(self, exc: Exception, attempt: int) -> bool:
        if attempt >= SMTP_SEND_MAX_ATTEMPTS:
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
    ) -> tuple[bool, str | None]:
        logger.info(
            "[EMAIL] Preparing email to=%s subject=%s sender=%s prefer_vps=%s",
            mask_email(to_email),
            subject,
            current_app.config.get("MAIL_DEFAULT_SENDER"),
            prefer_vps,
        )

        if not current_app.config.get("MAIL_PASSWORD"):
            logger.error(
                "[EMAIL] MAIL_PASSWORD missing in .env — cannot send email to %s",
                mask_email(to_email),
            )
            return False, SMTP_NOT_CONFIGURED
        if not self.is_configured():
            logger.error(
                "[EMAIL] SMTP not fully configured — cannot send email to %s",
                mask_email(to_email),
            )
            return False, SMTP_NOT_CONFIGURED

        sender = current_app.config["MAIL_DEFAULT_SENDER"]
        username = (current_app.config.get("MAIL_USERNAME") or "").strip()
        # Keep display name, but force mailbox address = authenticated user (GoDaddy).
        if username and "<" not in str(sender) and str(sender).lower() != username.lower():
            sender = f"Joshi Tax Consultancy & Services <{username}>"
        elif username and "<" in str(sender) and username.lower() not in str(sender).lower():
            sender = f"Joshi Tax Consultancy & Services <{username}>"

        message = Message(
            subject=subject,
            recipients=[to_email],
            body=text_body or "Please view this message in an HTML-capable email client.",
            html=html_body,
            sender=sender,
        )
        if reply_to:
            message.reply_to = reply_to

        self._log_smtp_config()
        last_error: Exception | None = None
        attempts = max_attempts or SMTP_SEND_MAX_ATTEMPTS

        for attempt in range(1, attempts + 1):
            try:
                try:
                    # Prefer direct SMTP (SSL/587 fallbacks for VPS). Flask-Mail is backup.
                    self._send_message_direct(
                        message,
                        prefer_vps=prefer_vps,
                        timeout=timeout,
                    )
                except Exception as direct_exc:
                    logger.warning(
                        "[EMAIL] Direct SMTP send failed (attempt %s/%s): %s",
                        attempt,
                        attempts,
                        direct_exc,
                        exc_info=True,
                    )
                    if prefer_vps:
                        # Skip Flask-Mail on registration path — it lacks VPS SSL/port fallbacks.
                        raise
                    self._send_message(message)

                logger.info("[EMAIL] Email sent successfully to %s: %s", mask_email(to_email), subject)
                return True, None
            except smtplib.SMTPAuthenticationError as exc:
                logger.error(
                    "[EMAIL] SMTP authentication failed for %s: %s",
                    mask_email(current_app.config.get("MAIL_USERNAME")),
                    exc,
                    exc_info=True,
                )
                return False, SMTP_USER_MESSAGE
            except smtplib.SMTPException as exc:
                last_error = exc
                logger.error(
                    "[EMAIL] SMTP error sending to %s (attempt %s/%s): %s",
                    mask_email(to_email),
                    attempt,
                    attempts,
                    exc,
                    exc_info=True,
                )
                if attempt >= attempts or isinstance(exc, smtplib.SMTPAuthenticationError):
                    return False, SMTP_USER_MESSAGE
                if not self._should_retry(exc, attempt):
                    # Still retry once more for registration (prefer_vps) on generic SMTP errors.
                    if not prefer_vps:
                        return False, SMTP_USER_MESSAGE
            except TRANSIENT_SMTP_ERRORS as exc:
                last_error = exc
                logger.error(
                    "[EMAIL] SMTP connection error sending to %s (attempt %s/%s): %s",
                    mask_email(to_email),
                    attempt,
                    attempts,
                    exc,
                    exc_info=True,
                )
                if attempt >= attempts:
                    return False, SMTP_USER_MESSAGE
                if not prefer_vps and not self._should_retry(exc, attempt):
                    return False, SMTP_USER_MESSAGE
            except Exception as exc:
                logger.error(
                    "[EMAIL] Unexpected email error sending to %s: %s",
                    mask_email(to_email),
                    exc,
                    exc_info=True,
                )
                return False, SMTP_USER_MESSAGE

            time.sleep(SMTP_RETRY_DELAY_SECONDS)

        if last_error is not None:
            logger.error(
                "[EMAIL] SMTP send failed after %s attempts to %s: %s",
                attempts,
                mask_email(to_email),
                last_error,
                exc_info=True,
            )
        return False, SMTP_USER_MESSAGE

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
        return self.send_html(to_email, "Reset your Password", html, text)

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
