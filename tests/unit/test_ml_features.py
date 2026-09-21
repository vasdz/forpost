from datetime import timedelta

import pandas as pd
import pytest
from forpost_prediction_core.features import build_channel_features
from forpost_prediction_core.labeling import label_silence_horizon
from forpost_prediction_core.splits import split_by_time


def test_channel_features_exclude_events_at_or_after_cutoff() -> None:
    """Ловит утечку будущего события в rolling-признаки точки прогнозирования."""
    cutoff = pd.Timestamp("2025-01-02 00:00:00")
    events = pd.DataFrame(
        {
            "channel_id": ["a", "a", "a"],
            "observed_at": [
                cutoff - timedelta(hours=23),
                cutoff - timedelta(hours=1),
                cutoff + timedelta(hours=1),
            ],
            "sensor_value": ["10", "20", "999"],
        }
    )
    channels = pd.DataFrame({"channel_id": ["a"], "sensor_type": ["temperature"]})

    result = build_channel_features(events, channels, cutoff, windows=(24,))

    assert result.loc[0, "event_count_24h"] == 2
    assert result.loc[0, "value_max_24h"] == 20.0
    assert result.loc[0, "hours_since_last_event"] == 1.0


def test_channel_features_separate_alarm_and_technical_quality_signals() -> None:
    """Ловит смешивание технических кодов с физической статистикой датчика."""
    cutoff = pd.Timestamp("2025-02-03 12:00:00")
    events = pd.DataFrame(
        {
            "channel_id": ["a", "a", "a"],
            "observed_at": [
                cutoff - timedelta(hours=3),
                cutoff - timedelta(hours=2),
                cutoff - timedelta(hours=1),
            ],
            "sensor_value": ["10", "-100", "20"],
            "is_alarm": [False, True, True],
            "quality_status": ["valid", "technical_anomaly", "valid"],
            "analysis_eligible": [True, False, True],
        }
    )
    channels = pd.DataFrame({"channel_id": ["a"], "sensor_type": ["temperature"]})

    result = build_channel_features(events, channels, cutoff, windows=(24,))

    assert result.loc[0, "event_count_24h"] == 2
    assert result.loc[0, "alarm_count_24h"] == 1
    assert result.loc[0, "alarm_ratio_24h"] == pytest.approx(1 / 2)
    assert "technical_anomaly_count_24h" not in result
    assert result.loc[0, "value_min_24h"] == 10.0
    assert result.loc[0, "value_max_24h"] == 20.0
    assert result.loc[0, "cutoff_hour"] == 12
    assert result.loc[0, "cutoff_weekday"] == 0


def test_value_slope_is_zero_when_numeric_events_share_timestamp() -> None:
    """Одинаковые timestamps не должны ломать обучение через singular polyfit."""
    cutoff = pd.Timestamp("2026-01-02T00:00:00Z")
    events = pd.DataFrame(
        {
            "channel_id": ["channel-1", "channel-1"],
            "observed_at": [cutoff - pd.Timedelta(hours=1)] * 2,
            "sensor_value": [1.0, 2.0],
            "is_alarm": [False, False],
            "quality_status": ["observed", "observed"],
        }
    )
    channels = pd.DataFrame({"channel_id": ["channel-1"]})

    result = build_channel_features(events, channels, cutoff)

    assert result.iloc[0]["value_slope_per_hour"] == 0.0


def test_long_history_statistics_are_bounded_by_largest_feature_window() -> None:
    """Левое усечение не должно влиять на entropy/trend после полного прогрева."""
    cutoff = pd.Timestamp("2026-02-01T00:00:00Z")
    recent = pd.DataFrame(
        {
            "channel_id": ["a", "a", "a"],
            "observed_at": [
                cutoff - pd.Timedelta(hours=20),
                cutoff - pd.Timedelta(hours=10),
                cutoff - pd.Timedelta(hours=1),
            ],
            "sensor_value": [1.0, 2.0, 3.0],
        }
    )
    with_old = pd.concat(
        [
            pd.DataFrame(
                {
                    "channel_id": ["a"],
                    "observed_at": [cutoff - pd.Timedelta(days=30)],
                    "sensor_value": [10_000.0],
                }
            ),
            recent,
        ],
        ignore_index=True,
    )
    channels = pd.DataFrame({"channel_id": ["a"]})

    expected = build_channel_features(recent, channels, cutoff, windows=(1, 6, 24))
    actual = build_channel_features(with_old, channels, cutoff, windows=(1, 6, 24))

    assert actual.loc[0, "interarrival_entropy"] == expected.loc[0, "interarrival_entropy"]
    assert actual.loc[0, "value_slope_per_hour"] == expected.loc[0, "value_slope_per_hour"]


