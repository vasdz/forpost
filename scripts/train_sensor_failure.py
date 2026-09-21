"""Локальное обучение proxy-модели отказа датчика на обезличенной телеметрии."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import TypeAdapter

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for source_path in (
    REPOSITORY_ROOT / "packages" / "domain" / "src",
    REPOSITORY_ROOT / "packages" / "connectors" / "src",
    REPOSITORY_ROOT / "packages" / "prediction" / "src",
):
    if str(source_path) not in sys.path:
        sys.path.insert(0, str(source_path))

from forpost_connectors.local_snapshot import SourceSnapshotError, load_training_window
from forpost_prediction_core.capabilities import EvidenceTier, PredictionTask
from forpost_prediction_core.config import load_ml_config
from forpost_prediction_core.dataset import build_sensor_failure_dataset
from forpost_prediction_core.evaluation_report import (
    EvaluationHorizonHours,
    EvaluationReport,
    EvaluationReportUnavailableError,
    EvaluationVersion,
    QualityThresholds,
    write_evaluation_report,
)
from forpost_prediction_core.registry import (
    ModelCard,
    ModelUnavailableError,
    publish_model_release,
)
from forpost_prediction_core.time_utils import normalize_event_times
from forpost_prediction_core.training import (
    TrainingEvidence,
    TrainingUnavailableError,
    train_champion,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Обучить proxy-модель отказа датчиков")
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "raw" / "extracted",
    )
    parser.add_argument("--registry-root", type=Path, default=REPOSITORY_ROOT / "ml" / "models")
    parser.add_argument("--version", default="v1")
    parser.add_argument(
        "--evaluation-report",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "processed" / "ml-evaluation.json",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    evidence = TrainingEvidence()
    # При отказе версии v1 обозначает только каноническую версию rejected-отчёта.
    report_version = "v1"
    quality_thresholds = None
    horizon_hours = None
    stage = "configuration"
    try:
        report_version = TypeAdapter(EvaluationVersion).validate_python(arguments.version)
        ml_config = load_ml_config(REPOSITORY_ROOT / "ml" / "config.yaml")
        quality_thresholds = QualityThresholds.model_validate(
            {name: getattr(ml_config.training, name) for name in QualityThresholds.model_fields}
        )
        horizon_hours = TypeAdapter(EvaluationHorizonHours).validate_python(ml_config.horizon_hours)
        stage = "source"
        window = load_training_window(arguments.raw_root, max_events=ml_config.max_training_events)
        stage = "dataset"
        events, channels = _to_frames(window.events, window.channels)
        dataset = build_sensor_failure_dataset(
            events,
            channels,
            horizon_hours=ml_config.horizon_hours,
            cutoff_count=ml_config.cutoff_count,
            minimum_history_events=3,
            feature_windows_hours=ml_config.feature_windows_hours,
        )
        stage = "training"
        result = train_champion(
            dataset.drop(columns=["evidence_tier"]),
            label_column="silence_label",
            time_column="prediction_at",
            config=ml_config.training,
            evidence=evidence,
        )
        stage = "inference"
        current = _current_features(
            events,
            channels,
            result.feature_columns,
            ml_config.feature_windows_hours,
        )
        inference_started = time.perf_counter()
        payload = _prediction_payload(
            current,
            result,
            arguments.version,
            horizon_hours=ml_config.horizon_hours,
            history_truncated_before=window.truncated_before,
        )
        inference_duration = time.perf_counter() - inference_started
        if inference_duration >= 300:
            raise TrainingUnavailableError("Время batch inference превышает 5 минут")
        dataset_times = normalize_event_times(dataset["prediction_at"])
        card = ModelCard(
            task=PredictionTask.SENSOR_FAILURE,
            version=arguments.version,
            feature_schema_version=ml_config.feature_schema_version,
            evidence_tier=EvidenceTier.PROXY,
            calibrated=True,
            created_at=datetime.now(UTC),
            threshold=result.threshold,
            feature_columns=result.feature_columns,
            validation_metrics=_public_metrics(result.validation_metrics),
            test_metrics=_public_metrics(result.test_metrics),
            label_strategy=ml_config.label_strategy,
            horizon_hours=ml_config.horizon_hours,
            purge_hours=ml_config.training.purge_hours,
            config_sha256=ml_config.sha256,
            library_versions={
                package: importlib.metadata.version(package)
                for package in ("numpy", "pandas", "scikit-learn", "skops")
            },
            dataset_start_at=dataset_times.min().to_pydatetime(),
            dataset_end_at=dataset_times.max().to_pydatetime(),
            source_event_count=len(window.events),
            skipped_source_event_count=window.skipped_event_count,
            history_truncated_before=window.truncated_before,
            fit_row_count=result.fit_row_count,
            calibration_row_count=result.calibration_row_count,
            validation_row_count=result.validation_row_count,
            test_row_count=result.test_row_count,
            inference_duration_seconds=inference_duration,
        )
        stage = "release"
        publish_model_release(arguments.registry_root, result.model, card, payload)
    except (
        OSError,
        SourceSnapshotError,
        ModelUnavailableError,
        TrainingUnavailableError,
        TypeError,
        ValueError,
    ):
        failure_stage = evidence.stage if stage == "training" else stage
        reason_code = {
            "configuration": "configuration_invalid",
            "source": "source_unavailable",
            "dataset": "dataset_unavailable",
            "training": "training_unavailable",
            "validation": "validation_rejected",
            "test": "test_rejected",
            "inference": "inference_unavailable",
            "release": "release_unavailable",
        }[failure_stage]
        _save_report(
            arguments,
            evidence,
            version=report_version,
            quality_thresholds=quality_thresholds,
            horizon_hours=horizon_hours if stage != "configuration" else None,
            reason_code=reason_code,
        )
        print(f"Обучение не опубликовано: {reason_code}", file=sys.stderr)
        return 1
    if not _save_report(
        arguments,
        evidence,
        version=report_version,
        quality_thresholds=quality_thresholds,
        horizon_hours=horizon_hours,
        result=result,
    ):
        return 1
    summary = {
        "status": "published",
        "task": "sensor_failure",
        "version": arguments.version,
        "champion": result.champion_name,
        "validation": _public_metrics(result.validation_metrics),
        "test": _public_metrics(result.test_metrics),
        "prediction_count": len(payload["predictions"]),
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


def _save_report(
    arguments,
    evidence,
    *,
    version,
    quality_thresholds,
    horizon_hours,
    reason_code=None,
    result=None,
) -> bool:
    """Сохраняет только доступные доказательства, не раскрывая текст исключений."""
    try:
        report = EvaluationReport(
            format_version=1,
            task="sensor_failure",
            version=version,
            status="rejected" if reason_code is not None else "published",
            evidence_tier="proxy",
            label_strategy="silence_horizon_proxy",
            horizon_hours=horizon_hours,
            created_at=datetime.now(UTC),
            reason_code=reason_code,
            quality_thresholds=quality_thresholds,
            split_sizes=evidence.split_sizes,
            baseline_validation_pr_auc=evidence.baseline_validation_pr_auc,
            validation_metrics=(
                _public_metrics(evidence.validation_metrics)
                if evidence.validation_metrics is not None
                else None
            ),
            test_metrics=_public_metrics(result.test_metrics) if result is not None else None,
            threshold=evidence.threshold,
            champion_name=evidence.champion_name,
        )
        write_evaluation_report(arguments.evaluation_report, report)
    except (EvaluationReportUnavailableError, OSError, TypeError, ValueError):
        print("Отчёт оценки не сохранён: evaluation_write_failed", file=sys.stderr)
        return False
    return True


def _to_frames(events, channels) -> tuple[pd.DataFrame, pd.DataFrame]:
    event_frame = pd.DataFrame(
        [
            {
                "channel_id": event.channel_id,
                "observed_at": event.recorded_at,
                "sensor_value": event.sensor_value,
                "is_alarm": event.is_alarm,
                "quality_status": event.quality_code,
                "analysis_eligible": event.analysis_eligible,
            }
            for event in events
        ]
    )
    channel_frame = pd.DataFrame(
        [
            {"channel_id": channel.channel_id, "sensor_type": channel.sensor_type}
            for channel in channels
        ]
    )
    return event_frame, channel_frame


def _public_metrics(metrics) -> dict[str, float]:
    return {
        "precision": float(metrics.precision),
        "recall": float(metrics.recall),
        "f1": float(metrics.f1),
        "pr_auc": float(metrics.pr_auc),
        "roc_auc": float(metrics.roc_auc),
        "brier_score": float(metrics.brier_score),
        "expected_calibration_error": float(metrics.expected_calibration_error),
        "alert_rate": float(metrics.alert_rate),
    }


def _current_features(
    events: pd.DataFrame,
    channels: pd.DataFrame,
    feature_columns: tuple[str, ...],
    feature_windows_hours: tuple[int, ...],
) -> pd.DataFrame:
    from forpost_prediction_core.features import build_channel_features

    observed_at = normalize_event_times(events["observed_at"])
    cutoff = observed_at.max() + pd.Timedelta(seconds=1)
    recent = events.loc[
        observed_at >= cutoff - pd.Timedelta(hours=max(feature_windows_hours))
    ].copy()
    features = build_channel_features(recent, channels, cutoff, windows=feature_windows_hours)
    eligible = (
        recent["analysis_eligible"].fillna(False).astype(bool)
        if "analysis_eligible" in recent
        else pd.Series(True, index=recent.index)
    )
    history_counts = recent.loc[eligible].groupby("channel_id").size()
    features = features.loc[
        features["channel_id"].isin(set(history_counts[history_counts >= 3].index))
    ].copy()
    features["prediction_at"] = cutoff
    if any(column not in features for column in feature_columns):
        raise TrainingUnavailableError("inference не соответствует схеме признаков")
    return features


def _prediction_payload(
    current: pd.DataFrame,
    result,
    version: str,
    *,
    horizon_hours: int,
    history_truncated_before: bool,
) -> dict[str, object]:
    probabilities = result.model.predict_proba(current.loc[:, result.feature_columns])[:, 1]
    selected = np.flatnonzero(probabilities >= result.threshold)
    selected = selected[np.argsort(-probabilities[selected], kind="stable")]
    metrics = _public_metrics(result.test_metrics)
    factors = _factors(result.feature_importances)
    predictions: list[dict[str, object]] = []
    for index in selected:
        probability = float(probabilities[index])
        channel_id = str(current.iloc[index]["channel_id"])
        limitations = [
            "Прокси-метка тишины не подтверждает физический отказ датчика.",
            "Индивидуальный интервал неопределённости не оценён.",
        ]
        if history_truncated_before:
            limitations.append(
                "История слева усечена; признаки рассчитаны только после полного окна прогрева."
            )
        predictions.append(
            {
                "id": f"sensor-failure-{version}-{channel_id}",
                "entity_type": "sensor",
                "entity_id": channel_id,
                "prediction_type": "sensor_failure",
                "probability": probability,
                "anomaly_score": None,
                "evidence_tier": "proxy",
                "calibrated": True,
                "provenance": "derived",
                "confidence": None,
                "model_metrics": {
                    key: metrics[key]
                    for key in ("precision", "recall", "f1", "pr_auc", "brier_score")
                },
                "quality_status": "passed",
                "limitations": limitations,
                "predicted_at": current.iloc[index]["prediction_at"].isoformat(),
                "horizon_hours": horizon_hours,
                "model_version": version,
                "factors": factors,
                "recommended_action": "Проверить связь и назначить внеплановую диагностику датчика.",
                "priority": "high" if probability >= 0.8 else "medium",
                "status": "new",
            }
        )
    return {"predictions": predictions}


def _factors(importances: dict[str, float]) -> list[dict[str, object]]:
    ordered = sorted(importances.items(), key=lambda item: item[1], reverse=True)
    top = [(name, value) for name, value in ordered if math.isfinite(value) and value > 0][:5]
    total = sum(value for _, value in top)
    if not top or total == 0:
        raise TrainingUnavailableError("permutation importance не дал объяснимых факторов")
    return [
        {
            "factor": name,
            "weight": value / total,
            "description": "Глобальный вклад по permutation importance на temporal holdout.",
        }
        for name, value in top
    ]


if __name__ == "__main__":
    raise SystemExit(main())
