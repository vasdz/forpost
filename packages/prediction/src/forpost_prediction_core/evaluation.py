"""Метрики временного holdout без неявной подмены недоступных результатов."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


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
    if not np.isin(truth, (0, 1)).all() or not np.isfinite(scores).all() or not (
        (scores >= 0) & (scores <= 1)
    ).all():
        raise ValueError("Оценка требует бинарных меток и конечных вероятностей от 0 до 1")
    positives = int(truth.sum())
    negatives = len(truth) - positives
    if not positives or not negatives:
        raise EvaluationUnavailableError("Для расчёта метрик требуются наблюдения обоих классов")

    predicted = scores >= threshold
    true_positive = int(np.count_nonzero(predicted & (truth == 1)))
    false_positive = int(np.count_nonzero(predicted & (truth == 0)))
    false_negative = int(np.count_nonzero(~predicted & (truth == 1)))
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return BinaryMetrics(
        precision=precision,
        recall=recall,
        f1=f1,
        pr_auc=_average_precision(truth, scores),
        roc_auc=_roc_auc(truth, scores),
    )


def _average_precision(truth: np.ndarray, scores: np.ndarray) -> float:
    order = np.argsort(-scores, kind="stable")
    ordered_truth = truth[order]
    cumulative_true_positive = np.cumsum(ordered_truth)
    ranks = np.arange(1, len(ordered_truth) + 1)
    precision_at_rank = cumulative_true_positive / ranks
    return float(precision_at_rank[ordered_truth == 1].sum() / ordered_truth.sum())


def _roc_auc(truth: np.ndarray, scores: np.ndarray) -> float:
    positive_scores = scores[truth == 1]
    negative_scores = scores[truth == 0]
    comparisons = positive_scores[:, None] - negative_scores[None, :]
    return float(
        (np.count_nonzero(comparisons > 0) + 0.5 * np.count_nonzero(comparisons == 0))
        / comparisons.size
    )
