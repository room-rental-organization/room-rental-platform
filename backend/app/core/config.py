from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from typing import Literal
from urllib.parse import urlsplit
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    database_url: str
    public_cache_ttl_seconds: float = Field(default=30, gt=0, le=300)
    public_cache_max_entries: int = Field(default=128, gt=0)
    public_cache_max_bytes: int = Field(default=4194304, gt=0)
    jwt_secret_key: SecretStr | None = None
    access_token_expire_minutes: int = Field(default=30, gt=0)
    auth_rate_limit_enabled: bool = True
    frontend_public_url: str = 'http://localhost:5173'
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_security: Literal['starttls', 'ssl', 'plain'] = 'starttls'
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_email: str | None = None
    email_verification_expire_minutes: int = Field(default=60, gt=0, le=1440)
    password_reset_expire_minutes: int = Field(default=30, gt=0, le=60)

    @field_validator('frontend_public_url')
    @classmethod
    def validate_frontend_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
                or (parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in {'localhost', '127.0.0.1'}))):
            raise ValueError('Use an HTTPS frontend URL, or HTTP localhost for development.')
        return value.rstrip('/')
    rental_interest_expiry_days: int = Field(default=90, gt=0)
    rental_interest_max_submissions_per_day: int = Field(default=20, gt=0)
    trust_verification_max_submissions_per_day: int = Field(default=5, gt=0)
    report_max_submissions_per_day: int = Field(default=10, gt=0)
    cors_allowed_origins: str = (
        "http://127.0.0.1:5173,http://localhost:5173,"
        "http://127.0.0.1:5174,http://localhost:5174"
    )
    cloudinary_cloud_name: str | None = None
    cloudinary_api_key: str | None = None
    cloudinary_api_secret: SecretStr | None = None
    whatsapp_access_token: SecretStr | None = None
    whatsapp_phone_number_id: str | None = None
    whatsapp_app_secret: SecretStr | None = None
    whatsapp_verify_token: SecretStr | None = None
    whatsapp_phone_encryption_key: SecretStr | None = None
    whatsapp_phone_lookup_key: SecretStr | None = None
    whatsapp_graph_api_version: str = "v23.0"
    whatsapp_template_language: str = "en_US"
    whatsapp_verification_template_name: str = "rental_phone_verification"
    whatsapp_message_template_name: str = "rental_message_notification"
    whatsapp_room_alert_template_name: str = "room_rental_new_listing_alert"
    groq_api_key: SecretStr | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    groq_max_tokens: int = Field(default=1024, gt=0)
    google_maps_server_api_key: SecretStr | None = None
    inception_api_key: SecretStr | None = None
    inception_base_url: str = "https://api.inceptionlabs.ai/v1"
    inception_model: str = "mercury-3"
    inception_max_tokens: int = Field(default=1024, gt=0)
    inception_max_retries: int = Field(default=2, ge=0)
    inception_backoff_base_seconds: float = Field(default=1, gt=0)
    inception_backoff_max_seconds: float = Field(default=8, gt=0)
    llm_call_timeout_seconds: float = Field(default=20, gt=0)

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
