
import logging
import smtplib
import ssl

from email.message import EmailMessage

from app.core.config import settings


logger = logging.getLogger(__name__)


def _validate_smtp_configuration() -> None:
    """Validate SMTP settings before attempting delivery."""

    required_settings = {
        "SMTP_HOST": settings.SMTP_HOST,
        "SMTP_PORT": settings.SMTP_PORT,
        "SMTP_USERNAME": settings.SMTP_USERNAME,
        "SMTP_PASSWORD": settings.SMTP_PASSWORD,
        "SMTP_FROM_EMAIL": settings.SMTP_FROM_EMAIL,
    }

    missing = [
        name
        for name, value in required_settings.items()
        if not value
    ]

    if missing:
        raise RuntimeError(
            f"SMTP configuration is incomplete. Missing: {', '.join(missing)}"
        )


def _send_email(message: EmailMessage) -> None:
    """Send an email using authenticated Gmail SMTP."""

    _validate_smtp_configuration()

    context = ssl.create_default_context()

    try:
        with smtplib.SMTP(
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            timeout=20,
        ) as server:

            server.ehlo()

            server.starttls(context=context)

            server.ehlo()

            server.login(
                settings.SMTP_USERNAME,
                settings.SMTP_PASSWORD,
            )

            server.send_message(message)

    except Exception:
        logger.exception("SMTP email delivery failed.")
        raise


def send_otp_email(to_email: str, otp: str) -> bool:
    """Send an email verification OTP."""

    message = EmailMessage()

    message["Subject"] = "Verify Your Email - E-commerce Support"
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = to_email

    message.set_content(
        f"""
Hello,

Thank you for registering with our e-commerce platform.

Your email verification OTP is: {otp}

This OTP is valid for 5 minutes.

Please do not share this OTP with anyone.

If you did not request this verification, please ignore this email.

Regards,
E-commerce Support Team
"""
    )

    _send_email(message)

    return True


def send_password_reset_otp_email(
    to_email: str,
    otp: str,
) -> bool:
    """Send a password-reset OTP."""

    message = EmailMessage()

    message["Subject"] = "Password Reset OTP - E-commerce Support"
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = to_email

    message.set_content(
        f"""
Hello,

We received a request to reset your e-commerce account password.

Your password reset OTP is: {otp}

This OTP is valid for 5 minutes.

Do not share this OTP with anyone.

If you did not request a password reset, please ignore this email.

Regards,
E-commerce Support Team
"""
    )

    _send_email(message)

    return True
