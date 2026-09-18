from datetime import timedelta

import pandas as pd
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
