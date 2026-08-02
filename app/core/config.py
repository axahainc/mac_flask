"""
Central app configuration, loaded from environment variables (.env).
Never hardcode secrets — this file only defines *where* they come from.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENV: str = "development"
    SECRET_KEY: str
    DATABASE_URL: str
    REDIS_URL: str

    PAYSTACK_SECRET_KEY: str = ""
    PAYSTACK_PUBLIC_KEY: str = ""

    VTPASS_BASE_URL: str = ""
    VTPASS_API_KEY: str = ""
    VTPASS_SECRET_KEY: str = ""
    VTPASS_PUBLIC_KEY: str = ""

    RELOADLY_BASE_URL: str = ""
    RELOADLY_CLIENT_ID: str = ""
    RELOADLY_CLIENT_SECRET: str = ""

    WEBHOOK_SIGNING_SECRET: str = ""


settings = Settings()
