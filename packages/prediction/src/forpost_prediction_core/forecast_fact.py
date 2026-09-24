"""Строгий контракт доказательств «прогноз → наблюдаемый исход»."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Annotated, Literal, Self

import numpy as np
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator

from .evaluation_report import EvaluationReport, load_evaluation_report

MAX_FORECAST_FACT_BYTES = 5 * 1024 * 1024
MAX_FORECAST_FACT_MANIFEST_BYTES = 64 * 1024
UnitFloat = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
Sha256 = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]


class ForecastFactUnavailableError(ValueError):
    """Артефакт отсутствует, повреждён или не связан с опубликованным релизом."""


class ExactModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ForecastFactMetrics(ExactModel):
    precision: UnitFloat
    recall: UnitFloat
    f1: UnitFloat
    pr_auc: UnitFloat


class ForecastFactRow(ExactModel):
    id: Annotated[str, Field(pattern=r"^ff_[0-9a-f]{16}$")]
    prediction_at: AwareDatetime
    deadline: AwareDatetime
    probability: UnitFloat
    observed_outcome: bool
    confusion: Literal["TP", "FP", "FN", "TN"]
    sensor_type: Literal["contact", "volume", "temperature", "smoke", "gas", "other"]
    lead_time_hours: Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]

    @model_validator(mode="after")
    def validate_time_order(self) -> Self:
        if self.deadline <= self.prediction_at:
            raise ValueError("Дедлайн должен следовать за временем прогноза")
        return self


class CalibrationPoint(ExactModel):
    mean_probability: UnitFloat
    observed_rate: UnitFloat
    count: Annotated[int, Field(strict=True, gt=0)]


class LiftPoint(ExactModel):
    top_fraction: Annotated[float, Field(strict=True, gt=0, le=1, allow_inf_nan=False)]
    precision: UnitFloat
    lift: Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]


class ForecastFactEvidence(ExactModel):
    format_version: Literal[1]
    task: Literal["sensor_failure"]
    version: Annotated[str, Field(pattern=r"^v[1-9][0-9]*$", max_length=32)]
    evidence_tier: Literal["proxy"]
    source_split: Literal["final_test"]
    created_at: AwareDatetime
    evaluation_report_sha256: Sha256
    threshold: Annotated[float, Field(strict=True, gt=0, lt=1, allow_inf_nan=False)]
    metrics: ForecastFactMetrics
    rows: tuple[ForecastFactRow, ...] = Field(min_length=1, max_length=20_000)
    calibration_curve: tuple[CalibrationPoint, ...] = Field(min_length=1, max_length=100)
    lift_curve: tuple[LiftPoint, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_derived_evidence(self) -> Self:
        if len({row.id for row in self.rows}) != len(self.rows):
            raise ValueError("Идентификаторы строк должны быть уникальны")
        expected_confusion = tuple(
            _confusion(row.probability >= self.threshold, row.observed_outcome)
            for row in self.rows
        )
        if expected_confusion != tuple(row.confusion for row in self.rows):
            raise ValueError("Матрица ошибок не соответствует прогнозам и фактам")
        expected_metrics = _derive_metrics(self.rows)
        if any(
            not np.isclose(
                getattr(self.metrics, name),
                expected_metrics[name],
                rtol=1e-10,
                atol=1e-12,
            )
            for name in ForecastFactMetrics.model_fields
        ):
            raise ValueError("Метрики не соответствуют построчным исходам")
        _validate_calibration(self.rows, self.calibration_curve)
        _validate_lift(self.rows, self.lift_curve)
        return self


class ForecastFactManifest(ExactModel):
    format_version: Literal[1]
    task: Literal["sensor_failure"]
    version: Annotated[str, Field(pattern=r"^v[1-9][0-9]*$", max_length=32)]
    sha256: Sha256
    evaluation_report_sha256: Sha256


def load_forecast_fact_evidence(
    evaluation_report_path: Path,
    artifact_path: Path,
    manifest_path: Path,
) -> ForecastFactEvidence:
    """Читает evidence только после подтверждения опубликованного frozen-релиза."""

    try:
        report = load_evaluation_report(evaluation_report_path)
        if report.status != "published":
            raise ForecastFactUnavailableError("Доказательства недоступны")
        report_bytes = _read_regular_file(
            evaluation_report_path,
            maximum_bytes=256 * 1024,
        )
        report_digest = hashlib.sha256(report_bytes).hexdigest()
        manifest = ForecastFactManifest.model_validate_json(
            _read_regular_file(manifest_path, maximum_bytes=MAX_FORECAST_FACT_MANIFEST_BYTES)
        )
        artifact_bytes = _read_regular_file(
            artifact_path,
            maximum_bytes=MAX_FORECAST_FACT_BYTES,
        )
        evidence = ForecastFactEvidence.model_validate_json(artifact_bytes)
        if (
            hashlib.sha256(artifact_bytes).hexdigest() != manifest.sha256
            or manifest.evaluation_report_sha256 != report_digest
            or evidence.evaluation_report_sha256 != report_digest
            or manifest.task != evidence.task
            or manifest.version != evidence.version
            or evidence.task != report.task
            or evidence.version != report.version
            or evidence.threshold != report.threshold
        ):
            raise ForecastFactUnavailableError("Доказательства недоступны")
        _validate_against_report(evidence, report)
        return evidence
    except (OSError, ValueError, ValidationError):
        raise ForecastFactUnavailableError("Доказательства недоступны") from None


def _read_regular_file(path: Path, *, maximum_bytes: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ForecastFactUnavailableError("Доказательства недоступны")
    with path.open("rb") as stream:
        content = stream.read(maximum_bytes + 1)
    if len(content) > maximum_bytes:
        raise ForecastFactUnavailableError("Доказательства недоступны")
    return content


def _validate_against_report(evidence: ForecastFactEvidence, report: EvaluationReport) -> None:
    if report.test_metrics is None or report.split_sizes is None or report.horizon_hours is None:
        raise ForecastFactUnavailableError("Доказательства недоступны")
    if len(evidence.rows) != report.split_sizes.test:
        raise ForecastFactUnavailableError("Доказательства недоступны")
    for name in ForecastFactMetrics.model_fields:
        if not np.isclose(
            getattr(evidence.metrics, name),
            getattr(report.test_metrics, name),
            rtol=1e-10,
            atol=1e-12,
        ):
            raise ForecastFactUnavailableError("Доказательства недоступны")
    for row in evidence.rows:
        horizon = (row.deadline - row.prediction_at).total_seconds() / 3600
        if not np.isclose(horizon, report.horizon_hours) or row.lead_time_hours > horizon:
            raise ForecastFactUnavailableError("Доказательства недоступны")


def _confusion(predicted: bool, observed: bool) -> str:
    if predicted:
        return "TP" if observed else "FP"
    return "FN" if observed else "TN"


def _derive_metrics(rows: tuple[ForecastFactRow, ...]) -> dict[str, float]:
    counts = {name: sum(row.confusion == name for row in rows) for name in ("TP", "FP", "FN")}
    precision = _safe_ratio(counts["TP"], counts["TP"] + counts["FP"])
    recall = _safe_ratio(counts["TP"], counts["TP"] + counts["FN"])
    return {
        "precision": precision,
        "recall": recall,
        "f1": _safe_ratio(2 * precision * recall, precision + recall),
        "pr_auc": _average_precision(rows),
    }


def _average_precision(rows: tuple[ForecastFactRow, ...]) -> float:
    positives = sum(row.observed_outcome for row in rows)
    if positives == 0:
        return 0.0
    true_positives = 0
    precision_sum = 0.0
    for rank, row in enumerate(sorted(rows, key=lambda item: item.probability, reverse=True), 1):
        if row.observed_outcome:
            true_positives += 1
            precision_sum += true_positives / rank
    return precision_sum / positives


def _validate_calibration(
    rows: tuple[ForecastFactRow, ...],
    points: tuple[CalibrationPoint, ...],
) -> None:
    if sum(point.count for point in points) != len(rows):
        raise ValueError("Калибровочная кривая не покрывает выборку")
    if tuple(point.mean_probability for point in points) != tuple(
        sorted(point.mean_probability for point in points)
    ):
        raise ValueError("Калибровочная кривая не упорядочена")
    weighted_probability = sum(point.mean_probability * point.count for point in points)
    weighted_outcome = sum(point.observed_rate * point.count for point in points)
    if not np.isclose(weighted_probability, sum(row.probability for row in rows)) or not np.isclose(
        weighted_outcome,
        sum(row.observed_outcome for row in rows),
    ):
        raise ValueError("Калибровочная кривая не соответствует выборке")


def _validate_lift(rows: tuple[ForecastFactRow, ...], points: tuple[LiftPoint, ...]) -> None:
    fractions = tuple(point.top_fraction for point in points)
    if fractions != tuple(sorted(fractions)) or not np.isclose(fractions[-1], 1.0):
        raise ValueError("Lift-кривая должна быть упорядочена и завершаться на 100%")
    ranked = sorted(rows, key=lambda item: item.probability, reverse=True)
    prevalence = sum(row.observed_outcome for row in ranked) / len(ranked)
    for point in points:
        count = max(1, math.ceil(len(ranked) * point.top_fraction))
        precision = sum(row.observed_outcome for row in ranked[:count]) / count
        lift = precision / prevalence if prevalence else 0.0
        if not np.isclose(point.precision, precision) or not np.isclose(point.lift, lift):
            raise ValueError("Lift-кривая не соответствует выборке")


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0

