"""Детерминированное сравнение моделей на хронологических выборках."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from typing import Any

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.inspection import permutation_importance

from forpost_prediction_core.candidates import (
    CANDIDATE_COMPLEXITY,
    build_candidate_estimators,
    candidate_model_format,
)
from forpost_prediction_core.errors import TrainingUnavailableError
from forpost_prediction_core.evaluation import (
    BinaryMetrics,
    EvaluationUnavailableError,
    evaluate_binary_probabilities,
    select_operating_threshold,
)
from forpost_prediction_core.splits import make_rolling_origin_folds
from forpost_prediction_core.validation_diagnostics import empty_diagnostics


@dataclass
class TrainingEvidence:
    """Снимок уже вычисленных доказательств без test-метрик и исходных строк."""

    stage: str = "training"
    split_sizes: dict[str, int] | None = None
    baseline_validation_pr_auc: float | None = None
    validation_metrics: BinaryMetrics | None = None
    threshold: float | None = None
    champion_name: str | None = None
    rolling_folds: tuple[FoldMetrics, ...] = ()
    rolling_fold_sizes: tuple[dict[str, int], ...] = ()
    operating_profiles: dict[str, OperatingProfile] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=empty_diagnostics)


@dataclass(frozen=True)
class ProfileConstraints:
    name: str
    minimum_precision: float
    minimum_recall: float
    maximum_alert_rate: float


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
    minimum_validation_folds: int = 3
    validation_points_per_fold: int = 4
    operating_profiles: tuple[ProfileConstraints, ...] | None = None

    def __post_init__(self) -> None:
        if (
            type(self.minimum_validation_folds) is not int
            or self.minimum_validation_folds < 3
            or type(self.validation_points_per_fold) is not int
            or self.validation_points_per_fold < 1
        ):
            raise ValueError("Нужны минимум три rolling folds с целыми временными точками")
        if not self.thresholds or any(not 0 < value < 1 for value in self.thresholds):
            raise ValueError("Пороги должны находиться строго между 0 и 1")
        if {profile.name for profile in self.profiles} != {
            "high_precision",
            "balanced",
            "high_recall",
        } or len(self.profiles) != 3:
            raise ValueError("Требуются три именованных рабочих профиля")
        for profile in self.profiles:
            if (
                not 0 <= profile.minimum_precision <= 1
                or not 0 <= profile.minimum_recall <= 1
                or not 0 < profile.maximum_alert_rate <= 1
            ):
                raise ValueError("Некорректные ограничения рабочего профиля")
        balanced = next(profile for profile in self.profiles if profile.name == "balanced")
        if (balanced.minimum_precision, balanced.minimum_recall, balanced.maximum_alert_rate) != (
            self.minimum_precision,
            self.minimum_recall,
            self.maximum_alert_rate,
        ):
            raise ValueError("Профиль balanced должен совпадать с общим quality gate")

    @property
    def profiles(self) -> tuple[ProfileConstraints, ...]:
        if self.operating_profiles is not None:
            return self.operating_profiles
        return (
            ProfileConstraints(
                "high_precision",
                max(0.85, self.minimum_precision),
                self.minimum_recall,
                self.maximum_alert_rate,
            ),
            ProfileConstraints(
                "balanced", self.minimum_precision, self.minimum_recall, self.maximum_alert_rate
            ),
            ProfileConstraints(
                "high_recall",
                self.minimum_precision,
                max(0.75, self.minimum_recall),
                self.maximum_alert_rate,
            ),
        )


@dataclass(frozen=True)
class FoldMetrics:
    fold_index: int
    threshold: float
    metrics: BinaryMetrics
    baseline_pr_auc: float = 0.0


@dataclass(frozen=True)
class FoldPredictions:
    """Только out-of-time validation-прогнозы; test не передаётся селекторам."""

    fold_index: int
    labels: np.ndarray
    probabilities: np.ndarray
    baseline_pr_auc: float


@dataclass(frozen=True)
class OperatingProfile:
    name: str
    threshold: float
    rolling_folds: tuple[FoldMetrics, ...]


@dataclass(frozen=True)
class CandidateValidation:
    name: str
    threshold: float
    metrics: BinaryMetrics
    rolling_folds: tuple[FoldMetrics, ...] = ()


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
    rolling_folds: tuple[FoldMetrics, ...]
    operating_profiles: dict[str, OperatingProfile]
    model_format: str
    rolling_fold_sizes: tuple[dict[str, int], ...]
    default_profile: str = "balanced"


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


def split_development_and_test(
    frame: pd.DataFrame,
    time_column: str,
    *,
    test_fraction: float,
    purge_hours: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Изолирует финальный период до любого чтения целевых меток."""
    if time_column not in frame or not 0 < test_fraction < 1 or purge_hours < 0:
        raise TrainingUnavailableError("Некорректные параметры финального temporal split")
    ordered = frame.copy()
    ordered[time_column] = pd.to_datetime(ordered[time_column])
    if ordered[time_column].isna().any():
        raise TrainingUnavailableError("Набор содержит неизвестные временные точки")
    ordered = ordered.sort_values(time_column, kind="stable")
    points = ordered[time_column].drop_duplicates().reset_index(drop=True)
    boundary_index = int(len(points) * (1 - test_fraction))
    if not 0 < boundary_index < len(points):
        raise TrainingUnavailableError("Недостаточно временных точек для final test")
    boundary = points.iloc[boundary_index]
    development = ordered.loc[ordered[time_column] < boundary - pd.Timedelta(hours=purge_hours)]
    test = ordered.loc[ordered[time_column] >= boundary]
    if development.empty or test.empty:
        raise TrainingUnavailableError("Embargo оставляет пустую часть final test split")
    return development.reset_index(drop=True), test.reset_index(drop=True)


