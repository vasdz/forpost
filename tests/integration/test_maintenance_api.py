"""Интеграционный контракт недоступности контура заявок без реального реестра."""

import pytest
from fastapi.testclient import TestClient
from forpost_api.dependencies import get_current_subject
from forpost_api.main import app
from forpost_api.routes.v1.availability import (
    REAL_DATA_INTEGRATION_UNAVAILABLE_CODE,
    REAL_DATA_INTEGRATION_UNAVAILABLE_MESSAGE,
)
from forpost_platform.maintenance.generator import get_maintenance_store
from forpost_platform.security.identity import Role, SecuritySubject


@pytest.fixture
def client():
    """Даёт роуту доверенный тестовый субъект без включения внешнего поставщика identity."""

    app.dependency_overrides[get_current_subject] = lambda: SecuritySubject(
        user_id="test-dispatcher",
        username="test-dispatcher",
        role=Role.DISPATCHER,
        allowed_districts=["rek-1"],
    )
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def assert_data_integration_unavailable(response) -> None:
    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": REAL_DATA_INTEGRATION_UNAVAILABLE_CODE,
            "message": REAL_DATA_INTEGRATION_UNAVAILABLE_MESSAGE,
        }
    }


def test_generation_request_cannot_create_order_without_real_prediction(client: TestClient):
    """Удаление защитного отказа снова сохранит заявку из выдуманного прогноза."""
    store = get_maintenance_store()
    order_ids_before = {order.order_id for order in store.get_all()}

    response = client.post(
        "/api/v1/maintenance/generate-from-prediction",
        json={"risk_prediction_ids": [], "auto_approve": True},
    )

    assert_data_integration_unavailable(response)
    assert {order.order_id for order in store.get_all()} == order_ids_before


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/maintenance"),
        ("patch", "/api/v1/maintenance/not-a-real-order/status?new_status=approved"),
    ],
)
def test_maintenance_read_and_update_are_unavailable_without_registry(
    client: TestClient,
    method: str,
    path: str,
):
    """Временное хранилище не может подменять реестр оборудования ни при чтении, ни при записи."""

    assert_data_integration_unavailable(getattr(client, method)(path))
