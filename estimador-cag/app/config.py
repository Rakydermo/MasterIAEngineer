from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SUPPORTED_PROVIDERS = ("openai", "anthropic")


def split_model_id(model: str) -> tuple[str, str]:
    """Split a provider-prefixed model id into ``(provider, model name)``."""
    provider, _, name = model.partition("/")
    return provider, name


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None

    LLM_MODEL: str = "anthropic/claude-haiku-4-5"
    LLM_FALLBACK_MODEL: str | None = None

    LLM_CONNECT_TIMEOUT_S: float = Field(default=5, gt=0)
    LLM_READ_TIMEOUT_S: float = Field(default=120, gt=0)
    LLM_WRITE_TIMEOUT_S: float = Field(default=10, gt=0)
    LLM_POOL_TIMEOUT_S: float = Field(default=5, gt=0)
    LLM_MAX_RETRIES: int = Field(default=0, ge=0)
    LLM_MAX_CONCURRENCY: int = Field(default=8, gt=0)

    APP_ENV: Literal["development", "staging", "production"] = "development"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "DEBUG"

    @model_validator(mode="after")
    def validate_llm_configuration(self) -> "Settings":
        """Ensure every configured model has a supported provider and its API key."""
        models = [self.LLM_MODEL]
        if self.LLM_FALLBACK_MODEL:
            models.append(self.LLM_FALLBACK_MODEL)

        providers: set[str] = set()
        for model in models:
            provider, name = split_model_id(model)
            if not name or provider not in SUPPORTED_PROVIDERS:
                raise ValueError(
                    f"LLM model '{model}' must be prefixed with a supported provider "
                    f"({', '.join(SUPPORTED_PROVIDERS)}), e.g. 'anthropic/claude-haiku-4-5'"
                )
            providers.add(provider)

        for provider in sorted(providers):
            key = self.ANTHROPIC_API_KEY if provider == "anthropic" else self.OPENAI_API_KEY
            if not key:
                raise ValueError(
                    f"{provider.upper()}_API_KEY is required for a model with the "
                    f"'{provider}/' prefix"
                )
        return self

    def configured_models(self) -> list[str]:
        """Return the provider-prefixed models configured for this process."""
        models = [self.LLM_MODEL]
        if self.LLM_FALLBACK_MODEL:
            models.append(self.LLM_FALLBACK_MODEL)
        return models


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings (singleton)."""
    return Settings()
