"""Строгая загрузка единственного локального ML-конфига."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

from forpost_prediction_core.training import ProfileConstraints, TrainingConfig


@dataclass(frozen=True)
class MlConfig:
    seed: int
    feature_schema_version: str
    label_strategy: str
    horizon_hours: int
    cutoff_count: int
    max_training_events: int
    feature_windows_hours: tuple[int, ...]
    training: TrainingConfig
    sha256: str


def load_ml_config(path: Path) -> MlConfig:
    """Читает YAML без неявных defaults и проверяет все поля политики."""
    raw = Path(path).read_bytes()
    try:
        payload = yaml.safe_load(raw)
    except yaml.YAMLError:
        raise ValueError("ML-конфиг содержит некорректный YAML") from None
    required = {
        "seed",
        "feature_schema_version",
        "label_strategy",
        "horizon_hours",
        "cutoff_count",
        "max_training_events",
        "feature_windows_hours",
        "minimum_positive_examples",
        "minimum_negative_examples",
        "validation_fraction",
        "test_fraction",
        "calibration_fraction",
        "purge_hours",
        "thresholds",
        "minimum_precision",
        "minimum_recall",
        "maximum_alert_rate",
        "maximum_expected_calibration_error",
        "maximum_brier_score",
        "minimum_baseline_pr_auc_delta",
        "minimum_validation_folds",
        "validation_points_per_fold",
        "operating_profiles",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError("ML-конфиг не соответствует фиксированной схеме")
    if payload["label_strategy"] != "silence_horizon_proxy":
        raise ValueError("Неутверждённая стратегия proxy-разметки")
    for key in ("minimum_validation_folds", "validation_points_per_fold"):
        if type(payload[key]) is not int:
            raise ValueError("Параметры rolling folds должны быть целыми числами")
    profiles = payload["operating_profiles"]
    if not isinstance(profiles, dict) or set(profiles) != {
        "high_precision",
        "balanced",
        "high_recall",
    }:
        raise ValueError("Неизвестная схема рабочих профилей")
    constraints = {"minimum_precision", "minimum_recall", "maximum_alert_rate"}
    if any(
        not isinstance(profile, dict)
        or set(profile) != constraints
        or any(type(value) not in (int, float) for value in profile.values())
        for profile in profiles.values()
    ):
        raise ValueError("Некорректные ограничения рабочих профилей")
    training = TrainingConfig(
        seed=int(payload["seed"]),
        validation_fraction=float(payload["validation_fraction"]),
        test_fraction=float(payload["test_fraction"]),
        calibration_fraction=float(payload["calibration_fraction"]),
        purge_hours=int(payload["purge_hours"]),
        thresholds=tuple(float(value) for value in payload["thresholds"]),
        minimum_precision=float(payload["minimum_precision"]),
        minimum_recall=float(payload["minimum_recall"]),
        maximum_alert_rate=float(payload["maximum_alert_rate"]),
        minimum_positive_examples=int(payload["minimum_positive_examples"]),
        minimum_negative_examples=int(payload["minimum_negative_examples"]),
        maximum_expected_calibration_error=float(payload["maximum_expected_calibration_error"]),
        maximum_brier_score=float(payload["maximum_brier_score"]),
        minimum_baseline_pr_auc_delta=float(payload["minimum_baseline_pr_auc_delta"]),
        minimum_validation_folds=payload["minimum_validation_folds"],
        validation_points_per_fold=payload["validation_points_per_fold"],
        operating_profiles=tuple(
            ProfileConstraints(name=name, **profile) for name, profile in profiles.items()
        ),
    )
    horizon = int(payload["horizon_hours"])
    if horizon < 24 or training.purge_hours < horizon:
        raise ValueError("Embargo не может быть короче горизонта прогноза")
    windows = tuple(int(value) for value in payload["feature_windows_hours"])
    if not windows or any(value < 1 for value in windows):
        raise ValueError("Окна признаков должны быть положительными")
    return MlConfig(
        seed=training.seed,
        feature_schema_version=str(payload["feature_schema_version"]),
        label_strategy=str(payload["label_strategy"]),
        horizon_hours=horizon,
        cutoff_count=int(payload["cutoff_count"]),
        max_training_events=int(payload["max_training_events"]),
        feature_windows_hours=windows,
        training=training,
        sha256=hashlib.sha256(raw).hexdigest(),
    )
