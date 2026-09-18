"""Интеграционный контракт чтения экспортов ML-прогнозов."""

import pytest
from fastapi.testclient import TestClient
from forpost_api.dependencies import get_current_human_subject, get_current_subject
from forpost_api.main import app
from forpost_api.routes import predictions
from forpost_platform.audit.ledger import audit_ledger
from forpost_platform.security.identity import Role, SecuritySubject


def prediction_json(prediction_id: str, model_version: str = "v1") -> str:
    return (
        '{"predictions": [{'
        f'"id": "{prediction_id}", '
        '"entity_type": "sensor", '
        '"entity_id": "sensor-001", '
        '"prediction_type": "sensor_failure", '
        '"probability": 0.82, '
        '"predicted_at": "2026-09-15T18:00:00+03:00", '
        '"horizon_hours": 24, '
        f'"model_version": "{model_version}", '
        '"factors": [{"factor": "temperature", "weight": 0.7, '
        '"description": "Рост температуры"}], '
        '"recommended_action": "Проверить датчик", '
        '"priority": "high", '
        '"status": "new"'
        "}]} "
    )


@pytest.fixture
def client():
    """Подключает доверенного диспетчера без внешнего поставщика идентификации."""

    subject = SecuritySubject(
        user_id="test-dispatcher",
        username="test-dispatcher",
        roles=frozenset({Role.DISTRICT_DISPATCHER}),
        allowed_districts=frozenset({"rek-1"}),
    )
    app.dependency_overrides[get_current_subject] = lambda: subject
    app.dependency_overrides[get_current_human_subject] = lambda: subject
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_predictions_endpoint_reports_pending_model_and_audits_request(
    client: TestClient,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Удаление fail-closed отказа или аудита скроет отсутствие обученной модели."""

    records_before = len(audit_ledger._chain)
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path, raising=False)

    response = client.get("/api/predictions")

    assert response.status_code == 503
    assert response.json() == {"error": "ML модель не обучена", "status": "pending"}
    assert len(audit_ledger._chain) == records_before + 1
    assert audit_ledger._chain[-1].event_type == "PREDICTIONS_VIEW_REQUESTED"
    assert audit_ledger._chain[-1].user_id == "test-dispatcher"


def test_predictions_endpoint_reads_exported_predictions(client: TestClient, tmp_path, monkeypatch):
    """Игнорирование экспорта ML или выдача не его содержимого нарушит контракт UI."""

    export_path = tmp_path / "sensor_failure" / "v1" / "predictions.json"
    export_path.parent.mkdir(parents=True)
    export_path.write_text(prediction_json("prediction-001"), encoding="utf-8")
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path, raising=False)

    response = client.get("/api/predictions")

    assert response.status_code == 200
    assert response.json() == {
        "predictions": [
            {
                "id": "prediction-001",
                "entity_type": "sensor",
                "entity_id": "sensor-001",
                "prediction_type": "sensor_failure",
                "probability": 0.82,
                "predicted_at": "2026-09-15T18:00:00+03:00",
                "horizon_hours": 24,
                "model_version": "v1",
                "factors": [
                    {
                        "factor": "temperature",
                        "weight": 0.7,
                        "description": "Рост температуры",
                    }
                ],
                "recommended_action": "Проверить датчик",
                "priority": "high",
                "status": "new",
            }
        ]
    }


def test_predictions_endpoint_uses_latest_export_version_for_each_case(
    client: TestClient,
    tmp_path,
    monkeypatch,
):
    """Выдача устаревшей версии вместе с актуальной исказит решения диспетчера."""

    for version, prediction_id in (("v1", "stale-sensor-001"), ("v2", "current-sensor-001")):
        export_path = tmp_path / "sensor_failure" / version / "predictions.json"
        export_path.parent.mkdir(parents=True)
        export_path.write_text(prediction_json(prediction_id, version), encoding="utf-8")
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path, raising=False)

    response = client.get("/api/predictions")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["predictions"]] == ["current-sensor-001"]


def test_predictions_endpoint_rejects_malformed_export(client: TestClient, tmp_path, monkeypatch):
    """Произвольный JSON из ML-каталога не должен достигать frontend."""

    export_path = tmp_path / "sensor_failure" / "v1" / "predictions.json"
    export_path.parent.mkdir(parents=True)
    export_path.write_text(
        prediction_json("prediction-001").replace('"probability": 0.82', '"probability": 1.82'),
        encoding="utf-8",
    )
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path, raising=False)

    response = client.get("/api/predictions")

    assert response.status_code == 503
    assert response.json() == {"error": "ML модель не обучена", "status": "pending"}


def test_dispatcher_decision_is_written_to_audit_ledger(client: TestClient, tmp_path, monkeypatch):
    """Решение и причина должны сохраняться для последующего аудита."""

    export_path = tmp_path / "sensor_failure" / "v1" / "predictions.json"
    export_path.parent.mkdir(parents=True)
    export_path.write_text(prediction_json("prediction-001"), encoding="utf-8")
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path, raising=False)

    response = client.post(
        "/api/predictions/prediction-001/decisions",
        json={"decision": "confirmed", "reason": "Назначена внеплановая проверка датчика."},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "recorded"
    assert response.json()["prediction_id"] == "prediction-001"
    record = audit_ledger._chain[-1]
    assert record.event_type == "PREDICTION_DECISION_RECORDED"
    assert record.details == {
        "decision": "confirmed",
        "reason": "Назначена внеплановая проверка датчика.",
    }


def test_decision_for_unknown_prediction_is_rejected(client: TestClient, tmp_path, monkeypatch):
    """Нельзя привязать аудиторское решение к несуществующему прогнозу."""

    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path, raising=False)

    response = client.post(
        "/api/predictions/unknown/decisions",
        json={"decision": "rejected", "reason": "Прогноз отсутствует в текущем экспорте."},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Прогноз не найден"}
