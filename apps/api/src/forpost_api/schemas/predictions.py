"""Строгий транспортный контракт прогнозов и решений диспетчера."""

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PredictionType(StrEnum):
    SENSOR_FAILURE = "sensor_failure"
    FIRE_RISK = "fire_risk"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    INFRASTRUCTURE_WEAR = "infrastructure_wear"


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
    probability: float = Field(ge=0.0, le=1.0)
    predicted_at: datetime
    horizon_hours: int = Field(gt=0)
    model_version: str = Field(pattern=r"^v[1-9]\d*$")
    factors: list[PredictionFactor] = Field(max_length=50)
    recommended_action: str = Field(min_length=1, max_length=1000)
    priority: str = Field(min_length=1, max_length=32)
    status: str = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_contract_invariants(self) -> Self:
        if self.predicted_at.tzinfo is None or self.predicted_at.utcoffset() is None:
            raise ValueError("predicted_at должен содержать часовой пояс")
        factor_weights = [abs(item.weight) for item in self.factors]
        if factor_weights != sorted(factor_weights, reverse=True):
            raise ValueError("factors должны быть упорядочены по абсолютному влиянию")
        return self


class PredictionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predictions: list[Prediction]


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
