
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_customer
from app.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    hash_password,
    verify_password,
)
from app.models import (
    ActivityLog,
    Customer,
    PendingRegistration,
    PasswordResetOTP,
)
from app.db.session import get_db
from app.schemas.auth import (
    RegisterOTPRequest,
    VerifyRegistrationOTPRequest,
    CompleteRegistrationRequest,
    LoginRequest,
    ForgotPasswordOTPRequest,
    VerifyPasswordResetOTPRequest,
    ResetPasswordRequest,
    MessageResponse,
    TokenResponse,
    CustomerResponse,
)
from app.services.email_service import (
    send_otp_email,
    send_password_reset_otp_email,
)
from app.services.otp_service import (
    create_pending_registration,
    create_password_reset_otp,
    generate_otp,
    verify_registration_otp,
    verify_password_reset_otp,
    get_verified_password_reset,
)


router = APIRouter(prefix="/auth", tags=["Authentication"])


# ---------------------------------------------------------
# HELPER: INVALIDATE REGISTRATION OTP AFTER EMAIL FAILURE
# ---------------------------------------------------------

def invalidate_registration_otp(db: Session, email: str) -> None:
    pending = (
        db.query(PendingRegistration)
        .filter(PendingRegistration.email == email)
        .first()
    )

    if pending:
        pending.expires_at = datetime.now(timezone.utc)
        db.commit()


# ---------------------------------------------------------
# 1. REQUEST REGISTRATION OTP
# POST /auth/register/request-otp
# ---------------------------------------------------------

@router.post(
    "/register/request-otp",
    response_model=MessageResponse,
)
def request_registration_otp(
    request: RegisterOTPRequest,
    db: Session = Depends(get_db),
):
    existing_customer = (
        db.query(Customer)
        .filter(Customer.email == request.email)
        .first()
    )

    if existing_customer:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    existing_username = (
        db.query(Customer)
        .filter(Customer.username == request.username)
        .first()
    )

    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This username is already taken.",
        )

    username_pending = (
        db.query(PendingRegistration)
        .filter(
            PendingRegistration.username == request.username,
            PendingRegistration.email != request.email,
        )
        .first()
    )

    if username_pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This username is currently reserved.",
        )

    existing_pending = (
        db.query(PendingRegistration)
        .filter(PendingRegistration.email == request.email)
        .first()
    )

    if existing_pending and existing_pending.is_verified:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This email is already verified. "
                "Please complete registration."
            ),
        )

    otp = generate_otp()

    create_pending_registration(
        db=db,
        email=request.email,
        otp=otp,
        username=request.username,
    )

    try:
        send_otp_email(request.email, otp)

    except Exception as exc:
        invalidate_registration_otp(db, request.email)

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Unable to send verification email. "
                "Please try again after the cooldown."
            ),
        ) from exc

    return MessageResponse(
        message="Verification OTP sent successfully."
    )


# ---------------------------------------------------------
# 2. VERIFY REGISTRATION OTP
# POST /auth/register/verify-otp
# ---------------------------------------------------------

@router.post(
    "/register/verify-otp",
    response_model=MessageResponse,
)
def verify_registration(
    request: VerifyRegistrationOTPRequest,
    db: Session = Depends(get_db),
):
    pending = verify_registration_otp(
        db=db,
        email=request.email,
        otp=request.otp,
    )

    if not pending.username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Registration details are missing. "
                "Please request a new OTP."
            ),
        )

    return MessageResponse(
        message=(
            "Email verified successfully. "
            "You can now create your password and register."
        )
    )


# ---------------------------------------------------------
# 3. COMPLETE CUSTOMER REGISTRATION
# POST /auth/register/complete
# ---------------------------------------------------------

@router.post(
    "/register/complete",
    response_model=MessageResponse,
)
def complete_registration(
    request: CompleteRegistrationRequest,
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)

    pending = (
        db.query(PendingRegistration)
        .filter(PendingRegistration.email == request.email)
        .with_for_update()
        .first()
    )

    if pending is None or not pending.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please verify your email before registering.",
        )

    if pending.verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email verification has expired. Please verify again.",
        )

    verified_at = pending.verified_at

    if verified_at.tzinfo is None:
        verified_at = verified_at.replace(tzinfo=timezone.utc)

    if now - verified_at > timedelta(minutes=10):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Registration verification has expired. "
                "Please verify your email again."
            ),
        )

    if not pending.username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username is missing. Please restart registration.",
        )

    if db.query(Customer).filter(
        Customer.email == request.email
    ).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    if db.query(Customer).filter(
        Customer.username == pending.username
    ).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This username is already taken.",
        )

    customer = Customer(
        username=pending.username,
        full_name=pending.username,
        email=request.email,
        password_hash=hash_password(request.password),
        is_active=True,
        is_email_verified=True,
        email_verified_at=now,
    )

    try:
        db.add(customer)
        db.flush()

        db.add(
            ActivityLog(
                customer_id=customer.id,
                action="customer_registered",
                details="Customer completed email-verified registration.",
            )
        )

        db.delete(pending)
        db.commit()
        db.refresh(customer)

    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The email or username is already registered.",
        ) from exc

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to complete customer registration.",
        ) from exc

    return MessageResponse(
        message="Registration successful. You can now log in."
    )


