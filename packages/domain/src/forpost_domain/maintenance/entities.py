from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class MaintenancePriority(StrEnum):
    """Приоритет превентивного обслуживания."""
    LOW = "low"  # Низкий
    MEDIUM = "medium"  # Средний
    HIGH = "high"  # Высокий
    CRITICAL = "critical"  # Критический


class MaintenanceStatus(StrEnum):
    """Статус заявки на обслуживание."""
    DRAFT = "draft"  # Черновик
    PENDING_APPROVAL = "pending_approval"  # Ожидание утверждения
    APPROVED = "approved"  # Утверждена
    COMPLETED = "completed"  # Завершена


class MaintenanceOrder(BaseModel):
    """Заявка на превентивное обслуживание / ремонт."""
    order_id: str = Field(..., description="Уникальный идентификатор заявки")
    target_id: str = Field(..., description="ID целевого объекта (датчик, участок, техника)")
    district: str = Field(..., description="Эксплуатационный район (rek-1..rek-4)")
    risk_category: str = Field(..., description="Категория риска (sensor_failure, fire_risk и т.д.)")
    priority: MaintenancePriority
    status: MaintenanceStatus = Field(default=MaintenanceStatus.DRAFT)
    recommended_action: str = Field(..., description="Рекомендуемое действие")
    normative_ref: str = Field(..., description="Ссылка на нормативный документ / регламент")
    deadline_hours: int = Field(..., ge=1, description="Время до критического отказа (часов)")
    created_at: datetime
    generated_by_model_version: str = Field(..., description="Версия модели, сгенерировавшей заявку")


class MaintenanceGenerationRequest(BaseModel):
    """Запрос на генерацию заявок из прогнозов рисков."""
    risk_prediction_ids: list[str] = Field(default_factory=list, description="Список ID прогнозов для преобразования")
    auto_approve: bool = Field(default=False, description="Автоматически утверждать созданные заявки")


class MaintenanceGenerationResponse(BaseModel):
    """Ответ на запрос генерации заявок."""
    generated_count: int
    orders: list[MaintenanceOrder]
    audit_trail_id: str = Field(..., description="ID записи в аудит-логе")
