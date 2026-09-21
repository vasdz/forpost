"""Локальная диагностика validation: только агрегаты, без строк и test-метрик."""

import os
import tempfile
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from forpost_prediction_core.evaluation_report import (
    EvaluationMetrics,
    EvaluationVersion,
    ExactModel,
    ProfileName,
    ReasonCode,
    Sha256,
    UnitMetric,
)

Count = Annotated[int, Field(strict=True, ge=0)]
Gate = Literal["precision", "recall", "alert_rate", "calibration", "brier", "baseline_delta"]
CandidateName = Annotated[
    str,
    Field(
        pattern=r"^(logistic_regression|extra_trees|hist_gradient_boosting|catboost|lightgbm)_(sigmoid|isotonic)$"
    ),
]


def empty_diagnostics() -> dict:
    return {"step": "development_split", "development": None, "folds": [], "candidates": {}}


class Support(ExactModel):
    positive: Count
    negative: Count
    time_points: Count


class FoldSupport(ExactModel):
    index: Annotated[int, Field(strict=True, ge=1, le=20)]
    fit: Support | None
    calibration: Support | None
    validation: Support
    failure_code: Literal["calibration_split_unavailable", "class_support_insufficient"] | None


class FoldGate(ExactModel):
    index: Annotated[int, Field(strict=True, ge=1, le=20)]
    metrics: EvaluationMetrics
    failed_gates: tuple[Gate, ...]


class ProfileDiagnostic(ExactModel):
    feasible_threshold_count: Count
    failure_counts: dict[Gate, Count]
    closest_threshold: UnitMetric
    closest_folds: tuple[FoldGate, ...]
    mean_metrics: EvaluationMetrics
    worst_metrics: EvaluationMetrics


class CandidateDiagnostic(ExactModel):
    thresholds_evaluated: Count
    profiles: dict[ProfileName, ProfileDiagnostic]


class DiagnosticEvidence(ExactModel):
    step: Literal[
        "development_split",
        "development_support",
        "rolling_split",
        "calibration_split",
        "partition_support",
        "candidate_fit",
        "calibration",
        "validation_selection",
        "refit",
        "frozen_test",
    ]
    development: Support | None
    folds: tuple[FoldSupport, ...]
    candidates: dict[CandidateName, CandidateDiagnostic]


class ValidationDiagnosticReport(ExactModel):
    format_version: Literal[1]
    version: EvaluationVersion
    config_sha256: Sha256 | None
    reason_code: ReasonCode | None
    diagnostics: DiagnosticEvidence


def write_validation_diagnostics(path: Path, report: ValidationDiagnosticReport) -> None:
    """Пишет ограниченный local-only JSON атомарной заменой."""
    content = (report.model_dump_json(indent=2) + "\n").encode("utf-8")
    if len(content) > 1024 * 1024:
        raise ValueError("Диагностика превышает допустимый размер")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".validation-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
