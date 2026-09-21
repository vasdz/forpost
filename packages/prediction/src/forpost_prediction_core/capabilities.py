"""Явно фиксирует доступность данных для обучения каждой ML-задачи."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PredictionTask(StrEnum):
    """Четыре согласованные задачи прогнозирования."""

    SENSOR_FAILURE = "sensor_failure"
    FIRE_RISK = "fire_risk"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    INFRASTRUCTURE_WEAR = "infrastructure_wear"


class EvidenceTier(StrEnum):
    """Доказательность результата, которую обязан показывать API и интерфейс."""

    VALIDATED = "validated"
    PROXY = "proxy"
    ANOMALY = "anomaly"
    SCENARIO = "scenario"
    UNAVAILABLE = "unavailable"


class EvidenceTierError(ValueError):
    """Запрошенная доказательность не подтверждена доступными источниками."""


class SourceKind(StrEnum):
    """Типы источников, разрешённые локальным ML-контуром."""

    EVENTS = "events"
    CHANNELS = "channels"
    OBJECTS = "objects"
    ACCESS_EVENTS = "access_events"
    WORK_PERMITS = "work_permits"
    MAINTENANCE_HISTORY = "maintenance_history"
    VERIFICATION_RESULTS = "verification_results"
    WEATHER = "weather"


@dataclass(frozen=True)
class TaskCapability:
    """Решение о допустимости обучения без подмены отсутствующих источников."""

    task: PredictionTask
    training_available: bool
    label_strategy: str | None
    required_sources: frozenset[SourceKind]
    missing_sources: frozenset[SourceKind]
    maximum_evidence_tier: EvidenceTier


_TASK_REQUIREMENTS: dict[PredictionTask, tuple[frozenset[SourceKind], str]] = {
    PredictionTask.SENSOR_FAILURE: (
        frozenset({SourceKind.EVENTS, SourceKind.CHANNELS}),
        "silence_horizon_proxy",
    ),
    PredictionTask.FIRE_RISK: (
        frozenset({SourceKind.EVENTS, SourceKind.CHANNELS, SourceKind.VERIFICATION_RESULTS}),
        "verified_smoke_or_temperature_incident",
    ),
    PredictionTask.UNAUTHORIZED_ACCESS: (
        frozenset(
            {
                SourceKind.EVENTS,
                SourceKind.CHANNELS,
                SourceKind.ACCESS_EVENTS,
                SourceKind.WORK_PERMITS,
                SourceKind.VERIFICATION_RESULTS,
            }
        ),
        "verified_access_anomaly",
    ),
    PredictionTask.INFRASTRUCTURE_WEAR: (
        frozenset({SourceKind.OBJECTS, SourceKind.MAINTENANCE_HISTORY}),
        "repair_or_maintenance_horizon",
    ),
}


def assess_task_capability(
    task: PredictionTask, available_sources: frozenset[SourceKind]
) -> TaskCapability:
    """Возвращает готовность задачи только при наличии всех источников её разметки."""
    required_sources, label_strategy = _TASK_REQUIREMENTS[task]
    missing_sources = required_sources - available_sources
    maximum_evidence_tier = _maximum_evidence_tier(task, available_sources, missing_sources)
    return TaskCapability(
        task=task,
        training_available=not missing_sources,
        label_strategy=label_strategy if not missing_sources else None,
        required_sources=required_sources,
        missing_sources=missing_sources,
        maximum_evidence_tier=maximum_evidence_tier,
    )


def require_evidence_tier(capability: TaskCapability, requested_tier: EvidenceTier) -> EvidenceTier:
    """Запрещает повышать доказательность результата выше подтверждённого уровня."""
    if requested_tier is not capability.maximum_evidence_tier:
        raise EvidenceTierError("Запрошенный уровень доказательности не подтверждён источниками")
    return requested_tier


def _maximum_evidence_tier(
    task: PredictionTask,
    available_sources: frozenset[SourceKind],
    missing_sources: frozenset[SourceKind],
) -> EvidenceTier:
    if not missing_sources:
        return (
            EvidenceTier.PROXY if task is PredictionTask.SENSOR_FAILURE else EvidenceTier.VALIDATED
        )
    if (
        task in {PredictionTask.FIRE_RISK, PredictionTask.UNAUTHORIZED_ACCESS}
        and {
            SourceKind.EVENTS,
            SourceKind.CHANNELS,
        }
        <= available_sources
    ):
        return EvidenceTier.ANOMALY
    if task is PredictionTask.INFRASTRUCTURE_WEAR and SourceKind.OBJECTS in available_sources:
        return EvidenceTier.SCENARIO
    return EvidenceTier.UNAVAILABLE
