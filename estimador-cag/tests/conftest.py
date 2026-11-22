import os

import pytest

os.environ["ANTHROPIC_API_KEY"] = "test"
os.environ["LLM_PROVIDER"] = "anthropic"
os.environ["APP_ENV"] = "development"
os.environ["LOG_LEVEL"] = "INFO"


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Evita que la caché de Settings filtre el entorno entre tests."""
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
