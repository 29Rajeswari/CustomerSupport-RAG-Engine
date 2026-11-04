
from datetime import datetime, timedelta, timezone
import secrets

from fastapi import HTTPException, status
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.db.models import PendingRegistration, PasswordResetOTP


# ---------------------------------------------------------
# OTP CONFIGURATION
# ---------------------------------------------------------

OTP_EXPIRY_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_VERIFICATION_WINDOW_MINUTES = 10

otp_hasher = PasswordHash.recommended()


# ---------------------------------------------------------
# DATETIME HELPER
# ---------------------------------------------------------

def ensure_utc(value: datetime) -> datetime:
    """Ensure a database datetime is timezone-aware."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


# ---------------------------------------------------------
# OTP GENERATION AND HASHING
# ---------------------------------------------------------

def generate_otp() -> str:
    """Generate a cryptographically secure six-digit OTP."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(otp: str) -> str:
    return otp_hasher.hash(otp)


def verify_otp_hash(otp: str, otp_hash: str) -> bool:
    try:
        return otp_hasher.verify(otp, otp_hash)
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------
# RESEND COOLDOWN
# ---------------------------------------------------------

def check_resend_cooldown(last_sent_at: datetime | None) -> None:
    if last_sent_at is None:
        return

    now = datetime.now(timezone.utc)
    last_sent = ensure_utc(last_sent_at)

    elapsed = (now - last_sent).total_seconds()

    if elapsed < OTP_RESEND_COOLDOWN_SECONDS:
        remaining = int(OTP_RESEND_COOLDOWN_SECONDS - elapsed) + 1

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {remaining} seconds before requesting another OTP.",
        )


# ---------------------------------------------------------
# REGISTRATION OTP CREATION
# ---------------------------------------------------------

def create_pending_registration(
    db: Session,
    email: str,
    otp: str,
    username: str | None = None,
) -> PendingRegistration:

    now = datetime.now(timezone.utc)

    pending = (
        db.query(PendingRegistration)
        .filter(PendingRegistration.email == email)
        .with_for_update()
        .first()
    )

    if pending is not None:

        if pending.is_verified:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This email has already been verified. Please complete registration.",
            )

        check_resend_cooldown(pending.last_sent_at)

        pending.username = username or pending.username
        pending.otp_hash = hash_otp(otp)
        pending.expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)
        pending.attempt_count = 0
        pending.is_verified = False
        pending.verified_at = None
        pending.last_sent_at = now

    else:
        pending = PendingRegistration(
            username=username,
            email=email,
            otp_hash=hash_otp(otp),
            expires_at=now + timedelta(minutes=OTP_EXPIRY_MINUTES),
            attempt_count=0,
            is_verified=False,
            verified_at=None,
            last_sent_at=now,
        )
        db.add(pending)

    db.commit()
    db.refresh(pending)

    return pending


# ---------------------------------------------------------
# REGISTRATION OTP VERIFICATION
# ---------------------------------------------------------

def verify_registration_otp(
    db: Session,
    email: str,
    otp: str,
) -> PendingRegistration:

    pending = (
        db.query(PendingRegistration)
        .filter(PendingRegistration.email == email)
        .with_for_update()
        .first()
    )

    if pending is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending registration found. Request an OTP first.",
        )

    if pending.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email has already been verified.",
        )

    now = datetime.now(timezone.utc)

    if ensure_utc(pending.expires_at) <= now:
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired. Request a new OTP.",
        )

    if pending.attempt_count >= OTP_MAX_ATTEMPTS:
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum OTP attempts reached. Request a new OTP after the cooldown.",
        )

    if not verify_otp_hash(otp, pending.otp_hash):
        pending.attempt_count += 1
        db.commit()

        if pending.attempt_count >= OTP_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Maximum OTP attempts reached. Request a new OTP after the cooldown.",
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect OTP.",
        )

    pending.is_verified = True
    pending.verified_at = now

    db.commit()
    db.refresh(pending)

    return pending


