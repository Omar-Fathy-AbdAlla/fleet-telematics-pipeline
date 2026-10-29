"""Reads backend/.env once. Every other module imports `settings` from here (single source of config)."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8")

    snowflake_api_account: str
    snowflake_api_user: str
    snowflake_api_password: str
    snowflake_api_database: str
    # Optional: empty in .env means "use the Snowflake user's defaults"
    snowflake_api_role: str | None = None
    snowflake_api_warehouse: str | None = None
    snowflake_api_schema: str | None = None

    api_cors_origins: str = "http://localhost:5173"

    # Live stream (Kafka silver topics). STREAM_HISTORY_MINUTES: read back this much on start, drop older rows.
    kafka_bootstrap_servers: str
    kafka_telemetry_topic: str
    kafka_reefer_topic: str
    stream_history_minutes: int = 60

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]


settings = Settings()
