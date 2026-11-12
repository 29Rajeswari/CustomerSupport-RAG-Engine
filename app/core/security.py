
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from pwdlib import PasswordHash

from app.config import settings


# ---------------------------------------------------------
# SECURITY CONFIGURATION
# ---------------------------------------------------------

JWT_ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 30

password_hasher = PasswordHash.recommended()

UserRole = Literal["admin", "customer"]


# ---------------------------------------------------------
# PASSWORD HASHING
# ---------------------------------------------------------

def hash_password(password: str) -> str:
    """
    Hash a password using the recommended Argon2 algorithm.
    Never store plaintext passwords.
    """
    return password_hasher.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    """
    Verify a plaintext password against its stored hash.
    """
    try:
        return password_hasher.verify(
            plain_password,
            hashed_password,
        )
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------
# JWT ACCESS TOKEN CREATION
# ---------------------------------------------------------

def create_access_token(
    subject: str | int,
    role: UserRole,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Generate a signed JWT access token.

    subject:
        Customer ID or administrator identifier.

    role:
        Either 'customer' or 'admin'.
    """

    now = datetime.now(timezone.utc)

    if expires_delta is None:
        expires_delta = timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )

    payload = {
        "sub": str(subject),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + expires_delta,
    }

    return jwt.encode(
        payload,
        settings.APP_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


# ---------------------------------------------------------
# JWT ACCESS TOKEN VALIDATION
# ---------------------------------------------------------

def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT access token.

    Checks:
    - Signature
    - Expiration
    - Token type
    - Subject
    - User role
    """

    payload = jwt.decode(
        token,
        settings.APP_SECRET_KEY,
        algorithms=[JWT_ALGORITHM],
    )

    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Invalid token type")

    subject = payload.get("sub")
    role = payload.get("role")

    if not isinstance(subject, str) or not subject:
        raise jwt.InvalidTokenError("Invalid token subject")

    if role not in ("admin", "customer"):
        raise jwt.InvalidTokenError("Invalid user role")

    return payload
