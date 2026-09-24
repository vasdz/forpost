"""Временная разметка локальных задач без доступа к будущим данным в признаках."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from forpost_prediction_core.time_utils import normalize_cutoff, normalize_event_times

MINIMUM_CADENCE_INTERVALS = 3
MAXIMUM_RELATIVE_CADENCE_IQR = 0.5
MINIMUM_MATERIAL_DELAY_FRACTION = 0.25
MATERIAL_DELAY_MAD_MULTIPLIER = 3.0


@dataclass(frozen=True)
class CadenceEligibility:
    """Единый причинный контракт целевой популяции обучения и inference."""

    expected_cadence_hours: float
    expected_deadline: pd.Timestamp


def assess_cadence_eligibility(
    observed_at: pd.Series,
    cutoff: pd.Timestamp,
    *,
    horizon_hours: int,
) -> CadenceEligibility | None:
    """Проверяет устойчивый cadence только по уникальной истории до cutoff."""
    cutoff = normalize_cutoff(cutoff)
    history = normalize_event_times(observed_at)
    history = history.loc[history < cutoff].drop_duplicates().sort_values()
    if len(history) < MINIMUM_CADENCE_INTERVALS + 1:
        return None
    intervals = history.diff().dropna().dt.total_seconds().to_numpy(dtype=float) / 3600
    intervals = intervals[intervals > 0]
    if len(intervals) < MINIMUM_CADENCE_INTERVALS:
        return None
    cadence = float(np.median(intervals))
    mad = float(np.median(np.abs(intervals - cadence)))
    lower_quartile, upper_quartile = np.quantile(intervals, (0.25, 0.75))
    relative_iqr = float((upper_quartile - lower_quartile) / cadence)
    if not np.isfinite(cadence) or cadence <= 0 or relative_iqr > MAXIMUM_RELATIVE_CADENCE_IQR:
        return None
    material_delay = max(
        MATERIAL_DELAY_MAD_MULTIPLIER * mad,
        MINIMUM_MATERIAL_DELAY_FRACTION * cadence,
    )
    deadline = history.iloc[-1] + pd.Timedelta(hours=cadence + material_delay)
    if deadline <= cutoff or deadline > cutoff + pd.Timedelta(hours=horizon_hours):
        return None
    return CadenceEligibility(cadence, deadline)


def eligible_channel_cadences(
    events: pd.DataFrame,
    channels: pd.DataFrame,
    cutoff: pd.Timestamp,
    *,
    horizon_hours: int,
) -> pd.DataFrame:
    """Возвращает только общую target population для labels и serving."""
    if horizon_hours < 1:
        raise ValueError("Горизонт должен быть положительным")
    if "channel_id" not in events or "observed_at" not in events or "channel_id" not in channels:
        raise ValueError("Для cadence требуются канал и время события")
    cutoff = normalize_cutoff(cutoff)
    eligible = events.loc[:, ["channel_id", "observed_at"]].copy()
    eligible["observed_at"] = normalize_event_times(eligible["observed_at"])
    if "analysis_eligible" in events:
        eligible = eligible.loc[events["analysis_eligible"].eq(True)].copy()  # noqa: E712
    eligible = eligible.dropna(subset=["channel_id", "observed_at"])
    grouped = {
        channel_id: values["observed_at"]
        for channel_id, values in eligible.groupby("channel_id", sort=False)
    }
    rows: list[dict[str, object]] = []
    for channel_id in channels["channel_id"].drop_duplicates():
        observed_at = grouped.get(channel_id)
        if observed_at is None:
            continue
        cadence = assess_cadence_eligibility(observed_at, cutoff, horizon_hours=horizon_hours)
        if cadence is not None:
            rows.append(
                {
                    "channel_id": channel_id,
                    "expected_cadence_hours": cadence.expected_cadence_hours,
                    "expected_deadline": cadence.expected_deadline,
                }
            )
    return pd.DataFrame(rows, columns=["channel_id", "expected_cadence_hours", "expected_deadline"])


def label_silence_horizon(
    events: pd.DataFrame, channels: pd.DataFrame, cutoff: pd.Timestamp, *, horizon_hours: int
) -> pd.DataFrame:
    """Размечает зрелое превышение устойчивого индивидуального cadence."""
    if horizon_hours < 1:
        raise ValueError("Горизонт должен быть положительным")
    if "channel_id" not in events or "observed_at" not in events or "channel_id" not in channels:
        raise ValueError("Для разметки требуются канал и время события")
    cutoff = normalize_cutoff(cutoff)
    cadence_rows = eligible_channel_cadences(events, channels, cutoff, horizon_hours=horizon_hours)
    eligible = events.loc[:, ["channel_id", "observed_at"]].copy()
    eligible["observed_at"] = normalize_event_times(eligible["observed_at"])
    if "analysis_eligible" in events:
        eligible = eligible.loc[events["analysis_eligible"].eq(True)].copy()  # noqa: E712
    grouped = {
        channel_id: values["observed_at"]
        for channel_id, values in eligible.groupby("channel_id", sort=False)
    }
    rows: list[dict[str, object]] = []
    for item in cadence_rows.itertuples(index=False):
        channel_events = grouped[item.channel_id]
        timely = channel_events.loc[
            (channel_events >= cutoff) & (channel_events <= item.expected_deadline)
        ]
        rows.append(
            {
                "channel_id": item.channel_id,
                "silence_label": int(timely.empty),
                "expected_cadence_hours": item.expected_cadence_hours,
                "expected_deadline": item.expected_deadline,
            }
        )
    result = pd.DataFrame(
        rows,
        columns=[
            "channel_id",
            "silence_label",
            "expected_cadence_hours",
            "expected_deadline",
        ],
    )
    if not result.empty:
        result["silence_label"] = result["silence_label"].astype("int8")
    return result.sort_values("channel_id", kind="stable").reset_index(drop=True)