def _passes(metrics: BinaryMetrics, config: TrainingConfig, baseline: float) -> bool:
    values = [getattr(metrics, field.name) for field in fields(BinaryMetrics)]
    return bool(
        np.isfinite(values).all()
        and np.isfinite(baseline)
        and metrics.precision > config.minimum_precision
        and metrics.recall > config.minimum_recall
        and metrics.alert_rate <= config.maximum_alert_rate
        and metrics.expected_calibration_error <= config.maximum_expected_calibration_error
        and metrics.brier_score <= config.maximum_brier_score
        and metrics.pr_auc > baseline + config.minimum_baseline_pr_auc_delta
    )


def _mean_metrics(folds: tuple[FoldMetrics, ...]) -> BinaryMetrics:
    counts = {"true_positive", "false_positive", "false_negative", "true_negative"}
    return BinaryMetrics(
        **{
            field.name: (
                sum(getattr(fold.metrics, field.name) for fold in folds)
                if field.name in counts
                else float(np.mean([getattr(fold.metrics, field.name) for fold in folds]))
            )
            for field in fields(BinaryMetrics)
        }
    )


def _complexity(name: str) -> tuple[int, int, str]:
    base = name.removesuffix("_sigmoid").removesuffix("_isotonic")
    return CANDIDATE_COMPLEXITY.get(base, 99), int(name.endswith("_isotonic")), name


def rank_fold_candidates(
    results: dict[str, tuple[FoldMetrics, ...]], config: TrainingConfig
) -> CandidateValidation:
    """Сначала worst-fold F1 и mean PR-AUC; при paired-SE ничьей проще модель."""
    eligible = {
        name: folds
        for name, folds in results.items()
        if len(folds) == config.minimum_validation_folds
        and tuple(fold.fold_index for fold in folds) == tuple(range(1, len(folds) + 1))
        and len({fold.threshold for fold in folds}) == 1
        and all(
            0 < fold.threshold < 1 and _passes(fold.metrics, config, fold.baseline_pr_auc)
            for fold in folds
        )
    }
    if not eligible:
        raise TrainingUnavailableError("Ни один кандидат не прошёл все rolling-origin folds")
    best = max(
        sorted(eligible),
        key=lambda name: (
            min(fold.metrics.f1 for fold in eligible[name]),
            float(np.mean([fold.metrics.pr_auc for fold in eligible[name]])),
        ),
    )
    best_folds = eligible[best]
    tied = []
    for name, folds in eligible.items():
        f1_delta = np.array(
            [
                left.metrics.f1 - right.metrics.f1
                for left, right in zip(best_folds, folds, strict=True)
            ]
        )
        auc_delta = np.array(
            [
                left.metrics.pr_auc - right.metrics.pr_auc
                for left, right in zip(best_folds, folds, strict=True)
            ]
        )
        f1_se = float(np.std(f1_delta, ddof=1) / np.sqrt(len(folds)))
        auc_se = float(np.std(auc_delta, ddof=1) / np.sqrt(len(folds)))
        worst_gap = min(fold.metrics.f1 for fold in best_folds) - min(
            fold.metrics.f1 for fold in folds
        )
        if worst_gap <= f1_se + 1e-12 and abs(float(auc_delta.mean())) <= auc_se + 1e-12:
            tied.append(name)
    name = min(tied, key=_complexity)
    folds = eligible[name]
    return CandidateValidation(name, folds[0].threshold, _mean_metrics(folds), folds)


