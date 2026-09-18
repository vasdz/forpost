"""Проверка метаданных локально обученной модели перед serving."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from forpost_prediction_core.capabilities import PredictionTask


class ModelUnavailableError(ValueError):
    """Артефакт нельзя использовать для формирования вероятностей."""


@dataclass(frozen=True)
class ModelMetadata:
    """Минимальный model card, необходимый для безопасного serving."""

    task: PredictionTask
    version: str
    feature_schema_version: str
    calibrated: bool
    created_at: datetime


def validate_model_metadata(
    metadata: ModelMetadata,
    *,
    expected_task: PredictionTask,
    expected_feature_schema_version: str,
) -> None:
    """Не допускает в serving несовместимую или некалиброванную модель."""
    if metadata.task != expected_task:
        raise ModelUnavailableError("Модель не соответствует требуемой задаче")
    if metadata.feature_schema_version != expected_feature_schema_version:
        raise ModelUnavailableError("Модель не соответствует версии схемы признаков")
    if not metadata.calibrated:
        raise ModelUnavailableError("Модель не прошла обязательную калибровку вероятностей")
    if not metadata.version:
        raise ModelUnavailableError("У модели отсутствует локальная версия")
    if metadata.created_at.tzinfo is None:
        raise ModelUnavailableError("У метаданных модели отсутствует часовой пояс")
