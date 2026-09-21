from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from config import Settings


logger = logging.getLogger("login_microservice.email")


def send_verification_email(settings: Settings, to_email: str, verification_url: str) -> None:
    """
    Decoupled from auth_service on purpose: no SMTP credentials are
    hard-coded here, everything comes from Settings (env vars), and the
    caller never has to know whether mail is actually enabled.

    Never raises: a failed/disabled send must not roll back the user that
    was already created, so any SMTP error is only logged.
    """
    if not settings.mail_enabled:
        logger.info("MAIL_ENABLED=false: verification email not sent (development mode).")
        return

    message = EmailMessage()
    message["Subject"] = "Verify your email address"
    message["From"] = settings.mail_from
    message["To"] = to_email
    message.set_content(
        "Thanks for registering. Verify your email by visiting the "
        f"following link:\n\n{verification_url}\n\n"
        "If you did not request this account, you can ignore this message."
    )

    try:
        with smtplib.SMTP(settings.mail_host, settings.mail_port, timeout=10) as smtp:
            if settings.mail_use_tls:
                smtp.starttls()
            if settings.mail_username and settings.mail_password:
                smtp.login(settings.mail_username, settings.mail_password)
            smtp.send_message(message)
    except Exception:
        # Never log the token/URL contents here beyond what the caller
        # already logs explicitly in dev mode; this is strictly an
        # operational failure log (SMTP host/port, no secrets).
        logger.exception("Failed to send verification email to %s", to_email)
