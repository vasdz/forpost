"""Авторизованное чтение доказательств оценки без изменения serving-допуска."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from forpost_platform.security.identity import Permission, SecuritySubject
from forpost_prediction_core.evaluation_report import (
    EvaluationReport,
    EvaluationReportUnavailableError,
    load_evaluation_report,
)

from forpost_api.dependencies import require_permission

router = APIRouter(tags=["Model evaluation"])
Subject = Annotated[SecuritySubject, Depends(require_permission(Permission.VIEW_RISKS))]
EVALUATION_REPORT_PATH = (
    Path(__file__).resolve().parents[5] / "data" / "processed" / "ml-evaluation.json"
)


@router.get("/api/model-evaluation", response_model=EvaluationReport)
async def get_model_evaluation(_subject: Subject):
    """Отсутствие или повреждение отчёта явно оставляет оценку недоступной."""
    try:
        return load_evaluation_report(EVALUATION_REPORT_PATH)
    except EvaluationReportUnavailableError:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "reason_code": "evaluation_unavailable",
            },
        )
