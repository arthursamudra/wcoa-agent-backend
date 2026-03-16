from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: str = Field(default="dev")
    LOG_LEVEL: str = Field(default="INFO")

    # watsonx.ai
    WATSONX_URL: str
    WATSONX_APIKEY: str
    WATSONX_PROJECT_ID: str
    WATSONX_MODEL_ID: str = Field(default="ibm/granite-4-h-small")
    WATSONX_VERIFY: bool = Field(default=True)
    WATSONX_MAX_RETRIES: int = Field(default=5)
    WATSONX_RETRY_DELAY_SECONDS: float = Field(default=0.5)

    # Chat defaults
    WCOA_CHAT_TEMPERATURE: float = Field(default=0.1)
    WCOA_CHAT_TOP_P: float = Field(default=0.9)
    WCOA_CHAT_MAX_TOKENS: int = Field(default=1200)
    WCOA_DATASET_PAYLOAD_CHAR_LIMIT: int = Field(default=120_000)

    # Postgres
    PG_HOST: str
    PG_PORT: int = Field(default=5432)
    PG_DB: str = Field(default="ibmclouddb")
    PG_USER: str
    PG_PASSWORD: str
    PG_SSLMODE: str = Field(default="verify-full")
    PG_SSLROOTCERT_PATH: str | None = Field(default=None)

    # COS (IBM COS SDK / S3-compatible HMAC auth)
    COS_ENDPOINT: str
    COS_BUCKET: str
    COS_ACCESS_KEY_ID: str
    COS_SECRET_ACCESS_KEY: str
    COS_PRESIGN_EXPIRES_SECONDS: int = Field(default=900)

    # Retention
    RAW_DELETE_AFTER_MINUTES: int = Field(default=15)
    CANONICAL_TTL_HOURS: int = Field(default=72)
    DEFAULT_TENANT_TTL_HOURS: int = Field(default=72)

    # Limits
    MAX_EXCEL_BYTES: int = Field(default=25_000_000)  # 25MB


settings = Settings()
