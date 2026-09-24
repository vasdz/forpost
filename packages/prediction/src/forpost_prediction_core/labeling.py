"""Временная разметка локальных задач без доступа к будущим данным в признаках."""

from __future__ import annotations

import numpy as np
import pandas as pd

from forpost_prediction_core.time_utils import normalize_cutoff, normalize_event_times

MINIMUM_CADENCE_INTERVALS = 3
MAXIMUM_RELATIVE_CADENCE_IQR = 0.5
MINIMUM_MATERIAL_DELAY_FRACTION = 0.25
MATERIAL_DELAY_MAD_MULTIPLIER = 3.0


def label_silence_horizon(
    events: pd.DataFrame, channels: pd.DataFrame, cutoff: pd.Timestamp, *, horizon_hours: int
) -> pd.DataFrame:
    """Размечает зрелое превышение устойчивого индивидуального cadence."""
    if horizon_hours < 1:
        raise ValueError("Горизонт должен быть положительным")
    if "channel_id" not in events or "observed_at" not in events or "channel_id" not in channels:
        raise ValueError("Для разметки требуются канал и время события")
    cutoff = normalize_cutoff(cutoff)
    eligible = events.copy()
    eligible["observed_at"] = normalize_event_times(eligible["observed_at"])
    if "analysis_eligible" in eligible:
        eligible = eligible.loc[eligible["analysis_eligible"].eq(True)].copy()  # noqa: E712
    eligible = eligible.dropna(subset=["channel_id", "observed_at"])
    horizon_end = cutoff + pd.Timedelta(hours=horizon_hours)
    rows: list[dict[str, object]] = []
    channel_times = {
        channel_id: values["observed_at"]
        for channel_id, values in eligible.groupby("channel_id", sort=False)
    }
    for channel_id in channels["channel_id"].drop_duplicates():
        channel_events = channel_times.get(channel_id)
        if channel_events is None:
            continue
        history = channel_events.loc[channel_events < cutoff].drop_duplicates().sort_values()
        if len(history) < MINIMUM_CADENCE_INTERVALS + 1:
            continue
        intervals = history.diff().dropna().dt.total_seconds().to_numpy(dtype=float) / 3600
        intervals = intervals[intervals > 0]
        if len(intervals) < MINIMUM_CADENCE_INTERVALS:
            continue
        cadence = float(np.median(intervals))
        mad = float(np.median(np.abs(intervals - cadence)))
        lower_quartile, upper_quartile = np.quantile(intervals, (0.25, 0.75))
        relative_iqr = float((upper_quartile - lower_quartile) / cadence)
        if not np.isfinite(cadence) or cadence <= 0 or relative_iqr > MAXIMUM_RELATIVE_CADENCE_IQR:
            continue
        material_delay = max(
            MATERIAL_DELAY_MAD_MULTIPLIER * mad,
            MINIMUM_MATERIAL_DELAY_FRACTION * cadence,
        )
        deadline = history.iloc[-1] + pd.Timedelta(hours=cadence + material_delay)
        if deadline <= cutoff or deadline > horizon_end:
            continue
        timely = channel_events.loc[(channel_events >= cutoff) & (channel_events <= deadline)]
        rows.append(
            {
                "channel_id": channel_id,
                "silence_label": int(timely.empty),
                "expected_cadence_hours": cadence,
            }
        )
    result = pd.DataFrame(
        rows,
        columns=["channel_id", "silence_label", "expected_cadence_hours"],
    )
    if not result.empty:
        result["silence_label"] = result["silence_label"].astype("int8")
    return result.sort_values("channel_id", kind="stable").reset_index(drop=True)
