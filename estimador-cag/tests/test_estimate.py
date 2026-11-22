from fastapi.testclient import TestClient

from app.main import app

FAKE_RESULT = {
    "estimation": "## Estimación de prueba",
    "model": "test-model",
    "provider": "anthropic",
    "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
}


def _fake_estimation(transcription: str) -> dict:
    return FAKE_RESULT


def test_estimate_returns_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.estimations.generate_estimation", _fake_estimation
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/estimate", json={"transcription": "x" * 60}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["estimation"] == FAKE_RESULT["estimation"]
    assert body["model"] == FAKE_RESULT["model"]
    assert body["provider"] == FAKE_RESULT["provider"]
    assert body["usage"] == FAKE_RESULT["usage"]


def test_estimate_rejects_short_transcription(monkeypatch) -> None:
    called = False

    def _fail_if_called(transcription: str) -> dict:
        nonlocal called
        called = True
        return FAKE_RESULT

    monkeypatch.setattr(
        "app.routers.estimations.generate_estimation", _fail_if_called
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/estimate", json={"transcription": "corta"}
        )

    assert response.status_code == 422
    assert called is False
