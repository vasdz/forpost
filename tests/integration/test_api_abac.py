"""Контракт реестра рисков до появления проверенного источника и модели."""

from fastapi.testclient import TestClient
from forpost_api.dependencies import get_current_subject
from forpost_api.main import app
from forpost_api.routes.v1.availability import (
    REAL_DATA_INTEGRATION_UNAVAILABLE_CODE,
    REAL_DATA_INTEGRATION_UNAVAILABLE_MESSAGE,
)
from forpost_platform.security.identity import Role, SecuritySubject


def test_risk_registry_never_replaces_unavailable_data_with_predictions():
    """Даже доверенный тестовый диспетчер не получает выдуманные прогнозы вместо источника."""
    app.dependency_overrides[get_current_subject] = lambda: SecuritySubject(
        user_id="test-dispatcher",
        username="test-dispatcher",
        role=Role.DISPATCHER,
        allowed_districts=["rek-1"],
    )
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/risks")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": REAL_DATA_INTEGRATION_UNAVAILABLE_CODE,
            "message": REAL_DATA_INTEGRATION_UNAVAILABLE_MESSAGE,
        }
    }
