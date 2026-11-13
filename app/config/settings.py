"""
Application configuration settings
Loads environment variables from .env file
"""

from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    model_config = ConfigDict(env_file=".env", case_sensitive=False, extra="ignore")
    
    # Application Settings
    app_name: str = "Santa's Draw API"
    app_version: str = "1.0.0"
    debug: bool = True
    api_version: str = "v1"
    
    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    
    # CORS Settings
    cors_origins: List[str] = ["*"]
    frontend_url: str = "http://localhost:5173"
    # Public base URL of this API; used for links in e-mails that point back at the API (unsubscribe).
    api_url: str = "http://localhost:8000"
    app_store_url: str = "https://apps.apple.com/app/id6834004682"
    
    # PostgreSQL Connection Details
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "santas_draw"
    
    # Database Configuration
    database_echo: bool = False
    database_pool_size: int = 10
    database_max_overflow: int = 20
    
    # JWT Configuration
    secret_key: str = "your-secret-key-change-this-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 90
    refresh_token_expire_days: int = 30
    
    # Sentry Configuration (Optional - only DSN from .env)
    sentry_dsn: Optional[str] = None

    # Sign in with Apple (iOS bundle identifier used as token audience)
    apple_bundle_id: str = "com.letsraffle.ios"
    # Web Services ID used by the Apple JS popup on letsraffle.co; web Apple sign-in is off when unset.
    apple_services_id: Optional[str] = None
    # Sign in with Apple key (.p8), used to revoke a user's Apple tokens when the account is
    # deleted. Token exchange and revocation are skipped when unset.
    apple_team_id: Optional[str] = None
    apple_signin_key_id: Optional[str] = None
    apple_signin_key: Optional[str] = None  # .p8 contents (PEM); "\\n" escapes are accepted

    @property
    def apple_signin_team_id(self) -> Optional[str]:
        return self.apple_team_id or self.apns_team_id

    # Sign in with Google: web client ID (Google Identity Services on letsraffle.co) and iOS client
    # ID (GoogleSignIn SDK). Tokens from either are accepted; Google sign-in is off when both are unset.
    google_client_id: Optional[str] = None
    google_ios_client_id: Optional[str] = None

    @property
    def google_audiences(self) -> list[str]:
        return [aud for aud in (self.google_client_id, self.google_ios_client_id) if aud]

    # APNs push notifications (token based auth). Push is disabled when unset.
    apns_key_id: Optional[str] = None
    apns_team_id: Optional[str] = None
    apns_key: Optional[str] = None  # .p8 contents (PEM); "\\n" escapes are accepted
    apns_key_path: Optional[str] = None
    apns_topic: str = "com.letsraffle.ios"
    apns_use_sandbox: bool = True
    
    # AWS SES Configuration
    aws_region: str = "us-east-1"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    ses_from_email: str = "noreply@example.com"
    
    @property
    def database_url(self) -> str:
        """Generate database URL from PostgreSQL connection details"""
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"


# Create settings instance
settings = Settings()
