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


def test_blank_transcription_is_rejected_without_calling_the_provider(monkeypatch) -> None:
    called = False

    def _fail_if_called(transcription: str) -> dict:
        nonlocal called
        called = True
        return FAKE_RESULT

    monkeypatch.setattr("app.routers.estimations.generate_estimation", _fail_if_called)

    with TestClient(app) as client:
        response = client.post("/api/v1/estimate", json={"transcription": " " * 50})

    assert response.status_code == 422
    assert called is False


def test_too_long_transcription_is_rejected_without_calling_the_provider(monkeypatch) -> None:
    called = False

    def _fail_if_called(transcription: str) -> dict:
        nonlocal called
        called = True
        return FAKE_RESULT

    monkeypatch.setattr("app.routers.estimations.generate_estimation", _fail_if_called)

    with TestClient(app) as client:
        response = client.post("/api/v1/estimate", json={"transcription": "x" * 50_001})

    assert response.status_code == 422
    assert called is False


def test_maximum_length_is_accepted(monkeypatch) -> None:
    monkeypatch.setattr("app.routers.estimations.generate_estimation", _fake_estimation)

    with TestClient(app) as client:
        response = client.post("/api/v1/estimate", json={"transcription": "x" * 50_000})

    assert response.status_code == 200
