import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import llm_service

TRANSCRIPTION = "x" * 60

CASES = [
    ("timeout", lambda: llm_service.LLMTimeoutError("slow"), 504, None),
    ("rate_limit", lambda: llm_service.LLMRateLimitError("429"), 503, "5"),
    ("capacity", lambda: llm_service.LLMCapacityError("full"), 503, "5"),
    ("upstream", lambda: llm_service.LLMUpstreamError("down"), 502, None),
    ("config", lambda: llm_service.LLMConfigError("401"), 500, None),
    ("base", lambda: llm_service.LLMServiceError("unknown"), 500, None),
]


@pytest.mark.parametrize("name, factory, status, retry_after", CASES)
def test_each_failure_maps_to_its_status(
    monkeypatch, name, factory, status, retry_after
) -> None:
    def _boom(transcription: str) -> dict:
        raise factory()

    monkeypatch.setattr("app.routers.estimations.generate_estimation", _boom)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/estimate", json={"transcription": TRANSCRIPTION}
        )

    assert response.status_code == status
    assert response.headers.get("retry-after") == retry_after
    assert response.headers.get("x-request-id")


def test_provider_message_is_not_leaked(monkeypatch) -> None:
    def _boom(transcription: str) -> dict:
        raise llm_service.LLMUpstreamError("SECRET-MARKER-123 org_abc")

    monkeypatch.setattr("app.routers.estimations.generate_estimation", _boom)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/estimate", json={"transcription": TRANSCRIPTION}
        )

    assert response.status_code == 502
    assert "SECRET-MARKER-123" not in response.text
    assert "org_abc" not in response.text
    assert response.json()["detail"] == "El proveedor del LLM no está disponible"
