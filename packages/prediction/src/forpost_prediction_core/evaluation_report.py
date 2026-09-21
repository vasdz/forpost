"""Ограниченный отчёт об оценке; не является разрешением на serving модели."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator

MAX_EVALUATION_REPORT_BYTES = 256 * 1024
UnitMetric = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
EvaluationVersion = Annotated[str, Field(pattern=r"^v[1-9][0-9]*$", max_length=32)]
ReasonCode = Literal[
    "configuration_invalid",
    "source_unavailable",
    "dataset_unavailable",
    "training_unavailable",
    "validation_rejected",
    "test_rejected",
    "inference_unavailable",
    "release_unavailable",
]


class EvaluationReportUnavailableError(ValueError):
    """Отчёт отсутствует либо не прошёл безопасную проверку."""


class ExactModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvaluationMetrics(ExactModel):
    precision: UnitMetric
    recall: UnitMetric
    f1: UnitMetric
    pr_auc: UnitMetric
    roc_auc: UnitMetric
    brier_score: UnitMetric
    expected_calibration_error: UnitMetric
    alert_rate: UnitMetric


class QualityThresholds(ExactModel):
    minimum_precision: UnitMetric
    minimum_recall: UnitMetric
    maximum_alert_rate: UnitMetric
    maximum_expected_calibration_error: UnitMetric
    maximum_brier_score: UnitMetric
    minimum_baseline_pr_auc_delta: UnitMetric


class SplitSizes(ExactModel):
    fit: Annotated[int, Field(strict=True, gt=0)]
    calibration: Annotated[int, Field(strict=True, gt=0)]
    validation: Annotated[int, Field(strict=True, gt=0)]
    test: Annotated[int, Field(strict=True, gt=0)]


class EvaluationReport(ExactModel):
    format_version: Literal[1]
    task: Literal["sensor_failure"]
    version: EvaluationVersion
    status: Literal["rejected", "published"]
    evidence_tier: Literal["proxy"]
    label_strategy: Literal["silence_horizon_proxy"]
    created_at: AwareDatetime
    reason_code: ReasonCode | None
    quality_thresholds: QualityThresholds | None
    split_sizes: SplitSizes | None
    baseline_validation_pr_auc: UnitMetric | None
    validation_metrics: EvaluationMetrics | None
    test_metrics: EvaluationMetrics | None
    threshold: Annotated[float, Field(strict=True, gt=0, lt=1, allow_inf_nan=False)] | None
    champion_name: (
        Literal[
            "extra_trees_isotonic",
            "extra_trees_sigmoid",
            "hist_gradient_boosting_isotonic",
            "hist_gradient_boosting_sigmoid",
            "logistic_regression_isotonic",
            "logistic_regression_sigmoid",
        ]
        | None
    )

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        if self.status == "rejected":
            if self.reason_code is None or self.test_metrics is not None:
                raise ValueError("Отклонённый отчёт требует причины и не раскрывает test-метрики")
        elif self.reason_code is not None or any(
            value is None
            for value in (
                self.quality_thresholds,
                self.split_sizes,
                self.baseline_validation_pr_auc,
                self.validation_metrics,
                self.test_metrics,
                self.threshold,
                self.champion_name,
            )
        ):
            raise ValueError("Опубликованный отчёт требует полных доказательств")
        return self


def load_evaluation_report(path: Path) -> EvaluationReport:
    """Читает ограниченный JSON; ошибки не раскрывают исходные пути и содержимое."""
    try:
        if path.is_symlink() or not path.is_file():
            raise EvaluationReportUnavailableError("Отчёт оценки недоступен")
        with path.open("rb") as stream:
            content = stream.read(MAX_EVALUATION_REPORT_BYTES + 1)
        if len(content) > MAX_EVALUATION_REPORT_BYTES:
            raise EvaluationReportUnavailableError("Отчёт оценки недоступен")
        return EvaluationReport.model_validate_json(content)
    except (OSError, ValueError, ValidationError):
        raise EvaluationReportUnavailableError("Отчёт оценки недоступен") from None


def write_evaluation_report(path: Path, report: EvaluationReport) -> None:
    """Заменяет отчёт только полностью записанным и проверенным временным файлом."""
    temporary: Path | None = None
    try:
        validated = EvaluationReport.model_validate(report.model_dump(mode="json"))
        content = (validated.model_dump_json(indent=2) + "\n").encode("utf-8")
        if len(content) > MAX_EVALUATION_REPORT_BYTES:
            raise EvaluationReportUnavailableError("Отчёт оценки не сохранён")
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".evaluation-", suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except (OSError, ValueError, ValidationError):
        raise EvaluationReportUnavailableError("Отчёт оценки не сохранён") from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                raise EvaluationReportUnavailableError("Временный отчёт не удалён") from None