def select_fold_operating_profiles(
    predictions: tuple[FoldPredictions, ...],
    config: TrainingConfig,
    *,
    diagnostics: dict | None = None,
) -> dict[str, OperatingProfile]:
    """Каждый единый порог одобряется во всех validation folds, без медианного суррогата."""
    if len(predictions) != config.minimum_validation_folds or tuple(
        item.fold_index for item in predictions
    ) != tuple(range(1, len(predictions) + 1)):
        raise TrainingUnavailableError("Неполные rolling-origin доказательства")
    candidates = set(config.thresholds)
    probability_boundaries = {0.0, 1.0}
    prepared = []
    for item in predictions:
        metrics = evaluate_binary_probabilities(item.labels, item.probabilities, threshold=0.5)
        candidates.update(float(value) for value in item.probabilities if 0 < value < 1)
        probability_boundaries.update(float(value) for value in item.probabilities)
        positives = np.sort(item.probabilities[item.labels == 1])
        negatives = np.sort(item.probabilities[item.labels == 0])
        prepared.append((item, metrics, positives, negatives))
    # Проверяем и интервалы между scores, включая область выше последнего score < 1.
    boundaries = sorted(probability_boundaries)
    candidates.update(
        midpoint
        for lower, upper in zip(boundaries[:-1], boundaries[1:], strict=True)
        if 0 < (midpoint := lower + (upper - lower) / 2) < 1
    )
    selected: dict[str, OperatingProfile] = {}
    scores: dict[str, tuple[float, float, float, float]] = {}
    diagnostic_scores = {}
    if diagnostics is not None:
        diagnostics.update(thresholds_evaluated=len(candidates), profiles={})
    for threshold in sorted(candidates):
        folds = []
        for item, base, positives, negatives in prepared:
            tp = len(positives) - int(np.searchsorted(positives, threshold, side="left"))
            fp = len(negatives) - int(np.searchsorted(negatives, threshold, side="left"))
            fn, tn = len(positives) - tp, len(negatives) - fp
            precision = tp / (tp + fp) if tp + fp else 0.0
            recall = tp / len(positives)
            metrics = replace(
                base,
                precision=precision,
                recall=recall,
                f1=2 * tp / (2 * tp + fp + fn),
                alert_rate=(tp + fp) / len(item.labels),
                true_positive=tp,
                false_positive=fp,
                false_negative=fn,
                true_negative=tn,
            )
            folds.append(FoldMetrics(item.fold_index, threshold, metrics, item.baseline_pr_auc))
        frozen_folds = tuple(folds)
        for profile in config.profiles:
            if diagnostics is not None:
                _record_profile_diagnostic(
                    diagnostics, diagnostic_scores, profile, frozen_folds, config
                )
            if not all(
                _passes(fold.metrics, config, fold.baseline_pr_auc)
                and fold.metrics.precision > profile.minimum_precision
                and fold.metrics.recall > profile.minimum_recall
                and fold.metrics.alert_rate <= profile.maximum_alert_rate
                for fold in folds
            ):
                continue
            # Профили отличаются целевой метрикой, но каждый сохраняет общий quality gate.
            target = (
                "precision"
                if profile.name == "high_precision"
                else "recall"
                if profile.name == "high_recall"
                else "f1"
            )
            score = (
                min(getattr(fold.metrics, target) for fold in folds),
                min(fold.metrics.f1 for fold in folds),
                float(np.mean([fold.metrics.f1 for fold in folds])),
                threshold,
            )
            if profile.name not in scores or score > scores[profile.name]:
                scores[profile.name] = score
                selected[profile.name] = OperatingProfile(profile.name, threshold, frozen_folds)
    if len(selected) != 3:
        raise TrainingUnavailableError("Не все рабочие профили прошли каждый validation fold")
    return selected


