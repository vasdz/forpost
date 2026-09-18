"""API аналитики до подключения проверенных источников и обученной модели."""

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends
from forpost_domain.analytics.entities import (
    ExportFormat,
    ReportPeriod,
)
from forpost_platform.security.identity import SecuritySubject

from forpost_api.dependencies import get_current_subject
from forpost_api.routes.v1.availability import (
    REAL_DATA_INTEGRATION_UNAVAILABLE_MESSAGE,
    raise_real_data_integration_unavailable,
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])

Subject = Annotated[SecuritySubject, Depends(get_current_subject)]


@router.get("/kpi", response_model=None)
async def get_kpi_dashboard(_subject: Subject) -> NoReturn:
    """Не подменяет реальные KPI сгенерированными значениями."""

    raise_real_data_integration_unavailable()


@router.post("/reports/operational", response_model=None)
async def generate_operational_report(
    _subject: Subject,
    period: ReportPeriod = ReportPeriod.DAILY,
) -> NoReturn:
    """Не создаёт отчёт-заглушку вместо отчёта по источникам мониторинга."""

    del period
    raise_real_data_integration_unavailable()


@router.get("/export", response_model=None)
async def export_data(
    _subject: Subject,
    format: ExportFormat = ExportFormat.JSON,
) -> NoReturn:
    """Не формирует псевдоэкспорт до подключения реальных данных."""

    del format
    raise_real_data_integration_unavailable()


@router.get("/health", response_model=dict[str, str])
async def analytics_health_check() -> dict[str, str]:
    """Правдиво сообщает о недоступности аналитического контура данных."""

    return {
        "status": "limited",
        "module": "analytics",
        "data_integration": "unavailable",
        "message": REAL_DATA_INTEGRATION_UNAVAILABLE_MESSAGE,
    }
