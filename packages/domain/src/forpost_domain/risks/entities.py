from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class RiskCategory(StrEnum):
    SENSOR_FAILURE = "sensor_failure"  # Отказ датчика
    FIRE_RISK = "fire_risk"  # Пожарный риск
    UNAUTHORIZED_ACCESS = "unauthorized_access"  # Несанкционированный доступ
    INFRASTRUCTURE_WEAR = "infrastructure_wear"  # Износ инфраструктуры


class RiskPrediction(BaseModel):
    prediction_id: str
    target_id: str = Field(..., description="ID сенсора, камеры или участка коллектора")
    category: RiskCategory
    probability: float = Field(..., ge=0.0, le=1.0)
    horizon_hours: int = Field(default=24, ge=24, description="Горизонт не менее 24 ч")
    calculated_at: datetime
    model_version: str
    explanation: str
