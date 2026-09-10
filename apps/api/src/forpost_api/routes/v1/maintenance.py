"""API роуты для управления заявками на превентивное обслуживание."""

from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from forpost_domain.maintenance.entities import (
    MaintenanceGenerationRequest,
    MaintenanceGenerationResponse,
    MaintenanceOrder,
    MaintenanceStatus,
)
from forpost_domain.risks.entities import RiskCategory, RiskPrediction
from forpost_platform.audit.ledger import AuditSeverity, audit_ledger
from forpost_platform.maintenance.generator import (
    MaintenanceOrderStore,
    MaintenanceRegulator,
    get_maintenance_store,
)
from forpost_platform.security.identity import Permission, SecuritySubject
from forpost_prediction_core.mock_predictor import MockRiskPredictor

from forpost_api.dependencies import get_current_subject

router = APIRouter(prefix="/maintenance", tags=["Maintenance"])

# Для генерации тестовых данных
PREDICTORS = {
    RiskCategory.SENSOR_FAILURE: MockRiskPredictor(RiskCategory.SENSOR_FAILURE),
    RiskCategory.FIRE_RISK: MockRiskPredictor(RiskCategory.FIRE_RISK),
    RiskCategory.UNAUTHORIZED_ACCESS: MockRiskPredictor(RiskCategory.UNAUTHORIZED_ACCESS),
    RiskCategory.INFRASTRUCTURE_WEAR: MockRiskPredictor(RiskCategory.INFRASTRUCTURE_WEAR),
}

COLLECTOR_ASSETS = [
    {"id": "sensor-deg-014", "category": RiskCategory.SENSOR_FAILURE, "district": "rek-1"},
    {"id": "collector-sector-9", "category": RiskCategory.FIRE_RISK, "district": "rek-1"},
    {"id": "picket-104-shaft", "category": RiskCategory.UNAUTHORIZED_ACCESS, "district": "rek-3"},
    {"id": "pump-station-02", "category": RiskCategory.INFRASTRUCTURE_WEAR, "district": "rek-4"},
]


@router.get("", response_model=list[MaintenanceOrder])
async def get_maintenance_orders(
    subject: SecuritySubject = Depends(get_current_subject),
    store: MaintenanceOrderStore = Depends(get_maintenance_store),
):
    """Получить заявки на обслуживание с фильтрацией по районам (ABAC)."""

    if not subject.has_permission(Permission.VIEW_RISKS):
        audit_ledger.append(
            event_type="UNAUTHORIZED_ACCESS_ATTEMPT",
            severity=AuditSeverity.ALERT,
            user_id=subject.user_id,
            resource_id="/maintenance",
            details={"reason": "Missing VIEW_RISKS permission", "role": subject.role.value},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Отказано в доступе: недостаточный уровень привилегий",
        )

    # Собрать все заявки из всех доступных районов
    all_orders = store.get_all()
    accessible_orders = [
        order for order in all_orders
        if subject.can_access_collector(order.district)
    ]

    audit_ledger.append(
        event_type="READ_MAINTENANCE_REGISTRY",
        severity=AuditSeverity.INFO,
        user_id=subject.user_id,
        resource_id="maintenance_registry",
        details={
            "returned_records": len(accessible_orders),
            "districts": subject.allowed_districts,
        },
    )

    return accessible_orders


@router.post("/generate-from-prediction", response_model=MaintenanceGenerationResponse)
async def generate_from_prediction(
    request: MaintenanceGenerationRequest,
    subject: SecuritySubject = Depends(get_current_subject),
    store: MaintenanceOrderStore = Depends(get_maintenance_store),
):
    """Генерирует заявки на обслуживание из прогнозов рисков.

    Этот эндпоинт:
    1. Берет прогнозы по рискам
    2. Преобразует их в заявки на превентивное обслуживание
    3. Логирует в WORM-аудит
    4. Возвращает список созданных заявок
    """

    if not subject.has_permission(Permission.VIEW_RISKS):
        audit_ledger.append(
            event_type="UNAUTHORIZED_ACCESS_ATTEMPT",
            severity=AuditSeverity.ALERT,
            user_id=subject.user_id,
            resource_id="/maintenance/generate-from-prediction",
            details={"reason": "Missing VIEW_RISKS permission"},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Отказано в доступе",
        )

    # Генерируем прогнозы по рискам (в продакшене это будут реальные данные из БД)
    predictions: list[RiskPrediction] = []
    accessible_assets = [
        asset for asset in COLLECTOR_ASSETS
        if subject.can_access_collector(asset["district"])
    ]

    for asset in accessible_assets:
        predictor = PREDICTORS[asset["category"]]
        prediction = predictor.predict(target_id=asset["id"], context_data={})
        predictions.append(prediction)

    # Конвертируем прогнозы в заявки
    generated_orders: list[MaintenanceOrder] = []
    for prediction in predictions:
        order = MaintenanceRegulator.generate_order_from_risk(prediction, model_version="0.1.0")

        # Устанавливаем район из прогноза
        asset = next((a for a in accessible_assets if a["id"] == prediction.target_id), None)
        if asset:
            order.district = asset["district"]

        # Если требуется автоутверждение
        if request.auto_approve:
            order.status = MaintenanceStatus.APPROVED

        # Сохраняем в хранилище
        store.save(order)
        generated_orders.append(order)

    # Логируем в аудит
    audit_trail_id = f"AT-{uuid.uuid4().hex[:8].upper()}"
    audit_ledger.append(
        event_type="GENERATE_MAINTENANCE_ORDERS",
        severity=AuditSeverity.INFO,
        user_id=subject.user_id,
        resource_id="maintenance_generator",
        details={
            "generated_count": len(generated_orders),
            "auto_approve": request.auto_approve,
            "districts": subject.allowed_districts,
            "audit_trail_id": audit_trail_id,
        },
    )

    return MaintenanceGenerationResponse(
        generated_count=len(generated_orders),
        orders=generated_orders,
        audit_trail_id=audit_trail_id,
    )


@router.patch("/{order_id}/status")
async def update_order_status(
    order_id: str,
    new_status: MaintenanceStatus,
    subject: SecuritySubject = Depends(get_current_subject),
    store: MaintenanceOrderStore = Depends(get_maintenance_store),
):
    """Обновить статус заявки (ABAC + аудит)."""

    order = store.get_by_id(order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Заявка {order_id} не найдена",
        )

    if not subject.can_access_collector(order.district):
        audit_ledger.append(
            event_type="UNAUTHORIZED_ACCESS_ATTEMPT",
            severity=AuditSeverity.ALERT,
            user_id=subject.user_id,
            resource_id=f"/maintenance/{order_id}",
            details={"reason": "District access denied", "target_district": order.district},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ запрещен: заявка находится в другом районе",
        )

    old_status = order.status
    updated = store.update_status(order_id, new_status)

    audit_ledger.append(
        event_type="UPDATE_MAINTENANCE_ORDER_STATUS",
        severity=AuditSeverity.INFO,
        user_id=subject.user_id,
        resource_id=f"maintenance_order:{order_id}",
        details={
            "old_status": old_status,
            "new_status": new_status,
            "district": order.district,
        },
    )

    return {"status": "updated", "order": updated}
