from datetime import timedelta

import numpy as np
import pandas as pd
import pytest
from forpost_prediction_core.features import build_channel_features
from forpost_prediction_core.labeling import label_silence_horizon
from forpost_prediction_core.splits import split_by_time


def test_interval_statistics_and_frequency_change_use_bounded_history() -> None:
    """Ловит подмену MAD стандартным отклонением и сравнение ненормированных count."""
    cutoff = pd.Timestamp("2026-01-05T03:00:00Z")
    events = pd.DataFrame(
        {
            "channel_id": ["a"] * 4,
            "observed_at": [cutoff - pd.Timedelta(hours=h) for h in (13, 11, 7, 1)],
            "sensor_value": [1, 2, 3, 4],
        }
    )
    row = build_channel_features(
        events, pd.DataFrame({"channel_id": ["a"]}), cutoff, windows=(6, 24)
    ).iloc[0]

    assert row["interarrival_median_hours"] == 4
    assert row["interarrival_mad_hours"] == 2
    assert row["interarrival_q25_hours"] == 3
    assert row["interarrival_q75_hours"] == 5
    assert row["interarrival_cv"] == pytest.approx(0.5)
    assert row["silence_to_normal_ratio"] == pytest.approx(0.25)
    assert row["frequency_change_6h_to_24h"] == pytest.approx(0)
    assert row["history_event_count"] == 4
    assert row["history_span_hours"] == 12
    assert row["history_window_coverage"] == pytest.approx(13 / 24)
    assert row["history_window_incomplete"] == 1


def test_frequency_change_compares_hourly_rates() -> None:
    cutoff = pd.Timestamp("2026-01-05T00:00:00Z")
    events = pd.DataFrame(
        {
            "channel_id": ["a"] * 3,
            "observed_at": [cutoff - pd.Timedelta(hours=h) for h in (24, 6, 1)],
            "sensor_value": [1, 2, 3],
        }
    )
    row = build_channel_features(
        events, pd.DataFrame({"channel_id": ["a"]}), cutoff, windows=(6, 24)
    ).iloc[0]
    assert row["frequency_change_6h_to_24h"] == pytest.approx(5 / 24)
    assert row["history_window_coverage"] == 1
    assert row["history_window_incomplete"] == 0


def test_value_decay_uses_elapsed_time_for_mean_and_variance() -> None:
    """Вес наблюдения 12 часов назад равен четверти, а не половине последнего."""
    cutoff = pd.Timestamp("2026-01-05T00:00:00Z")
    events = pd.DataFrame(
        {
            "channel_id": ["a", "a"],
            "observed_at": [cutoff - pd.Timedelta(hours=h) for h in (1, 13)],
            "sensor_value": [10, 2],
        }
    )
    row = build_channel_features(
        events, pd.DataFrame({"channel_id": ["a"]}), cutoff, windows=(24,)
    ).iloc[0]
    assert row["value_ewm_mean"] == pytest.approx(8.4)
    assert row["value_ewm_variance"] == pytest.approx(10.24)
    assert row["value_ewm_std"] == pytest.approx(3.2)


def test_frequency_decay_and_interval_trends_use_positive_intervals() -> None:
    cutoff = pd.Timestamp("2026-01-05T00:00:00Z")
    events = pd.DataFrame(
        {
            "channel_id": ["a"] * 3,
            "observed_at": [cutoff - pd.Timedelta(hours=h) for h in (19, 13, 1)],
            "sensor_value": [1, 2, 3],
        }
    )
    row = build_channel_features(
        events, pd.DataFrame({"channel_id": ["a"]}), cutoff, windows=(24,)
    ).iloc[0]
    assert row["frequency_ewm_mean"] == pytest.approx(0.1)
    assert row["frequency_ewm_variance"] == pytest.approx(1 / 900)
    assert row["interarrival_slope_per_hour"] == pytest.approx(0.5)
    assert row["interarrival_robust_slope_per_hour"] == pytest.approx(0.5)


def test_robust_value_trend_resists_a_single_outlier() -> None:
    cutoff = pd.Timestamp("2026-01-05T00:00:00Z")
    events = pd.DataFrame(
        {
            "channel_id": ["a"] * 5,
            "observed_at": [cutoff - pd.Timedelta(hours=h) for h in (5, 4, 3, 2, 1)],
            "sensor_value": [1, 2, 3, 4, 100],
        }
    )
    row = build_channel_features(events, pd.DataFrame({"channel_id": ["a"]}), cutoff).iloc[0]
    assert row["value_slope_per_hour"] == pytest.approx(20)
    assert row["value_robust_slope_per_hour"] == pytest.approx(1)


