from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration supplied through environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Document Search Service"
    environment: str = "local"
    database_url: str = "postgresql+asyncpg://documents:documents@localhost:5432/documents"
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index: str = "documents"


@lru_cache
def get_settings() -> Settings:
    return Settings()
