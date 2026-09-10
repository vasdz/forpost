from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SensorType(StrEnum):
    CONTACT = "contact"  # Контактные
    VOLUME = "volume"  # Объёмные (СКУД / проникновение)
    TEMPERATURE = "temperature"  # Температурные
    SMOKE = "smoke"  # Дымовые
    GAS = "gas"  # Газовые


class Sensor(BaseModel):
    id: str
    type: SensorType
    collector_id: str = Field(..., description="Идентификатор коллектора")
    picket: int = Field(..., description="Номер пикета/участка")
    installed_at: datetime
    last_maintenance_at: datetime | None = None
    is_active: bool = True