def test_rolling_missing_and_quality_statistics_ignore_ineligible_events() -> None:
    cutoff = pd.Timestamp("2026-01-05T00:00:00Z")
    events = pd.DataFrame(
        {
            "channel_id": ["a"] * 6,
            "observed_at": [cutoff - pd.Timedelta(hours=h) for h in (7, 5, 4, 3, 2, 1)],
            "sensor_value": [10, None, "bad", np.inf, -np.inf, -100],
            "quality_status": [
                "valid",
                "unknown",
                "invalid",
                "valid",
                "valid",
                "technical_anomaly",
            ],
            "analysis_eligible": [True] * 5 + [False],
        }
    )
    row = build_channel_features(
        events, pd.DataFrame({"channel_id": ["a"]}), cutoff, windows=(6, 24)
    ).iloc[0]
    assert row["missing_count_24h"] == 4
    assert row["missing_ratio_24h"] == pytest.approx(0.8)
    assert row["missing_ratio_6h"] == 1
    assert row["quality_issue_count_24h"] == 2
    assert row["quality_issue_ratio_24h"] == pytest.approx(0.4)
    assert row["quality_issue_ratio_6h"] == pytest.approx(0.5)
    assert row["value_mean_24h"] == 10
    assert row["value_ewm_mean"] == 10
    assert row["value_ewm_std"] == 0


def test_cyclical_features_use_moscow_cutoff_and_optional_metadata() -> None:
    cutoff = pd.Timestamp("2026-01-05T03:00:00Z")
    events = pd.DataFrame(columns=["channel_id", "observed_at", "sensor_value"])
    channels = pd.DataFrame(
        {
            "channel_id": ["ventilation:a"],
            "sensor_type": ["temperature"],
            "engineering_system": ["provided-system"],
        }
    )
    row = build_channel_features(events, channels, cutoff).iloc[0]
    assert row["hour_sin"] == pytest.approx(1)
    assert row["hour_cos"] == pytest.approx(0, abs=1e-12)
    assert row["weekday_sin"] == pytest.approx(0)
    assert row["weekday_cos"] == pytest.approx(1)
    assert row["month_sin"] == pytest.approx(0)
    assert row["month_cos"] == pytest.approx(1)
    assert row["sensor_type"] == "temperature"
    assert row["engineering_system"] == "provided-system"
    absent = build_channel_features(events, channels[["channel_id"]], cutoff)
    assert "engineering_system" not in absent
    assert "sensor_type" not in absent


def test_schema_is_stable_for_empty_singleton_and_duplicate_history() -> None:
    """Недостаток интервалов обозначается NaN; нулевой интервал не даёт бесконечность."""
    cutoff = pd.Timestamp("2026-01-05T00:00:00Z")
    events = pd.DataFrame(
        {
            "channel_id": ["single", "duplicate", "duplicate"],
            "observed_at": [cutoff - pd.Timedelta(hours=1)] * 3,
            "sensor_value": [10, 2, 4],
        }
    )
    channels = pd.DataFrame({"channel_id": ["empty", "single", "duplicate"]})
    result = build_channel_features(events, channels, cutoff, windows=(6, 24)).set_index(
        "channel_id"
    )
    empty = build_channel_features(events.iloc[:0], channels, cutoff, windows=(6, 24))
    assert result.columns.tolist() == empty.drop(columns="channel_id").columns.tolist()
    assert pd.isna(result.loc["single", "interarrival_median_hours"])
    assert pd.isna(result.loc["empty", "value_ewm_mean"])
    assert result.loc["duplicate", "interarrival_median_hours"] == 0
    assert result.loc["duplicate", "silence_to_normal_ratio"] == 60
    assert pd.isna(result.loc["duplicate", "frequency_ewm_mean"])
    assert result.loc["empty", "missing_ratio_24h"] == 0
    assert result.loc["empty", "history_window_coverage"] == 0
    assert not np.isinf(result.select_dtypes(include="number").to_numpy()).any()


def test_future_rows_cannot_change_any_past_feature() -> None:
    """Ловит утечку во все признаки, включая качество, интервалы, decay и тренды."""
    cutoff = pd.Timestamp("2026-01-05T00:00:00Z")
    events = pd.DataFrame(
        {
            "channel_id": ["a"] * 3,
            "observed_at": [cutoff - pd.Timedelta(hours=h) for h in (20, 10, 1)],
            "sensor_value": [1, 2, 3],
            "quality_status": ["valid"] * 3,
            "is_alarm": [False] * 3,
        }
    )
    channels = pd.DataFrame({"channel_id": ["a", "empty"]})
    expected = build_channel_features(events, channels, cutoff)
    poison = pd.DataFrame(
        {
            "channel_id": ["a", "a", "empty"],
            "observed_at": [cutoff, cutoff + pd.Timedelta(hours=1), cutoff],
            "sensor_value": [999999, np.inf, -999999],
            "quality_status": ["invalid"] * 3,
            "is_alarm": [True] * 3,
        }
    )
    actual = build_channel_features(
        pd.concat([events, poison], ignore_index=True), channels, cutoff
    )
    pd.testing.assert_frame_equal(actual, expected)


def test_new_pattern_features_are_bounded_by_largest_window() -> None:
    cutoff = pd.Timestamp("2026-01-05T00:00:00Z")
    events = pd.DataFrame(
        {
            "channel_id": ["a"] * 4,
            "observed_at": [cutoff - pd.Timedelta(hours=h) for h in (500, 20, 10, 1)],
            "sensor_value": [999999, 1, 2, 3],
        }
    )
    channels = pd.DataFrame({"channel_id": ["a"]})
    pd.testing.assert_frame_equal(
        build_channel_features(events, channels, cutoff, windows=(6, 24)),
        build_channel_features(events.iloc[1:], channels, cutoff, windows=(6, 24)),
    )


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
