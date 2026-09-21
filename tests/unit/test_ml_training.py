from __future__ import annotations

import inspect
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from forpost_prediction_core.evaluation import evaluate_binary_probabilities
from forpost_prediction_core.training import (
    CandidateValidation,
    FoldMetrics,
    FoldPredictions,
    TrainingConfig,
    TrainingUnavailableError,
    _split_fit_calibration,
    rank_candidates,
    rank_fold_candidates,
    select_fold_operating_profiles,
    split_development_and_test,
    train_champion,
)
from sklearn.frozen import FrozenEstimator


def _passing_folds():
    metrics = evaluate_binary_probabilities(
        np.array([1, 1, 0, 0, 0, 0, 0, 0]),
        np.array([0.9, 0.9, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]),
        threshold=0.5,
    )
    return tuple(FoldMetrics(index, 0.5, metrics, 0.25) for index in (1, 2, 3))


def test_champion_must_pass_every_validation_fold():
    passing = _passing_folds()
    failing = replace(passing[2], metrics=replace(passing[2].metrics, recall=0.4))
    selected = rank_fold_candidates(
        {"stable": passing, "fragile": (*passing[:2], failing)}, TrainingConfig()
    )
    assert selected.name == "stable"


def test_final_test_probabilities_are_not_accepted_by_selector():
    assert "test_probabilities" not in inspect.signature(rank_fold_candidates).parameters


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "calibration", "baseline", "nan"])
def test_fold_selector_rejects_incomplete_or_failing_evidence(mutation):
    folds = _passing_folds()
    if mutation == "missing":
        folds = folds[:2]
    elif mutation == "duplicate":
        folds = (folds[0], folds[0], folds[2])
    elif mutation == "baseline":
        folds = (*folds[:2], replace(folds[2], baseline_pr_auc=1.0))
    else:
        metrics = replace(
            folds[2].metrics,
            expected_calibration_error=0.9 if mutation == "calibration" else float("nan"),
        )
        folds = (*folds[:2], replace(folds[2], metrics=metrics))
    with pytest.raises(TrainingUnavailableError):
        rank_fold_candidates({"only": folds}, TrainingConfig())


def test_fold_selector_prefers_worst_fold_then_simplicity_on_ties():
    folds = _passing_folds()
    stable = tuple(replace(f, metrics=replace(f.metrics, f1=0.85)) for f in folds)
    volatile = (folds[0], folds[1], replace(folds[2], metrics=replace(folds[2].metrics, f1=0.6)))
    assert (
        rank_fold_candidates({"stable": stable, "volatile": volatile}, TrainingConfig()).name
        == "stable"
    )
    assert (
        rank_fold_candidates(
            {"extra_trees_isotonic": folds, "logistic_regression_sigmoid": folds}, TrainingConfig()
        ).name
        == "logistic_regression_sigmoid"
    )


def test_fold_selector_uses_mean_pr_auc_when_worst_f1_is_equal():
    folds = _passing_folds()
    lower_auc = tuple(replace(fold, metrics=replace(fold.metrics, pr_auc=0.8)) for fold in folds)
    assert (
        rank_fold_candidates(
            {"logistic_regression_sigmoid": lower_auc, "extra_trees_sigmoid": folds},
            TrainingConfig(),
        ).name
        == "extra_trees_sigmoid"
    )


def test_fold_selector_uses_paired_fold_uncertainty_for_simplicity_tie():
    folds = _passing_folds()
    simpler = tuple(
        replace(fold, metrics=replace(fold.metrics, f1=value))
        for fold, value in zip(folds, (0.82, 0.95, 0.9), strict=True)
    )
    complex_model = tuple(
        replace(fold, metrics=replace(fold.metrics, f1=value))
        for fold, value in zip(folds, (0.83, 0.9, 0.95), strict=True)
    )
    assert (
        rank_fold_candidates(
            {"logistic_regression_sigmoid": simpler, "catboost_isotonic": complex_model},
            TrainingConfig(),
        ).name
        == "logistic_regression_sigmoid"
    )


def test_profiles_share_one_approved_threshold_across_all_folds():
    labels = np.array([1, 1, 0, 0, 0, 0, 0, 0])
    predictions = tuple(
        FoldPredictions(
            index, labels, np.array([0.9, positive, negative, 0.1, 0.1, 0.1, 0.1, 0.1]), 0.25
        )
        for index, positive, negative in [(1, 0.7, 0.6), (2, 0.8, 0.65), (3, 0.75, 0.6)]
    )
    profiles = select_fold_operating_profiles(predictions, TrainingConfig())
    assert set(profiles) == {"high_precision", "balanced", "high_recall"}
    for profile in profiles.values():
        assert len(profile.rolling_folds) == 3
        assert all(fold.threshold == profile.threshold for fold in profile.rolling_folds)
        assert all(
            fold.metrics.precision == 1 and fold.metrics.recall == 1
            for fold in profile.rolling_folds
        )


