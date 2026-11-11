
import smtplib
from email.message import EmailMessage

from app.config import settings


def send_otp_email(to_email: str, otp: str) -> bool:
    """Send an email verification OTP using Gmail SMTP."""

    if not all([
        settings.SMTP_HOST,
        settings.SMTP_PORT,
        settings.SMTP_USERNAME,
        settings.SMTP_PASSWORD,
        settings.SMTP_FROM_EMAIL,
    ]):
        raise RuntimeError("SMTP configuration is incomplete.")

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

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(message)

    return True



def send_password_reset_otp_email(to_email: str, otp: str) -> bool:
    """Send a password-reset OTP using Gmail SMTP."""

    if not all([
        settings.SMTP_HOST,
        settings.SMTP_PORT,
        settings.SMTP_USERNAME,
        settings.SMTP_PASSWORD,
        settings.SMTP_FROM_EMAIL,
    ]):
        raise RuntimeError("SMTP configuration is incomplete.")

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

    with smtplib.SMTP(
        settings.SMTP_HOST,
        settings.SMTP_PORT,
        timeout=20,
    ) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(message)

    return True