def test_channel_without_recent_events_gets_zero_recent_pattern_features() -> None:
    """Пустое окно — допустимый сигнал тишины, а не ошибка Pandas groupby.apply."""
    cutoff = pd.Timestamp("2026-02-01T00:00:00Z")
    events = pd.DataFrame(
        {
            "channel_id": ["a"],
            "observed_at": [cutoff - pd.Timedelta(hours=48)],
            "sensor_value": [1.0],
        }
    )
    channels = pd.DataFrame({"channel_id": ["a"]})

    result = build_channel_features(events, channels, cutoff, windows=(1, 6, 24))

    assert result.loc[0, "event_count_24h"] == 0
    assert result.loc[0, "hours_since_last_event"] == 48.0
    assert result.loc[0, "interarrival_entropy"] == 0.0
    assert result.loc[0, "value_slope_per_hour"] == 0.0


def test_silence_label_uses_only_the_declared_future_horizon() -> None:
    """Ловит подмену horizon-лейбла событием за границей окна."""
    cutoff = pd.Timestamp("2025-01-02 00:00:00")
    events = pd.DataFrame(
        {
            "channel_id": ["active", "silent", "late"],
            "observed_at": [
                cutoff + timedelta(hours=1),
                cutoff - timedelta(hours=1),
                cutoff + timedelta(hours=25),
            ],
        }
    )
    channels = pd.DataFrame({"channel_id": ["active", "silent", "late"]})

    labels = label_silence_horizon(events, channels, cutoff, horizon_hours=24)

    assert labels.set_index("channel_id")["silence_label"].to_dict() == {
        "active": 0,
        "silent": 1,
        "late": 1,
    }


def test_temporal_split_keeps_future_rows_out_of_training() -> None:
    """Ловит случайное перемешивание строк между train, validation и test."""
    frame = pd.DataFrame(
        {
            "observed_at": pd.date_range("2025-01-01", periods=10, freq="D"),
            "label": range(10),
        }
    )

    split = split_by_time(frame, "observed_at", validation_fraction=0.2, test_fraction=0.2)

    assert split.train["observed_at"].max() < split.validation["observed_at"].min()
    assert split.validation["observed_at"].max() < split.test["observed_at"].min()
    assert split.train["label"].tolist() == list(range(6))


def test_temporal_split_keeps_equal_cutoffs_in_one_partition() -> None:
    """Ловит утечку одной точки прогнозирования между train и validation."""
    frame = pd.DataFrame(
        {
            "observed_at": [
                *([pd.Timestamp("2025-01-01")] * 3),
                *([pd.Timestamp("2025-01-02")] * 3),
                *([pd.Timestamp("2025-01-03")] * 3),
                *([pd.Timestamp("2025-01-04")] * 3),
                *([pd.Timestamp("2025-01-05")] * 3),
            ],
            "channel_id": [f"channel-{index}" for index in range(15)],
        }
    )

    split = split_by_time(frame, "observed_at", validation_fraction=0.2, test_fraction=0.2)

    assert set(split.train["observed_at"]).isdisjoint(split.validation["observed_at"])
    assert set(split.validation["observed_at"]).isdisjoint(split.test["observed_at"])


def test_temporal_split_applies_purge_gap_before_future_partitions() -> None:
    """Ловит попадание хвоста rolling-окна в следующий временной блок."""
    frame = pd.DataFrame(
        {
            "observed_at": pd.date_range("2025-01-01", periods=12, freq="D"),
            "label": range(12),
        }
    )

    split = split_by_time(
        frame,
        "observed_at",
        validation_fraction=0.25,
        test_fraction=0.25,
        purge_hours=24,
    )

    assert split.validation["observed_at"].min() - split.train["observed_at"].max() > pd.Timedelta(
        hours=24
    )
    assert split.test["observed_at"].min() - split.validation["observed_at"].max() > pd.Timedelta(
        hours=24
    )


def test_temporal_split_moves_boundary_when_cluster_conflicts_with_purge() -> None:
    """Ловит ложный отказ разбиения на неравномерных временных точках."""
    frame = pd.DataFrame(
        {
            "observed_at": pd.to_datetime(
                [
                    "2025-01-01 00:00",
                    "2025-01-02 00:00",
                    "2025-01-03 00:00",
                    "2025-01-04 00:00",
                    "2025-01-10 00:00",
                    "2025-01-10 01:00",
                    "2025-01-10 02:00",
                    "2025-01-15 00:00",
                ]
            ),
            "label": range(8),
        }
    )

    split = split_by_time(
        frame,
        "observed_at",
        validation_fraction=0.25,
        test_fraction=0.25,
        purge_hours=24,
    )

    assert not split.train.empty
    assert not split.validation.empty
    assert not split.test.empty
    assert split.validation["observed_at"].min() - split.train["observed_at"].max() > pd.Timedelta(
        hours=24
    )
    assert split.test["observed_at"].min() - split.validation["observed_at"].max() > pd.Timedelta(
        hours=24
    )