def _record_profile_diagnostic(diagnostics, scores, profile, folds, config):
    """Сохраняет ближайший rejected-порог отдельно от одобренного operating profile."""
    from forpost_prediction_core.evaluation_report import EvaluationMetrics

    failures = []
    for fold in folds:
        metrics = fold.metrics
        checks = {
            "precision": metrics.precision
            > max(config.minimum_precision, profile.minimum_precision),
            "recall": metrics.recall > max(config.minimum_recall, profile.minimum_recall),
            "alert_rate": metrics.alert_rate
            <= min(config.maximum_alert_rate, profile.maximum_alert_rate),
            "calibration": metrics.expected_calibration_error
            <= config.maximum_expected_calibration_error,
            "brier": metrics.brier_score <= config.maximum_brier_score,
            "baseline_delta": metrics.pr_auc
            > fold.baseline_pr_auc + config.minimum_baseline_pr_auc_delta,
        }
        failures.append(tuple(name for name, passed in checks.items() if not passed))
    entry = diagnostics["profiles"].setdefault(
        profile.name, {"feasible_threshold_count": 0, "failure_counts": {}}
    )
    entry["feasible_threshold_count"] += int(not any(failures))
    for gate in sorted({gate for failed in failures for gate in failed}):
        entry["failure_counts"][gate] = entry["failure_counts"].get(gate, 0) + 1
    score = (-sum(map(len, failures)), min(fold.metrics.f1 for fold in folds), folds[0].threshold)
    if profile.name in scores and score <= scores[profile.name]:
        return
    scores[profile.name] = score
    names = EvaluationMetrics.model_fields
    entry.update(
        closest_threshold=folds[0].threshold,
        closest_folds=[
            {
                "index": fold.fold_index,
                "metrics": {name: float(getattr(fold.metrics, name)) for name in names},
                "failed_gates": failed,
            }
            for fold, failed in zip(folds, failures, strict=True)
        ],
        mean_metrics={
            name: float(np.mean([getattr(fold.metrics, name) for fold in folds])) for name in names
        },
        worst_metrics={
            name: float(
                (
                    max
                    if name in {"alert_rate", "brier_score", "expected_calibration_error"}
                    else min
                )(getattr(fold.metrics, name) for fold in folds)
            )
            for name in names
        },
    )


