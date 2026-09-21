"""Строгий транспортный контракт прогнозов и решений диспетчера."""

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_PREDICTIONS_PER_RESPONSE = 10_000


class PredictionType(StrEnum):
    SENSOR_FAILURE = "sensor_failure"
    FIRE_RISK = "fire_risk"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    INFRASTRUCTURE_WEAR = "infrastructure_wear"


class EvidenceTier(StrEnum):
    VALIDATED = "validated"
    PROXY = "proxy"
    ANOMALY = "anomaly"
    SCENARIO = "scenario"


class PredictionProvenance(StrEnum):
    OBSERVED = "observed"
    DERIVED = "derived"
    SIMULATED = "simulated"


class QualityStatus(StrEnum):
    PASSED = "passed"
    LIMITED = "limited"


class PredictionConfidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lower: float = Field(ge=0.0, le=1.0)
    upper: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        if self.lower > self.upper:
            raise ValueError("Нижняя граница confidence не может превышать верхнюю")
        return self


class PredictionMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    f1: float = Field(ge=0.0, le=1.0)
    pr_auc: float = Field(ge=0.0, le=1.0)
    brier_score: float = Field(ge=0.0, le=1.0)


class PredictionFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factor: str = Field(min_length=1, max_length=128)
    weight: float = Field(ge=-1.0, le=1.0)
    description: str = Field(min_length=1, max_length=500)


class Prediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    entity_type: Literal["sensor", "location"]
    entity_id: str = Field(min_length=1, max_length=128)
    prediction_type: PredictionType
    probability: float | None = Field(default=None, ge=0.0, le=1.0)
    anomaly_score: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_tier: EvidenceTier
    calibrated: bool
    provenance: PredictionProvenance
    confidence: PredictionConfidence | None = None
    model_metrics: PredictionMetrics | None = None
    quality_status: QualityStatus
    limitations: list[str] = Field(min_length=1, max_length=20)
    predicted_at: datetime
    horizon_hours: int = Field(gt=0)
    model_version: str = Field(pattern=r"^v[1-9]\d*$")
    factors: list[PredictionFactor] = Field(max_length=50)
    recommended_action: str = Field(min_length=1, max_length=1000)
    priority: Literal["low", "medium", "high", "critical"]
    status: Literal[
        "new",
        "acknowledged",
        "confirmed",
        "rejected",
        "escalated",
        "resolved",
    ]

    @model_validator(mode="after")
    def validate_contract_invariants(self) -> Self:
        if self.predicted_at.tzinfo is None or self.predicted_at.utcoffset() is None:
            raise ValueError("predicted_at должен содержать часовой пояс")
        factor_weights = [abs(item.weight) for item in self.factors]
        if factor_weights != sorted(factor_weights, reverse=True):
            raise ValueError("factors должны быть упорядочены по абсолютному влиянию")
        if self.evidence_tier in {EvidenceTier.VALIDATED, EvidenceTier.PROXY}:
            if (
                self.probability is None
                or self.anomaly_score is not None
                or not self.calibrated
                or self.model_metrics is None
            ):
                raise ValueError("Вероятностный прогноз требует калибровку и метрики")
            if (
                self.confidence
                and not self.confidence.lower <= self.probability <= self.confidence.upper
            ):
                raise ValueError("Вероятность должна находиться внутри confidence interval")
            if self.quality_status is QualityStatus.PASSED and (
                self.model_metrics.precision <= 0.7 or self.model_metrics.recall <= 0.5
            ):
                raise ValueError("Passed-прогноз не прошёл обязательные метрики ТЗ")
        elif self.evidence_tier is EvidenceTier.ANOMALY:
            if self.probability is not None or self.anomaly_score is None or self.calibrated:
                raise ValueError("Anomaly-результат содержит score, а не вероятность")
        elif self.evidence_tier is EvidenceTier.SCENARIO:
            if self.provenance is not PredictionProvenance.SIMULATED:
                raise ValueError("Сценарный результат должен иметь simulated provenance")
            if self.probability is not None or self.anomaly_score is not None or self.calibrated:
                raise ValueError("Сценарный результат не является вероятностным прогнозом")
        return self


class PredictionExport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predictions: list[Prediction] = Field(max_length=MAX_PREDICTIONS_PER_RESPONSE)


class PredictionListResponse(PredictionExport):
    available_types: list[PredictionType] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def validate_available_types(self) -> Self:
        if len(set(self.available_types)) != len(self.available_types):
            raise ValueError("available_types не должен содержать дубли")
        return self


class DispatcherDecision(StrEnum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class PredictionDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: DispatcherDecision
    reason: str = Field(min_length=3, max_length=1000)


class PredictionDecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["recorded"]
    prediction_id: str
    audit_record_id: int
