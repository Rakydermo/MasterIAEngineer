import structlog
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from app.main import app

FAKE_RESULT = {
    "estimation": "## Estimación de prueba",
    "model": "test-model",
    "provider": "anthropic",
    "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
}


def test_every_response_carries_a_request_id() -> None:
    with TestClient(app) as client:
        healthy = client.get("/health")
        not_found = client.get("/does-not-exist")
        invalid = client.post("/api/v1/estimate", json={"transcription": "short"})

    assert healthy.status_code == 200
    assert healthy.headers["x-request-id"]
    assert not_found.status_code == 404
    assert not_found.headers["x-request-id"]
    assert invalid.status_code == 422
    assert invalid.headers["x-request-id"]


def test_two_requests_get_different_ids() -> None:
    with TestClient(app) as client:
        first = client.get("/health")
        second = client.get("/health")

    assert first.headers["x-request-id"] != second.headers["x-request-id"]


def test_client_supplied_id_is_ignored() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/health", headers={"X-Request-ID": "client-controlled-value"}
        )

    assert response.headers["x-request-id"] != "client-controlled-value"
    assert len(response.headers["x-request-id"]) == 32


def test_log_request_id_matches_the_response(monkeypatch) -> None:
    def _fake(transcription: str) -> dict:
        structlog.get_logger().info("fake_estimation_completed")
        return FAKE_RESULT

    monkeypatch.setattr("app.routers.estimations.generate_estimation", _fake)

    with TestClient(app) as client:
        with capture_logs(
            processors=(structlog.contextvars.merge_contextvars,)
        ) as logs:
            response = client.post(
                "/api/v1/estimate", json={"transcription": "x" * 60}
            )

    request_id = response.headers["x-request-id"]
    assert any(event.get("request_id") == request_id for event in logs)
