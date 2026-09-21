"""Интеграционный контракт чтения экспортов ML-прогнозов."""

import hashlib
import json
from pathlib import Path

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
        '"anomaly_score": null, '
        '"evidence_tier": "proxy", '
        '"calibrated": true, '
        '"provenance": "derived", '
        '"confidence": {"lower": 0.74, "upper": 0.88}, '
        '"model_metrics": {"precision": 0.78, "recall": 0.68, "f1": 0.72, '
        '"pr_auc": 0.76, "brier_score": 0.14}, '
        '"quality_status": "passed", '
        '"limitations": ["Прокси-метка тишины не подтверждает физический отказ"], '
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


def write_prediction_export(root, case: str, version: str, content: str):
    export_path = root / case / version / "predictions.json"
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(content, encoding="utf-8")
    payload = json.loads(content)
    first = payload["predictions"][0] if payload["predictions"] else {}
    card_content = json.dumps(
        {
            "task": case,
            "version": version,
            "evidence_tier": first.get("evidence_tier", "proxy"),
            "calibrated": first.get("calibrated", True),
            "test_metrics": first.get("model_metrics", {}),
        },
        sort_keys=True,
    )
    (export_path.parent / "model-card.json").write_text(card_content, encoding="utf-8")
    (export_path.parent / "predictions-manifest.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "task": case,
                "version": version,
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "model_card_sha256": hashlib.sha256(card_content.encode("utf-8")).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return export_path


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
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate, private"
    assert len(audit_ledger._chain) == records_before + 1
    assert audit_ledger._chain[-1].event_type == "PREDICTIONS_VIEW_REQUESTED"
    assert audit_ledger._chain[-1].user_id == "test-dispatcher"


def test_predictions_endpoint_reads_exported_predictions(client: TestClient, tmp_path, monkeypatch):
    """Игнорирование экспорта ML или выдача не его содержимого нарушит контракт UI."""

    write_prediction_export(tmp_path, "sensor_failure", "v1", prediction_json("prediction-001"))
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path, raising=False)

    response = client.get("/api/predictions")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate, private"
    assert response.json() == {
        "available_types": ["sensor_failure"],
        "predictions": [
            {
                "id": "prediction-001",
                "entity_type": "sensor",
                "entity_id": "sensor-001",
                "prediction_type": "sensor_failure",
                "probability": 0.82,
                "anomaly_score": None,
                "evidence_tier": "proxy",
                "calibrated": True,
                "provenance": "derived",
                "confidence": {"lower": 0.74, "upper": 0.88},
                "model_metrics": {
                    "precision": 0.78,
                    "recall": 0.68,
                    "f1": 0.72,
                    "pr_auc": 0.76,
                    "brier_score": 0.14,
                },
                "quality_status": "passed",
                "limitations": ["Прокси-метка тишины не подтверждает физический отказ"],
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
        ],
    }


def test_predictions_endpoint_uses_latest_export_version_for_each_case(
    client: TestClient,
    tmp_path,
    monkeypatch,
):
    """Выдача устаревшей версии вместе с актуальной исказит решения диспетчера."""

    for version, prediction_id in (("v1", "stale-sensor-001"), ("v2", "current-sensor-001")):
        write_prediction_export(
            tmp_path, "sensor_failure", version, prediction_json(prediction_id, version)
        )
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path, raising=False)

    response = client.get("/api/predictions")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["predictions"]] == ["current-sensor-001"]
    assert response.json()["available_types"] == ["sensor_failure"]


def test_predictions_endpoint_reports_available_model_with_no_active_alerts(
    client: TestClient, tmp_path, monkeypatch
):
    """Пустой валидный экспорт нельзя выдавать за неготовую модель."""

    write_prediction_export(tmp_path, "sensor_failure", "v1", '{"predictions": []}')
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path, raising=False)

    response = client.get("/api/predictions")

    assert response.status_code == 200
    assert response.json() == {
        "available_types": ["sensor_failure"],
        "predictions": [],
    }


def test_predictions_endpoint_lists_only_types_with_valid_exports(
    client: TestClient, tmp_path, monkeypatch
):
    """Доступность одной модели не должна объявлять готовыми остальные направления."""

    write_prediction_export(tmp_path, "sensor_failure", "v1", prediction_json("prediction-001"))
    write_prediction_export(tmp_path, "fire_risk", "v1", '{"predictions": []}')
    malformed = write_prediction_export(
        tmp_path, "unauthorized_access", "v1", '{"predictions": []}'
    )
    malformed.write_text('{"predictions": [{"unexpected": true}]}', encoding="utf-8")
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path, raising=False)

    response = client.get("/api/predictions")

    assert response.status_code == 200
    assert response.json()["available_types"] == ["sensor_failure", "fire_risk"]


