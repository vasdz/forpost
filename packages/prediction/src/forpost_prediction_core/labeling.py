"""Временная разметка локальных задач без доступа к будущим данным в признаках."""

from __future__ import annotations

import pandas as pd

from forpost_prediction_core.time_utils import normalize_cutoff, normalize_event_times


def label_silence_horizon(
    events: pd.DataFrame, channels: pd.DataFrame, cutoff: pd.Timestamp, *, horizon_hours: int
) -> pd.DataFrame:
    """Помечает отсутствие события в будущем окне как прокси-лейбл тишины."""
    if horizon_hours < 1:
        raise ValueError("Горизонт должен быть положительным")
    if "channel_id" not in events or "observed_at" not in events or "channel_id" not in channels:
        raise ValueError("Для разметки требуются канал и время события")
    observed_at = normalize_event_times(events["observed_at"])
    cutoff = normalize_cutoff(cutoff)
    horizon_end = cutoff + pd.Timedelta(hours=horizon_hours)
    future = events.loc[(observed_at >= cutoff) & (observed_at < horizon_end), "channel_id"]
    result = channels.loc[:, ["channel_id"]].drop_duplicates("channel_id").copy()
    result["silence_label"] = (~result["channel_id"].isin(set(future))).astype("int8")
    return result.sort_values("channel_id", kind="stable").reset_index(drop=True)
