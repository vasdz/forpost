"""Проверка защищённого API оценки независимо от допуска прогнозов."""

import importlib
import importlib.util
import json

import pytest
from fastapi.testclient import TestClient
from forpost_api.main import app
from forpost_api.routes import predictions
from forpost_platform.security.demo_identity import issue_demo_assertion
from forpost_platform.security.identity import Role, SecuritySubject


@pytest.fixture
def evaluation_route(tmp_path, monkeypatch):
    name = "forpost_api.routes.model_evaluation"
    assert importlib.util.find_spec(name) is not None, "Отсутствует API отчёта оценки"
    route = importlib.import_module(name)
    monkeypatch.setattr(route, "EVALUATION_REPORT_PATH", tmp_path / "evaluation.json")
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path / "models")
    monkeypatch.setenv("FORPOST_API_SERVICE_TOKEN", "evaluation-api-test-token-1234567890")
    return route


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def authenticated_get(client, url):
    return client.get(url, headers={"Authorization": "Bearer evaluation-api-test-token-1234567890"})


def test_evaluation_requires_authentication_before_reading(client, evaluation_route):
    response = client.get("/api/model-evaluation")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_evaluation_uses_demo_subject_permissions_instead_of_service_token(client, evaluation_route, monkeypatch):
    """Demo-утверждение не должно заменяться центральным BFF-токеном."""
    secret = "d" * 48
    monkeypatch.setenv("FORPOST_DEMO_MODE", "1")
    monkeypatch.setenv("FORPOST_DEMO_ASSERTION_SECRET", secret)
    subject = SecuritySubject(
        user_id="demo-admin",
        username="Демо-администратор",
        roles=frozenset({Role.SYSTEM_ADMIN}),
        allowed_districts=frozenset(),
        allowed_complexes=frozenset(),
    )
    assertion = issue_demo_assertion(subject, secret)

    response = client.get("/api/model-evaluation", headers={"Authorization": f"Bearer demo.{assertion}"})

    assert response.status_code == 403
    assert response.json()["detail"] == "Недостаточно прав для выполнения операции"


@pytest.mark.parametrize(
    "content",
    [None, b"{}", b"\xff", b" " * (256 * 1024 + 1)],
    ids=["missing", "invalid", "encoding", "oversized"],
)
def test_invalid_report_returns_safe_unavailable(client, evaluation_route, content):
    if content is not None:
        evaluation_route.EVALUATION_REPORT_PATH.write_bytes(content)
    response = authenticated_get(client, "/api/model-evaluation")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "reason_code": "evaluation_unavailable"}
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate, private"


@pytest.mark.parametrize("status", ["rejected", "published"])
def test_valid_evidence_never_authorizes_predictions(client, evaluation_route, status):
    metrics = {
        "precision": 0.8,
        "recall": 0.7,
        "f1": 0.75,
        "pr_auc": 0.8,
        "roc_auc": 0.85,
        "brier_score": 0.12,
        "expected_calibration_error": 0.1,
        "alert_rate": 0.2,
    }
    payload = {
        "format_version": 1,
        "task": "sensor_failure",
        "version": "v1",
        "status": status,
        "evidence_tier": "proxy",
        "label_strategy": "silence_horizon_proxy",
        "created_at": "2026-09-21T10:00:00Z",
        "reason_code": "validation_rejected",
        "quality_thresholds": None,
        "split_sizes": None,
        "baseline_validation_pr_auc": None,
        "validation_metrics": None,
        "test_metrics": None,
        "threshold": None,
        "champion_name": None,
    }
    if status == "published":
        payload.update(
            reason_code=None,
            validation_metrics=metrics,
            test_metrics=metrics,
            threshold=0.6,
            champion_name="extra_trees_isotonic",
            baseline_validation_pr_auc=0.25,
            split_sizes={"fit": 100, "calibration": 30, "validation": 40, "test": 40},
            quality_thresholds={
                "minimum_precision": 0.7,
                "minimum_recall": 0.5,
                "maximum_alert_rate": 0.35,
                "maximum_expected_calibration_error": 0.2,
                "maximum_brier_score": 0.25,
                "minimum_baseline_pr_auc_delta": 0.01,
            },
        )
    evaluation_route.EVALUATION_REPORT_PATH.write_text(json.dumps(payload), encoding="utf-8")
    response = authenticated_get(client, "/api/model-evaluation")
    assert response.status_code == 200
    assert response.json() == payload
    assert authenticated_get(client, "/api/predictions").status_code == 503
