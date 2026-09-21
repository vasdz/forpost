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
    purge_hours: int = 0,
) -> TemporalSplit:
    """Делит целые временные точки и удаляет хвост перед будущими блоками."""
    if time_column not in frame:
        raise ValueError("Не найдена колонка времени для временного разбиения")
    if not 0 < validation_fraction < 1 or not 0 < test_fraction < 1:
        raise ValueError("Доли validation и test должны быть в интервале от 0 до 1")
    if validation_fraction + test_fraction >= 1:
        raise ValueError("Доли validation и test оставляют пустую train-часть")
    if purge_hours < 0:
        raise ValueError("Период очистки не может быть отрицательным")
    ordered = frame.copy()
    ordered[time_column] = pd.to_datetime(ordered[time_column])
    ordered = ordered.sort_values(time_column, kind="stable").reset_index(drop=True)
    unique_times = ordered[time_column].drop_duplicates().reset_index(drop=True)
    target_validation_index = int(len(unique_times) * (1 - validation_fraction - test_fraction))
    target_test_index = int(len(unique_times) * (1 - test_fraction))
    if (
        target_validation_index < 1
        or target_test_index <= target_validation_index
        or len(unique_times) <= target_test_index
    ):
        raise ValueError("Недостаточно временных точек для train/validation/test")
    purge = pd.Timedelta(hours=purge_hours)
    first_validation_index = int(
        unique_times.searchsorted(unique_times.iloc[0] + purge, side="right")
    )
    boundary: tuple[pd.Timestamp, pd.Timestamp] | None = None
    test_indices = sorted(
        range(2, len(unique_times)),
        key=lambda index: (abs(index - target_test_index), index),
    )
    for test_index in test_indices:
        test_start = unique_times.iloc[test_index]
        validation_stop_index = int(unique_times.searchsorted(test_start - purge, side="left"))
        last_validation_index = validation_stop_index - 1
        if first_validation_index > last_validation_index:
            continue
        validation_index = min(
            max(target_validation_index, first_validation_index),
            last_validation_index,
        )
        boundary = unique_times.iloc[validation_index], test_start
        break
    if boundary is None:
        raise ValueError("Период очистки оставляет пустую часть временного разбиения")
    validation_start, test_start = boundary
    train = ordered.loc[ordered[time_column] < validation_start - purge].copy()
    validation = ordered.loc[
        (ordered[time_column] >= validation_start) & (ordered[time_column] < test_start - purge)
    ].copy()
    test = ordered.loc[ordered[time_column] >= test_start].copy()
    if train.empty or validation.empty or test.empty:
        raise ValueError("Период очистки оставляет пустую часть временного разбиения")
    return TemporalSplit(
        train=train.reset_index(drop=True),
        validation=validation.reset_index(drop=True),
        test=test.reset_index(drop=True),
    )
