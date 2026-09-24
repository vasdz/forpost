import pandas as pd
import pytest
from forpost_prediction_core import dataset as dataset_module
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
    from scripts.train_sensor_failure import _current_features

    inference = _current_features(
        events,
        channels,
        tuple(feature_columns),
        (1, 6, 24, 72, 168),
        horizon_hours=24,
    )
    assert tuple(inference.loc[:, feature_columns].columns) == tuple(feature_columns)


def test_dataset_is_chronological_and_uses_only_channels_with_history():
    channel_a_times = pd.date_range("2026-01-01", periods=25, freq="4h", tz="UTC")
    channel_b_times = pd.date_range("2026-01-01T02:00:00Z", periods=24, freq="4h")
    observed_at = channel_a_times.append(channel_b_times).append(
        pd.DatetimeIndex([pd.Timestamp("2026-01-05T03:00:00Z")])
    )
    events = pd.DataFrame(
        {
            "channel_id": ["a"] * len(channel_a_times) + ["b"] * len(channel_b_times) + ["future"],
            "observed_at": observed_at,
            "sensor_value": [1.0] * len(observed_at),
            "is_alarm": [False] * len(observed_at),
            "quality_status": ["valid"] * len(observed_at),
            "analysis_eligible": [True] * len(observed_at),
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
    assert set(dataset["silence_label"]) <= {0, 1}
    assert dataset["evidence_tier"].eq("proxy").all()


def test_dataset_excludes_ineligible_migration_events():
    eligible_times = pd.date_range("2026-01-01", periods=40, freq="h", tz="UTC")
    events = pd.DataFrame(
        {
            "channel_id": ["a"] * (len(eligible_times) + 1),
            "observed_at": pd.DatetimeIndex([pd.Timestamp("2021-05-01T00:00:00Z")]).append(
                eligible_times
            ),
            "sensor_value": [999.0] + [1.0] * len(eligible_times),
            "is_alarm": [True] + [False] * len(eligible_times),
            "quality_status": ["monitoring_system_migration"] + ["valid"] * len(eligible_times),
            "analysis_eligible": [False] + [True] * len(eligible_times),
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


def test_dataset_contains_only_channels_with_mature_cadence_labels() -> None:
    """Ловит попадание censored-канала в обучающий набор как отрицательного."""
    fast_times = pd.date_range("2026-01-01", periods=80, freq="h", tz="UTC")
    sparse_times = pd.date_range("2026-01-01", periods=3, freq="12h", tz="UTC")
    events = pd.DataFrame(
        {
            "channel_id": ["fast"] * len(fast_times) + ["sparse"] * len(sparse_times),
            "observed_at": fast_times.append(sparse_times),
            "sensor_value": [1.0] * (len(fast_times) + len(sparse_times)),
            "analysis_eligible": [True] * (len(fast_times) + len(sparse_times)),
        }
    )
    channels = pd.DataFrame({"channel_id": ["fast", "sparse"]})

    dataset = build_sensor_failure_dataset(
        events,
        channels,
        horizon_hours=24,
        cutoff_count=3,
        minimum_history_events=1,
        feature_windows_hours=(1, 24),
    )

    assert set(dataset["channel_id"]) == {"fast"}


def test_label_layout_matches_the_training_dataset_without_building_features() -> None:
    """Ловит расхождение label-only precheck и фактического training dataset."""
    assert hasattr(dataset_module, "build_sensor_failure_label_layout")
    times = pd.date_range("2026-01-01", periods=80, freq="h", tz="UTC")
    events = pd.DataFrame(
        {
            "channel_id": ["a"] * len(times),
            "observed_at": times,
            "sensor_value": [1.0] * len(times),
            "analysis_eligible": [True] * len(times),
        }
    )
    channels = pd.DataFrame({"channel_id": ["a"]})
    options = {
        "horizon_hours": 24,
        "cutoff_count": 3,
        "minimum_history_events": 1,
        "feature_windows_hours": (1, 24),
    }

    layout = dataset_module.build_sensor_failure_label_layout(events, channels, **options)
    dataset = build_sensor_failure_dataset(events, channels, **options)

    pd.testing.assert_frame_equal(
        layout.loc[:, ["channel_id", "silence_label", "prediction_at"]],
        dataset.loc[:, ["channel_id", "silence_label", "prediction_at"]].reset_index(drop=True),
    )


def test_dataset_includes_event_exactly_at_horizon_deadline() -> None:
    """Ловит исключение своевременного события на правой границе horizon."""
    cutoff = pd.Timestamp("2026-01-04T00:00:00Z")
    cadence = pd.Timedelta(hours=19.28)
    last = cutoff - pd.Timedelta(minutes=6)
    history = pd.DatetimeIndex([last - 3 * cadence, last - 2 * cadence, last - cadence, last])
    deadline = cutoff + pd.Timedelta(hours=24)
    normalized = pd.DataFrame(
        {
            "channel_id": ["a"] * 5,
            "observed_at": history.append(pd.DatetimeIndex([deadline])),
            "sensor_value": [1.0] * 5,
        }
    ).sort_values("observed_at", ignore_index=True)

    layout = dataset_module._build_label_layout(
        normalized,
        pd.DataFrame({"channel_id": ["a"]}),
        pd.DatetimeIndex([cutoff]),
        horizon_hours=24,
        minimum_history_events=3,
        feature_windows_hours=(168,),
    )

    assert layout.loc[0, "expected_deadline"] == deadline
    assert layout.loc[0, "silence_label"] == 0


def test_cutoffs_are_uniform_in_calendar_time_not_event_density() -> None:
    """Ловит выбор cutoff по позициям событий вместо календарной оси."""
    dense = pd.date_range("2026-01-01", periods=200, freq="10min", tz="UTC")
    sparse = pd.date_range("2026-01-10", periods=20, freq="6h", tz="UTC")
    times = dense.append(sparse)
    events = pd.DataFrame(
        {"channel_id": ["a"] * len(times), "observed_at": times, "sensor_value": 1.0}
    )

    _normalized, cutoffs = dataset_module._prepare_sensor_failure_inputs(
        events,
        pd.DataFrame({"channel_id": ["a"]}),
        horizon_hours=24,
        cutoff_count=8,
        minimum_history_events=3,
        feature_windows_hours=(24,),
    )

    gaps = cutoffs.to_series().diff().dropna().dt.total_seconds()
    assert gaps.max() - gaps.min() <= 0.001


def test_dataset_honours_source_selected_calendar_cutoffs() -> None:
    """Ловит повторный выбор cutoff по границам разреженного window corpus."""
    times = pd.date_range("2026-01-01", periods=240, freq="h", tz="UTC")
    events = pd.DataFrame(
        {
            "channel_id": ["a"] * len(times),
            "observed_at": times,
            "sensor_value": [1.0] * len(times),
        }
    )
    requested = pd.DatetimeIndex(
        [pd.Timestamp("2026-01-04T00:00:00Z"), pd.Timestamp("2026-01-08T00:00:00Z")]
    )

    dataset = build_sensor_failure_dataset(
        events,
        pd.DataFrame({"channel_id": ["a"]}),
        horizon_hours=24,
        cutoff_count=2,
        minimum_history_events=1,
        feature_windows_hours=(24,),
        prediction_cutoffs=requested,
    )

    assert tuple(dataset["prediction_at"].drop_duplicates()) == tuple(requested)


def test_dataset_skips_empty_partition_calendar_endpoints() -> None:
    """Ловит отказ sparse corpus из-за пустых календарных точек по краям года."""
    times = pd.date_range("2026-01-04", periods=96, freq="h", tz="UTC")
    events = pd.DataFrame(
        {
            "channel_id": ["a"] * len(times),
            "observed_at": times,
            "sensor_value": [1.0] * len(times),
        }
    )
    requested = pd.DatetimeIndex(
        [
            pd.Timestamp("2026-01-02T00:00:00Z"),
            pd.Timestamp("2026-01-06T00:00:00Z"),
            pd.Timestamp("2026-12-31T00:00:00Z"),
        ]
    )

    dataset = build_sensor_failure_dataset(
        events,
        pd.DataFrame({"channel_id": ["a"]}),
        horizon_hours=24,
        cutoff_count=3,
        minimum_history_events=1,
        feature_windows_hours=(24,),
        prediction_cutoffs=requested,
    )

    assert tuple(dataset["prediction_at"].drop_duplicates()) == (requested[1],)


def test_sorted_time_slice_avoids_boolean_full_frame_scan(monkeypatch) -> None:
    """Ловит возврат O(cutoffs * all_rows) масок по полной таблице."""
    times = pd.date_range("2026-01-01", periods=100, freq="h", tz="UTC")
    frame = pd.DataFrame({"observed_at": times, "value": range(100)})

    def forbidden_comparison(*_args, **_kwargs):
        raise AssertionError("Временной slice не должен строить full-frame boolean mask")

    monkeypatch.setattr(pd.Series, "__ge__", forbidden_comparison)
    monkeypatch.setattr(pd.Series, "__le__", forbidden_comparison)
    sliced = dataset_module._slice_sorted_events(
        frame, pd.Timestamp("2026-01-02T00:00:00Z"), pd.Timestamp("2026-01-02T03:00:00Z")
    )

    assert sliced["value"].tolist() == [24, 25, 26, 27]


def test_dataset_rejects_when_every_candidate_label_is_censored() -> None:
    """Ловит возврат пустого training frame при отсутствии зрелых исходов."""
    times = pd.date_range("2026-01-01", periods=6, freq="12h", tz="UTC")
    events = pd.DataFrame(
        {
            "channel_id": ["sparse"] * len(times),
            "observed_at": times,
            "sensor_value": [1.0] * len(times),
            "analysis_eligible": [True] * len(times),
        }
    )

    with pytest.raises(ValueError, match="истории"):
        build_sensor_failure_dataset(
            events,
            pd.DataFrame({"channel_id": ["sparse"]}),
            horizon_hours=24,
            cutoff_count=2,
            minimum_history_events=1,
            feature_windows_hours=(1, 24),
        )
