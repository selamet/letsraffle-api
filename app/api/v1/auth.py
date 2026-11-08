"""
Authentication endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.models import get_db, User
from app.schemas import (
    UserCreate, UserLogin, TokenResponse, RefreshTokenRequest, ForgotPasswordRequest,
    ResetPasswordRequest, AppleSignInRequest, GoogleSignInRequest
)
from app.api.deps import get_current_user
from app.config import settings
from app.core import apple, google
from app.schemas.user import UserResponse
from app.models.draw import Draw
from app.models.device import Device
from app.core.security import create_access_token, create_refresh_token, decode_refresh_token, decode_access_token
from app.tasks.email_tasks import send_password_reset_email_task
from datetime import timedelta

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user and return access token with user data
    
    Args:
        user_data: User creation data
        db: Database session
        
    Returns:
        Access token and user data
    """
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    hashed_password = User.hash_password(user_data.password)
    new_user = User(
        email=user_data.email,
        password=hashed_password
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    access_token = create_access_token(data={"sub": new_user.email})
    refresh_token = create_refresh_token(data={"sub": new_user.email})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": new_user
    }


@router.post("/login", response_model=TokenResponse)
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """
    Login user and return access token with user data
    
    Args:
        user_data: User login credentials
        db: Database session
        
    Returns:
        Access token and user data
    """

    user = db.query(User).filter(User.email == user_data.email).first()

    if not user or not user.verify_password(user_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.email})
    refresh_token = create_refresh_token(data={"sub": user.email})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user
    }


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    token_data: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """
    Refresh access token using refresh token
    
    Args:
        token_data: Refresh token data
        db: Database session
        
    Returns:
        New access token, refresh token and user data
    """
    # Decode refresh token
    payload = decode_refresh_token(token_data.refresh_token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    email: str = payload.get("sub")
    
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user from email in token
    user = db.query(User).filter(User.email == email).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Generate new tokens (refresh token is validated by JWT signature, no DB check needed)
    access_token = create_access_token(data={"sub": user.email})
    refresh_token = create_refresh_token(data={"sub": user.email})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user
    }


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Request password reset email
    
    Args:
        request: Forgot password request with email
        db: Database session
    """
    user = db.query(User).filter(User.email == request.email).first()
    
    if not user:
        return {"message": "If email exists, password reset instructions have been sent."}
    
    reset_token = create_access_token(
        data={"sub": user.email, "type": "reset"},
        expires_delta=timedelta(hours=1)
    )
    
    send_password_reset_email_task.delay(user.email, reset_token, request.language)
    
    return {"message": "If email exists, password reset instructions have been sent."}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Reset password using token
    
    Args:
        request: Reset password request with token and new password
        db: Database session
    """
    payload = decode_access_token(request.token)
    
    if not payload or payload.get("type") != "reset":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token"
        )
    
    email = payload.get("sub")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid token"
        )
        
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
        
    user.password = User.hash_password(request.new_password)
    db.commit()
    
    return {"message": "Password has been reset successfully"}


def _token_response(user: User) -> dict:
    return {
        "access_token": create_access_token(data={"sub": user.email}),
        "refresh_token": create_refresh_token(data={"sub": user.email}),
        "token_type": "bearer",
        "user": user
    }


@router.post("/apple", response_model=TokenResponse)
async def sign_in_with_apple(request: AppleSignInRequest, db: Session = Depends(get_db)):
    """
    Sign in (or sign up) with an Apple identity token.

    - Existing Apple user (same `sub`) → signs in
    - Existing email/password user with the same email → links Apple to that account
    - Otherwise a new password-less account is created
    """
    try:
        identity = apple.verify_identity_token(request.identity_token)
    except apple.AppleTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Apple identity token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.apple_sub == identity.sub).first()

    if not user and identity.email:
        email = identity.email.lower()
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.apple_sub = identity.sub
        else:
            user = User(email=email, password=None, apple_sub=identity.sub)
            db.add(user)
        db.commit()
        db.refresh(user)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apple account has no email. Please share your email on first sign in."
        )

    return _token_response(user)


@router.post("/google", response_model=TokenResponse)
async def sign_in_with_google(request: GoogleSignInRequest, db: Session = Depends(get_db)):
    """
    Sign in (or sign up) with a Google ID token from the web (Google Identity Services) or iOS (GoogleSignIn).

    - Existing Google user (same `sub`) → signs in
    - Existing account with the same (Google-verified) email → links Google to it
    - Otherwise a new password-less account is created
    """
    if not settings.google_audiences:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured"
        )

    try:
        identity = google.verify_id_token(request.credential)
    except google.GoogleTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google ID token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.google_sub == identity.sub).first()

    if not user:
        email = identity.email.lower()
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.google_sub = identity.sub
        else:
            user = User(email=email, password=None, google_sub=identity.sub)
            db.add(user)
        db.commit()
        db.refresh(user)

    return _token_response(user)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the authenticated user"""
    return current_user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Permanently delete the authenticated account.

    Draws created by the user are kept for their participants but detached from the account.
    """
    db.query(Draw).filter(Draw.creator_id == current_user.id).update(
        {Draw.creator_id: None}, synchronize_session=False
    )
    db.query(Device).filter(Device.user_id == current_user.id).update(
        {Device.user_id: None}, synchronize_session=False
    )
    db.delete(current_user)
    db.commit()
