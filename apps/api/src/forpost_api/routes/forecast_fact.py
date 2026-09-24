"""Защищённое чтение опубликованных доказательств «прогноз → факт»."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from forpost_platform.security.identity import Permission, SecuritySubject
from forpost_prediction_core.forecast_fact import (
    ForecastFactEvidence,
    ForecastFactUnavailableError,
    load_forecast_fact_evidence,
)

from forpost_api.dependencies import require_permission

router = APIRouter(tags=["Forecast fact evidence"])
Subject = Annotated[SecuritySubject, Depends(require_permission(Permission.VIEW_RISKS))]
PROCESSED_DATA_DIRECTORY = Path(__file__).resolve().parents[5] / "data" / "processed"
EVALUATION_REPORT_PATH = PROCESSED_DATA_DIRECTORY / "ml-evaluation.json"
FORECAST_FACT_PATH = PROCESSED_DATA_DIRECTORY / "forecast-fact.json"
FORECAST_FACT_MANIFEST_PATH = PROCESSED_DATA_DIRECTORY / "forecast-fact-manifest.json"


@router.get("/api/forecast-fact", response_model=ForecastFactEvidence)
async def get_forecast_fact(_subject: Subject):
    """Возвращает evidence только для integrity-bound опубликованного релиза."""

    try:
        return load_forecast_fact_evidence(
            EVALUATION_REPORT_PATH,
            FORECAST_FACT_PATH,
            FORECAST_FACT_MANIFEST_PATH,
        )
    except ForecastFactUnavailableError:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "reason_code": "forecast_fact_unavailable",
            },
        )

