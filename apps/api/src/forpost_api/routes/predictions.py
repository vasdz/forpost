"""Граница чтения экспортированных ML-прогнозов."""

import json
import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Path as ApiPath
from fastapi.responses import JSONResponse
from forpost_platform.audit.ledger import AuditSeverity, audit_ledger
from forpost_platform.security.identity import Permission, SecuritySubject
from pydantic import ValidationError

from forpost_api.dependencies import require_permission
from forpost_api.schemas.predictions import (
    Prediction,
    PredictionDecisionRequest,
    PredictionDecisionResponse,
    PredictionListResponse,
)

router = APIRouter(tags=["Predictions"])

Subject = Annotated[SecuritySubject, Depends(require_permission(Permission.VIEW_RISKS))]
PENDING_MODEL_RESPONSE = {"error": "ML модель не обучена", "status": "pending"}
ML_MODELS_DIRECTORY = Path(__file__).resolve().parents[6] / "ml" / "models"
MODEL_VERSION_PATTERN = re.compile(r"v[1-9]\d*")


def load_exported_predictions() -> tuple[list[Prediction], int]:
    """Читает только корректные JSON-экспорты из контрактного каталога ML."""

    models_directory = ML_MODELS_DIRECTORY.resolve()
    if not models_directory.is_dir():
        return [], 0

    latest_exports: dict[str, tuple[int, Path]] = {}
    for export_path in models_directory.glob("*/v*/predictions.json"):
        version_name = export_path.parent.name
        if not MODEL_VERSION_PATTERN.fullmatch(version_name):
            continue
        case_name = export_path.parent.parent.name
        version_number = int(version_name[1:])
        known_export = latest_exports.get(case_name)
        if known_export is None or version_number > known_export[0]:
            latest_exports[case_name] = (version_number, export_path)

    predictions: list[Prediction] = []
    export_count = 0
    for _, export_path in sorted(latest_exports.values(), key=lambda item: item[1]):
        try:
            export_path.resolve().relative_to(models_directory)
            payload = json.loads(export_path.read_text(encoding="utf-8"))
            validated = PredictionListResponse.model_validate(payload)
            if any(item.model_version != export_path.parent.name for item in validated.predictions):
                continue
        except (OSError, ValueError, ValidationError):
            continue

        predictions.extend(validated.predictions)
        export_count += 1

    return predictions, export_count


@router.get("/api/predictions")
async def get_predictions(subject: Subject) -> JSONResponse:
    """Выдаёт экспорт ML или fail-closed сообщает о неготовности модели."""

    predictions, export_count = load_exported_predictions()
    if export_count == 0:
        audit_ledger.append(
            "PREDICTIONS_VIEW_REQUESTED",
            AuditSeverity.INFO,
            subject.user_id,
            "/api/predictions",
            {"status": "pending"},
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=PENDING_MODEL_RESPONSE,
        )

    audit_ledger.append(
        "PREDICTIONS_VIEW_REQUESTED",
        AuditSeverity.INFO,
        subject.user_id,
        "/api/predictions",
        {"status": "ready", "export_count": export_count, "prediction_count": len(predictions)},
    )
    payload = PredictionListResponse(predictions=predictions).model_dump(mode="json")
    return JSONResponse(content=payload)


@router.post(
    "/api/predictions/{prediction_id}/decisions",
    response_model=PredictionDecisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_prediction_decision(
    request: PredictionDecisionRequest,
    subject: Subject,
    prediction_id: Annotated[str, ApiPath(min_length=1, max_length=128)],
) -> PredictionDecisionResponse:
    """Связывает решение диспетчера только с текущим валидным прогнозом."""

    predictions, _ = load_exported_predictions()
    if not any(item.id == prediction_id for item in predictions):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Прогноз не найден")

    record = audit_ledger.append(
        "PREDICTION_DECISION_RECORDED",
        AuditSeverity.WARNING,
        subject.user_id,
        prediction_id,
        {"decision": request.decision.value, "reason": request.reason},
    )
    return PredictionDecisionResponse(
        status="recorded",
        prediction_id=prediction_id,
        audit_record_id=record.index,
    )