# ---------------------------------------------------------
# PASSWORD RESET OTP CREATION
# ---------------------------------------------------------

def create_password_reset_otp(
    db: Session,
    customer_id: int,
    otp: str,
) -> PasswordResetOTP:

    now = datetime.now(timezone.utc)

    reset_record = (
        db.query(PasswordResetOTP)
        .filter(PasswordResetOTP.customer_id == customer_id)
        .with_for_update()
        .first()
    )

    if reset_record is not None:
        check_resend_cooldown(reset_record.last_sent_at)

        reset_record.otp_hash = hash_otp(otp)
        reset_record.expires_at = now + timedelta(
            minutes=OTP_EXPIRY_MINUTES
        )
        reset_record.attempt_count = 0
        reset_record.is_verified = False
        reset_record.verified_at = None
        reset_record.last_sent_at = now

    else:
        reset_record = PasswordResetOTP(
            customer_id=customer_id,
            otp_hash=hash_otp(otp),
            expires_at=now + timedelta(minutes=OTP_EXPIRY_MINUTES),
            attempt_count=0,
            is_verified=False,
            verified_at=None,
            last_sent_at=now,
        )
        db.add(reset_record)

    db.commit()
    db.refresh(reset_record)

    return reset_record


# ---------------------------------------------------------
# PASSWORD RESET OTP VERIFICATION
# ---------------------------------------------------------

def verify_password_reset_otp(
    db: Session,
    customer_id: int,
    otp: str,
) -> PasswordResetOTP:

    reset_record = (
        db.query(PasswordResetOTP)
        .filter(PasswordResetOTP.customer_id == customer_id)
        .with_for_update()
        .first()
    )

    if reset_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No password reset request found. Request a new OTP.",
        )

    if reset_record.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This OTP has already been verified.",
        )

    now = datetime.now(timezone.utc)

    if ensure_utc(reset_record.expires_at) <= now:
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired. Request a new OTP.",
        )

    if reset_record.attempt_count >= OTP_MAX_ATTEMPTS:
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum OTP attempts reached. Request a new OTP after the cooldown.",
        )

    if not verify_otp_hash(otp, reset_record.otp_hash):
        reset_record.attempt_count += 1
        db.commit()

        if reset_record.attempt_count >= OTP_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Maximum OTP attempts reached. Request a new OTP after the cooldown.",
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect OTP.",
        )

    reset_record.is_verified = True
    reset_record.verified_at = now

    db.commit()
    db.refresh(reset_record)

    return reset_record


# ---------------------------------------------------------
# CHECK VERIFIED PASSWORD RESET
# ---------------------------------------------------------

def get_verified_password_reset(
    db: Session,
    customer_id: int,
) -> PasswordResetOTP:

    reset_record = (
        db.query(PasswordResetOTP)
        .filter(
            PasswordResetOTP.customer_id == customer_id,
            PasswordResetOTP.is_verified.is_(True),
        )
        .with_for_update()
        .first()
    )

    if reset_record is None or reset_record.verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please verify your password reset OTP first.",
        )

    now = datetime.now(timezone.utc)
    expires_at = ensure_utc(reset_record.expires_at)
    verified_at = ensure_utc(reset_record.verified_at)

    if (
        expires_at <= now
        or now - verified_at > timedelta(
            minutes=OTP_VERIFICATION_WINDOW_MINUTES
        )
    ):
        db.delete(reset_record)
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset verification has expired. Request a new OTP.",
        )

    return reset_record


# ---------------------------------------------------------
# CONSUME PASSWORD RESET OTP
# ---------------------------------------------------------

def consume_password_reset_otp(
    db: Session,
    reset_record: PasswordResetOTP,
) -> None:
    """Delete a verified OTP after a successful password reset."""
    db.delete(reset_record)
    db.commit()
