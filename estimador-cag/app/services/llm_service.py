import threading
import time
from typing import Any

import httpx
import litellm
import structlog
from litellm import Router
from litellm.router import RetryPolicy

from app.config import Settings, get_settings, split_model_id
from app.context.examples import ESTIMATION_EXAMPLES, format_examples_for_prompt

litellm.telemetry = False
litellm.suppress_debug_info = True
litellm.drop_params = True

log = structlog.get_logger()

MODEL_ALIAS = "estimator"
MAX_TOKENS = 4000

_state_lock = threading.Lock()
_router: Router | None = None
_semaphore: threading.BoundedSemaphore | None = None


class LLMServiceError(Exception):
    """Base class for every failure of the LLM layer."""


class LLMTimeoutError(LLMServiceError):
    """The provider did not answer within the configured budget."""


class LLMRateLimitError(LLMServiceError):
    """The provider rejected the call due to rate limiting."""


class LLMUpstreamError(LLMServiceError):
    """The provider failed or could not be reached."""


class LLMConfigError(LLMServiceError):
    """Credentials or request configuration were rejected."""


class LLMCapacityError(LLMServiceError):
    """The local concurrency limit is exhausted."""


def build_system_prompt() -> str:
    """Construct the system prompt with role definition and reference examples."""
    examples_text = format_examples_for_prompt(ESTIMATION_EXAMPLES)
    return (
        "You are a senior software consultant with 15+ years of experience in project "
        "estimation. Your task is to produce a detailed software project estimation based "
        "on a meeting transcription provided by the user.\n\n"
        "Below are reference estimations from previous projects. Use them as a guide for "
        "structure, level of detail, and realistic pricing. Adapt the content to match the "
        "specific project described in the transcription.\n\n"
        "Your output MUST follow this exact format:\n"
        "- Project title as an H2 heading\n"
        "- A task breakdown table with columns: Task, Hours, Cost (EUR)\n"
        "- Total hours\n"
        "- Total cost in EUR\n"
        "- Recommended team composition\n"
        "- Estimated duration in weeks\n\n"
        "Use a developer rate of approximately 62.50 EUR/hour (500 EUR/day) and a designer "
        "rate of approximately 50 EUR/hour (400 EUR/day). Provide realistic, well-justified "
        "numbers.\n\n"
        f"{examples_text}"
    )


def _build_timeout(settings: Settings) -> httpx.Timeout:
    """Build the per-attempt timeout budget for a deployment."""
    return httpx.Timeout(
        connect=settings.LLM_CONNECT_TIMEOUT_S,
        write=settings.LLM_WRITE_TIMEOUT_S,
        read=settings.LLM_READ_TIMEOUT_S,
        pool=settings.LLM_POOL_TIMEOUT_S,
    )


def _api_key_for(settings: Settings, provider: str) -> str | None:
    """Return the API key configured for a provider."""
    return settings.ANTHROPIC_API_KEY if provider == "anthropic" else settings.OPENAI_API_KEY


def _build_model_list(settings: Settings) -> list[dict[str, Any]]:
    """Build the LiteLLM deployment list from settings, ordered by priority."""
    deployments: list[dict[str, Any]] = []
    for order, model in enumerate(settings.configured_models(), start=1):
        provider, _ = split_model_id(model)
        deployments.append(
            {
                "model_name": MODEL_ALIAS,
                "litellm_params": {
                    "model": model,
                    "api_key": _api_key_for(settings, provider),
                    "order": order,
                    "timeout": _build_timeout(settings),
                },
            }
        )
    return deployments


def _get_router() -> Router:
    """Return the process-wide Router, building it on first use."""
    global _router
    if _router is None:
        with _state_lock:
            if _router is None:
                settings = get_settings()
                _router = Router(
                    model_list=_build_model_list(settings),
                    num_retries=settings.LLM_MAX_RETRIES,
                    retry_policy=RetryPolicy(DefaultRetries=settings.LLM_MAX_RETRIES),
                    cache_responses=False,
                )
    return _router


def _get_semaphore() -> threading.BoundedSemaphore:
    """Return the process-wide concurrency limiter, building it on first use."""
    global _semaphore
    if _semaphore is None:
        with _state_lock:
            if _semaphore is None:
                _semaphore = threading.BoundedSemaphore(get_settings().LLM_MAX_CONCURRENCY)
    return _semaphore


def reset_llm_state() -> None:
    """Drop the cached Router and semaphore (tests and settings reloads)."""
    global _router, _semaphore
    with _state_lock:
        _router = None
        _semaphore = None


