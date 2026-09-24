"""API evidence for forecast-to-fact is fail-closed and release-bound."""

import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from forpost_api.main import app


def _metrics() -> dict[str, float]:
    return {
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
        "pr_auc": 5 / 6,
    }


def _published_report() -> dict[str, object]:
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
    return {
        "format_version": 2,
        "task_semantics": "risk_of_unexpected_telemetry_silence_within_horizon",
        "feature_schema_version": "6",
        "config_sha256": "a" * 64,
        "library_versions": dict.fromkeys(
            ("numpy", "pandas", "scikit-learn", "skops", "catboost", "lightgbm"),
            "1.0",
        ),
        "rolling_folds": [
            {
                "index": index,
                "train_rows": 100,
                "calibration_rows": 30,
                "validation_rows": 40,
                "threshold": 0.5,
                "metrics": metrics,
            }
            for index in range(1, 4)
        ],
        "operating_profiles": {
            name: {"threshold": 0.5, "precision": 0.8, "recall": 0.7, "alert_rate": 0.2}
            for name in ("high_precision", "balanced", "high_recall")
        },
        "validation_confidence_intervals": {
            name: {
                "lower": value,
                "upper": value,
                "level": 0.95,
                "method": "student_t_across_rolling_folds",
            }
            for name, value in metrics.items()
        },
        "task": "sensor_failure",
        "version": "v12",
        "status": "published",
        "evidence_tier": "proxy",
        "label_strategy": "cadence_adjusted_silence_horizon_proxy_v2",
        "horizon_hours": 24,
        "created_at": "2026-09-21T10:00:00Z",
        "reason_code": None,
        "quality_thresholds": {
            "minimum_precision": 0.7,
            "minimum_recall": 0.5,
            "maximum_alert_rate": 0.35,
            "maximum_expected_calibration_error": 0.2,
            "maximum_brier_score": 0.25,
            "minimum_baseline_pr_auc_delta": 0.01,
        },
        "split_sizes": {"fit": 100, "calibration": 30, "validation": 120, "test": 4},
        "baseline_validation_pr_auc": 0.25,
        "validation_metrics": metrics,
        "test_metrics": {
            **metrics,
            "precision": 0.5,
            "recall": 0.5,
            "f1": 0.5,
            "pr_auc": 5 / 6,
        },
        "threshold": 0.5,
        "champion_name": "extra_trees_isotonic",
    }


def _artifact(report_digest: str) -> dict[str, object]:
    return {
        "format_version": 1,
        "task": "sensor_failure",
        "version": "v12",
        "evidence_tier": "proxy",
        "source_split": "final_test",
        "created_at": "2026-09-21T10:05:00Z",
        "evaluation_report_sha256": report_digest,
        "threshold": 0.5,
        "metrics": _metrics(),
        "rows": [
            {
                "id": "ff_0000000000000001",
                "prediction_at": "2026-08-01T00:00:00Z",
                "deadline": "2026-08-02T00:00:00Z",
                "probability": 0.9,
                "observed_outcome": True,
                "confusion": "TP",
                "sensor_type": "smoke",
                "lead_time_hours": 24.0,
            },
            {
                "id": "ff_0000000000000002",
                "prediction_at": "2026-08-02T00:00:00Z",
                "deadline": "2026-08-03T00:00:00Z",
                "probability": 0.8,
                "observed_outcome": False,
                "confusion": "FP",
                "sensor_type": "smoke",
                "lead_time_hours": 24.0,
            },
            {
                "id": "ff_0000000000000003",
                "prediction_at": "2026-08-03T00:00:00Z",
                "deadline": "2026-08-04T00:00:00Z",
                "probability": 0.4,
                "observed_outcome": True,
                "confusion": "FN",
                "sensor_type": "temperature",
                "lead_time_hours": 24.0,
            },
            {
                "id": "ff_0000000000000004",
                "prediction_at": "2026-08-04T00:00:00Z",
                "deadline": "2026-08-05T00:00:00Z",
                "probability": 0.1,
                "observed_outcome": False,
                "confusion": "TN",
                "sensor_type": "temperature",
                "lead_time_hours": 24.0,
            },
        ],
        "calibration_curve": [
            {"mean_probability": 0.25, "observed_rate": 0.5, "count": 2},
            {"mean_probability": 0.85, "observed_rate": 0.5, "count": 2},
        ],
        "lift_curve": [
            {"top_fraction": 0.25, "precision": 1.0, "lift": 2.0},
            {"top_fraction": 0.5, "precision": 0.5, "lift": 1.0},
            {"top_fraction": 1.0, "precision": 0.5, "lift": 1.0},
        ],
    }


