"""
User model
"""

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from passlib.context import CryptContext
from app.models.base import BaseModel

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class User(BaseModel):
    """User model with email and password"""
    
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    # Nullable: accounts created with Sign in with Apple have no password.
    password = Column(String(255), nullable=True)
    apple_sub = Column(String(255), unique=True, index=True, nullable=True)
    google_sub = Column(String(255), unique=True, index=True, nullable=True)
    # Kept only to revoke the user's Apple tokens when the account is deleted. It is useless
    # without the Sign in with Apple key, which never leaves the server environment.
    apple_refresh_token = Column(String(1024), nullable=True)
    # The client the refresh token belongs to (iOS bundle id or web Services ID).
    apple_client_id = Column(String(255), nullable=True)

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password"""
        return pwd_context.hash(password)
    
    def verify_password(self, password: str) -> bool:
        """Verify a password against the stored hash"""
        if not self.password:
            return False
        return pwd_context.verify(password, self.password)

    @property
    def has_apple(self) -> bool:
        """Whether the account is linked with Sign in with Apple"""
        return self.apple_sub is not None

    @property
    def has_google(self) -> bool:
        """Whether the account is linked with Sign in with Google"""
        return self.google_sub is not None