def test_predictions_endpoint_rejects_malformed_export(client: TestClient, tmp_path, monkeypatch):
    """Произвольный JSON из ML-каталога не должен достигать frontend."""

    content = prediction_json("prediction-001").replace(
        '"probability": 0.82', '"probability": 1.82'
    )
    write_prediction_export(tmp_path, "sensor_failure", "v1", content)
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path, raising=False)

    response = client.get("/api/predictions")

    assert response.status_code == 503
    assert response.json() == {"error": "ML модель не обучена", "status": "pending"}


def test_predictions_endpoint_rejects_uncalibrated_probability(
    client: TestClient, tmp_path, monkeypatch
):
    """Raw score не должен попасть в UI как вероятность инцидента."""
    content = prediction_json("prediction-001").replace('"calibrated": true', '"calibrated": false')
    write_prediction_export(tmp_path, "sensor_failure", "v1", content)
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path, raising=False)

    response = client.get("/api/predictions")

    assert response.status_code == 503
    assert response.json() == {"error": "ML модель не обучена", "status": "pending"}


def test_predictions_endpoint_rejects_passed_status_below_tz_metrics(
    client: TestClient, tmp_path, monkeypatch
):
    content = prediction_json("prediction-001").replace(
        '"precision": 0.78, "recall": 0.68',
        '"precision": 0.01, "recall": 0.01',
    )
    write_prediction_export(tmp_path, "sensor_failure", "v1", content)
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path, raising=False)

    response = client.get("/api/predictions")

    assert response.status_code == 503


def test_predictions_endpoint_accepts_missing_individual_confidence_interval(
    client: TestClient, tmp_path, monkeypatch
):
    content = prediction_json("prediction-001").replace(
        '"confidence": {"lower": 0.74, "upper": 0.88}',
        '"confidence": null',
    )
    write_prediction_export(tmp_path, "sensor_failure", "v1", content)
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path, raising=False)

    response = client.get("/api/predictions")

    assert response.status_code == 200


def test_dispatcher_decision_is_written_to_audit_ledger(client: TestClient, tmp_path, monkeypatch):
    """Решение и причина должны сохраняться для последующего аудита."""

    write_prediction_export(tmp_path, "sensor_failure", "v1", prediction_json("prediction-001"))
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


def test_predictions_endpoint_rejects_tampered_export(client, tmp_path, monkeypatch):
    export_path = write_prediction_export(
        tmp_path, "sensor_failure", "v1", prediction_json("prediction-001")
    )
    export_path.write_text(prediction_json("tampered"), encoding="utf-8")
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path, raising=False)

    response = client.get("/api/predictions")

    assert response.status_code == 503


def test_predictions_endpoint_rejects_task_mismatch(client, tmp_path, monkeypatch):
    content = prediction_json("prediction-001").replace(
        '"prediction_type": "sensor_failure"', '"prediction_type": "fire_risk"'
    )
    write_prediction_export(tmp_path, "sensor_failure", "v1", content)
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path, raising=False)

    response = client.get("/api/predictions")

    assert response.status_code == 503


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    (("priority", "urgent"), ("status", "queued")),
)
def test_predictions_endpoint_rejects_unknown_dispatcher_taxonomy(
    client: TestClient,
    tmp_path,
    monkeypatch,
    field: str,
    invalid_value: str,
):
    """Неизвестные priority/status не должны достигать UI."""

    payload = json.loads(prediction_json("prediction-001"))
    payload["predictions"][0][field] = invalid_value
    content = json.dumps(payload, ensure_ascii=False)
    write_prediction_export(tmp_path, "sensor_failure", "v1", content)
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path, raising=False)

    response = client.get("/api/predictions")

    assert response.status_code == 503


def test_predictions_endpoint_rejects_scenario_with_anomaly_score(
    client: TestClient, tmp_path, monkeypatch
):
    """Сценарный результат не должен маскировать anomaly score."""

    payload = json.loads(prediction_json("prediction-001"))
    item = payload["predictions"][0]
    item.update(
        probability=None,
        anomaly_score=0.73,
        evidence_tier="scenario",
        calibrated=False,
        provenance="simulated",
        confidence=None,
        model_metrics=None,
        quality_status="limited",
    )
    content = json.dumps(payload, ensure_ascii=False)
    write_prediction_export(tmp_path, "sensor_failure", "v1", content)
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path, raising=False)

    response = client.get("/api/predictions")

    assert response.status_code == 503