@pytest.fixture
def forecast_fact_route(tmp_path, monkeypatch):
    from forpost_api.routes import forecast_fact

    monkeypatch.setattr(forecast_fact, "EVALUATION_REPORT_PATH", tmp_path / "evaluation.json")
    monkeypatch.setattr(forecast_fact, "FORECAST_FACT_PATH", tmp_path / "forecast-fact.json")
    monkeypatch.setattr(
        forecast_fact,
        "FORECAST_FACT_MANIFEST_PATH",
        tmp_path / "forecast-fact-manifest.json",
    )
    monkeypatch.setenv("FORPOST_API_SERVICE_TOKEN", "forecast-fact-api-test-token-1234567890")
    return forecast_fact


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def _authorize(client: TestClient):
    return client.get(
        "/api/forecast-fact",
        headers={"Authorization": "Bearer forecast-fact-api-test-token-1234567890"},
    )


def _write_evidence(route, *, report: dict[str, object] | None = None, tamper=False):
    report = report or _published_report()
    report_bytes = json.dumps(report).encode()
    route.EVALUATION_REPORT_PATH.write_bytes(report_bytes)
    report_digest = hashlib.sha256(report_bytes).hexdigest()
    artifact_bytes = json.dumps(_artifact(report_digest)).encode()
    route.FORECAST_FACT_PATH.write_bytes(artifact_bytes)
    manifest = {
        "format_version": 1,
        "task": "sensor_failure",
        "version": "v12",
        "sha256": ("0" * 64 if tamper else hashlib.sha256(artifact_bytes).hexdigest()),
        "evaluation_report_sha256": report_digest,
    }
    route.FORECAST_FACT_MANIFEST_PATH.write_text(json.dumps(manifest), encoding="utf-8")


def test_forecast_fact_requires_authentication(client, forecast_fact_route):
    assert client.get("/api/forecast-fact").status_code == 401


def test_rejected_release_keeps_forecast_fact_unavailable_and_test_sealed(
    client, forecast_fact_route
):
    report = _published_report()
    report.update(status="rejected", reason_code="validation_rejected", test_metrics=None)
    forecast_fact_route.EVALUATION_REPORT_PATH.write_text(json.dumps(report), encoding="utf-8")

    response = _authorize(client)

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "reason_code": "forecast_fact_unavailable",
    }


def test_published_release_exposes_only_integrity_bound_anonymized_evidence(
    client, forecast_fact_route
):
    _write_evidence(forecast_fact_route)

    response = _authorize(client)

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "v12"
    assert payload["source_split"] == "final_test"
    assert payload["metrics"] == pytest.approx(_metrics())
    assert {row["confusion"] for row in payload["rows"]} == {"TP", "FP", "FN", "TN"}
    assert all(row["id"].startswith("ff_") for row in payload["rows"])


def test_tampered_or_release_mismatched_evidence_fails_closed(client, forecast_fact_route):
    _write_evidence(forecast_fact_route, tamper=True)
    assert _authorize(client).status_code == 503

    _write_evidence(forecast_fact_route)
    artifact = json.loads(forecast_fact_route.FORECAST_FACT_PATH.read_text(encoding="utf-8"))
    artifact["version"] = "v11"
    forecast_fact_route.FORECAST_FACT_PATH.write_text(json.dumps(artifact), encoding="utf-8")
    assert _authorize(client).status_code == 503

