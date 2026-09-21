import pandas as pd
from forpost_prediction_core.dataset import build_sensor_failure_dataset
from forpost_prediction_core.features import build_channel_features


def test_default_dataset_warms_up_weekly_features_and_matches_inference() -> None:
    """Ловит расхождение окон schema-v5 между dataset и прямым inference."""
    events = pd.DataFrame(
        {
            "channel_id": ["a"] * 49,
            "observed_at": pd.date_range("2026-01-01", periods=49, freq="6h", tz="UTC"),
            "sensor_value": list(range(49)),
        }
    )
    channels = pd.DataFrame({"channel_id": ["a"], "engineering_system": ["source-system"]})
    dataset = build_sensor_failure_dataset(events, channels, cutoff_count=3)
    assert dataset["prediction_at"].min() >= events["observed_at"].min() + pd.Timedelta(days=7)
    assert dataset["event_count_168h"].eq(28).all()
    assert dataset["event_count_72h"].eq(12).all()
    assert dataset["engineering_system"].eq("source-system").all()
    feature_columns = dataset.columns.drop(["silence_label", "prediction_at", "evidence_tier"])
    for cutoff, frame in dataset.groupby("prediction_at"):
        expected = build_channel_features(events, channels, cutoff)
        pd.testing.assert_frame_equal(frame[feature_columns].reset_index(drop=True), expected)


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
