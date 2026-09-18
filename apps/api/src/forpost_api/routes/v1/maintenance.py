"""API превентивного обслуживания до подключения реестра оборудования."""

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends
from forpost_domain.maintenance.entities import (
    MaintenanceGenerationRequest,
    MaintenanceStatus,
)
from forpost_platform.security.identity import SecuritySubject

from forpost_api.dependencies import get_current_subject
from forpost_api.routes.v1.availability import raise_real_data_integration_unavailable

router = APIRouter(prefix="/maintenance", tags=["Maintenance"])

Subject = Annotated[SecuritySubject, Depends(get_current_subject)]


@router.get("", response_model=None)
async def get_maintenance_orders(_subject: Subject) -> NoReturn:
    """Не выдаёт заявки из временного хранилища вместо реестра оборудования."""

    raise_real_data_integration_unavailable()


@router.post("/generate-from-prediction", response_model=None)
async def generate_from_prediction(
    request: MaintenanceGenerationRequest,
    _subject: Subject,
) -> NoReturn:
    """Не создаёт заявки без реального прогноза и доверенного реестра оборудования."""

    del request
    raise_real_data_integration_unavailable()


@router.patch("/{order_id}/status", response_model=None)
async def update_order_status(
    order_id: str,
    new_status: MaintenanceStatus,
    _subject: Subject,
) -> NoReturn:
    """Не изменяет временные заявки до подключения реального контура обслуживания."""

    del order_id, new_status
    raise_real_data_integration_unavailable()
