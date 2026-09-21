"""Метрики временного holdout без неявной подмены недоступных результатов."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score


class EvaluationUnavailableError(ValueError):
    """В holdout недостаточно подтверждённых классов для честной оценки."""


@dataclass(frozen=True)
class BinaryMetrics:
    """Набор метрик бинарного прогноза для локального model card."""

    precision: float
    recall: float
    f1: float
    pr_auc: float
    roc_auc: float
    brier_score: float
    expected_calibration_error: float
    alert_rate: float
    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int


@dataclass(frozen=True)
class ThresholdSelection:
    """Рабочий порог, выбранный только на validation-наборе."""

    threshold: float
    metrics: BinaryMetrics


def evaluate_binary_probabilities(
    labels: np.ndarray, probabilities: np.ndarray, *, threshold: float
) -> BinaryMetrics:
    """Считает метрики вероятностной модели на заранее выделенном временном holdout."""
    truth = np.asarray(labels, dtype=np.int8)
    scores = np.asarray(probabilities, dtype=np.float64)
    if truth.ndim != 1 or scores.ndim != 1 or len(truth) != len(scores):
        raise ValueError("Метки и вероятности должны быть одномерными массивами одной длины")
    if not 0 < threshold < 1 or not np.isfinite(threshold):
        raise ValueError("Порог вероятности должен находиться строго между 0 и 1")
    if (
        not np.isin(truth, (0, 1)).all()
        or not np.isfinite(scores).all()
        or not ((scores >= 0) & (scores <= 1)).all()
    ):
        raise ValueError("Оценка требует бинарных меток и конечных вероятностей от 0 до 1")
    positives = int(truth.sum())
    negatives = len(truth) - positives
    if not positives or not negatives:
        raise EvaluationUnavailableError("Для расчёта метрик требуются наблюдения обоих классов")

    predicted = scores >= threshold
    true_positive = int(np.count_nonzero(predicted & (truth == 1)))
    false_positive = int(np.count_nonzero(predicted & (truth == 0)))
    false_negative = int(np.count_nonzero(~predicted & (truth == 1)))
    true_negative = int(np.count_nonzero(~predicted & (truth == 0)))
    precision = (
        true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    )
    recall = true_positive / (true_positive + false_negative)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return BinaryMetrics(
        precision=precision,
        recall=recall,
        f1=f1,
        pr_auc=_average_precision(truth, scores),
        roc_auc=_roc_auc(truth, scores),
        brier_score=float(np.mean((scores - truth) ** 2)),
        expected_calibration_error=_expected_calibration_error(truth, scores),
        alert_rate=float(np.mean(predicted)),
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        true_negative=true_negative,
    )


def select_operating_threshold(
    labels: np.ndarray,
    probabilities: np.ndarray,
    *,
    thresholds: tuple[float, ...],
    minimum_recall: float,
    maximum_alert_rate: float,
    minimum_precision: float = 0.0,
) -> ThresholdSelection:
    """Выбирает лучший F1 среди порогов, допустимых для диспетчерского процесса."""
    if not thresholds:
        raise ValueError("Нужен хотя бы один кандидат рабочего порога")
    if not 0 <= minimum_precision <= 1 or not 0 <= minimum_recall <= 1:
        raise ValueError("Ограничения precision и recall должны быть от 0 до 1")
    if not 0 < maximum_alert_rate <= 1:
        raise ValueError("Допустимая доля тревог должна быть больше 0 и не больше 1")

    observed_scores = np.asarray(probabilities, dtype=np.float64)
    candidate_thresholds = {
        float(value)
        for value in (*thresholds, *observed_scores.tolist())
        if np.isfinite(value) and 0 < float(value) < 1
    }
    candidates: list[ThresholdSelection] = []
    for threshold in sorted(candidate_thresholds):
        metrics = evaluate_binary_probabilities(labels, probabilities, threshold=threshold)
        if (
            metrics.precision > minimum_precision
            and metrics.recall > minimum_recall
            and metrics.alert_rate <= maximum_alert_rate
        ):
            candidates.append(ThresholdSelection(threshold=threshold, metrics=metrics))
    if not candidates:
        raise EvaluationUnavailableError("Не найден рабочий порог для заданных ограничений")
    return max(
        candidates,
        key=lambda item: (
            item.metrics.f1,
            item.metrics.precision,
            item.metrics.recall,
            -item.metrics.alert_rate,
            item.threshold,
        ),
    )


def _average_precision(truth: np.ndarray, scores: np.ndarray) -> float:
    return float(average_precision_score(truth, scores))


def _roc_auc(truth: np.ndarray, scores: np.ndarray) -> float:
    return float(roc_auc_score(truth, scores))


def _expected_calibration_error(
    truth: np.ndarray, scores: np.ndarray, *, bin_count: int = 10
) -> float:
    boundaries = np.linspace(0.0, 1.0, bin_count + 1)
    weighted_error = 0.0
    for index in range(bin_count):
        lower = boundaries[index]
        upper = boundaries[index + 1]
        in_bin = (scores >= lower) & (scores < upper if index < bin_count - 1 else scores <= upper)
        count = int(np.count_nonzero(in_bin))
        if not count:
            continue
        observed = float(np.mean(truth[in_bin]))
        predicted = float(np.mean(scores[in_bin]))
        weighted_error += count / len(scores) * abs(observed - predicted)
    return weighted_error