def _call_router(messages: list[dict[str, str]]) -> Any:
    """Call the configured model alias through the Router."""
    try:
        return _get_router().completion(
            model=MODEL_ALIAS,
            messages=messages,
            max_tokens=MAX_TOKENS,
        )
    except LLMServiceError:
        raise
    except Exception as exc:
        raise _translate_error(exc) from exc


def _translate_error(exc: Exception) -> LLMServiceError:
    """Map a provider/library exception to the service error hierarchy.

    ``litellm.Timeout`` subclasses ``APIConnectionError``, so the timeout check
    must come first or every timeout would be classified as an upstream failure.
    """
    from litellm import exceptions as le

    if isinstance(exc, (le.Timeout, httpx.TimeoutException)):
        return LLMTimeoutError(f"LLM request timed out: {exc}")
    if isinstance(exc, le.RateLimitError):
        return LLMRateLimitError(f"LLM provider rate limited: {exc}")
    if isinstance(
        exc,
        (
            le.AuthenticationError,
            le.PermissionDeniedError,
            le.BadRequestError,
            le.ContextWindowExceededError,
        ),
    ):
        return LLMConfigError(f"LLM configuration rejected: {exc}")
    if isinstance(
        exc,
        (
            le.APIConnectionError,
            le.InternalServerError,
            le.ServiceUnavailableError,
            le.BadGatewayError,
        ),
    ):
        return LLMUpstreamError(f"LLM provider unavailable: {exc}")
    return LLMUpstreamError(f"LLM call failed: {exc}")


def _provider_table(settings: Settings) -> dict[str, str]:
    """Map both the prefixed and bare model ids to their provider."""
    table: dict[str, str] = {}
    for model in settings.configured_models():
        provider, name = split_model_id(model)
        table[model] = provider
        table[name] = provider
    return table


def _resolve_provider(model: str, settings: Settings) -> str:
    """Resolve which provider served the response."""
    provider = _provider_table(settings).get(model)
    if provider:
        return provider
    log.warning("llm_provider_unresolved", model=model)
    return split_model_id(settings.LLM_MODEL)[0]


def _completion_cost(response: Any) -> float | None:
    """Return the estimated cost of a completion, or None if unavailable."""
    try:
        cost = litellm.completion_cost(completion_response=response)
    except Exception as exc:  # pragma: no cover - depends on the pricing table
        log.warning("llm_cost_unavailable", error=str(exc))
        return None
    return cost if cost is not None else None


def _normalize_response(response: Any, settings: Settings) -> tuple[dict[str, Any], float | None]:
    """Turn a LiteLLM response into the service contract."""
    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    total_tokens = int(getattr(usage, "total_tokens", 0) or (input_tokens + output_tokens))

    model = getattr(response, "model", None) or settings.LLM_MODEL
    provider = _resolve_provider(model, settings)
    cost = _completion_cost(response)

    log.info(
        "llm_response_received",
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost_usd=cost,
    )

    result = {
        "estimation": response.choices[0].message.content,
        "model": model,
        "provider": provider,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        },
    }
    return result, cost


def _log_failure(exc: LLMServiceError, started: float, settings: Settings) -> None:
    """Log a failed call with the full detail; the client only sees a fixed message."""
    provider, model = split_model_id(settings.LLM_MODEL)
    log.error(
        "estimation_failed",
        outcome=f"error:{type(exc).__name__}",
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
        error_type=type(exc).__name__,
        error=str(exc),
        provider=provider,
        model=model,
    )


def generate_estimation(transcription: str) -> dict:
    """Generate a software estimation from a meeting transcription using the configured LLM."""
    started = time.perf_counter()
    settings = get_settings()
    messages = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": transcription},
    ]

    log.info(
        "generating_estimation",
        model_alias=MODEL_ALIAS,
        models=settings.configured_models(),
    )

    semaphore = _get_semaphore()
    if not semaphore.acquire(blocking=False):
        log.warning("llm_capacity_exhausted", max_concurrency=settings.LLM_MAX_CONCURRENCY)
        raise LLMCapacityError("LLM concurrency limit reached")

    try:
        response = _call_router(messages)
    except LLMServiceError as exc:
        _log_failure(exc, started, settings)
        raise
    finally:
        semaphore.release()

    result, cost = _normalize_response(response, settings)
    log.info(
        "estimation_completed",
        outcome="success",
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
        provider=result["provider"],
        model=result["model"],
        input_tokens=result["usage"]["input_tokens"],
        output_tokens=result["usage"]["output_tokens"],
        total_tokens=result["usage"]["total_tokens"],
        cost_usd=cost,
    )
    return result
