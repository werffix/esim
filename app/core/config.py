from functools import lru_cache
from typing import Optional
from pydantic import PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    APP_ENV: str = "production"
    APP_DEBUG: bool = False
    APP_SECRET_KEY: str
    APP_BASE_URL: str

    # Bot
    BOT_TOKEN: str
    BOT_WEBHOOK_PATH: str = "/webhook/bot"
    BOT_WEBHOOK_SECRET: str
    BOT_USERNAME: str = "q1esim_bot"

    # Database
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def SYNC_DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DB: int = 0

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # Nova eSIM API
    NOVA_API_BASE_URL: str = "https://api.novaesim.app"
    NOVA_API_KEY: str
    NOVA_API_SECRET: str
    NOVA_API_TIMEOUT: int = 30
    NOVA_API_RETRY_COUNT: int = 3

    # Platega
    PLATEGA_API_URL: str = "https://api.platega.io"
    PLATEGA_API_KEY: str
    PLATEGA_SECRET_KEY: str
    PLATEGA_WEBHOOK_PATH: str = "/webhook/payment"
    PLATEGA_SUCCESS_URL: str
    PLATEGA_FAIL_URL: str

    # Referral
    REFERRAL_PERCENT: float = 5.0  # percent of purchase

    # Markup
    DEFAULT_MARKUP_PERCENT: float = 20.0

    # Rate limiting
    RATE_LIMIT_MESSAGES: int = 30
    RATE_LIMIT_WINDOW: int = 60  # seconds

    # Cache TTL
    CACHE_COUNTRIES_TTL: int = 3600
    CACHE_PLANS_TTL: int = 1800
    CACHE_ESIM_STATUS_TTL: int = 300

    # Admin
    ADMIN_IDS: list[int] = []

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, int):
            return [v]
        if isinstance(v, (list, tuple)):
            return [int(x) for x in v]
        return v

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
