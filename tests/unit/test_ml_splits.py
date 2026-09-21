from __future__ import annotations

import pandas as pd
import pytest
from forpost_prediction_core.splits import make_rolling_origin_folds


def test_rolling_folds_expand_train_keep_validation_horizon_and_apply_embargo() -> None:
    """Ловит утечку будущих наблюдений или нерасширяющееся обучение."""
    frame = pd.DataFrame({"at": pd.date_range("2026-01-01", periods=14, freq="24h", tz="UTC")})

    folds = make_rolling_origin_folds(
        frame, "at", fold_count=3, validation_points=2, purge_hours=24
    )

    assert len(folds) == 3
    assert [len(fold.train) for fold in folds] == sorted(len(fold.train) for fold in folds)
    assert [len(fold.validation) for fold in folds] == [2, 2, 2]
    assert all(
        fold.train["at"].max() < fold.validation["at"].min() - pd.Timedelta(hours=24)
        for fold in folds
    )


def test_rolling_folds_reject_overlapping_or_empty_partitions() -> None:
    """Ловит попытку строить fold без достаточного временного горизонта."""
    frame = pd.DataFrame({"at": pd.date_range("2026-01-01", periods=5, freq="h", tz="UTC")})

    with pytest.raises(ValueError, match="временных точек"):
        make_rolling_origin_folds(frame, "at", fold_count=3, validation_points=2, purge_hours=24)


def test_rolling_folds_reject_negative_embargo_that_would_overlap_partitions() -> None:
    """Ловит попадание наблюдений validation в train при отрицательном embargo."""
    frame = pd.DataFrame({"at": pd.date_range("2026-01-01", periods=14, freq="24h", tz="UTC")})

    with pytest.raises(ValueError, match="не может быть отрицательным"):
        make_rolling_origin_folds(frame, "at", fold_count=3, validation_points=2, purge_hours=-24)


def test_rolling_folds_normalize_iso_timestamp_strings() -> None:
    """Ловит арифметику embargo над строками вместо временных меток."""
    frame = pd.DataFrame(
        {
            "at": pd.date_range("2026-01-01", periods=14, freq="24h", tz="UTC").strftime(
                "%Y-%m-%dT%H:%M:%S%z"
            )
        }
    )

    folds = make_rolling_origin_folds(
        frame, "at", fold_count=3, validation_points=2, purge_hours=24
    )

    assert pd.api.types.is_datetime64_any_dtype(folds[0].train["at"])
    assert folds[0].validation["at"].min() == pd.Timestamp("2026-01-09", tz="UTC")
