"""
Security utilities for JWT authentication
"""

from datetime import datetime, timedelta
from typing import Optional
import jwt
from jwt.exceptions import InvalidTokenError
from app.config import settings

ACCESS_TOKEN_TYPE = "access"
RESET_TOKEN_TYPE = "reset"
RESET_TOKEN_EXPIRE_HOURS = 1


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token
    
    Args:
        data: Data to encode in the token
        expires_delta: Optional expiration time delta
        
    Returns:
        Encoded JWT token
    """
    from datetime import timezone
    
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    
    to_encode.update({"exp": expire, "type": ACCESS_TOKEN_TYPE})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode and verify a JWT access token
    
    Every token the API issues is signed with the same key, so the type is what
    keeps a refresh, reset, participant or unsubscribe token from authenticating
    a request.
    
    Args:
        token: JWT token to decode
        
    Returns:
        Decoded token data or None if invalid or of another type
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except InvalidTokenError:
        return None
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        return None
    return payload


def create_reset_token(email: str) -> str:
    """Create the short-lived token carried by the password reset link."""
    from datetime import timezone

    payload = {
        "sub": email,
        "type": RESET_TOKEN_TYPE,
        "exp": datetime.now(timezone.utc) + timedelta(hours=RESET_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_reset_token(token: str) -> Optional[dict]:
    """Decode a password reset token; returns None if invalid or of another type."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except InvalidTokenError:
        return None
    if payload.get("type") != RESET_TOKEN_TYPE:
        return None
    return payload


def create_refresh_token(data: dict) -> str:
    """
    Create a JWT refresh token with longer expiration
    
    Args:
        data: Data to encode in the token
        
    Returns:
        Encoded JWT refresh token
    """
    from datetime import timezone
    
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    
    return encoded_jwt


def decode_refresh_token(token: str) -> Optional[dict]:
    """
    Decode and verify a JWT refresh token
    
    Args:
        token: JWT refresh token to decode
        
    Returns:
        Decoded token data or None if invalid
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        # Check if it's a refresh token
        if payload.get("type") != "refresh":
            return None
        return payload
    except InvalidTokenError:
        return None


PARTICIPANT_TOKEN_TYPE = "participant"
PARTICIPANT_TOKEN_EXPIRE_DAYS = 365


def create_participant_token(participant_id: int, draw_id: int) -> str:
    """
    Create a long-lived token that identifies an anonymous participant.

    Handed to the device that joined a draw so it can later read its own match
    and register for push notifications without an account.
    """
    from datetime import timezone

    payload = {
        "sub": f"participant:{participant_id}",
        "pid": participant_id,
        "did": draw_id,
        "type": PARTICIPANT_TOKEN_TYPE,
        "exp": datetime.now(timezone.utc) + timedelta(days=PARTICIPANT_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_participant_token(token: str) -> Optional[dict]:
    """Decode a participant token; returns None if invalid or of another type."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except InvalidTokenError:
        return None
    if payload.get("type") != PARTICIPANT_TOKEN_TYPE or not isinstance(payload.get("pid"), int):
        return None
    return payload


UNSUBSCRIBE_TOKEN_TYPE = "unsubscribe"


def create_unsubscribe_token(email: str, language: str = "TR") -> str:
    """
    Create the token carried by the unsubscribe link of announcement e-mails.

    It never expires: an old e-mail must still be able to opt its recipient out.
    """
    payload = {
        "sub": email.strip().lower(),
        "lang": "en" if (language or "").upper() == "EN" else "tr",
        "type": UNSUBSCRIBE_TOKEN_TYPE,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_unsubscribe_token(token: str) -> Optional[dict]:
    """Decode an unsubscribe token into {"email", "lang"}; None if invalid or of another type."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except InvalidTokenError:
        return None
    email = payload.get("sub")
    if payload.get("type") != UNSUBSCRIBE_TOKEN_TYPE or not isinstance(email, str) or "@" not in email:
        return None
    return {"email": email, "lang": "en" if payload.get("lang") == "en" else "tr"}