def test_fold_ranking_does_not_depend_on_candidate_insertion_order():
    folds = _passing_folds()
    results = {
        name: tuple(
            replace(fold, metrics=replace(fold.metrics, f1=f1))
            for fold, f1 in zip(folds, values, strict=True)
        )
        for name, values in (
            ("extra_trees_sigmoid", (0.8, 0.8, 0.8)),
            ("catboost_sigmoid", (0.8, 0.95, 0.95)),
            ("logistic_regression_sigmoid", (0.79, 0.8, 0.8)),
        )
    }
    assert (
        rank_fold_candidates(results, TrainingConfig()).name
        == rank_fold_candidates(dict(reversed(list(results.items()))), TrainingConfig()).name
    )


def test_profiles_reject_individually_valid_but_incompatible_thresholds():
    labels = np.array([1, 1, 0, 0, 0, 0, 0, 0])
    predictions = tuple(
        FoldPredictions(
            index,
            labels,
            np.array([positive, positive, negative, negative, 0.01, 0.01, 0.01, 0.01]),
            0.25,
        )
        for index, positive, negative in [(1, 0.4, 0.3), (2, 0.8, 0.7), (3, 0.6, 0.5)]
    )
    with pytest.raises(TrainingUnavailableError):
        select_fold_operating_profiles(
            predictions, TrainingConfig(maximum_expected_calibration_error=1, maximum_brier_score=1)
        )


def test_implicit_profiles_honor_configured_operational_alert_capacity():
    labels = np.array([1, 1, 1, 0, 0, 0, 0, 0])
    scores = np.array([0.95, 0.95, 0.95, 0.05, 0.05, 0.05, 0.05, 0.05])
    profiles = select_fold_operating_profiles(
        tuple(FoldPredictions(index, labels, scores, 0.375) for index in (1, 2, 3)),
        TrainingConfig(maximum_alert_rate=0.6),
    )
    assert all(
        fold.metrics.recall == 1 for profile in profiles.values() for fold in profile.rolling_folds
    )


def test_final_test_split_keeps_whole_timestamps_and_purges_boundary():
    development, test = split_development_and_test(
        _training_frame(), "cutoff", test_fraction=0.2, purge_hours=24
    )
    assert len(test) == 64
    assert development["cutoff"].max() == pd.Timestamp("2025-03-04")
    assert test["cutoff"].min() == pd.Timestamp("2025-03-06")
    assert development["cutoff"].max() + pd.Timedelta(hours=24) < test["cutoff"].min()


def test_final_test_labels_do_not_affect_selection_or_refitting(monkeypatch):
    """Ловит использование final test в выборе, калибровке или fit модели."""
    from forpost_prediction_core import training

    original_builder = training.build_candidate_estimators

    def logistic_only(frame, seed):
        return {"logistic_regression": original_builder(frame, seed)["logistic_regression"]}

    monkeypatch.setattr(training, "build_candidate_estimators", logistic_only)
    config = TrainingConfig(
        purge_hours=24,
        minimum_positive_examples=1,
        minimum_negative_examples=1,
        maximum_alert_rate=0.6,
        maximum_expected_calibration_error=1,
        maximum_brier_score=1,
        validation_points_per_fold=8,
    )
    frame = _training_frame()
    first = train_champion(frame, label_column="label", time_column="cutoff", config=config)
    poisoned = frame.copy()
    future = poisoned["cutoff"] >= pd.Timestamp("2025-03-06")
    poisoned.loc[future, "label"] = 1 - poisoned.loc[future, "label"]
    evidence = training.TrainingEvidence()
    with pytest.raises(TrainingUnavailableError, match="holdout"):
        train_champion(
            poisoned, label_column="label", time_column="cutoff", config=config, evidence=evidence
        )
    assert evidence.stage == "test"
    assert evidence.champion_name == first.champion_name
    assert evidence.threshold == first.threshold
    assert evidence.validation_metrics == first.validation_metrics


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
        validation_points_per_fold=8,
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
    assert first.feature_columns == tuple(
        column for column in frame if column not in {"label", "cutoff"}
    )
    assert len(first.rolling_folds) == 3
    assert first.default_profile == "balanced"
    assert first.threshold == first.operating_profiles["balanced"].threshold
    assert set(first.operating_profiles) == {"high_precision", "balanced", "high_recall"}


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
