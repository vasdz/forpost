import json
import os
import stat
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
from pydantic import ValidationError
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression


def _features():
    return pd.DataFrame({"hours_since_last_event": [0.0, 1.0, 2.0, 3.0]})


def _calibrated_model():
    features = _features()
    labels = np.array([0, 0, 1, 1])
    estimator = LogisticRegression(random_state=7).fit(features, labels)
    return CalibratedClassifierCV(FrozenEstimator(estimator), ensemble=False, cv=2).fit(
        features, labels
    )


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
    model = _calibrated_model()
    card = _model_card()

    bundle_path = publish_model_bundle(tmp_path, model, card, parity_features=_features())
    loaded = load_model_bundle(
        bundle_path,
        expected_task=PredictionTask.SENSOR_FAILURE,
        expected_feature_schema_version="6",
        maximum_evidence_tier=EvidenceTier.PROXY,
    )

    assert loaded.card == card
    assert loaded.model.predict(_features().tail(1)).tolist() == [1]
    assert (bundle_path / "model.skops").is_file()
    assert (bundle_path / "model-card.json").is_file()
    assert (bundle_path / "manifest.json").is_file()


def test_registry_rejects_tampered_model_artifact(tmp_path: Path) -> None:
    """Ловит подмену артефакта после проверки качества модели."""
    model = _calibrated_model()
    bundle_path = publish_model_bundle(tmp_path, model, _model_card(), parity_features=_features())
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
    model = _calibrated_model()
    bundle_path = publish_model_bundle(tmp_path, model, _model_card(), parity_features=_features())

    with pytest.raises(ModelUnavailableError, match="доказательност"):
        load_model_bundle(
            bundle_path,
            expected_task=PredictionTask.SENSOR_FAILURE,
            expected_feature_schema_version="6",
            maximum_evidence_tier=EvidenceTier.VALIDATED,
        )


def test_prediction_export_is_published_with_integrity_manifest(tmp_path: Path) -> None:
    model = _calibrated_model()
    bundle = publish_model_release(
        tmp_path,
        model,
        _model_card(),
        {"predictions": []},
        parity_features=_features(),
    )

    manifest = json.loads((bundle / "predictions-manifest.json").read_text(encoding="utf-8"))
    assert manifest["task"] == "sensor_failure"
    assert manifest["version"] == "v1"
    assert len(manifest["sha256"]) == 64
    assert len(manifest["model_card_sha256"]) == 64


def test_release_rejects_prediction_task_mismatch_before_creating_version(
    tmp_path: Path,
) -> None:
    model = _calibrated_model()
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
        publish_model_release(tmp_path, model, _model_card(), payload, parity_features=_features())

    assert not (tmp_path / "sensor_failure" / "v1").exists()


def test_bare_native_candidate_without_preprocessing_and_calibration_cannot_publish(tmp_path):
    from forpost_prediction_core.candidates import NativeBoosterClassifier

    with pytest.raises(ModelUnavailableError):
        publish_model_bundle(
            tmp_path,
            NativeBoosterClassifier("catboost"),
            _model_card(),
            parity_features=_features(),
        )
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
            validation_points_per_fold=8,
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
    from forpost_prediction_core.evaluation_report import validation_evidence_payload

    audit = _audit_fields(
        fit_rows=result.fit_row_count,
        calibration_rows=result.calibration_row_count,
        validation_rows=result.validation_row_count,
        test_rows=result.test_row_count,
    )
    audit.update(validation_evidence_payload(result))
    audit["model_format"] = result.model_format
    card = ModelCard(
        task=PredictionTask.SENSOR_FAILURE,
        version="v1",
        feature_schema_version="6",
        evidence_tier=EvidenceTier.PROXY,
        calibrated=True,
        created_at=datetime(2026, 9, 18, tzinfo=UTC),
        threshold=result.threshold,
        feature_columns=result.feature_columns,
        validation_metrics=_metric_payload(result.validation_metrics),
        test_metrics=_metric_payload(result.test_metrics),
        **audit,
    )

    bundle_path = publish_model_bundle(
        tmp_path,
        result.model,
        card,
        parity_features=pd.DataFrame(rows).loc[:, result.feature_columns],
    )
    loaded = load_model_bundle(
        bundle_path,
        expected_task=PredictionTask.SENSOR_FAILURE,
        expected_feature_schema_version="6",
        maximum_evidence_tier=EvidenceTier.PROXY,
    )

    assert loaded.card == card
    assert hasattr(loaded.model, "predict_proba")


