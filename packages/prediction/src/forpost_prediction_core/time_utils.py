"""Единая временная семантика локальной телеметрии Москвы."""

from __future__ import annotations

import pandas as pd

SOURCE_TIMEZONE = "Europe/Moscow"


def normalize_event_times(values: pd.Series) -> pd.Series:
    """Интерпретирует naive source timestamps как Europe/Moscow и возвращает UTC."""
    parsed = pd.to_datetime(values, errors="coerce")
    if parsed.dt.tz is None:
        return parsed.dt.tz_localize(SOURCE_TIMEZONE).dt.tz_convert("UTC")
    return parsed.dt.tz_convert("UTC")


def normalize_cutoff(value: pd.Timestamp) -> pd.Timestamp:
    """Приводит cutoff к UTC по той же политике, что и source timestamps."""
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize(SOURCE_TIMEZONE).tz_convert("UTC")
    return timestamp.tz_convert("UTC")
