import structlog
from fastapi import APIRouter, HTTPException

from app.schemas.estimation import EstimationRequest, EstimationResponse
from app.services.llm_service import (
    LLMCapacityError,
    LLMConfigError,
    LLMRateLimitError,
    LLMServiceError,
    LLMTimeoutError,
    LLMUpstreamError,
    generate_estimation,
)

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["estimations"])

RETRY_AFTER_SECONDS = 5


def _http_error(exc: LLMServiceError) -> HTTPException:
    """Map a service failure to a stable HTTP error without leaking provider detail."""
    if isinstance(exc, LLMTimeoutError):
        return HTTPException(
            status_code=504,
            detail="El proveedor del LLM no respondió a tiempo",
        )
    if isinstance(exc, (LLMRateLimitError, LLMCapacityError)):
        return HTTPException(
            status_code=503,
            detail="El servicio está saturado; reintenta más tarde",
            headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
        )
    if isinstance(exc, LLMUpstreamError):
        return HTTPException(
            status_code=502,
            detail="El proveedor del LLM no está disponible",
        )
    if isinstance(exc, LLMConfigError):
        return HTTPException(
            status_code=500,
            detail="Error de configuración del servicio LLM",
        )
    return HTTPException(
        status_code=500,
        detail="Error interno del servicio LLM",
    )


@router.post("/estimate", response_model=EstimationResponse)
def create_estimation(request: EstimationRequest) -> EstimationResponse:
    """Receive a meeting transcription and return a software project estimation."""
    try:
        result = generate_estimation(request.transcription)
    except LLMServiceError as exc:
        log.error("estimation_endpoint_error", error_type=type(exc).__name__)
        raise _http_error(exc) from exc

    return EstimationResponse(**result)
