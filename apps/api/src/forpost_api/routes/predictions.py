"""Граница чтения экспортированных ML-прогнозов."""

import hashlib
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

from forpost_api.dependencies import get_current_human_subject, require_permission
from forpost_api.schemas.predictions import (
    MAX_PREDICTIONS_PER_RESPONSE,
    Prediction,
    PredictionDecisionRequest,
    PredictionDecisionResponse,
    PredictionExport,
    PredictionListResponse,
    PredictionType,
)

router = APIRouter(tags=["Predictions"])

Subject = Annotated[SecuritySubject, Depends(require_permission(Permission.VIEW_RISKS))]
DecisionSubject = Annotated[SecuritySubject, Depends(get_current_human_subject)]
PENDING_MODEL_RESPONSE = {"error": "ML модель не обучена", "status": "pending"}
ML_MODELS_DIRECTORY = Path(__file__).resolve().parents[6] / "ml" / "models"
MODEL_VERSION_PATTERN = re.compile(r"v[1-9]\d*")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
MAX_PREDICTION_EXPORT_BYTES = 10 * 1024 * 1024
MAX_PREDICTION_MANIFEST_BYTES = 64 * 1024
MAX_MODEL_CARD_BYTES = 1024 * 1024


def load_exported_predictions() -> tuple[list[Prediction], int]:
    """Читает только корректные JSON-экспорты из контрактного каталога ML."""

    predictions, available_types = _load_exported_prediction_state()
    return predictions, len(available_types)


def _load_exported_prediction_state() -> tuple[list[Prediction], list[PredictionType]]:
    """Возвращает прогнозы и типы только из валидных экспортов."""

    models_root = ML_MODELS_DIRECTORY
    if models_root.is_symlink():
        return [], []
    try:
        models_directory = models_root.resolve(strict=True)
    except OSError:
        return [], []
    if not models_directory.is_dir():
        return [], []

    latest_exports: dict[PredictionType, tuple[int, Path]] = {}
    for export_path in models_directory.glob("*/v*/predictions.json"):
        version_name = export_path.parent.name
        if not MODEL_VERSION_PATTERN.fullmatch(version_name):
            continue
        case_name = export_path.parent.parent.name
        try:
            prediction_type = PredictionType(case_name)
        except ValueError:
            continue
        version_number = int(version_name[1:])
        known_export = latest_exports.get(prediction_type)
        if known_export is None or version_number > known_export[0]:
            latest_exports[prediction_type] = (version_number, export_path)

    predictions: list[Prediction] = []
    available_types: list[PredictionType] = []
    for prediction_type in PredictionType:
        known_export = latest_exports.get(prediction_type)
        if known_export is None:
            continue
        _, export_path = known_export
        try:
            model_card, export_bytes = _verify_prediction_export(export_path, models_directory)
            payload = json.loads(export_bytes)
            validated = PredictionExport.model_validate(payload)
            if any(
                item.model_version != export_path.parent.name
                or item.prediction_type.value != export_path.parent.parent.name
                or item.evidence_tier.value != model_card.get("evidence_tier")
                or item.calibrated is not model_card.get("calibrated")
                or not _metrics_match_card(item, model_card)
                for item in validated.predictions
            ):
                continue
            if len(predictions) + len(validated.predictions) > MAX_PREDICTIONS_PER_RESPONSE:
                continue
        except (OSError, ValueError, ValidationError):
            continue

        predictions.extend(validated.predictions)
        available_types.append(prediction_type)

    return predictions, available_types


def _verify_prediction_export(
    export_path: Path,
    models_directory: Path,
) -> tuple[dict[str, object], bytes]:
    """Проверяет отдельный manifest до разбора содержимого прогноза."""
    resolved = _checked_regular_file(
        export_path,
        models_directory,
        MAX_PREDICTION_EXPORT_BYTES,
    )
    manifest_path = _checked_regular_file(
        export_path.parent / "predictions-manifest.json",
        models_directory,
        MAX_PREDICTION_MANIFEST_BYTES,
    )
    card_path = _checked_regular_file(
        export_path.parent / "model-card.json",
        models_directory,
        MAX_MODEL_CARD_BYTES,
    )

    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, dict) or set(manifest) != {
        "format_version",
        "task",
        "version",
        "sha256",
        "model_card_sha256",
    }:
        raise ValueError("Некорректная схема manifest")
    if (
        manifest["format_version"] != 1
        or manifest["task"] != export_path.parent.parent.name
        or manifest["version"] != export_path.parent.name
        or not isinstance(manifest["sha256"], str)
        or not SHA256_PATTERN.fullmatch(manifest["sha256"])
        or not isinstance(manifest["model_card_sha256"], str)
        or not SHA256_PATTERN.fullmatch(manifest["model_card_sha256"])
    ):
        raise ValueError("Manifest не соответствует пути экспорта")
    export_bytes = resolved.read_bytes()
    digest = hashlib.sha256(export_bytes).hexdigest()
    if digest != manifest["sha256"]:
        raise ValueError("Нарушена целостность экспорта")
    card_bytes = card_path.read_bytes()
    if hashlib.sha256(card_bytes).hexdigest() != manifest["model_card_sha256"]:
        raise ValueError("Manifest прогноза не связан с model card")
    card = json.loads(card_bytes)
    if (
        not isinstance(card, dict)
        or card.get("task") != manifest["task"]
        or card.get("version") != manifest["version"]
    ):
        raise ValueError("Model card не соответствует экспорту")
    return card, export_bytes


def _checked_regular_file(path: Path, root: Path, maximum_bytes: int) -> Path:
    """Отклоняет symlink, выход из корня и слишком большие файлы."""

    if path.is_symlink() or path.parent.is_symlink() or path.parent.parent.is_symlink():
        raise ValueError("Некорректный путь ML-артефакта")
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError("ML-артефакт выходит за корень хранилища") from error
    if not resolved.is_file() or resolved.stat().st_size > maximum_bytes:
        raise ValueError("Некорректный размер ML-артефакта")
    return resolved


def _metrics_match_card(prediction: Prediction, card: dict[str, object]) -> bool:
    if prediction.model_metrics is None:
        return prediction.evidence_tier.value in {"anomaly", "scenario"}
    metrics = card.get("test_metrics")
    if not isinstance(metrics, dict):
        return False
    expected = prediction.model_metrics.model_dump()
    return all(metrics.get(key) == value for key, value in expected.items())


@router.get("/api/predictions")
async def get_predictions(subject: Subject) -> JSONResponse:
    """Выдаёт экспорт ML или fail-closed сообщает о неготовности модели."""

    predictions, available_types = _load_exported_prediction_state()
    if not available_types:
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
        {
            "status": "ready",
            "export_count": len(available_types),
            "prediction_count": len(predictions),
        },
    )
    payload = PredictionListResponse(
        predictions=predictions,
        available_types=available_types,
    ).model_dump(mode="json")
    return JSONResponse(content=payload)


@router.post(
    "/api/predictions/{prediction_id}/decisions",
    response_model=PredictionDecisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_prediction_decision(
    request: PredictionDecisionRequest,
    subject: DecisionSubject,
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
