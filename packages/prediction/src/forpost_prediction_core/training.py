"""Детерминированное сравнение моделей на хронологических выборках."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from forpost_prediction_core.evaluation import (
    BinaryMetrics,
    EvaluationUnavailableError,
    evaluate_binary_probabilities,
    select_operating_threshold,
)
from forpost_prediction_core.splits import split_by_time


class TrainingUnavailableError(ValueError):
    """Набор или кандидаты не позволяют честно опубликовать модель."""


@dataclass
class TrainingEvidence:
    """Снимок уже вычисленных доказательств без test-метрик и исходных строк."""

    stage: str = "training"
    split_sizes: dict[str, int] | None = None
    baseline_validation_pr_auc: float | None = None
    validation_metrics: BinaryMetrics | None = None
    threshold: float | None = None
    champion_name: str | None = None


@dataclass(frozen=True)
class TrainingConfig:
    seed: int = 20260915
    validation_fraction: float = 0.2
    test_fraction: float = 0.2
    calibration_fraction: float = 0.2
    purge_hours: int = 24
    thresholds: tuple[float, ...] = tuple(np.linspace(0.1, 0.9, 17))
    minimum_precision: float = 0.7
    minimum_recall: float = 0.5
    maximum_alert_rate: float = 0.35
    minimum_positive_examples: int = 50
    minimum_negative_examples: int = 50
    maximum_expected_calibration_error: float = 0.2
    maximum_brier_score: float = 0.25
    minimum_baseline_pr_auc_delta: float = 0.01


@dataclass(frozen=True)
class CandidateValidation:
    name: str
    threshold: float
    metrics: BinaryMetrics


@dataclass(frozen=True)
class TrainingResult:
    champion_name: str
    threshold: float
    validation_metrics: BinaryMetrics
    test_metrics: BinaryMetrics
    validation_row_count: int
    test_row_count: int
    fit_row_count: int
    calibration_row_count: int
    model: Any
    feature_columns: tuple[str, ...]
    feature_importances: dict[str, float]
    baseline_validation_pr_auc: float


def rank_candidates(
    labels: np.ndarray,
    candidate_probabilities: dict[str, np.ndarray],
    config: TrainingConfig,
    *,
    baseline_pr_auc: float = 0.0,
) -> CandidateValidation:
    """Выбирает кандидата по validation без доступа к будущему test."""
    valid: list[CandidateValidation] = []
    for name in sorted(candidate_probabilities):
        try:
            selected = select_operating_threshold(
                labels,
                candidate_probabilities[name],
                thresholds=config.thresholds,
                minimum_precision=config.minimum_precision,
                minimum_recall=config.minimum_recall,
                maximum_alert_rate=config.maximum_alert_rate,
            )
        except EvaluationUnavailableError:
            continue
        if (
            selected.metrics.expected_calibration_error > config.maximum_expected_calibration_error
            or selected.metrics.brier_score > config.maximum_brier_score
            or selected.metrics.pr_auc <= baseline_pr_auc + config.minimum_baseline_pr_auc_delta
        ):
            continue
        valid.append(
            CandidateValidation(
                name=name,
                threshold=selected.threshold,
                metrics=selected.metrics,
            )
        )
    if not valid:
        raise TrainingUnavailableError("Ни один кандидат не прошёл рабочий quality gate")
    return max(
        valid,
        key=lambda item: (
            item.metrics.f1,
            item.metrics.pr_auc,
            -item.metrics.expected_calibration_error,
            -item.metrics.brier_score,
            item.name,
        ),
    )


def train_champion(
    frame: pd.DataFrame,
    *,
    label_column: str,
    time_column: str,
    config: TrainingConfig | None = None,
    evidence: TrainingEvidence | None = None,
) -> TrainingResult:
    """Обучает кандидатов, выбирает их по validation и один раз оценивает test."""
    if evidence is not None:
        evidence.stage = "training"
        evidence.split_sizes = None
        evidence.baseline_validation_pr_auc = None
        evidence.validation_metrics = None
        evidence.threshold = None
        evidence.champion_name = None
    settings = config or TrainingConfig()
    _validate_training_frame(frame, label_column, time_column, settings)
    split = split_by_time(
        frame,
        time_column,
        validation_fraction=settings.validation_fraction,
        test_fraction=settings.test_fraction,
        purge_hours=settings.purge_hours,
    )
    excluded = {label_column, time_column, "object_id"}
    feature_columns = tuple(column for column in frame.columns if column not in excluded)
    if not feature_columns:
        raise TrainingUnavailableError("В наборе отсутствуют допустимые признаки")

    fit, calibration = _split_fit_calibration(
        split.train,
        time_column,
        calibration_fraction=settings.calibration_fraction,
        purge_hours=settings.purge_hours,
    )
    fit_x = fit.loc[:, feature_columns]
    calibration_x = calibration.loc[:, feature_columns]
    validation_x = split.validation.loc[:, feature_columns]
    test_x = split.test.loc[:, feature_columns]
    fit_y = fit[label_column].to_numpy(dtype=np.int8)
    calibration_y = calibration[label_column].to_numpy(dtype=np.int8)
    validation_y = split.validation[label_column].to_numpy(dtype=np.int8)
    test_y = split.test[label_column].to_numpy(dtype=np.int8)
    _require_partition_support(fit_y, "fit", settings)
    _require_partition_support(calibration_y, "calibration", settings)
    _require_partition_support(validation_y, "validation", settings)
    _require_partition_support(test_y, "test", settings)

    if evidence is not None:
        evidence.split_sizes = {
            "fit": len(fit),
            "calibration": len(calibration),
            "validation": len(split.validation),
            "test": len(split.test),
        }

    fitted: dict[str, Any] = {}
    validation_probabilities: dict[str, np.ndarray] = {}
    estimators = _candidate_estimators(fit_x, settings.seed)
    baseline = estimators.pop("dummy_prior")
    baseline.fit(fit_x, fit_y)
    baseline_probabilities = baseline.predict_proba(validation_x)[:, 1]
    baseline_metrics = evaluate_binary_probabilities(
        validation_y,
        baseline_probabilities,
        threshold=max(settings.thresholds),
    )
    if evidence is not None:
        evidence.baseline_validation_pr_auc = baseline_metrics.pr_auc
    for name, estimator in estimators.items():
        estimator.fit(fit_x, fit_y)
        for calibration_method in ("isotonic", "sigmoid"):
            calibrated = CalibratedClassifierCV(
                FrozenEstimator(estimator),
                method=calibration_method,
                ensemble=False,
            )
            calibrated.fit(calibration_x, calibration_y)
            candidate_name = f"{name}_{calibration_method}"
            fitted[candidate_name] = calibrated
            validation_probabilities[candidate_name] = calibrated.predict_proba(validation_x)[:, 1]

    if evidence is not None:
        evidence.stage = "validation"
    champion = rank_candidates(
        validation_y,
        validation_probabilities,
        settings,
        baseline_pr_auc=baseline_metrics.pr_auc,
    )
    if evidence is not None:
        evidence.validation_metrics = champion.metrics
        evidence.threshold = champion.threshold
        evidence.champion_name = champion.name
        evidence.stage = "test"
    champion_model = fitted[champion.name]
    test_probabilities = champion_model.predict_proba(test_x)[:, 1]
    test_metrics = evaluate_binary_probabilities(
        test_y, test_probabilities, threshold=champion.threshold
    )
    baseline_test_metrics = evaluate_binary_probabilities(
        test_y,
        baseline.predict_proba(test_x)[:, 1],
        threshold=max(settings.thresholds),
    )
    _require_quality_gate(test_metrics, settings, baseline_test_metrics.pr_auc)
    importance = permutation_importance(
        champion_model,
        validation_x,
        validation_y,
        scoring="average_precision",
        n_repeats=3,
        random_state=settings.seed,
        n_jobs=1,
    )
    return TrainingResult(
        champion_name=champion.name,
        threshold=champion.threshold,
        validation_metrics=champion.metrics,
        test_metrics=test_metrics,
        validation_row_count=len(split.validation),
        test_row_count=len(split.test),
        fit_row_count=len(fit),
        calibration_row_count=len(calibration),
        model=champion_model,
        feature_columns=feature_columns,
        feature_importances={
            name: float(value)
            for name, value in zip(feature_columns, importance.importances_mean, strict=True)
        },
        baseline_validation_pr_auc=baseline_metrics.pr_auc,
    )


def _candidate_estimators(frame: pd.DataFrame, seed: int) -> dict[str, Any]:
    numeric_columns = tuple(frame.select_dtypes(include=["number", "bool"]).columns)
    categorical_columns = tuple(column for column in frame.columns if column not in numeric_columns)

    def preprocessing() -> ColumnTransformer:
        return ColumnTransformer(
            [
                (
                    "numeric",
                    Pipeline(
                        [
                            ("imputer", SimpleImputer(strategy="median")),
                            ("scale", StandardScaler()),
                        ]
                    ),
                    numeric_columns,
                ),
                (
                    "categorical",
                    Pipeline(
                        [
                            ("imputer", SimpleImputer(strategy="most_frequent")),
                            (
                                "one_hot",
                                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                            ),
                        ]
                    ),
                    categorical_columns,
                ),
            ],
            remainder="drop",
        )

    def pipeline(classifier: Any) -> Pipeline:
        return Pipeline([("preprocess", preprocessing()), ("classifier", classifier)])

    return {
        "dummy_prior": Pipeline(
            [
                ("preprocess", preprocessing()),
                ("classifier", DummyClassifier(strategy="prior")),
            ]
        ),
        "extra_trees": pipeline(
            ExtraTreesClassifier(
                n_estimators=160,
                min_samples_leaf=2,
                class_weight="balanced",
                random_state=seed,
                n_jobs=1,
            )
        ),
        "hist_gradient_boosting": pipeline(
            HistGradientBoostingClassifier(
                max_iter=120,
                learning_rate=0.08,
                max_leaf_nodes=15,
                l2_regularization=0.1,
                random_state=seed,
            )
        ),
        "logistic_regression": pipeline(
            LogisticRegression(
                class_weight="balanced",
                max_iter=1000,
                random_state=seed,
            )
        ),
    }


def _validate_training_frame(
    frame: pd.DataFrame, label_column: str, time_column: str, config: TrainingConfig
) -> None:
    if label_column not in frame or time_column not in frame:
        raise TrainingUnavailableError("Набор не содержит метку или точку прогнозирования")
    labels = frame[label_column].to_numpy()
    if not np.isin(labels, (0, 1)).all():
        raise TrainingUnavailableError("Целевая метка должна быть бинарной")
    positives = int(np.count_nonzero(labels == 1))
    negatives = int(np.count_nonzero(labels == 0))
    if positives < config.minimum_positive_examples:
        raise TrainingUnavailableError("Недостаточно примеров положительного класса")
    if negatives < config.minimum_negative_examples:
        raise TrainingUnavailableError("Недостаточно примеров отрицательного класса")


def _require_partition_support(labels: np.ndarray, partition: str, config: TrainingConfig) -> None:
    positives = int(np.count_nonzero(labels == 1))
    negatives = int(np.count_nonzero(labels == 0))
    if positives == 0 or negatives == 0:
        raise TrainingUnavailableError(f"В части {partition} отсутствует один из классов")
    if positives < config.minimum_positive_examples:
        raise TrainingUnavailableError(
            f"В части {partition} недостаточно примеров положительного класса"
        )
    if negatives < config.minimum_negative_examples:
        raise TrainingUnavailableError(
            f"В части {partition} недостаточно примеров отрицательного класса"
        )


def _split_fit_calibration(
    frame: pd.DataFrame,
    time_column: str,
    *,
    calibration_fraction: float,
    purge_hours: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not 0 < calibration_fraction < 0.5:
        raise TrainingUnavailableError("Доля calibration должна быть от 0 до 0.5")
    ordered = frame.sort_values(time_column, kind="stable").reset_index(drop=True)
    times = pd.to_datetime(ordered[time_column]).drop_duplicates().reset_index(drop=True)
    target_calibration_index = int(len(times) * (1 - calibration_fraction))
    if target_calibration_index < 1 or target_calibration_index >= len(times):
        raise TrainingUnavailableError("Недостаточно временных точек для calibration")
    purge = pd.Timedelta(hours=purge_hours)
    first_calibration_index = int(times.searchsorted(times.iloc[0] + purge, side="right"))
    calibration_index = max(target_calibration_index, first_calibration_index)
    if calibration_index >= len(times):
        raise TrainingUnavailableError("Embargo оставил пустую fit/calibration часть")
    calibration_start = times.iloc[calibration_index]
    fit = ordered.loc[pd.to_datetime(ordered[time_column]) < calibration_start - purge].copy()
    calibration = ordered.loc[pd.to_datetime(ordered[time_column]) >= calibration_start].copy()
    if fit.empty or calibration.empty:
        raise TrainingUnavailableError("Embargo оставил пустую fit/calibration часть")
    return fit.reset_index(drop=True), calibration.reset_index(drop=True)


def _require_quality_gate(
    metrics: BinaryMetrics, config: TrainingConfig, baseline_pr_auc: float
) -> None:
    if (
        metrics.precision <= config.minimum_precision
        or metrics.recall <= config.minimum_recall
        or metrics.alert_rate > config.maximum_alert_rate
        or metrics.expected_calibration_error > config.maximum_expected_calibration_error
        or metrics.brier_score > config.maximum_brier_score
        or metrics.pr_auc <= baseline_pr_auc + config.minimum_baseline_pr_auc_delta
    ):
        raise TrainingUnavailableError("Финальный temporal holdout не прошёл quality gate")
