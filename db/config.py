"""
Configuration and Environment Variable Management.
Loads environment variables from .env using pydantic-settings.
"""
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Razorpay Settings
    RAZORPAY_KEY_ID: str = "rzp_test_placeholder"
    RAZORPAY_KEY_SECRET: str = "placeholder_secret"
    RAZORPAY_WEBHOOK_SECRET: str = "placeholder_webhook_secret"

    # Supabase Settings
    SUPABASE_URL: str = "https://placeholder.supabase.co"
    SUPABASE_KEY: str = "placeholder_supabase_key"
    USE_LOCAL_DB: bool = False

    # SMTP / Email Nudge Settings (Phase 3)
    SMTP_HOST: str = "smtp.example.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: str = "recovery@merchant.com"
    SMTP_USE_TLS: bool = True

    # Compliance Guardrail Settings (Phase 3)
    DND_START_HOUR: int = 20  # 8:00 PM (20:00)
    DND_END_HOUR: int = 9     # 9:00 AM (09:00)
    DND_TIMEZONE: str = "Asia/Kolkata"  # Default Indian Standard Time
    MAX_LIFETIME_CONTACT_ATTEMPTS: int = 3  # Max 3 total contact touches across subscription lifecycle

    # Server Settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