def _model_card() -> ModelCard:
    return ModelCard(
        task=PredictionTask.SENSOR_FAILURE,
        version="v1",
        feature_schema_version="6",
        evidence_tier=EvidenceTier.PROXY,
        calibrated=True,
        created_at=datetime(2026, 9, 18, tzinfo=UTC),
        threshold=0.7,
        feature_columns=("hours_since_last_event",),
        validation_metrics=_complete_metrics(precision=0.8, recall=0.7, f1=0.75),
        test_metrics=_complete_metrics(precision=0.78, recall=0.68, f1=0.72),
        **_audit_fields(),
    )


def test_model_card_rejects_non_current_feature_schema() -> None:
    payload = _model_card().model_dump(mode="python")
    payload["feature_schema_version"] = "7"

    with pytest.raises(ValidationError):
        ModelCard.model_validate(payload)


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
    validation_rows: int = 60,
    test_rows: int = 20,
) -> dict[str, object]:
    return {
        "format_version": 2,
        "model_format": "skops",
        "task_semantics": "risk_of_unexpected_telemetry_silence_within_horizon",
        "rolling_folds": [
            {
                "index": index,
                "train_rows": 100,
                "calibration_rows": 20,
                "validation_rows": 20,
                "threshold": 0.7,
                "metrics": _complete_metrics(precision=0.8, recall=0.7, f1=0.75),
            }
            for index in range(1, 4)
        ],
        "operating_profiles": {
            name: {"threshold": 0.7, "precision": 0.8, "recall": 0.7, "alert_rate": 0.12}
            for name in ("high_precision", "balanced", "high_recall")
        },
        "validation_confidence_intervals": {
            name: {
                "lower": value,
                "upper": value,
                "level": 0.95,
                "method": "student_t_across_rolling_folds",
            }
            for name, value in _complete_metrics(precision=0.8, recall=0.7, f1=0.75).items()
        },
        "label_strategy": "cadence_adjusted_silence_horizon_proxy_v2",
        "horizon_hours": 24,
        "purge_hours": 24,
        "config_sha256": "a" * 64,
        "library_versions": {
            "numpy": "2.0.0",
            "pandas": "2.2.0",
            "scikit-learn": "1.9.1",
            "skops": "0.15.0",
            "catboost": "1.2.10",
            "lightgbm": "4.6.0",
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


@pytest.mark.parametrize(
    "backend,model_format", [("catboost", "catboost_cbm"), ("lightgbm", "lightgbm_text")]
)
@pytest.mark.parametrize("method", ["isotonic", "sigmoid"])
def test_native_calibrated_composite_roundtrip_preserves_pipeline(
    tmp_path, backend, model_format, method
):
    from forpost_prediction_core.candidates import build_candidate_estimators

    features = pd.DataFrame({"value": np.tile([0.0, 1.0], 40), "kind": ["a", "b"] * 40})
    labels = np.tile([0, 1], 40)
    estimator = build_candidate_estimators(features, 73)[backend].fit(features, labels)
    model = CalibratedClassifierCV(FrozenEstimator(estimator), method=method, ensemble=False).fit(
        features, labels
    )
    card = _model_card().model_copy(
        update={"model_format": model_format, "feature_columns": ("value", "kind")}
    )
    probe = features.iloc[:4].assign(kind="unseen", value=[np.nan, 1.0, 0.0, 0.25])
    bundle = publish_model_bundle(tmp_path, model, card, parity_features=probe)
    restored = _load(bundle)
    np.testing.assert_allclose(
        restored.model.predict_proba(probe), model.predict_proba(probe), rtol=1e-10, atol=1e-12
    )
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert manifest["model_format"] == model_format
    assert set(manifest["files"]) == {
        "model-card.json",
        "preprocess.skops",
        "calibration.skops",
        "model.cbm" if backend == "catboost" else "model.txt",
    }


def _load(path):
    return load_model_bundle(
        path,
        expected_task=PredictionTask.SENSOR_FAILURE,
        expected_feature_schema_version="6",
        maximum_evidence_tier=EvidenceTier.PROXY,
    )


def test_release_requires_roundtrip_parity_before_creating_version(tmp_path, monkeypatch):
    from forpost_prediction_core import registry

    original = registry.skops_io.loads

    def broken(*args, **kwargs):
        restored = original(*args, **kwargs)
        restored.calibrated_classifiers_[0].calibrators[0].a_ *= -1
        return restored

    monkeypatch.setattr(registry.skops_io, "loads", broken)
    with pytest.raises(ModelUnavailableError):
        publish_model_bundle(
            tmp_path, _calibrated_model(), _model_card(), parity_features=_features()
        )
    assert not (tmp_path / "sensor_failure" / "v1").exists()


@pytest.mark.parametrize("artifact", ["manifest.json", "model-card.json", "model.skops"])
@pytest.mark.parametrize("attack", ["directory", "oversized", "symlink"])
def test_registry_rejects_unsafe_files_before_deserialization(
    tmp_path, artifact, attack, monkeypatch
):
    from forpost_prediction_core import registry

    bundle = publish_model_bundle(
        tmp_path, _calibrated_model(), _model_card(), parity_features=_features()
    )
    target = bundle / artifact
    if attack == "oversized":
        monkeypatch.setattr(registry, "MAX_MODEL_FILE_BYTES", 1)
        monkeypatch.setattr(registry, "MAX_METADATA_BYTES", 1)
    elif attack == "directory":
        target.unlink()
        target.mkdir()
    else:
        original = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda path: path == target or original(path))
    with pytest.raises(ModelUnavailableError):
        _load(bundle)


@pytest.mark.parametrize(
    "field,value",
    [
        ("model_format", "pickle"),
        ("format_version", 1),
        ("feature_schema_version", "wrong"),
        ("task", "fire_risk"),
        ("extra", "unknown"),
    ],
)
def test_manifest_dispatch_is_exact_and_bound_to_card(tmp_path, field, value):
    bundle = publish_model_bundle(
        tmp_path, _calibrated_model(), _model_card(), parity_features=_features()
    )
    path = bundle / "manifest.json"
    payload = json.loads(path.read_text())
    payload[field] = value
    path.write_text(json.dumps(payload))
    with pytest.raises(ModelUnavailableError):
        _load(bundle)


def test_card_v2_rejects_coerced_metadata_and_incomplete_evidence():
    from pydantic import ValidationError

    for field, value in (
        ("rolling_folds", []),
        ("operating_profiles", {}),
        ("horizon_hours", True),
        ("calibrated", "true"),
        ("task_semantics", "physical_failure"),
    ):
        payload = _model_card().model_dump(mode="json")
        payload[field] = value
        with pytest.raises((ValidationError, ModelUnavailableError)):
            ModelCard.model_validate(payload)


def test_final_test_metrics_are_immutable_in_card():
    from pydantic import ValidationError

    card = _model_card()
    with pytest.raises((ValidationError, TypeError, AttributeError)):
        card.test_metrics.precision = 0.1
    with pytest.raises(TypeError):
        card.test_metrics["precision"] = 0.1


@pytest.mark.parametrize("change", ["aggregate", "rows", "profile", "interval"])
def test_card_rejects_contradictory_validation_evidence(change):
    from pydantic import ValidationError

    payload = _model_card().model_dump(mode="json")
    if change == "aggregate":
        payload["validation_metrics"]["precision"] = 0.2
    elif change == "rows":
        payload["validation_row_count"] = 1
    elif change == "profile":
        payload["operating_profiles"]["balanced"]["precision"] = 0.2
    else:
        payload["validation_confidence_intervals"]["precision"]["upper"] = 0.1
    with pytest.raises(ValidationError):
        ModelCard.model_validate(payload)


@pytest.mark.parametrize("component", ["model.cbm", "preprocess.skops", "calibration.skops"])
def test_native_bundle_checks_hashes_for_every_component(tmp_path, component):
    from forpost_prediction_core.candidates import build_candidate_estimators

    features = pd.DataFrame({"hours_since_last_event": np.tile([0.0, 1.0], 40)})
    labels = np.tile([0, 1], 40)
    estimator = build_candidate_estimators(features, 73)["catboost"].fit(features, labels)
    model = CalibratedClassifierCV(FrozenEstimator(estimator), ensemble=False).fit(features, labels)
    card = _model_card().model_copy(update={"model_format": "catboost_cbm"})
    bundle = publish_model_bundle(tmp_path, model, card, parity_features=features)
    with (bundle / component).open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(ModelUnavailableError, match="целостност"):
        _load(bundle)


def test_skops_replacement_after_verification_cannot_change_loaded_model(tmp_path, monkeypatch):
    from forpost_prediction_core import registry

    model = _calibrated_model()
    bundle = publish_model_bundle(tmp_path, model, _model_card(), parity_features=_features())
    replacement = _calibrated_model()
    replacement.calibrated_classifiers_[0].calibrators[0].a_ *= -1
    inspect_types = registry.skops_io.get_untrusted_types

    def replace_after_inspection(*args, **kwargs):
        untrusted = inspect_types(*args, **kwargs)
        registry.skops_io.dump(replacement, bundle / "model.skops")
        return untrusted

    monkeypatch.setattr(registry.skops_io, "get_untrusted_types", replace_after_inspection)
    restored = _load(bundle)
    np.testing.assert_allclose(
        restored.model.predict_proba(_features()),
        model.predict_proba(_features()),
        rtol=1e-10,
        atol=1e-12,
    )


@pytest.mark.parametrize(
    "backend,model_format", [("catboost", "catboost_cbm"), ("lightgbm", "lightgbm_text")]
)
@pytest.mark.parametrize("fail_loading", [False, True])
def test_native_loader_uses_private_verified_snapshot_and_cleans_it(
    tmp_path, monkeypatch, backend, model_format, fail_loading
):
    from forpost_prediction_core.candidates import (
        NativeBoosterClassifier,
        build_candidate_estimators,
    )

    features = pd.DataFrame({"hours_since_last_event": np.tile([0.0, 1.0], 40)})
    labels = np.tile([0, 1], 40)
    estimator = build_candidate_estimators(features, 73)[backend].fit(features, labels)
    model = CalibratedClassifierCV(FrozenEstimator(estimator), ensemble=False).fit(features, labels)
    card = _model_card().model_copy(update={"model_format": model_format})
    bundle = publish_model_bundle(tmp_path, model, card, parity_features=features)
    source = bundle / ("model.cbm" if backend == "catboost" else "model.txt")
    expected_bytes = source.read_bytes()
    load_native = NativeBoosterClassifier.load_native
    snapshot_paths = []

    def replace_original_then_load(path, *, model_format):
        snapshot_paths.append(path)
        source.write_bytes(b"replaced after integrity check")
        assert path != source
        assert path.read_bytes() == expected_bytes
        if os.name == "nt":
            with pytest.raises(PermissionError):
                path.write_bytes(b"snapshot replacement")
            with pytest.raises(PermissionError):
                path.unlink()
        else:
            assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
        if fail_loading:
            raise ValueError("native failure")
        return load_native(path, model_format=model_format)

    monkeypatch.setattr(NativeBoosterClassifier, "load_native", replace_original_then_load)
    if fail_loading:
        with pytest.raises(ModelUnavailableError):
            _load(bundle)
    else:
        restored = _load(bundle)
        np.testing.assert_allclose(
            restored.model.predict_proba(features),
            model.predict_proba(features),
            rtol=1e-10,
            atol=1e-12,
        )
    assert snapshot_paths
    assert all(not path.exists() and not path.parent.exists() for path in snapshot_paths)


def test_model_card_rejects_fabricated_student_t_bounds():
    from pydantic import ValidationError

    payload = _model_card().model_dump(mode="json")
    for fold, value in zip(payload["rolling_folds"], (0.6, 0.7, 0.8), strict=True):
        fold["metrics"]["precision"] = value
    payload["validation_metrics"]["precision"] = 0.7
    payload["operating_profiles"]["balanced"]["precision"] = 0.7
    payload["validation_confidence_intervals"]["precision"].update(
        lower=0.6999999999999998, upper=0.6999999999999998
    )
    with pytest.raises(ValidationError):
        ModelCard.model_validate(payload)
