import numpy as np
import pytest
from forpost_prediction_core.evaluation import (
    EvaluationUnavailableError,
    evaluate_binary_probabilities,
    select_operating_threshold,
)


def test_binary_evaluation_reports_calibrated_threshold_metrics() -> None:
    """Ловит расчёт accuracy вместо требуемых precision, recall, PR-AUC и ROC-AUC."""
    result = evaluate_binary_probabilities(
        np.array([0, 1, 1, 0]), np.array([0.1, 0.8, 0.9, 0.2]), threshold=0.7
    )

    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1 == 1.0
    assert result.pr_auc == 1.0
    assert result.roc_auc == 1.0
    assert result.brier_score == pytest.approx(0.025)
    assert result.alert_rate == 0.5
    assert result.true_positive == 2
    assert result.false_positive == 0
    assert result.false_negative == 0
    assert result.true_negative == 2


def test_binary_evaluation_refuses_one_class_holdout() -> None:
    """Ловит публикацию псевдометрики, когда во временном holdout нет второго класса."""
    with pytest.raises(EvaluationUnavailableError, match="обоих классов"):
        evaluate_binary_probabilities(np.array([0, 0]), np.array([0.1, 0.2]), threshold=0.7)


def test_threshold_selection_respects_recall_and_alert_budget() -> None:
    """Ловит выбор красивого F1, создающего слишком много тревог для диспетчера."""
    labels = np.array([1, 1, 0, 0, 0, 0, 0, 0])
    probabilities = np.array([0.95, 0.70, 0.80, 0.60, 0.55, 0.30, 0.20, 0.10])

    selected = select_operating_threshold(
        labels,
        probabilities,
        thresholds=(0.5, 0.7, 0.9),
        minimum_recall=0.5,
        maximum_alert_rate=0.5,
    )

    assert selected.threshold == 0.7
    assert selected.metrics.precision == pytest.approx(2 / 3)
    assert selected.metrics.recall == 1.0
    assert selected.metrics.alert_rate == pytest.approx(3 / 8)


def test_threshold_selection_fails_when_operational_constraints_are_impossible() -> None:
    """Ловит молчаливое снятие обязательного recall при неудобных данных."""
    with pytest.raises(EvaluationUnavailableError, match="рабочий порог"):
        select_operating_threshold(
            np.array([1, 0, 0, 0]),
            np.array([0.4, 0.3, 0.2, 0.1]),
            thresholds=(0.5, 0.8),
            minimum_recall=1.0,
            maximum_alert_rate=0.25,
        )


def test_threshold_selection_uses_observed_score_between_coarse_grid_points() -> None:
    """Ловит пропуск допустимой рабочей точки между шагами конфигурации."""
    labels = np.array([1, 1, 0, 0])
    probabilities = np.array([0.90, 0.61, 0.60, 0.10])

    selected = select_operating_threshold(
        labels,
        probabilities,
        thresholds=(0.5, 0.7),
        minimum_precision=0.7,
        minimum_recall=0.5,
        maximum_alert_rate=0.5,
    )

    assert selected.threshold == pytest.approx(0.61)
    assert selected.metrics.precision == 1.0
    assert selected.metrics.recall == 1.0


def test_pr_auc_is_invariant_to_order_for_tied_scores() -> None:
    first = evaluate_binary_probabilities(np.array([1, 0]), np.array([0.5, 0.5]), threshold=0.6)
    second = evaluate_binary_probabilities(np.array([0, 1]), np.array([0.5, 0.5]), threshold=0.6)

    assert first.pr_auc == second.pr_auc == 0.5


def test_auc_evaluation_scales_without_pairwise_matrix() -> None:
    labels = np.tile(np.array([0, 1], dtype=np.int8), 25_000)
    scores = np.linspace(0.0, 1.0, len(labels), dtype=np.float64)

    result = evaluate_binary_probabilities(labels, scores, threshold=0.5)

    assert 0 <= result.roc_auc <= 1
