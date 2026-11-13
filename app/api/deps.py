"""
Common dependencies for API endpoints
"""

from typing import Optional
from fastapi import Depends, HTTPException, status, Security
from sqlalchemy.orm import Session
from app.models import User, get_db
from app.core.security import decode_access_token
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current authenticated user from JWT token
    
    Args:
        token: JWT access token
        db: Database session
        
    Returns:
        Current authenticated user
    """
    payload = decode_access_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    email: str = payload.get("sub")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user


def get_current_user_optional(
    token: Optional[str] = Security(oauth2_scheme_optional),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Get current authenticated user from JWT token (optional).
    Returns None if user is not authenticated.
    
    Args:
        token: JWT access token (optional)
        db: Database session
        
    Returns:
        Current authenticated user or None
    """
    if not token:
        return None
    
    try:
        payload = decode_access_token(token)

        if not payload:
            return None
        
        email: str = payload.get("sub")

        if not email:
            return None
        
        user = db.query(User).filter(User.email == email).first()

        return user

    except Exception:
        return None

