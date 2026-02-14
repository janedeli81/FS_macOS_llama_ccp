# config.py
"""
Centralized configuration for the FastAPI backend.
All sensitive data loaded from environment variables.
"""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite:///./forensic_app.db"

    # JWT Authentication
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days

    # Stripe
    STRIPE_SECRET_KEY: str
    STRIPE_PUBLISHABLE_KEY: str
    STRIPE_WEBHOOK_SECRET: str

    # App Settings
    TRIAL_PERIOD_DAYS: int = 7
    CORS_ORIGINS: str = "http://localhost,http://localhost:8000"

    # Pricing (in cents)
    PACKAGE_10_PRICE: int = 999
    PACKAGE_50_PRICE: int = 3999
    PACKAGE_100_PRICE: int = 6999
    CURRENCY: str = "eur"

    class Config:
        env_file = ".env"
        case_sensitive = True

    def get_cors_origins(self) -> List[str]:
        """Parse CORS origins from comma-separated string"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]


# Global settings instance
settings = Settings()
