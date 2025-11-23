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
    
    @property
    def database_url(self) -> str:
        """Generate database URL from PostgreSQL connection details"""
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"


# Create settings instance
settings = Settings()
