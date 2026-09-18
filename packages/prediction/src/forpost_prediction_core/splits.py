"""Строгие временные разбиения для обучения и проверки модели."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class TemporalSplit:
    """Хронологически упорядоченные непересекающиеся части выборки."""

    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame


def split_by_time(
    frame: pd.DataFrame,
    time_column: str,
    *,
    validation_fraction: float = 0.2,
    test_fraction: float = 0.2,
) -> TemporalSplit:
    """Делит строки по времени без случайного перемешивания и пересечений."""
    if time_column not in frame:
        raise ValueError("Не найдена колонка времени для временного разбиения")
    if not 0 < validation_fraction < 1 or not 0 < test_fraction < 1:
        raise ValueError("Доли validation и test должны быть в интервале от 0 до 1")
    if validation_fraction + test_fraction >= 1:
        raise ValueError("Доли validation и test оставляют пустую train-часть")
    ordered = frame.copy()
    ordered[time_column] = pd.to_datetime(ordered[time_column])
    ordered = ordered.sort_values(time_column, kind="stable").reset_index(drop=True)
    train_end = int(len(ordered) * (1 - validation_fraction - test_fraction))
    validation_end = int(len(ordered) * (1 - test_fraction))
    if train_end < 1 or validation_end <= train_end or len(ordered) <= validation_end:
        raise ValueError("Недостаточно временных точек для train/validation/test")
    return TemporalSplit(
        train=ordered.iloc[:train_end].copy(),
        validation=ordered.iloc[train_end:validation_end].copy(),
        test=ordered.iloc[validation_end:].copy(),
    )
