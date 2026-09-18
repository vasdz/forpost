"""Безопасное преобразование подтверждённых вкладов модели в контракт факторов UI."""

from __future__ import annotations

import math
from dataclasses import dataclass


class ExplainabilityUnavailableError(ValueError):
    """Модель не дала пригодного для публикации набора факторов."""


@dataclass(frozen=True)
class RawContribution:
    """Вклад признака до нормировки абсолютного влияния."""

    factor: str
    contribution: float
    description: str


@dataclass(frozen=True)
class PredictionFactor:
    """Фактор в совместимом с UI порядке и масштабе."""

    factor: str
    weight: float
    description: str


def normalize_contributions(contributions: list[RawContribution]) -> tuple[PredictionFactor, ...]:
    """Сортирует вклады по абсолютной величине и нормирует их веса к единице."""
    if not contributions:
        raise ExplainabilityUnavailableError("Модель не вернула факторы")
    if any(not math.isfinite(item.contribution) for item in contributions):
        raise ExplainabilityUnavailableError("Влияние признака должно быть конечным")
    total = sum(abs(item.contribution) for item in contributions)
    if total == 0:
        raise ExplainabilityUnavailableError("Нужен хотя бы один ненулевой вклад признака")
    ordered = sorted(contributions, key=lambda item: abs(item.contribution), reverse=True)
    return tuple(
        PredictionFactor(
            factor=item.factor,
            weight=abs(item.contribution) / total,
            description=item.description,
        )
        for item in ordered
    )
