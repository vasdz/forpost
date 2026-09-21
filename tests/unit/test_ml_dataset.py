import pandas as pd
from forpost_prediction_core.dataset import build_sensor_failure_dataset


def test_dataset_is_chronological_and_uses_only_channels_with_history():
    events = pd.DataFrame(
        {
            "channel_id": ["a", "b", "a", "b", "future", "a"],
            "observed_at": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T01:00:00Z",
                    "2026-01-01T12:00:00Z",
                    "2026-01-02T01:00:00Z",
                    "2026-01-03T03:00:00Z",
                    "2026-01-03T02:00:00Z",
                ]
            ),
            "sensor_value": [1, 2, 3, 4, 5, 6],
            "is_alarm": [False, False, True, False, True, False],
            "quality_status": [
                "valid",
                "valid",
                "technical_anomaly",
                "valid",
                "technical_anomaly",
                "valid",
            ],
            "analysis_eligible": [True, True, False, True, False, True],
        }
    )
    channels = pd.DataFrame({"channel_id": ["a", "b", "future"], "sensor_type": ["t", "s", "t"]})

    dataset = build_sensor_failure_dataset(
        events,
        channels,
        horizon_hours=24,
        cutoff_count=3,
        minimum_history_events=1,
        feature_windows_hours=(1, 24),
    )

    assert dataset["prediction_at"].is_monotonic_increasing
    eligible_start = events.loc[events["analysis_eligible"], "observed_at"].min()
    assert dataset["prediction_at"].min() >= eligible_start + pd.Timedelta(hours=24)
    assert "future" not in set(dataset["channel_id"])
    assert set(dataset["silence_label"]) == {0, 1}
    assert dataset["evidence_tier"].eq("proxy").all()


def test_dataset_excludes_ineligible_migration_events():
    events = pd.DataFrame(
        {
            "channel_id": ["a", "a", "a", "a"],
            "observed_at": pd.to_datetime(
                [
                    "2021-05-01T00:00:00Z",
                    "2026-01-01T00:00:00Z",
                    "2026-01-02T00:00:00Z",
                    "2026-01-03T00:00:00Z",
                ]
            ),
            "sensor_value": [999, 1, 2, 3],
            "is_alarm": [True, False, False, False],
            "quality_status": [
                "monitoring_system_migration",
                "valid",
                "technical_anomaly",
                "valid",
            ],
            "analysis_eligible": [False, True, False, True],
        }
    )
    channels = pd.DataFrame({"channel_id": ["a"]})

    dataset = build_sensor_failure_dataset(
        events,
        channels,
        horizon_hours=12,
        cutoff_count=2,
        minimum_history_events=1,
        feature_windows_hours=(1, 12),
    )

    assert dataset.filter(like="value_max").max().max() < 999
