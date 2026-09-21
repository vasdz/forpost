"""Единое построение признаков для локального обучения и inference."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from forpost_prediction_core.time_utils import (
    SOURCE_TIMEZONE,
    normalize_cutoff,
    normalize_event_times,
)


def build_channel_features(
    events: pd.DataFrame,
    channels: pd.DataFrame,
    cutoff: pd.Timestamp,
    *,
    windows: Sequence[int] = (1, 6, 24),
) -> pd.DataFrame:
    """Строит поканальные признаки, используя только наблюдения до точки прогнозирования."""
    _require_columns(events, {"channel_id", "observed_at", "sensor_value"}, "события")
    _require_columns(channels, {"channel_id"}, "каналы")
    if not windows or any(window < 1 for window in windows):
        raise ValueError("Окна признаков должны быть положительными")

    normalized_events = events.copy()
    normalized_events["observed_at"] = normalize_event_times(normalized_events["observed_at"])
    cutoff = normalize_cutoff(cutoff)
    normalized_events["is_alarm"] = (
        normalized_events["is_alarm"].fillna(False).astype(bool)
        if "is_alarm" in normalized_events
        else False
    )
    normalized_events["quality_status"] = (
        normalized_events["quality_status"].fillna("unknown").astype(str)
        if "quality_status" in normalized_events
        else "unknown"
    )
    normalized_events["analysis_eligible"] = (
        normalized_events["analysis_eligible"].fillna(False).astype(bool)
        if "analysis_eligible" in normalized_events
        else True
    )
    history = normalized_events.loc[
        (normalized_events["observed_at"] < cutoff) & normalized_events["analysis_eligible"]
    ].copy()
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
        result = result.merge(
            grouped["is_alarm"].sum().rename(f"alarm_count_{window}h"),
            how="left",
            left_on="channel_id",
            right_index=True,
        )
        result[f"alarm_ratio_{window}h"] = (
            result[f"alarm_count_{window}h"]
            .div(result[f"event_count_{window}h"].where(result[f"event_count_{window}h"] > 0))
            .fillna(0.0)
        )
    count_columns = [
        column
        for window in windows
        for column in (
            f"event_count_{window}h",
            f"alarm_count_{window}h",
        )
    ]
    result[count_columns] = result[count_columns].fillna(0).astype("int64")

    latest = history.groupby("channel_id", sort=False)["observed_at"].max()
    result = result.merge(
        ((cutoff - latest).dt.total_seconds() / 3600).rename("hours_since_last_event"),
        how="left",
        left_on="channel_id",
        right_index=True,
    )
    bounded_history = history.loc[
        history["observed_at"] >= cutoff - pd.Timedelta(hours=max(windows))
    ]
    entropy = _interarrival_entropy_by_channel(bounded_history)
    result = result.merge(
        entropy.rename("interarrival_entropy"),
        how="left",
        left_on="channel_id",
        right_index=True,
    )
    slopes = _value_slope_per_hour_by_channel(bounded_history, cutoff)
    result = result.merge(
        slopes.rename("value_slope_per_hour"),
        how="left",
        left_on="channel_id",
        right_index=True,
    )
    result[["interarrival_entropy", "value_slope_per_hour"]] = result[
        ["interarrival_entropy", "value_slope_per_hour"]
    ].fillna(0.0)
    local_cutoff = cutoff.tz_convert(SOURCE_TIMEZONE)
    result["cutoff_hour"] = local_cutoff.hour
    result["cutoff_weekday"] = local_cutoff.weekday()
    result["cutoff_month"] = local_cutoff.month
    return result.sort_values("channel_id", kind="stable").reset_index(drop=True)


def _interarrival_entropy_by_channel(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float, name="interarrival_entropy")
    ordered = frame.sort_values(["channel_id", "observed_at"], kind="stable")
    intervals = (
        ordered.groupby("channel_id", sort=False)["observed_at"].diff().dt.total_seconds() / 3600
    )
    valid = intervals.notna() & intervals.ge(0)
    if not valid.any():
        return pd.Series(dtype=float, name="interarrival_entropy")
    edges = np.asarray((0, 1, 6, 24, 168, np.inf), dtype=float)
    buckets = np.searchsorted(edges, intervals.loc[valid].to_numpy(), side="right") - 1
    counts = (
        pd.DataFrame(
            {
                "channel_id": ordered.loc[valid, "channel_id"].to_numpy(),
                "bucket": buckets,
            }
        )
        .groupby(["channel_id", "bucket"], sort=False)
        .size()
    )
    totals = counts.groupby(level="channel_id").transform("sum")
    probabilities = counts / totals
    entropy = -(probabilities * np.log2(probabilities)).groupby(level="channel_id").sum()
    return entropy.rename("interarrival_entropy")


def _value_slope_per_hour_by_channel(frame: pd.DataFrame, cutoff: pd.Timestamp) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float, name="value_slope_per_hour")
    valid = frame.loc[frame["numeric_value"].notna(), ["channel_id", "observed_at"]].copy()
    valid["value"] = frame.loc[valid.index, "numeric_value"].astype(float)
    if valid.empty:
        return pd.Series(dtype=float, name="value_slope_per_hour")
    valid["hours"] = (valid["observed_at"].astype("int64") - cutoff.value) / 3_600_000_000_000
    valid["hours_sq"] = valid["hours"] ** 2
    valid["hours_value"] = valid["hours"] * valid["value"]
    stats = valid.groupby("channel_id", sort=False).agg(
        count=("value", "size"),
        hours_sum=("hours", "sum"),
        value_sum=("value", "sum"),
        hours_sq_sum=("hours_sq", "sum"),
        hours_value_sum=("hours_value", "sum"),
    )
    numerator = stats["hours_value_sum"] - (
        stats["hours_sum"] * stats["value_sum"] / stats["count"]
    )
    denominator = stats["hours_sq_sum"] - stats["hours_sum"] ** 2 / stats["count"]
    slope = numerator.div(denominator.where(denominator > 0)).fillna(0.0)
    slope.loc[stats["count"] < 2] = 0.0
    return slope.rename("value_slope_per_hour")


def _require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"В таблице {label} отсутствуют обязательные поля")
