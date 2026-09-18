"""Единое построение признаков для локального обучения и inference."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


def build_channel_features(
    events: pd.DataFrame,
    channels: pd.DataFrame,
    cutoff: pd.Timestamp,
    *,
    windows: Sequence[int] = (1, 24, 168, 720),
) -> pd.DataFrame:
    """Строит поканальные признаки, используя только наблюдения до точки прогнозирования."""
    _require_columns(events, {"channel_id", "observed_at", "sensor_value"}, "события")
    _require_columns(channels, {"channel_id"}, "каналы")
    if not windows or any(window < 1 for window in windows):
        raise ValueError("Окна признаков должны быть положительными")

    normalized_events = events.copy()
    normalized_events["observed_at"] = pd.to_datetime(normalized_events["observed_at"])
    history = normalized_events.loc[normalized_events["observed_at"] < cutoff].copy()
    history["numeric_value"] = pd.to_numeric(history["sensor_value"], errors="coerce")
    channel_columns = ["channel_id", *[name for name in ("sensor_type",) if name in channels]]
    result = channels.loc[:, channel_columns].drop_duplicates("channel_id").copy()

    for window in windows:
        start = cutoff - pd.Timedelta(hours=window)
        windowed = history.loc[history["observed_at"] >= start]
        grouped = windowed.groupby("channel_id", sort=False)
        result = result.merge(
            grouped.size().rename(f"event_count_{window}h"),
            how="left",
            left_on="channel_id",
            right_index=True,
        )
        numeric = windowed.loc[windowed["numeric_value"].notna()].groupby("channel_id", sort=False)[
            "numeric_value"
        ]
        result = result.merge(
            numeric.agg(["mean", "std", "min", "max"]).rename(
                columns={
                    "mean": f"value_mean_{window}h",
                    "std": f"value_std_{window}h",
                    "min": f"value_min_{window}h",
                    "max": f"value_max_{window}h",
                }
            ),
            how="left",
            left_on="channel_id",
            right_index=True,
        )
    result[[f"event_count_{window}h" for window in windows]] = result[
        [f"event_count_{window}h" for window in windows]
    ].fillna(0).astype("int64")

    latest = history.groupby("channel_id", sort=False)["observed_at"].max()
    result = result.merge(
        ((cutoff - latest).dt.total_seconds() / 3600).rename("hours_since_last_event"),
        how="left",
        left_on="channel_id",
        right_index=True,
    )
    entropy = history.groupby("channel_id", sort=False)["observed_at"].apply(_interarrival_entropy)
    result = result.merge(
        entropy.rename("interarrival_entropy"),
        how="left",
        left_on="channel_id",
        right_index=True,
    )
    slopes = history.groupby("channel_id", sort=False).apply(
        _value_slope_per_hour, include_groups=False
    )
    result = result.merge(
        slopes.rename("value_slope_per_hour"),
        how="left",
        left_on="channel_id",
        right_index=True,
    )
    return result.sort_values("channel_id", kind="stable").reset_index(drop=True)


def _interarrival_entropy(values: pd.Series) -> float:
    ordered = values.sort_values().astype("int64").to_numpy()
    if len(ordered) < 3:
        return 0.0
    intervals = np.diff(ordered) / 3_600_000_000_000
    counts, _ = np.histogram(intervals, bins=(0, 1, 6, 24, 168, np.inf))
    probabilities = counts[counts > 0] / counts.sum()
    return float(-(probabilities * np.log2(probabilities)).sum())


def _value_slope_per_hour(frame: pd.DataFrame) -> float:
    numeric = pd.to_numeric(frame["sensor_value"], errors="coerce")
    valid = numeric.notna()
    if int(valid.sum()) < 2:
        return 0.0
    timestamps = pd.to_datetime(frame.loc[valid, "observed_at"]).astype("int64").to_numpy()
    hours = (timestamps - timestamps.min()) / 3_600_000_000_000
    return float(np.polyfit(hours, numeric.loc[valid].to_numpy(dtype=float), deg=1)[0])


def _require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"В таблице {label} отсутствуют обязательные поля")
