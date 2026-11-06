"""
User schemas for request/response validation
"""

from pydantic import BaseModel, EmailStr, ConfigDict
from datetime import datetime
from typing import Optional


class UserCreate(BaseModel):
    """Schema for user creation"""
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    """Schema for user login"""
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Schema for user response"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    email: EmailStr
    created_at: datetime
    updated_at: datetime
    has_apple: bool = False


class TokenResponse(BaseModel):
    """Schema for token response with user data"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request"""
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    """Schema for forgot password request"""
    email: EmailStr
    language: str = "tr"


class AppleSignInRequest(BaseModel):
    """Schema for Sign in with Apple; names are only sent on the first authorization"""
    identity_token: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class ResetPasswordRequest(BaseModel):
    """Schema for reset password request"""
    token: str
    new_password: str
