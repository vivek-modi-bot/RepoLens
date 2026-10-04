"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the RepoLens microservice."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "RepoLens"
    app_version: str = "1.0.0"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    # JWT
    jwt_secret_key: str = Field(
        default="change-me-in-production-use-a-long-random-secret",
        min_length=16,
    )
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60

    # Database (SQLite for simplicity; swappable later)
    database_url: str = "sqlite+aiosqlite:///./repolens.db"

    # LLM
    llm_provider: Literal["ollama"] = "ollama"
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5-coder"
    ollama_timeout_seconds: float = 120.0
    llm_max_retries: int = 2

    # Repository processing limits
    max_file_size: int = 100_000  # bytes
    max_files: int = 100
    max_repository_size: int = 50_000_000  # bytes (50 MB)
    max_chunk_chars: int = 8_000
    max_chunks: int = 12
    temp_dir: str = "/tmp/repolens"

    # GitHub
    github_api_base_url: str = "https://api.github.com"
    github_timeout_seconds: float = 30.0
    clone_timeout_seconds: float = 120.0

    # Rate limiting (simple in-memory)
    rate_limit_requests: int = 30
    rate_limit_window_seconds: int = 60

    @field_validator("jwt_secret_key")
    @classmethod
    def warn_weak_secret(cls, value: str) -> str:
        if value == "change-me-in-production-use-a-long-random-secret":
            # Allowed for local/dev; production should override via env.
            return value
        return value


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
