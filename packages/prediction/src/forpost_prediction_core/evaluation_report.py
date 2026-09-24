"""Ограниченный отчёт об оценке; не является разрешением на serving модели."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Annotated, Literal, Self

import numpy as np
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator
from scipy.stats import t

MAX_EVALUATION_REPORT_BYTES = 256 * 1024
UnitMetric = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
EvaluationVersion = Annotated[str, Field(pattern=r"^v[1-9][0-9]*$", max_length=32)]
EvaluationHorizonHours = Annotated[int, Field(strict=True, gt=0, le=8760)]
Sha256 = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
EvidenceString = Annotated[str, Field(strict=True, min_length=1, max_length=128)]
ProfileName = Literal["high_precision", "balanced", "high_recall"]
TaskSemantics = Literal["risk_of_unexpected_telemetry_silence_within_horizon"]
LIBRARY_NAMES = frozenset({"numpy", "pandas", "scikit-learn", "skops", "catboost", "lightgbm"})
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

    def __getitem__(self, key: str) -> float:
        if key not in type(self).model_fields:
            raise KeyError(key)
        return getattr(self, key)


class FoldEvidence(ExactModel):
    index: Annotated[int, Field(strict=True, ge=1, le=20)]
    train_rows: Annotated[int, Field(strict=True, gt=0)]
    calibration_rows: Annotated[int, Field(strict=True, gt=0)]
    validation_rows: Annotated[int, Field(strict=True, gt=0)]
    threshold: UnitMetric
    metrics: EvaluationMetrics


class OperatingProfile(ExactModel):
    threshold: UnitMetric
    precision: UnitMetric
    recall: UnitMetric
    alert_rate: UnitMetric


class ConfidenceInterval(ExactModel):
    lower: UnitMetric
    upper: UnitMetric
    level: Literal[0.95]
    method: Literal["student_t_across_rolling_folds"]

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        if self.lower > self.upper:
            raise ValueError("Границы интервала перепутаны")
        return self


class ValidationEvidence(ExactModel):
    task_semantics: TaskSemantics
    feature_schema_version: EvidenceString | None
    config_sha256: Sha256 | None
    library_versions: dict[EvidenceString, EvidenceString]
    rolling_folds: tuple[FoldEvidence, ...]
    operating_profiles: dict[ProfileName, OperatingProfile]
    validation_confidence_intervals: dict[str, ConfidenceInterval]

    def require_complete(
        self, threshold: float, metrics: EvaluationMetrics, validation_rows: int
    ) -> None:
        if (
            self.feature_schema_version is None
            or self.config_sha256 is None
            or set(self.library_versions) != LIBRARY_NAMES
            or len(self.rolling_folds) < 3
            or tuple(fold.index for fold in self.rolling_folds)
            != tuple(range(1, len(self.rolling_folds) + 1))
            or set(self.operating_profiles) != {"high_precision", "balanced", "high_recall"}
            or set(self.validation_confidence_intervals) != set(EvaluationMetrics.model_fields)
        ):
            raise ValueError("Неполные validation-доказательства")
        if self.operating_profiles["balanced"].threshold != threshold or any(
            fold.threshold != threshold for fold in self.rolling_folds
        ):
            raise ValueError("Рабочий порог не соответствует rolling validation")
        if sum(fold.validation_rows for fold in self.rolling_folds) != validation_rows:
            raise ValueError("Размер validation не соответствует rolling folds")
        for name in EvaluationMetrics.model_fields:
            values = [fold.metrics[name] for fold in self.rolling_folds]
            mean = float(np.mean(values))
            interval = self.validation_confidence_intervals[name]
            expected = _fold_interval(values)
            if not np.isclose(metrics[name], mean, rtol=1e-10, atol=1e-12) or any(
                not np.isclose(getattr(interval, bound), expected[bound], rtol=1e-10, atol=1e-12)
                for bound in ("lower", "upper")
            ):
                raise ValueError("Агрегат или интервал не соответствует rolling folds")
        profile = self.operating_profiles["balanced"]
        if any(
            not np.isclose(getattr(profile, name), metrics[name], rtol=1e-10, atol=1e-12)
            for name in ("precision", "recall", "alert_rate")
        ):
            raise ValueError("Профиль balanced не соответствует validation-агрегату")


def validation_evidence_payload(evidence) -> dict[str, object]:
    """Агрегирует только выбранные validation folds, не читая final test.

    Student-t интервалы описывают разброс среднего между зависимыми rolling folds;
    это не индивидуальные интервалы риска и не гарантия независимой выборки.
    """
    folds = evidence.rolling_folds
    sizes = evidence.rolling_fold_sizes
    return {
        "rolling_folds": [
            {
                "index": fold.fold_index,
                **size,
                "threshold": fold.threshold,
                "metrics": {
                    name: float(getattr(fold.metrics, name))
                    for name in EvaluationMetrics.model_fields
                },
            }
            for fold, size in zip(folds, sizes, strict=True)
        ],
        "operating_profiles": {
            name: {
                "threshold": profile.threshold,
                **{
                    metric: float(
                        np.mean([getattr(fold.metrics, metric) for fold in profile.rolling_folds])
                    )
                    for metric in ("precision", "recall", "alert_rate")
                },
            }
            for name, profile in evidence.operating_profiles.items()
        },
        "validation_confidence_intervals": {
            name: _fold_interval([getattr(fold.metrics, name) for fold in folds])
            for name in EvaluationMetrics.model_fields
        }
        if len(folds) >= 3
        else {},
    }


def _fold_interval(values: list[float]) -> dict[str, object]:
    mean = float(np.mean(values))
    margin = float(t.ppf(0.975, len(values) - 1) * np.std(values, ddof=1) / np.sqrt(len(values)))
    return {
        "lower": max(0.0, mean - margin),
        "upper": min(1.0, mean + margin),
        "level": 0.95,
        "method": "student_t_across_rolling_folds",
    }


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


class EvaluationReport(ValidationEvidence):
    format_version: Literal[2]
    task: Literal["sensor_failure"]
    version: EvaluationVersion
    status: Literal["rejected", "published"]
    evidence_tier: Literal["proxy"]
    label_strategy: Literal["cadence_adjusted_silence_horizon_proxy_v2"]
    horizon_hours: EvaluationHorizonHours | None
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
            "catboost_isotonic",
            "catboost_sigmoid",
            "lightgbm_isotonic",
            "lightgbm_sigmoid",
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
                self.horizon_hours,
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
        if self.status == "published":
            self.require_complete(
                self.threshold, self.validation_metrics, self.split_sizes.validation
            )
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