def train_champion(
    frame: pd.DataFrame,
    *,
    label_column: str,
    time_column: str,
    config: TrainingConfig | None = None,
    evidence: TrainingEvidence | None = None,
) -> TrainingResult:
    """Изолирует test, замораживает выбор по rolling folds, затем оценивает test."""
    if evidence is not None:
        evidence.stage = "training"
        evidence.split_sizes = None
        evidence.baseline_validation_pr_auc = None
        evidence.validation_metrics = None
        evidence.threshold = None
        evidence.champion_name = None
        evidence.rolling_folds = ()
        evidence.rolling_fold_sizes = ()
        evidence.operating_profiles = {}
        evidence.diagnostics = empty_diagnostics()
    settings = config or TrainingConfig()
    development, test = split_development_and_test(
        frame,
        time_column,
        test_fraction=settings.test_fraction,
        purge_hours=settings.purge_hours,
    )
    if evidence is not None:
        evidence.diagnostics["step"] = "development_support"
        evidence.diagnostics["development"] = (
            _support(development, label_column, time_column)
            if label_column in development
            else None
        )
    _validate_training_frame(development, label_column, time_column, settings)
    excluded = {label_column, time_column, "object_id"}
    feature_columns = tuple(column for column in frame.columns if column not in excluded)
    if not feature_columns:
        raise TrainingUnavailableError("В наборе отсутствуют допустимые признаки")

    if evidence is not None:
        evidence.diagnostics["step"] = "rolling_split"
    try:
        folds = make_rolling_origin_folds(
            development,
            time_column,
            fold_count=settings.minimum_validation_folds,
            validation_points=settings.validation_points_per_fold,
            purge_hours=settings.purge_hours,
        )
    except ValueError:
        raise TrainingUnavailableError(
            "Недостаточно временных точек для rolling-origin проверки"
        ) from None
    predictions: dict[str, list[FoldPredictions]] = {}
    last_models: dict[str, Any] = {}
    baseline_scores: list[float] = []
    fold_sizes: list[dict[str, int]] = []
    prepared = []
    support_failed = False
    for fold in folds:
        diagnostic = {
            "index": fold.index,
            "fit": None,
            "calibration": None,
            "validation": _support(fold.validation, label_column, time_column),
            "failure_code": None,
        }
        if evidence is not None:
            evidence.diagnostics["step"] = "calibration_split"
            evidence.diagnostics["folds"].append(diagnostic)
        try:
            fit, calibration = _split_fit_calibration(
                fold.train,
                time_column,
                calibration_fraction=settings.calibration_fraction,
                purge_hours=settings.purge_hours,
            )
        except TrainingUnavailableError:
            diagnostic["failure_code"] = "calibration_split_unavailable"
            support_failed = True
            continue
        diagnostic["fit"] = _support(fit, label_column, time_column)
        diagnostic["calibration"] = _support(calibration, label_column, time_column)
        for partition, values in (
            ("fit", fit),
            ("calibration", calibration),
            ("validation", fold.validation),
        ):
            try:
                _require_partition_support(values[label_column].to_numpy(), partition, settings)
            except TrainingUnavailableError:
                diagnostic["failure_code"] = "class_support_insufficient"
                support_failed = True
        prepared.append((fold, fit, calibration))
    if support_failed:
        if evidence is not None:
            evidence.diagnostics["step"] = "partition_support"
        raise TrainingUnavailableError(
            "Rolling folds не имеют достаточной временной/классовой поддержки"
        )
    for fold, fit, calibration in prepared:
        fold_sizes.append(
            {
                "train_rows": len(fit),
                "calibration_rows": len(calibration),
                "validation_rows": len(fold.validation),
            }
        )
        fit_x, calibration_x = fit.loc[:, feature_columns], calibration.loc[:, feature_columns]
        validation_x = fold.validation.loc[:, feature_columns]
        validation_y = fold.validation[label_column].to_numpy(dtype=np.int8)
        baseline_score = evaluate_binary_probabilities(
            validation_y,
            np.full(len(validation_y), fit[label_column].mean()),
            threshold=0.5,
        ).pr_auc
        baseline_scores.append(baseline_score)
        if evidence is not None:
            evidence.split_sizes = {
                "fit": len(fit),
                "calibration": len(calibration),
                "validation": sum(len(item.validation) for item in folds),
                "test": len(test),
            }
            evidence.baseline_validation_pr_auc = float(np.mean(baseline_scores))
        for name, estimator in build_candidate_estimators(fit_x, settings.seed).items():
            if evidence is not None:
                evidence.diagnostics["step"] = "candidate_fit"
            estimator.fit(fit_x, fit[label_column].to_numpy(dtype=np.int8))
            for method in ("isotonic", "sigmoid"):
                if evidence is not None:
                    evidence.diagnostics["step"] = "calibration"
                calibrated = _calibrate(estimator, calibration_x, calibration[label_column], method)
                candidate_name = f"{name}_{method}"
                predictions.setdefault(candidate_name, []).append(
                    FoldPredictions(
                        fold.index,
                        validation_y,
                        calibrated.predict_proba(validation_x)[:, 1],
                        baseline_score,
                    )
                )
                if fold is folds[-1]:
                    last_models[candidate_name] = calibrated

    if evidence is not None:
        evidence.stage = "validation"
        evidence.diagnostics["step"] = "validation_selection"
    profiles_by_candidate: dict[str, dict[str, OperatingProfile]] = {}
    for name, values in predictions.items():
        diagnostic = {}
        if evidence is not None:
            evidence.diagnostics["candidates"][name] = diagnostic
        try:
            profiles_by_candidate[name] = select_fold_operating_profiles(
                tuple(values), settings, diagnostics=diagnostic if evidence is not None else None
            )
        except TrainingUnavailableError:
            continue
    champion = rank_fold_candidates(
        {
            name: profiles["balanced"].rolling_folds
            for name, profiles in profiles_by_candidate.items()
        },
        settings,
    )
    # Importance использует ещё не переобученную модель последнего fold.
    importance = permutation_importance(
        last_models[champion.name],
        folds[-1].validation.loc[:, feature_columns],
        folds[-1].validation[label_column].to_numpy(dtype=np.int8),
        scoring="average_precision",
        n_repeats=3,
        random_state=settings.seed,
        n_jobs=1,
    )
    if evidence is not None:
        evidence.diagnostics["step"] = "refit"
    fit, calibration = _split_fit_calibration(
        development,
        time_column,
        calibration_fraction=settings.calibration_fraction,
        purge_hours=settings.purge_hours,
    )
    _require_partition_support(fit[label_column].to_numpy(), "fit", settings)
    _require_partition_support(calibration[label_column].to_numpy(), "calibration", settings)
    name, method = champion.name.rsplit("_", 1)
    estimator = build_candidate_estimators(fit.loc[:, feature_columns], settings.seed)[name]
    estimator.fit(fit.loc[:, feature_columns], fit[label_column].to_numpy(dtype=np.int8))
    champion_model = _calibrate(
        estimator, calibration.loc[:, feature_columns], calibration[label_column], method
    )
    if evidence is not None:
        evidence.validation_metrics = champion.metrics
        evidence.threshold = champion.threshold
        evidence.champion_name = champion.name
        evidence.rolling_folds = champion.rolling_folds
        evidence.rolling_fold_sizes = tuple(fold_sizes)
        evidence.operating_profiles = profiles_by_candidate[champion.name]
        evidence.stage = "test"
        evidence.diagnostics["step"] = "frozen_test"
        evidence.split_sizes = {
            "fit": len(fit),
            "calibration": len(calibration),
            "validation": sum(len(item.validation) for item in folds),
            "test": len(test),
        }
    _validate_training_frame(test, label_column, time_column, settings)
    test_x = test.loc[:, feature_columns]
    test_y = test[label_column].to_numpy(dtype=np.int8)
    _require_partition_support(test_y, "test", settings)
    test_probabilities = champion_model.predict_proba(test_x)[:, 1]
    test_metrics = evaluate_binary_probabilities(
        test_y, test_probabilities, threshold=champion.threshold
    )
    baseline_test_metrics = evaluate_binary_probabilities(
        test_y,
        np.full(len(test_y), fit[label_column].mean()),
        threshold=max(settings.thresholds),
    )
    _require_quality_gate(test_metrics, settings, baseline_test_metrics.pr_auc)
    return TrainingResult(
        champion_name=champion.name,
        threshold=champion.threshold,
        validation_metrics=champion.metrics,
        test_metrics=test_metrics,
        validation_row_count=sum(len(item.validation) for item in folds),
        test_row_count=len(test),
        fit_row_count=len(fit),
        calibration_row_count=len(calibration),
        model=champion_model,
        feature_columns=feature_columns,
        feature_importances={
            name: float(value)
            for name, value in zip(feature_columns, importance.importances_mean, strict=True)
        },
        baseline_validation_pr_auc=float(np.mean(baseline_scores)),
        rolling_folds=champion.rolling_folds,
        operating_profiles=profiles_by_candidate[champion.name],
        model_format=candidate_model_format(champion.name),
        rolling_fold_sizes=tuple(fold_sizes),
    )


def _support(frame: pd.DataFrame, label_column: str, time_column: str) -> dict[str, int]:
    labels = frame[label_column].to_numpy()
    return {
        "positive": int(np.count_nonzero(labels == 1)),
        "negative": int(np.count_nonzero(labels == 0)),
        "time_points": int(frame[time_column].nunique()),
    }


def _calibrate(estimator: Any, features: pd.DataFrame, labels: pd.Series, method: str) -> Any:
    calibrated = CalibratedClassifierCV(FrozenEstimator(estimator), method=method, ensemble=False)
    return calibrated.fit(features, labels.to_numpy(dtype=np.int8))


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
    if not _passes(metrics, config, baseline_pr_auc):
        raise TrainingUnavailableError("Финальный temporal holdout не прошёл quality gate")
