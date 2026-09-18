"""Состояние подключённых backend-источников без синтетических данных."""

from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from forpost_platform.security.identity import Permission, SecuritySubject
from pydantic import BaseModel, ConfigDict

from forpost_api.dependencies import require_permission
from forpost_api.routes.predictions import load_exported_predictions

router = APIRouter(tags=["Availability"])
Subject = Annotated[SecuritySubject, Depends(require_permission(Permission.VIEW_RISKS))]
LOCAL_SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[5] / "data" / "processed" / "local-situation.json"
)
SourceState = Literal["available", "unavailable"]


class SourceAvailability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_snapshot: SourceState
    ml_predictions: SourceState
    access_events: SourceState
    maintenance_history: SourceState
    work_permits: SourceState


class AvailabilityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "limited"]
    sources: SourceAvailability


@router.get("/api/availability", response_model=AvailabilityResponse)
async def get_availability(_subject: Subject) -> AvailabilityResponse:
    """Возвращает фактическую доступность, не раскрывая локальные пути."""

    _, export_count = load_exported_predictions()
    sources = SourceAvailability(
        local_snapshot="available" if LOCAL_SNAPSHOT_PATH.is_file() else "unavailable",
        ml_predictions="available" if export_count > 0 else "unavailable",
        access_events="unavailable",
        maintenance_history="unavailable",
        work_permits="unavailable",
    )
    source_values = sources.model_dump().values()
    return AvailabilityResponse(
        status="ready" if all(value == "available" for value in source_values) else "limited",
        sources=sources,
    )
