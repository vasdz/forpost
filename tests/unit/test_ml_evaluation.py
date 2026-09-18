import numpy as np
import pytest
from forpost_prediction_core.evaluation import (
    EvaluationUnavailableError,
    evaluate_binary_probabilities,
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


def test_binary_evaluation_refuses_one_class_holdout() -> None:
    """Ловит публикацию псевдометрики, когда во временном holdout нет второго класса."""
    with pytest.raises(EvaluationUnavailableError, match="обоих классов"):
        evaluate_binary_probabilities(
            np.array([0, 0]), np.array([0.1, 0.2]), threshold=0.7
        )
