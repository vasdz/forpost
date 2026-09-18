from enum import StrEnum

from pydantic import BaseModel, Field


class Role(StrEnum):
    DISPATCHER = "dispatcher"  # Диспетчер ОДС (оперативный мониторинг)
    ANALYST = "analyst"  # Аналитик (верификация прогнозов и аудит)
    CHIEF_ENGINEER = "chief_engineer"  # Главный инженер (согласование ордеров/заявок)
    SECURITY_AUDITOR = "auditor"  # Офицер безопасности / Аудитор ИБ
    SYSTEM_ADMIN = "admin"  # Администратор платформы (без прав к бизнес-действиям)


class Permission(StrEnum):
    READ_TELEMETRY = "telemetry:read"
    VIEW_RISKS = "risks:view"
    APPROVE_SERVICE_ORDER = "service_order:approve"
    AUDIT_READ = "audit:read"
    MANAGE_MODELS = "models:manage"


# Матрица ролевых полномочий (RBAC)
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.DISPATCHER: {Permission.READ_TELEMETRY, Permission.VIEW_RISKS},
    Role.ANALYST: {
        Permission.READ_TELEMETRY,
        Permission.VIEW_RISKS,
        Permission.AUDIT_READ,
    },
    Role.CHIEF_ENGINEER: {
        Permission.READ_TELEMETRY,
        Permission.VIEW_RISKS,
        Permission.APPROVE_SERVICE_ORDER,
    },
    Role.SECURITY_AUDITOR: {Permission.AUDIT_READ},
    Role.SYSTEM_ADMIN: {Permission.MANAGE_MODELS},
}


class SecuritySubject(BaseModel):
    """Контекст субъекта доступа (Zero Trust Context)."""

    user_id: str
    username: str
    role: Role
    # Атрибуты для ABAC: разрешенные зоны коллекторного хозяйства
    allowed_districts: list[str] = Field(
        default_factory=list, description="Разрешенные районы: e.g. ['РЭК-1', 'РЭК-3']"
    )
    ip_address: str = "127.0.0.1"

    def has_permission(self, permission: Permission) -> bool:
        return permission in ROLE_PERMISSIONS.get(self.role, set())

    def can_access_collector(self, collector_district: str) -> bool:
        """Проверка мандата на географический участок."""
        if self.role in {Role.CHIEF_ENGINEER, Role.SECURITY_AUDITOR}:
            return True
        return collector_district in self.allowed_districts
