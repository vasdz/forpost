from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from forpost_platform.audit.ledger import audit_ledger
from forpost_platform.security.identity import Permission, SecuritySubject

from forpost_api.dependencies import get_current_subject
from forpost_api.routes.v1.availability import raise_real_data_integration_unavailable

router = APIRouter(prefix="/risks", tags=["Risks"])

Subject = Annotated[SecuritySubject, Depends(get_current_subject)]


@router.get("", response_model=None)
async def get_latest_risks(_subject: Subject) -> NoReturn:
    """Не выдаёт прогнозы до подключения обученной модели и проверенного источника."""

    raise_real_data_integration_unavailable()


@router.get("/audit/verify", tags=["Audit"])
async def verify_audit_chain(subject: Subject) -> dict[str, str | int | bool]:
    """Проверяет целостность служебной цепочки аудита, не раскрывая данные мониторинга."""
    if not subject.has_permission(Permission.AUDIT_READ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ запрещен")

    is_valid = audit_ledger.verify_integrity()
    return {
        "status": "verified" if is_valid else "tampered",
        "total_records": len(audit_ledger._chain),
        "chain_intact": is_valid,
    }
