"""Контракт доступности backend-источников для frontend."""

from fastapi.testclient import TestClient
from forpost_api.dependencies import get_current_subject
from forpost_api.main import app
from forpost_api.routes import availability, predictions
from forpost_platform.security.identity import Role, SecuritySubject


def test_availability_reports_real_state_without_invented_sources(tmp_path, monkeypatch):
    snapshot_path = tmp_path / "local-situation.json"
    snapshot_path.write_text("{}", encoding="utf-8")
    models_path = tmp_path / "models"
    monkeypatch.setattr(availability, "LOCAL_SNAPSHOT_PATH", snapshot_path, raising=False)
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", models_path, raising=False)
    app.dependency_overrides[get_current_subject] = lambda: SecuritySubject(
        user_id="test-dispatcher",
        username="test-dispatcher",
        role=Role.DISPATCHER,
        allowed_districts=["rek-1"],
    )
    try:
        with TestClient(app) as client:
            response = client.get("/api/availability")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "limited",
        "sources": {
            "local_snapshot": "available",
            "ml_predictions": "unavailable",
            "access_events": "unavailable",
            "maintenance_history": "unavailable",
            "work_permits": "unavailable",
        },
    }
