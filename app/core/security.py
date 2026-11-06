"""
Security utilities for JWT authentication
"""

from datetime import datetime, timedelta
from typing import Optional
import jwt
from jwt.exceptions import InvalidTokenError
from app.config import settings


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
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode and verify a JWT access token
    
    Args:
        token: JWT token to decode
        
    Returns:
        Decoded token data or None if invalid
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except InvalidTokenError:
        return None


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
