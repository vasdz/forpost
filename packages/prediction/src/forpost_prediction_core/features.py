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

DEFAULT_FEATURE_WINDOWS_HOURS = (1, 6, 24, 72, 168)


def build_channel_features(
    events: pd.DataFrame,
    channels: pd.DataFrame,
    cutoff: pd.Timestamp,
    *,
    windows: Sequence[int] = DEFAULT_FEATURE_WINDOWS_HOURS,
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
    history = history.reset_index(drop=True)
    history["numeric_value"] = pd.to_numeric(history["sensor_value"], errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )
    history["missing"] = history["numeric_value"].isna()
    # Качество характеризует только допустимую историю, как и физические значения.
    history["quality_issue"] = history["quality_status"].ne("valid")
    channel_columns = [
        "channel_id",
        *[name for name in ("sensor_type", "engineering_system") if name in channels],
    ]
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
        for signal in ("missing", "quality_issue"):
            result = result.merge(
                grouped[signal].sum().rename(f"{signal}_count_{window}h"),
                how="left",
                left_on="channel_id",
                right_index=True,
            )
            result[f"{signal}_ratio_{window}h"] = (
                result[f"{signal}_count_{window}h"]
                .div(result[f"event_count_{window}h"].where(result[f"event_count_{window}h"] > 0))
                .fillna(0.0)
            )
    count_columns = [
        column
        for window in windows
        for column in (
            f"event_count_{window}h",
            f"alarm_count_{window}h",
            f"missing_count_{window}h",
            f"quality_issue_count_{window}h",
        )
    ]
    result[count_columns] = result[count_columns].fillna(0).astype("int64")
    for short, long in zip(sorted(set(windows))[:-1], sorted(set(windows))[1:], strict=True):
        result[f"frequency_change_{short}h_to_{long}h"] = result[f"event_count_{short}h"].div(
            short
        ) - result[f"event_count_{long}h"].div(long)

    latest = history.groupby("channel_id", sort=False)["observed_at"].max()
    result = result.merge(
        ((cutoff - latest).dt.total_seconds() / 3600).rename("hours_since_last_event"),
        how="left",
        left_on="channel_id",
        right_index=True,
    )
    bounded_history = history.loc[
        history["observed_at"] >= cutoff - pd.Timedelta(hours=max(windows))
    ].sort_values(["channel_id", "observed_at"], kind="stable")
    bounded_history["interval_hours"] = (
        bounded_history.groupby("channel_id", sort=False)["observed_at"]
        .diff()
        .dt.total_seconds()
        .div(3600)
    )
    bounded_history["frequency"] = 1 / bounded_history["interval_hours"].where(
        bounded_history["interval_hours"] > 0
    )
    intervals = bounded_history.groupby("channel_id", sort=False)["interval_hours"]
    interval_stats = intervals.agg(
        interarrival_median_hours="median",
        interarrival_mad_hours=lambda values: (values - values.median()).abs().median(),
        interarrival_q25_hours=lambda values: values.quantile(0.25),
        interarrival_q75_hours=lambda values: values.quantile(0.75),
    )
    interval_stats["interarrival_cv"] = intervals.std().div(
        intervals.mean().where(intervals.mean() > 0)
    )
    result = result.merge(interval_stats, how="left", left_on="channel_id", right_index=True)
    result["silence_to_normal_ratio"] = result["hours_since_last_event"].div(
        result["interarrival_median_hours"].clip(lower=1 / 60)
    )
    coverage = bounded_history.groupby("channel_id", sort=False).agg(
        history_event_count=("observed_at", "size"),
        first=("observed_at", "min"),
        last=("observed_at", "max"),
    )
    coverage["history_span_hours"] = (
        coverage["last"] - coverage["first"]
    ).dt.total_seconds() / 3600
    # Это наблюдаемое покрытие окна, а не предположение о причине усечения источника.
    coverage["history_window_coverage"] = (
        (cutoff - coverage["first"]).dt.total_seconds() / (3600 * max(windows))
    ).clip(0, 1)
    coverage_columns = ["history_event_count", "history_span_hours", "history_window_coverage"]
    result = result.merge(
        coverage[coverage_columns], how="left", left_on="channel_id", right_index=True
    )
    result[coverage_columns] = result[coverage_columns].fillna(0)
    result["history_event_count"] = result["history_event_count"].astype("int64")
    result["history_window_incomplete"] = result["history_window_coverage"].lt(1).astype("int64")
    for column, prefix in (("numeric_value", "value"), ("frequency", "frequency")):
        decay = _time_decay_by_channel(bounded_history, column, prefix)
        result = result.merge(decay, how="left", left_on="channel_id", right_index=True)
    entropy = _interarrival_entropy_by_channel(bounded_history)
    result = result.merge(
        entropy.rename("interarrival_entropy"),
        how="left",
        left_on="channel_id",
        right_index=True,
    )
    result["interarrival_entropy"] = result["interarrival_entropy"].fillna(0.0)
    for column, prefix in (("numeric_value", "value"), ("interval_hours", "interarrival")):
        slopes = _slope_per_hour_by_channel(bounded_history, cutoff, column)
        robust = _robust_slope_by_channel(bounded_history, column)
        for values, name in (
            (slopes, f"{prefix}_slope_per_hour"),
            (robust, f"{prefix}_robust_slope_per_hour"),
        ):
            result = result.merge(
                values.rename(name), how="left", left_on="channel_id", right_index=True
            )
            result[name] = result[name].fillna(0.0)
    local_cutoff = cutoff.tz_convert(SOURCE_TIMEZONE)
    result["cutoff_hour"] = local_cutoff.hour
    result["cutoff_weekday"] = local_cutoff.weekday()
    result["cutoff_month"] = local_cutoff.month
    for name, value, period in (
        ("hour", local_cutoff.hour, 24),
        ("weekday", local_cutoff.weekday(), 7),
        ("month", local_cutoff.month - 1, 12),
    ):
        angle = 2 * np.pi * value / period
        result[f"{name}_sin"] = np.sin(angle)
        result[f"{name}_cos"] = np.cos(angle)
    numeric_columns = result.select_dtypes(include="number").columns
    result[numeric_columns] = result[numeric_columns].replace([np.inf, -np.inf], np.nan)
    return result.sort_values("channel_id", kind="stable").reset_index(drop=True)


def _time_decay_by_channel(frame: pd.DataFrame, column: str, prefix: str) -> pd.DataFrame:
    """Временные веса с полураспадом 6 ч; дисперсия генеральная, с теми же весами."""
    columns = [f"{prefix}_ewm_mean", f"{prefix}_ewm_variance", f"{prefix}_ewm_std"]
    rows = {}
    for channel_id, group in frame.loc[frame[column].notna()].groupby("channel_id", sort=False):
        values = group[column].astype(float)
        scale = max(float(values.abs().max()), 1.0)
        scaled = values / scale
        times = group["observed_at"]
        mean = scaled.ewm(halflife="6h", times=times).mean().iloc[-1]
        # Pandas ewm.var/std не используют times: считаем второй момент через mean.
        variance = ((scaled - mean) ** 2).ewm(halflife="6h", times=times).mean().iloc[-1]
        std = np.sqrt(max(variance, 0.0)) * scale
        with np.errstate(over="ignore", invalid="ignore"):
            rows[channel_id] = [mean * scale, std * std, std]
    return pd.DataFrame.from_dict(rows, orient="index", columns=columns).astype(float)


def _robust_slope_by_channel(frame: pd.DataFrame, column: str) -> pd.Series:
    """Медиана соседних скоростей устойчива к единичным выбросам и линейна по памяти."""
    valid = frame.loc[frame[column].notna()]
    grouped = valid.groupby("channel_id", sort=False)
    hours = grouped["observed_at"].diff().dt.total_seconds() / 3600
    rates = grouped[column].diff().div(hours.where(hours > 0)).replace([np.inf, -np.inf], np.nan)
    return rates.groupby(valid["channel_id"], sort=False).median()


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


def _slope_per_hour_by_channel(
    frame: pd.DataFrame,
    cutoff: pd.Timestamp,
    column: str,
) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float, name="value_slope_per_hour")
    valid = frame.loc[frame[column].notna(), ["channel_id", "observed_at"]].copy()
    valid["value"] = frame.loc[valid.index, column].astype(float)
    if valid.empty:
        return pd.Series(dtype=float, name="value_slope_per_hour")
    valid["hours"] = (valid["observed_at"] - cutoff).dt.total_seconds() / 3600
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
