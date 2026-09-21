from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from forpost_prediction_core.training import (
    CandidateValidation,
    TrainingConfig,
    TrainingUnavailableError,
    _split_fit_calibration,
    rank_candidates,
    train_champion,
)
from sklearn.frozen import FrozenEstimator


def test_candidate_ranking_uses_validation_metrics_and_operational_constraints() -> None:
    """Ловит выбор кандидата по будущему test или одной ROC-AUC."""
    labels = np.array([1, 1, 0, 0, 0, 0, 0, 0])
    candidates = {
        "operational": np.array([0.95, 0.75, 0.80, 0.30, 0.25, 0.20, 0.10, 0.05]),
        "too_many_alerts": np.array([0.95, 0.65, 0.85, 0.80, 0.75, 0.70, 0.60, 0.10]),
    }

    selected = rank_candidates(
        labels,
        candidates,
        TrainingConfig(
            thresholds=(0.5, 0.7, 0.9),
            minimum_precision=0.6,
            minimum_recall=0.5,
            maximum_alert_rate=0.5,
            minimum_positive_examples=1,
            minimum_negative_examples=1,
            maximum_expected_calibration_error=1.0,
            maximum_brier_score=1.0,
            minimum_baseline_pr_auc_delta=0.0,
        ),
    )

    assert isinstance(selected, CandidateValidation)
    assert selected.name == "operational"
    assert selected.threshold == 0.75


def test_training_refuses_dataset_without_enough_positive_examples() -> None:
    """Ловит обучение и публикацию стабильной псевдометрики на единичном событии."""
    frame = _training_frame()
    frame["label"] = 0
    frame.loc[0, "label"] = 1

    with pytest.raises(TrainingUnavailableError, match="положительного класса"):
        train_champion(
            frame,
            label_column="label",
            time_column="cutoff",
            config=TrainingConfig(minimum_positive_examples=2, minimum_negative_examples=2),
        )


def test_training_is_deterministic_and_evaluates_untouched_test() -> None:
    """Ловит недетерминированный champion и отсутствие финальной temporal-проверки."""
    frame = _training_frame()
    config = TrainingConfig(
        seed=73,
        validation_fraction=0.2,
        test_fraction=0.2,
        purge_hours=0,
        thresholds=(0.3, 0.5, 0.7),
        minimum_precision=0.5,
        minimum_recall=0.5,
        maximum_alert_rate=0.6,
        minimum_positive_examples=4,
        minimum_negative_examples=4,
        maximum_expected_calibration_error=1.0,
        maximum_brier_score=1.0,
        minimum_baseline_pr_auc_delta=0.0,
    )

    first = train_champion(frame, label_column="label", time_column="cutoff", config=config)
    second = train_champion(frame, label_column="label", time_column="cutoff", config=config)

    assert first.champion_name == second.champion_name
    assert first.champion_name.endswith(("_isotonic", "_sigmoid"))
    assert first.threshold == second.threshold
    assert first.test_metrics == second.test_metrics
    assert first.test_metrics.precision >= 0.5
    assert first.test_metrics.recall >= 0.5
    assert first.test_metrics.brier_score <= 1.0
    assert first.test_row_count > 0
    assert first.validation_row_count > 0
    assert isinstance(first.model.estimator, FrozenEstimator)
    assert "channel_id" in first.feature_columns
    assert set(first.feature_importances) == set(first.feature_columns)
    assert all(np.isfinite(value) for value in first.feature_importances.values())


def test_internal_calibration_is_later_than_fit_with_embargo() -> None:
    frame = pd.DataFrame(
        {
            "prediction_at": pd.date_range("2026-01-01", periods=20, freq="D"),
            "label": np.tile([0, 1], 10),
        }
    )

    fit, calibration = _split_fit_calibration(
        frame,
        "prediction_at",
        calibration_fraction=0.2,
        purge_hours=24,
    )

    assert calibration["prediction_at"].min() - fit["prediction_at"].max() > pd.Timedelta(hours=24)


def test_internal_calibration_moves_boundary_after_dense_cluster() -> None:
    frame = pd.DataFrame(
        {
            "prediction_at": pd.to_datetime(
                [
                    "2026-01-01 00:00",
                    "2026-01-01 01:00",
                    "2026-01-01 02:00",
                    "2026-01-01 03:00",
                    "2026-01-01 04:00",
                    "2026-01-01 05:00",
                    "2026-01-01 06:00",
                    "2026-01-03 00:00",
                ]
            ),
            "label": np.tile([0, 1], 4),
        }
    )

    fit, calibration = _split_fit_calibration(
        frame,
        "prediction_at",
        calibration_fraction=0.25,
        purge_hours=24,
    )

    assert not fit.empty
    assert not calibration.empty
    assert calibration["prediction_at"].min() - fit["prediction_at"].max() > pd.Timedelta(hours=24)


def _training_frame() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for day in range(80):
        for channel in range(4):
            risk = (day + channel) % 8
            rows.append(
                {
                    "cutoff": pd.Timestamp("2025-01-01") + pd.Timedelta(days=day),
                    "channel_id": f"channel-{channel}",
                    "sensor_type": "temperature" if channel % 2 else "smoke",
                    "event_count_24h": float(10 - risk),
                    "hours_since_last_event": float(risk),
                    "alarm_ratio_24h": float(risk >= 5),
                    "label": int(risk >= 6),
                }
            )
    return pd.DataFrame(rows)
