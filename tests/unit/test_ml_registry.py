import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from forpost_prediction_core.capabilities import EvidenceTier, PredictionTask
from forpost_prediction_core.registry import (
    ModelCard,
    ModelMetadata,
    ModelUnavailableError,
    load_model_bundle,
    publish_model_bundle,
    publish_model_release,
    validate_model_metadata,
)
from forpost_prediction_core.training import TrainingConfig, train_champion
from sklearn.linear_model import LogisticRegression


def test_metadata_validation_accepts_matching_task_and_feature_schema() -> None:
    """Ловит serving модели с другой задачей или другой схемой признаков."""
    metadata = ModelMetadata(
        task=PredictionTask.SENSOR_FAILURE,
        version="local-test",
        feature_schema_version="1",
        calibrated=True,
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
    )

    validate_model_metadata(
        metadata,
        expected_task=PredictionTask.SENSOR_FAILURE,
        expected_feature_schema_version="1",
    )


def test_metadata_validation_rejects_uncalibrated_or_mismatched_model() -> None:
    """Ловит выдачу raw score как вероятности из несовместимого артефакта."""
    metadata = ModelMetadata(
        task=PredictionTask.FIRE_RISK,
        version="local-test",
        feature_schema_version="2",
        calibrated=False,
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(ModelUnavailableError, match="калибровку"):
        validate_model_metadata(
            metadata,
            expected_task=PredictionTask.FIRE_RISK,
            expected_feature_schema_version="2",
        )
    with pytest.raises(ModelUnavailableError, match="Модель"):
        validate_model_metadata(
            metadata,
            expected_task=PredictionTask.SENSOR_FAILURE,
            expected_feature_schema_version="2",
        )


def test_registry_publishes_and_loads_verified_skops_bundle(tmp_path: Path) -> None:
    """Ловит serving модели без проверенного manifest и безопасного формата."""
    model = LogisticRegression(random_state=7).fit(
        np.array([[0.0], [1.0], [2.0], [3.0]]), np.array([0, 0, 1, 1])
    )
    card = _model_card()

    bundle_path = publish_model_bundle(tmp_path, model, card)
    loaded = load_model_bundle(
        bundle_path,
        expected_task=PredictionTask.SENSOR_FAILURE,
        expected_feature_schema_version="2",
        maximum_evidence_tier=EvidenceTier.PROXY,
    )

    assert loaded.card == card
    assert loaded.model.predict(np.array([[3.0]])).tolist() == [1]
    assert (bundle_path / "model.skops").is_file()
    assert (bundle_path / "model-card.json").is_file()
    assert (bundle_path / "manifest.json").is_file()


def test_registry_rejects_tampered_model_artifact(tmp_path: Path) -> None:
    """Ловит подмену артефакта после проверки качества модели."""
    model = LogisticRegression(random_state=7).fit(
        np.array([[0.0], [1.0], [2.0], [3.0]]), np.array([0, 0, 1, 1])
    )
    bundle_path = publish_model_bundle(tmp_path, model, _model_card())
    with (bundle_path / "model.skops").open("ab") as stream:
        stream.write(b"tampered")

    with pytest.raises(ModelUnavailableError, match="целостност"):
        load_model_bundle(
            bundle_path,
            expected_task=PredictionTask.SENSOR_FAILURE,
            expected_feature_schema_version="2",
            maximum_evidence_tier=EvidenceTier.PROXY,
        )


def test_registry_rejects_evidence_promotion(tmp_path: Path) -> None:
    """Ловит публикацию proxy-модели как модели на подтверждённой разметке."""
    model = LogisticRegression(random_state=7).fit(
        np.array([[0.0], [1.0], [2.0], [3.0]]), np.array([0, 0, 1, 1])
    )
    bundle_path = publish_model_bundle(tmp_path, model, _model_card())

    with pytest.raises(ModelUnavailableError, match="доказательност"):
        load_model_bundle(
            bundle_path,
            expected_task=PredictionTask.SENSOR_FAILURE,
            expected_feature_schema_version="2",
            maximum_evidence_tier=EvidenceTier.VALIDATED,
        )


def test_prediction_export_is_published_with_integrity_manifest(tmp_path: Path) -> None:
    model = LogisticRegression(random_state=7).fit(
        np.array([[0.0], [1.0], [2.0], [3.0]]), np.array([0, 0, 1, 1])
    )
    bundle = publish_model_release(
        tmp_path,
        model,
        _model_card(),
        {"predictions": []},
    )

    manifest = json.loads((bundle / "predictions-manifest.json").read_text(encoding="utf-8"))
    assert manifest["task"] == "sensor_failure"
    assert manifest["version"] == "v1"
    assert len(manifest["sha256"]) == 64
    assert len(manifest["model_card_sha256"]) == 64


def test_release_rejects_prediction_task_mismatch_before_creating_version(
    tmp_path: Path,
) -> None:
    model = LogisticRegression(random_state=7).fit(
        np.array([[0.0], [1.0], [2.0], [3.0]]), np.array([0, 0, 1, 1])
    )
    payload = {
        "predictions": [
            {
                "prediction_type": "fire_risk",
                "model_version": "v1",
                "evidence_tier": "proxy",
                "calibrated": True,
                "model_metrics": {},
            }
        ]
    }

    with pytest.raises(ModelUnavailableError, match="model card"):
        publish_model_release(tmp_path, model, _model_card(), payload)

    assert not (tmp_path / "sensor_failure" / "v1").exists()


def test_trained_champion_roundtrips_through_secure_registry(tmp_path: Path) -> None:
    rows = []
    for day in range(100):
        for channel in range(4):
            risk = (day + channel) % 8
            rows.append(
                {
                    "prediction_at": pd.Timestamp("2025-01-01") + pd.Timedelta(days=day),
                    "channel_id": f"channel-{channel}",
                    "event_count_24h": float(10 - risk),
                    "hours_since_last_event": float(risk),
                    "label": int(risk >= 6),
                }
            )
    result = train_champion(
        pd.DataFrame(rows),
        label_column="label",
        time_column="prediction_at",
        config=TrainingConfig(
            purge_hours=0,
            thresholds=(0.3, 0.5, 0.7),
            minimum_precision=0.5,
            minimum_recall=0.5,
            maximum_alert_rate=0.6,
            minimum_positive_examples=3,
            minimum_negative_examples=3,
            maximum_expected_calibration_error=1.0,
            maximum_brier_score=1.0,
            minimum_baseline_pr_auc_delta=0.0,
        ),
    )
    card = ModelCard(
        task=PredictionTask.SENSOR_FAILURE,
        version="v1",
        feature_schema_version="2",
        evidence_tier=EvidenceTier.PROXY,
        calibrated=True,
        created_at=datetime(2026, 9, 18, tzinfo=UTC),
        threshold=result.threshold,
        feature_columns=result.feature_columns,
        validation_metrics=_metric_payload(result.validation_metrics),
        test_metrics=_metric_payload(result.test_metrics),
        **_audit_fields(
            fit_rows=result.fit_row_count,
            calibration_rows=result.calibration_row_count,
            validation_rows=result.validation_row_count,
            test_rows=result.test_row_count,
        ),
    )

    bundle_path = publish_model_bundle(tmp_path, result.model, card)
    loaded = load_model_bundle(
        bundle_path,
        expected_task=PredictionTask.SENSOR_FAILURE,
        expected_feature_schema_version="2",
        maximum_evidence_tier=EvidenceTier.PROXY,
    )

    assert loaded.card == card
    assert hasattr(loaded.model, "predict_proba")


def _model_card() -> ModelCard:
    return ModelCard(
        task=PredictionTask.SENSOR_FAILURE,
        version="v1",
        feature_schema_version="2",
        evidence_tier=EvidenceTier.PROXY,
        calibrated=True,
        created_at=datetime(2026, 9, 18, tzinfo=UTC),
        threshold=0.7,
        feature_columns=("hours_since_last_event",),
        validation_metrics=_complete_metrics(precision=0.8, recall=0.7, f1=0.75),
        test_metrics=_complete_metrics(precision=0.78, recall=0.68, f1=0.72),
        **_audit_fields(),
    )


def _metric_payload(metrics) -> dict[str, float]:
    return {
        "precision": metrics.precision,
        "recall": metrics.recall,
        "f1": metrics.f1,
        "pr_auc": metrics.pr_auc,
        "roc_auc": metrics.roc_auc,
        "brier_score": metrics.brier_score,
        "expected_calibration_error": metrics.expected_calibration_error,
        "alert_rate": metrics.alert_rate,
    }


def _complete_metrics(*, precision: float, recall: float, f1: float) -> dict[str, float]:
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "pr_auc": 0.76,
        "roc_auc": 0.8,
        "brier_score": 0.14,
        "expected_calibration_error": 0.08,
        "alert_rate": 0.12,
    }


def _audit_fields(
    *,
    fit_rows: int = 100,
    calibration_rows: int = 20,
    validation_rows: int = 20,
    test_rows: int = 20,
) -> dict[str, object]:
    return {
        "label_strategy": "silence_horizon_proxy",
        "horizon_hours": 24,
        "purge_hours": 24,
        "config_sha256": "a" * 64,
        "library_versions": {
            "numpy": "2.0.0",
            "pandas": "2.2.0",
            "scikit-learn": "1.9.1",
            "skops": "0.15.0",
        },
        "dataset_start_at": datetime(2025, 1, 1, tzinfo=UTC),
        "dataset_end_at": datetime(2026, 1, 1, tzinfo=UTC),
        "source_event_count": 250_000,
        "skipped_source_event_count": 12,
        "history_truncated_before": True,
        "fit_row_count": fit_rows,
        "calibration_row_count": calibration_rows,
        "validation_row_count": validation_rows,
        "test_row_count": test_rows,
        "inference_duration_seconds": 1.0,
    }
