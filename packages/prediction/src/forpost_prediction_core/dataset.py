"""Point-in-time наборы для локального обучения моделей."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from forpost_prediction_core.features import DEFAULT_FEATURE_WINDOWS_HOURS, build_channel_features
from forpost_prediction_core.labeling import label_silence_horizon
from forpost_prediction_core.time_utils import normalize_event_times


def build_sensor_failure_dataset(
    events: pd.DataFrame,
    channels: pd.DataFrame,
    *,
    horizon_hours: int = 24,
    cutoff_count: int = 12,
    minimum_history_events: int = 3,
    feature_windows_hours: Sequence[int] = DEFAULT_FEATURE_WINDOWS_HOURS,
) -> pd.DataFrame:
    """Строит утверждённый proxy-набор тишины без утечки событий после cutoff."""
    normalized, cutoffs = _prepare_sensor_failure_inputs(
        events,
        channels,
        horizon_hours=horizon_hours,
        cutoff_count=cutoff_count,
        minimum_history_events=minimum_history_events,
        feature_windows_hours=feature_windows_hours,
    )
    layout = _build_label_layout(
        normalized,
        channels,
        cutoffs,
        horizon_hours=horizon_hours,
        minimum_history_events=minimum_history_events,
        feature_windows_hours=feature_windows_hours,
    )
    frames: list[pd.DataFrame] = []
    context_before = pd.Timedelta(hours=max(feature_windows_hours))
    context_after = pd.Timedelta(hours=horizon_hours)
    for cutoff, cutoff_labels in layout.groupby("prediction_at", sort=False):
        context = normalized.loc[
            (normalized["observed_at"] >= cutoff - context_before)
            & (normalized["observed_at"] < cutoff + context_after)
        ]
        features = build_channel_features(context, channels, cutoff, windows=feature_windows_hours)
        frame = features.merge(cutoff_labels.drop(columns="prediction_at"), on="channel_id")
        frame["prediction_at"] = cutoff
        frame["evidence_tier"] = "proxy"
        frames.append(frame)
    return pd.concat(frames, ignore_index=True).sort_values(
        ["prediction_at", "channel_id"], kind="stable", ignore_index=True
    )


def build_sensor_failure_label_layout(
    events: pd.DataFrame,
    channels: pd.DataFrame,
    *,
    horizon_hours: int = 24,
    cutoff_count: int = 12,
    minimum_history_events: int = 3,
    feature_windows_hours: Sequence[int] = DEFAULT_FEATURE_WINDOWS_HOURS,
) -> pd.DataFrame:
    """Строит только зрелые proxy-лейблы для проверки layout до расчёта признаков."""
    normalized, cutoffs = _prepare_sensor_failure_inputs(
        events,
        channels,
        horizon_hours=horizon_hours,
        cutoff_count=cutoff_count,
        minimum_history_events=minimum_history_events,
        feature_windows_hours=feature_windows_hours,
    )
    return _build_label_layout(
        normalized,
        channels,
        cutoffs,
        horizon_hours=horizon_hours,
        minimum_history_events=minimum_history_events,
        feature_windows_hours=feature_windows_hours,
    )


def _prepare_sensor_failure_inputs(
    events: pd.DataFrame,
    channels: pd.DataFrame,
    *,
    horizon_hours: int,
    cutoff_count: int,
    minimum_history_events: int,
    feature_windows_hours: Sequence[int],
) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    if horizon_hours < 1 or cutoff_count < 2 or minimum_history_events < 1:
        raise ValueError("Параметры временного набора должны быть положительными")
    if not feature_windows_hours or any(window < 1 for window in feature_windows_hours):
        raise ValueError("Окна признаков должны быть положительными")
    required_events = {"channel_id", "observed_at", "sensor_value"}
    if not required_events.issubset(events) or "channel_id" not in channels:
        raise ValueError("Источники не содержат обязательные поля ML")

    normalized = events.copy()
    normalized["observed_at"] = normalize_event_times(normalized["observed_at"])
    if "analysis_eligible" in normalized:
        normalized = normalized.loc[normalized["analysis_eligible"].eq(True)].copy()  # noqa: E712
    normalized = normalized.dropna(subset=["channel_id", "observed_at"])
    if normalized.empty:
        raise ValueError("Нет событий, допустимых для обучения")
    normalized = normalized.sort_values("observed_at", kind="stable").reset_index(drop=True)

    warmup_hours = max(horizon_hours, *feature_windows_hours)
    first = normalized["observed_at"].min() + pd.Timedelta(hours=warmup_hours)
    last = normalized["observed_at"].max() - pd.Timedelta(hours=horizon_hours)
    if first > last:
        raise ValueError("История короче двух горизонтов прогнозирования")
    candidate_cutoffs = (
        normalized.loc[
            (normalized["observed_at"] >= first) & (normalized["observed_at"] < last),
            "observed_at",
        ]
        .drop_duplicates()
        .sort_values(kind="stable")
        .reset_index(drop=True)
    )
    if len(candidate_cutoffs) >= 2:
        positions = np.linspace(
            0,
            len(candidate_cutoffs) - 1,
            min(cutoff_count, len(candidate_cutoffs)),
            dtype=np.int64,
        )
        # Опорное событие уже наблюдалось к cutoff и не должно попадать в future label.
        cutoffs = pd.DatetimeIndex(
            candidate_cutoffs.iloc[np.unique(positions)] + pd.Timedelta(microseconds=1)
        )
    else:
        # Малый разреженный fixture может не иметь двух внутренних событий;
        # границы остаются причинными и позволяют проверить контракт набора.
        cutoff_ns = np.linspace(first.value, last.value, cutoff_count, dtype=np.int64)
        cutoffs = pd.to_datetime(np.unique(cutoff_ns), utc=True)

    return normalized, cutoffs


def _build_label_layout(
    normalized: pd.DataFrame,
    channels: pd.DataFrame,
    cutoffs: pd.DatetimeIndex,
    *,
    horizon_hours: int,
    minimum_history_events: int,
    feature_windows_hours: Sequence[int],
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    context_before = pd.Timedelta(hours=max(feature_windows_hours))
    context_after = pd.Timedelta(hours=horizon_hours)
    for cutoff in cutoffs:
        context = normalized.loc[
            (normalized["observed_at"] >= cutoff - context_before)
            & (normalized["observed_at"] < cutoff + context_after)
        ]
        history_counts = context.loc[context["observed_at"] < cutoff].groupby("channel_id").size()
        eligible_channels = set(history_counts[history_counts >= minimum_history_events].index)
        if not eligible_channels:
            continue
        labels = label_silence_horizon(context, channels, cutoff, horizon_hours=horizon_hours)
        labels = labels.loc[
            labels["channel_id"].isin(eligible_channels), ["channel_id", "silence_label"]
        ].copy()
        if labels.empty:
            continue
        labels["prediction_at"] = cutoff
        frames.append(labels)
    if not frames:
        raise ValueError("Недостаточно истории для point-in-time набора")
    return pd.concat(frames, ignore_index=True).sort_values(
        ["prediction_at", "channel_id"], kind="stable", ignore_index=True
    )
