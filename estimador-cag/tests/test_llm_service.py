import threading
from types import SimpleNamespace

import httpx
import litellm
import pytest
import structlog
from structlog.testing import capture_logs

from app.config import Settings
from app.services import llm_service
from app.services.llm_service import (
    LLMCapacityError,
    LLMConfigError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUpstreamError,
    reset_llm_state,
)

TRANSCRIPTION = "x" * 60


class FakeRouter:
    """Minimal stand-in for ``litellm.Router`` that records the call."""

    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    def completion(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def make_response(
    model: str = "claude-haiku-4-5",
    content: str = "## Estimación",
    prompt_tokens: int = 10,
    completion_tokens: int = 20,
) -> SimpleNamespace:
    return SimpleNamespace(
        model=model,
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


def make_settings(**overrides) -> Settings:
    values = {
        "LLM_MODEL": "anthropic/claude-haiku-4-5",
        "LLM_FALLBACK_MODEL": "openai/gpt-4o-mini",
        "ANTHROPIC_API_KEY": "anthropic-key",
        "OPENAI_API_KEY": "openai-key",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture(autouse=True)
def reset_state():
    reset_llm_state()
    yield
    reset_llm_state()


def test_model_list_is_built_from_settings() -> None:
    deployments = llm_service._build_model_list(make_settings())

    assert [item["model_name"] for item in deployments] == ["estimator", "estimator"]
    params = [item["litellm_params"] for item in deployments]
    assert [item["model"] for item in params] == [
        "anthropic/claude-haiku-4-5",
        "openai/gpt-4o-mini",
    ]
    assert [item["order"] for item in params] == [1, 2]
    assert [item["api_key"] for item in params] == ["anthropic-key", "openai-key"]
    assert all(isinstance(item["timeout"], httpx.Timeout) for item in params)
    assert params[0]["timeout"].read == 120


def test_router_is_a_lazy_singleton() -> None:
    first = llm_service._get_router()
    second = llm_service._get_router()

    assert first is second
    assert first.settings().cache_responses is False
    deployments = first.registry().all()
    assert [item["litellm_params"]["model"] for item in deployments] == [
        "anthropic/claude-haiku-4-5"
    ]


def test_router_falls_back_to_the_secondary_deployment(monkeypatch) -> None:
    monkeypatch.setattr(llm_service, "get_settings", lambda: make_settings())
    deployments = llm_service._build_model_list(make_settings())
    deployments[0]["litellm_params"]["mock_response"] = Exception("primary down")
    deployments[1]["litellm_params"]["mock_response"] = "hello from secondary"
    router = llm_service.Router(
        model_list=deployments, num_retries=0, cache_responses=False
    )
    monkeypatch.setattr(llm_service, "_get_router", lambda: router)

    result = llm_service.generate_estimation(TRANSCRIPTION)

    assert result["estimation"] == "hello from secondary"
    assert result["model"] == "gpt-4o-mini"
    assert result["provider"] == "openai"


def test_litellm_noise_and_telemetry_are_disabled() -> None:
    assert litellm.telemetry is False
    assert litellm.suppress_debug_info is True
    assert litellm.drop_params is True


def test_generate_estimation_uses_the_logical_model(monkeypatch) -> None:
    fake = FakeRouter(response=make_response())
    monkeypatch.setattr(llm_service, "_get_router", lambda: fake)

    result = llm_service.generate_estimation(TRANSCRIPTION)

    assert len(fake.calls) == 1
    assert fake.calls[0]["model"] == "estimator"
    messages = fake.calls[0]["messages"]
    assert messages[0]["role"] == "system"
    assert "senior software consultant" in messages[0]["content"]
    assert messages[1] == {"role": "user", "content": TRANSCRIPTION}
    assert result["estimation"] == "## Estimación"


def test_primary_response_resolves_its_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        llm_service, "_get_router", lambda: FakeRouter(response=make_response())
    )
    monkeypatch.setattr(
        llm_service.litellm, "completion_cost", lambda completion_response: 0.00011000000000000001
    )

    result = llm_service.generate_estimation(TRANSCRIPTION)

    assert result["model"] == "claude-haiku-4-5"
    assert result["provider"] == "anthropic"
    assert result["usage"] == {
        "input_tokens": 10,
        "output_tokens": 20,
        "total_tokens": 30,
        "cost_usd": 0.00011,
    }


def test_unknown_cost_is_exposed_as_null(monkeypatch) -> None:
    monkeypatch.setattr(
        llm_service, "_get_router", lambda: FakeRouter(response=make_response())
    )
    monkeypatch.setattr(
        llm_service.litellm, "completion_cost", lambda completion_response: None
    )

    result = llm_service.generate_estimation(TRANSCRIPTION)

    assert result["usage"]["cost_usd"] is None


def test_secondary_response_resolves_its_provider(monkeypatch) -> None:
    monkeypatch.setattr(llm_service, "get_settings", lambda: make_settings())
    monkeypatch.setattr(
        llm_service,
        "_get_router",
        lambda: FakeRouter(response=make_response(model="gpt-4o-mini")),
    )

    result = llm_service.generate_estimation(TRANSCRIPTION)

    assert result["model"] == "gpt-4o-mini"
    assert result["provider"] == "openai"


def test_dated_snapshot_resolves_its_provider(monkeypatch) -> None:
    monkeypatch.setattr(llm_service, "get_settings", lambda: make_settings())
    monkeypatch.setattr(
        llm_service,
        "_get_router",
        lambda: FakeRouter(response=make_response(model="gpt-4o-mini-2024-07-18")),
    )

    result = llm_service.generate_estimation(TRANSCRIPTION)

    assert result["model"] == "gpt-4o-mini-2024-07-18"
    assert result["provider"] == "openai"


def test_unknown_model_falls_back_to_the_primary_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        llm_service,
        "_get_router",
        lambda: FakeRouter(response=make_response(model="mystery-model")),
    )

    with capture_logs(
        processors=(structlog.contextvars.merge_contextvars,)
    ) as logs:
        result = llm_service.generate_estimation(TRANSCRIPTION)

    assert result["provider"] == "anthropic"
    assert any(event["event"] == "llm_provider_unresolved" for event in logs)


def test_success_log_carries_consumption_and_cost(monkeypatch) -> None:
    monkeypatch.setattr(
        llm_service, "_get_router", lambda: FakeRouter(response=make_response())
    )
    monkeypatch.setattr(
        llm_service.litellm,
        "completion_cost",
        lambda completion_response: 0.00042,
    )

    with capture_logs(
        processors=(structlog.contextvars.merge_contextvars,)
    ) as logs:
        llm_service.generate_estimation(TRANSCRIPTION)

    completed = next(event for event in logs if event["event"] == "estimation_completed")
    for key in (
        "duration_ms",
        "outcome",
        "provider",
        "model",
        "input_tokens",
        "output_tokens",
        "cost_usd",
    ):
        assert key in completed, key
    assert completed["outcome"] == "success"
    assert completed["cost_usd"] == pytest.approx(0.00042)


def test_unknown_cost_does_not_fail_the_request(monkeypatch) -> None:
    monkeypatch.setattr(
        llm_service, "_get_router", lambda: FakeRouter(response=make_response())
    )
    monkeypatch.setattr(
        llm_service.litellm, "completion_cost", lambda completion_response: None
    )

    with capture_logs(
        processors=(structlog.contextvars.merge_contextvars,)
    ) as logs:
        result = llm_service.generate_estimation(TRANSCRIPTION)

    assert result["estimation"] == "## Estimación"
    completed = next(event for event in logs if event["event"] == "estimation_completed")
    assert completed["cost_usd"] is None


def test_capacity_exhaustion_rejects_without_calling_the_provider(monkeypatch) -> None:
    semaphore = threading.BoundedSemaphore(1)
    semaphore.acquire()
    fake = FakeRouter(response=make_response())
    monkeypatch.setattr(llm_service, "_get_semaphore", lambda: semaphore)
    monkeypatch.setattr(llm_service, "_get_router", lambda: fake)

    with pytest.raises(LLMCapacityError):
        llm_service.generate_estimation(TRANSCRIPTION)

    assert fake.calls == []


def test_hole_is_released_after_a_failure(monkeypatch) -> None:
    semaphore = threading.BoundedSemaphore(1)
    monkeypatch.setattr(llm_service, "_get_semaphore", lambda: semaphore)
    monkeypatch.setattr(
        llm_service,
        "_get_router",
        lambda: FakeRouter(error=litellm.Timeout("slow", "claude-haiku-4-5", "anthropic")),
    )

    with pytest.raises(LLMTimeoutError):
        llm_service.generate_estimation(TRANSCRIPTION)

    assert semaphore.acquire(blocking=False) is True
    semaphore.release()


def test_failure_is_logged_with_full_detail(monkeypatch) -> None:
    monkeypatch.setattr(
        llm_service,
        "_get_router",
        lambda: FakeRouter(error=LLMUpstreamError("provider said SECRET-MARKER")),
    )

    with capture_logs(
        processors=(structlog.contextvars.merge_contextvars,)
    ) as logs:
        with pytest.raises(LLMUpstreamError):
            llm_service.generate_estimation(TRANSCRIPTION)

    failed = next(event for event in logs if event["event"] == "estimation_failed")
    assert "SECRET-MARKER" in failed["error"]
    assert failed["provider"] == "anthropic"
    assert failed["model"] == "claude-haiku-4-5"
    assert failed["outcome"] == "error:LLMUpstreamError"


@pytest.mark.parametrize(
    "error, expected",
    [
        (litellm.Timeout("slow", "m", "anthropic"), LLMTimeoutError),
        (httpx.ReadTimeout("slow"), LLMTimeoutError),
        (litellm.RateLimitError("429", "anthropic", "m"), LLMRateLimitError),
        (litellm.InternalServerError("500", "anthropic", "m"), LLMUpstreamError),
        (
            litellm.APIConnectionError(message="down", llm_provider="anthropic", model="m"),
            LLMUpstreamError,
        ),
        (litellm.AuthenticationError("401", "anthropic", "m"), LLMConfigError),
        (ValueError("unexpected"), LLMUpstreamError),
    ],
)
def test_error_translation(error: Exception, expected: type[Exception]) -> None:
    translated = llm_service._translate_error(error)

    assert isinstance(translated, expected)


def test_timeout_is_translated_before_upstream(monkeypatch) -> None:
    """``litellm.Timeout`` subclasses ``APIConnectionError``: order matters."""
    monkeypatch.setattr(
        llm_service,
        "_get_router",
        lambda: FakeRouter(error=litellm.Timeout("slow", "m", "anthropic")),
    )

    with pytest.raises(LLMTimeoutError):
        llm_service.generate_estimation(TRANSCRIPTION)
