"""Контракт отказа для API, которым требуются ещё не подключённые источники."""

import pytest
from fastapi.testclient import TestClient
from forpost_api.dependencies import get_current_subject
from forpost_api.main import app
from forpost_platform.security.identity import Role, SecuritySubject

UNAVAILABLE_CODE = "REAL_DATA_INTEGRATION_UNAVAILABLE"
UNAVAILABLE_MESSAGE = "Интеграция с реальными данными и обученной моделью пока недоступна."


@pytest.fixture
def api_client():
    """Запускает роуты с доверенным тестовым субъектом, не подменяя их бизнес-логику."""

    app.dependency_overrides[get_current_subject] = lambda: SecuritySubject(
        user_id="test-dispatcher",
        username="test-dispatcher",
        role=Role.DISPATCHER,
        allowed_districts=["rek-1"],
    )
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("method", "path", "request_kwargs"),
    [
        ("get", "/api/v1/risks", {}),
        ("get", "/api/v1/maintenance", {}),
        (
            "post",
            "/api/v1/maintenance/generate-from-prediction",
            {"json": {"risk_prediction_ids": [], "auto_approve": False}},
        ),
        ("patch", "/api/v1/maintenance/unknown/status?new_status=approved", {}),
        ("get", "/api/v1/analytics/kpi", {}),
        ("post", "/api/v1/analytics/reports/operational", {}),
        ("get", "/api/v1/analytics/export", {}),
    ],
)
def test_unconnected_data_operations_do_not_fabricate_results(
    api_client: TestClient,
    method: str,
    path: str,
    request_kwargs: dict,
):
    """Удаление защитного отказа вернёт сгенерированный прогноз, отчёт или заявку."""

    response = getattr(api_client, method)(path, **request_kwargs)

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": UNAVAILABLE_CODE,
            "message": UNAVAILABLE_MESSAGE,
        }
    }
    assert "orders" not in response.json()["detail"]
    assert "prediction_id" not in response.json()["detail"]


def test_analytics_health_describes_limited_data_availability(api_client: TestClient):
    """Возврат статуса «operational» с фиктивными возможностями скроет отсутствие интеграции."""

    response = api_client.get("/api/v1/analytics/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "limited",
        "module": "analytics",
        "data_integration": "unavailable",
        "message": UNAVAILABLE_MESSAGE,
    }
