from fastapi import APIRouter, Depends, HTTPException, status
from forpost_domain.risks.entities import RiskCategory, RiskPrediction
from forpost_platform.audit.ledger import AuditSeverity, audit_ledger
from forpost_platform.security.identity import Permission, SecuritySubject
from forpost_prediction_core.mock_predictor import MockRiskPredictor

from forpost_api.dependencies import get_current_subject

router = APIRouter(prefix="/risks", tags=["Risks"])

PREDICTORS = {
    RiskCategory.SENSOR_FAILURE: MockRiskPredictor(RiskCategory.SENSOR_FAILURE),
    RiskCategory.FIRE_RISK: MockRiskPredictor(RiskCategory.FIRE_RISK),
    RiskCategory.UNAUTHORIZED_ACCESS: MockRiskPredictor(RiskCategory.UNAUTHORIZED_ACCESS),
    RiskCategory.INFRASTRUCTURE_WEAR: MockRiskPredictor(RiskCategory.INFRASTRUCTURE_WEAR),
}

# Системные коды эксплуатационных районов (rek-1 .. rek-4)
COLLECTOR_ASSETS = [
    {"id": "sensor-deg-014", "category": RiskCategory.SENSOR_FAILURE, "district": "rek-1"},
    {"id": "collector-sector-9", "category": RiskCategory.FIRE_RISK, "district": "rek-1"},
    {"id": "picket-104-shaft", "category": RiskCategory.UNAUTHORIZED_ACCESS, "district": "rek-3"},
    {"id": "pump-station-02", "category": RiskCategory.INFRASTRUCTURE_WEAR, "district": "rek-4"},
]


@router.get("", response_model=list[RiskPrediction])
async def get_latest_risks(
    subject: SecuritySubject = Depends(get_current_subject),
):
    """Выдача рисков с мандатной фильтрацией по эксплуатационным районам диспетчера."""

    if not subject.has_permission(Permission.VIEW_RISKS):
        audit_ledger.append(
            event_type="UNAUTHORIZED_ACCESS_ATTEMPT",
            severity=AuditSeverity.ALERT,
            user_id=subject.user_id,
            resource_id="/risks",
            details={"reason": "Missing VIEW_RISKS permission", "role": subject.role.value},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Отказано в доступе: недостаточный уровень привилегий",
        )

    accessible_objects = [
        item for item in COLLECTOR_ASSETS if subject.can_access_collector(item["district"])
    ]

    audit_ledger.append(
        event_type="READ_RISK_REGISTRY",
        severity=AuditSeverity.INFO,
        user_id=subject.user_id,
        resource_id="risk_registry",
        details={
            "returned_records": len(accessible_objects),
            "districts": subject.allowed_districts,
        },
    )

    return [
        PREDICTORS[obj["category"]].predict(target_id=obj["id"], context_data={})
        for obj in accessible_objects
    ]


@router.get("/audit/verify", tags=["Audit"])
async def verify_audit_chain(subject: SecuritySubject = Depends(get_current_subject)):
    """Эндпоинт верификации целостности аудит-лога (доступен только Аудитору ИБ)."""
    if not subject.has_permission(Permission.AUDIT_READ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ запрещен")

    is_valid = audit_ledger.verify_integrity()
    return {
        "status": "verified" if is_valid else "tampered",
        "total_records": len(audit_ledger._chain),
        "chain_intact": is_valid,
    }
