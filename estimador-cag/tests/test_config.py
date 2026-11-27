import pytest
from pydantic import ValidationError

from app.config import Settings, split_model_id


def _build(**overrides) -> Settings:
    values = {"LLM_MODEL": "anthropic/claude-haiku-4-5", "ANTHROPIC_API_KEY": "test"}
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_valid_configuration_is_accepted() -> None:
    settings = _build()

    assert settings.configured_models() == ["anthropic/claude-haiku-4-5"]
    assert settings.LLM_MAX_RETRIES == 0
    assert settings.LLM_MAX_CONCURRENCY == 8


def test_split_model_id() -> None:
    assert split_model_id("openai/gpt-4o-mini") == ("openai", "gpt-4o-mini")


@pytest.mark.parametrize("model", ["claude-haiku-4-5", "gemini/pro", "anthropic/"])
def test_model_without_supported_provider_is_rejected(model: str) -> None:
    with pytest.raises(ValidationError):
        _build(LLM_MODEL=model)


def test_missing_key_for_fallback_provider_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _build(LLM_FALLBACK_MODEL="openai/gpt-4o-mini", OPENAI_API_KEY=None)


def test_fallback_with_its_key_is_accepted() -> None:
    settings = _build(LLM_FALLBACK_MODEL="openai/gpt-4o-mini", OPENAI_API_KEY="test")

    assert settings.configured_models() == [
        "anthropic/claude-haiku-4-5",
        "openai/gpt-4o-mini",
    ]


@pytest.mark.parametrize(
    "field",
    [
        "LLM_CONNECT_TIMEOUT_S",
        "LLM_READ_TIMEOUT_S",
        "LLM_WRITE_TIMEOUT_S",
        "LLM_POOL_TIMEOUT_S",
    ],
)
def test_non_positive_timeout_is_rejected(field: str) -> None:
    with pytest.raises(ValidationError):
        _build(**{field: 0})


def test_negative_retries_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _build(LLM_MAX_RETRIES=-1)


def test_zero_concurrency_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _build(LLM_MAX_CONCURRENCY=0)