def test_predictions_endpoint_rejects_more_than_response_limit(
    client: TestClient, tmp_path, monkeypatch
):
    """Неограниченный массив прогнозов может исчерпать память API."""

    item = json.loads(prediction_json("prediction-001"))["predictions"][0]
    content = json.dumps(
        {"predictions": [item] * 10_001},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    write_prediction_export(tmp_path, "sensor_failure", "v1", content)
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path, raising=False)

    response = client.get("/api/predictions")

    assert response.status_code == 503


def test_predictions_endpoint_rejects_symlinked_models_root(
    client: TestClient, tmp_path, monkeypatch
):
    """Resolve не должен скрывать подмену корня хранилища symlink-ом."""

    real_root = tmp_path / "real-models"
    write_prediction_export(real_root, "sensor_failure", "v1", prediction_json("prediction-001"))
    models_link = tmp_path / "models-link"
    _create_directory_symlink_or_skip(models_link, real_root)
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", models_link, raising=False)

    response = client.get("/api/predictions")

    assert response.status_code == 503


def test_predictions_endpoint_rejects_symlinked_task_directory(
    client: TestClient, tmp_path, monkeypatch
):
    """Даже symlink внутри корня не должен подменять каталог задачи."""

    models_root = tmp_path / "models"
    real_task = models_root / "internal" / "sensor_failure"
    write_prediction_export(
        real_task.parent, "sensor_failure", "v1", prediction_json("prediction-001")
    )
    _create_directory_symlink_or_skip(models_root / "sensor_failure", real_task)
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", models_root, raising=False)

    response = client.get("/api/predictions")

    assert response.status_code == 503


def test_predictions_endpoint_checks_export_size_before_reading(
    client: TestClient, tmp_path, monkeypatch
):
    """Превышающий лимит экспорт нельзя даже читать в память."""

    export_path = write_prediction_export(
        tmp_path, "sensor_failure", "v1", prediction_json("prediction-001")
    )
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path, raising=False)
    monkeypatch.setattr(
        predictions,
        "MAX_PREDICTION_EXPORT_BYTES",
        export_path.stat().st_size - 1,
        raising=False,
    )
    original_read_bytes = Path.read_bytes

    def guarded_read_bytes(path: Path) -> bytes:
        if path == export_path:
            raise AssertionError("Экспорт прочитан до проверки размера")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)

    response = client.get("/api/predictions")

    assert response.status_code == 503


def test_predictions_endpoint_checks_manifest_size_before_reading(
    client: TestClient, tmp_path, monkeypatch
):
    """Превышающий лимит manifest отклоняется до JSON-разбора."""

    export_path = write_prediction_export(
        tmp_path, "sensor_failure", "v1", prediction_json("prediction-001")
    )
    manifest_path = export_path.parent / "predictions-manifest.json"
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path, raising=False)
    monkeypatch.setattr(
        predictions,
        "MAX_PREDICTION_MANIFEST_BYTES",
        manifest_path.stat().st_size - 1,
        raising=False,
    )
    original_read_text = Path.read_text

    def guarded_read_text(path: Path, *args, **kwargs) -> str:
        if path == manifest_path:
            raise AssertionError("Manifest прочитан до проверки размера")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    response = client.get("/api/predictions")

    assert response.status_code == 503


def test_predictions_endpoint_checks_model_card_size_before_reading(
    client: TestClient, tmp_path, monkeypatch
):
    """Превышающий лимит model card отклоняется до хеширования и JSON-разбора."""

    export_path = write_prediction_export(
        tmp_path, "sensor_failure", "v1", prediction_json("prediction-001")
    )
    card_path = export_path.parent / "model-card.json"
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path, raising=False)
    monkeypatch.setattr(
        predictions,
        "MAX_MODEL_CARD_BYTES",
        card_path.stat().st_size - 1,
        raising=False,
    )
    original_read_bytes = Path.read_bytes

    def guarded_read_bytes(path: Path) -> bytes:
        if path == card_path:
            raise AssertionError("Model card прочита до проверки размера")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)

    response = client.get("/api/predictions")

    assert response.status_code == 503


def _create_directory_symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"Символические ссылки недоступны: {error}")