# ---------------------------------------------------------
# 4. CUSTOMER LOGIN
# POST /auth/login
# ---------------------------------------------------------

@router.post(
    "/login",
    response_model=TokenResponse,
)
def login_customer(
    request: LoginRequest,
    db: Session = Depends(get_db),
):
    identifier = request.identifier

    if "@" in identifier:
        customer_filter = Customer.email == identifier
    else:
        customer_filter = Customer.username == identifier

    customer = (
        db.query(Customer)
        .filter(customer_filter)
        .first()
    )

    if (
        customer is None
        or not customer.password_hash
        or not verify_password(
            request.password,
            customer.password_hash,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/email or password.",
        )

    if not customer.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This customer account is inactive.",
        )

    if not customer.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in.",
        )

    token = create_access_token(
        subject=customer.id,
        role="customer",
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ---------------------------------------------------------
# 5. REQUEST PASSWORD RESET OTP
# POST /auth/forgot-password/request-otp
# ---------------------------------------------------------

@router.post(
    "/forgot-password/request-otp",
    response_model=MessageResponse,
)
def request_password_reset_otp(
    request: ForgotPasswordOTPRequest,
    db: Session = Depends(get_db),
):
    generic_message = (
        "If an eligible account exists, "
        "a password reset OTP has been sent."
    )

    customer = (
        db.query(Customer)
        .filter(Customer.email == request.email)
        .first()
    )

    # Do not reveal whether an email is registered.
    if (
        customer is None
        or not customer.is_active
        or not customer.is_email_verified
    ):
        return MessageResponse(message=generic_message)

    otp = generate_otp()

    create_password_reset_otp(
        db=db,
        customer_id=customer.id,
        otp=otp,
    )

    try:
        send_password_reset_otp_email(
            request.email,
            otp,
        )

    except Exception as exc:
        reset_record = (
            db.query(PasswordResetOTP)
            .filter(
                PasswordResetOTP.customer_id == customer.id
            )
            .first()
        )

        if reset_record:
            reset_record.expires_at = datetime.now(timezone.utc)
            db.commit()

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Unable to send the password reset email. "
                "Please try again after the cooldown."
            ),
        ) from exc

    return MessageResponse(message=generic_message)


# ---------------------------------------------------------
# 6. VERIFY PASSWORD RESET OTP
# POST /auth/forgot-password/verify-otp
# ---------------------------------------------------------

@router.post(
    "/forgot-password/verify-otp",
    response_model=MessageResponse,
)
def verify_password_reset(
    request: VerifyPasswordResetOTPRequest,
    db: Session = Depends(get_db),
):
    customer = (
        db.query(Customer)
        .filter(Customer.email == request.email)
        .first()
    )

    if (
        customer is None
        or not customer.is_active
        or not customer.is_email_verified
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid password reset request.",
        )

    verify_password_reset_otp(
        db=db,
        customer_id=customer.id,
        otp=request.otp,
    )

    return MessageResponse(
        message=(
            "OTP verified successfully. "
            "You can now create a new password."
        )
    )


# ---------------------------------------------------------
# 7. RESET PASSWORD
# POST /auth/forgot-password/reset
# ---------------------------------------------------------

@router.post(
    "/forgot-password/reset",
    response_model=MessageResponse,
)
def reset_customer_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    customer = (
        db.query(Customer)
        .filter(Customer.email == request.email)
        .with_for_update()
        .first()
    )

    if (
        customer is None
        or not customer.is_active
        or not customer.is_email_verified
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid password reset request.",
        )

    reset_record = get_verified_password_reset(
        db=db,
        customer_id=customer.id,
    )

    try:
        customer.password_hash = hash_password(
            request.new_password
        )

        db.add(
            ActivityLog(
                customer_id=customer.id,
                action="customer_password_reset",
                details="Customer successfully reset their password.",
            )
        )

        # The verified reset OTP is single-use.
        db.delete(reset_record)
        db.commit()

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to reset password.",
        ) from exc

    return MessageResponse(
        message=(
            "Password reset successful. "
            "Please log in using your new password."
        )
    )


# ---------------------------------------------------------
# 8. CURRENT CUSTOMER PROFILE
# GET /auth/me
# ---------------------------------------------------------

@router.get(
    "/me",
    response_model=CustomerResponse,
)
def get_my_profile(
    current_customer: Customer = Depends(get_current_customer),
):
    return current_customer
