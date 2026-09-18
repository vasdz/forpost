from enum import StrEnum

from pydantic import BaseModel, Field


class Role(StrEnum):
    DISTRICT_DISPATCHER = "district_dispatcher"
    CENTRAL_DISPATCHER = "central_dispatcher"
    TECHNICIAN = "technician"
    SYSTEM_ADMIN = "admin"


class Permission(StrEnum):
    READ_TELEMETRY = "telemetry:read"
    VIEW_RISKS = "risks:view"
    RECORD_DECISION = "incident:decide"
    VIEW_SERVICE_DRAFT = "service_draft:view"
    CREATE_SERVICE_DRAFT = "service_draft:create"
    RECORD_INSPECTION = "inspection:record"
    AUDIT_READ = "audit:read"
    MANAGE_SYSTEM = "system:manage"
    # Сохраняются для существующих fail-closed маршрутов до их замены доменными правами.
    APPROVE_SERVICE_ORDER = "service_order:approve"
    MANAGE_MODELS = "models:manage"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.DISTRICT_DISPATCHER: frozenset(
        {
            Permission.READ_TELEMETRY,
            Permission.VIEW_RISKS,
            Permission.RECORD_DECISION,
            Permission.VIEW_SERVICE_DRAFT,
            Permission.CREATE_SERVICE_DRAFT,
        }
    ),
    Role.CENTRAL_DISPATCHER: frozenset(
        {
            Permission.READ_TELEMETRY,
            Permission.VIEW_RISKS,
            Permission.RECORD_DECISION,
            Permission.VIEW_SERVICE_DRAFT,
            Permission.CREATE_SERVICE_DRAFT,
        }
    ),
    Role.TECHNICIAN: frozenset(
        {
            Permission.READ_TELEMETRY,
            Permission.VIEW_RISKS,
            Permission.VIEW_SERVICE_DRAFT,
            Permission.RECORD_INSPECTION,
        }
    ),
    Role.SYSTEM_ADMIN: frozenset({Permission.AUDIT_READ, Permission.MANAGE_SYSTEM}),
}


class SecuritySubject(BaseModel):
    """Проверенный сервером субъект с аддитивными ролями и областями."""

    user_id: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=1, max_length=256)
    roles: frozenset[Role] = Field(min_length=1, max_length=4)
    allowed_districts: frozenset[str] = Field(default_factory=frozenset, max_length=128)
    allowed_complexes: frozenset[str] = Field(default_factory=frozenset, max_length=512)
    ip_address: str = Field(default="127.0.0.1", max_length=64)

    def has_permission(self, permission: Permission) -> bool:
        return any(permission in ROLE_PERMISSIONS[role] for role in self.roles)

    def can_access_resource(self, district: str | None, complex_id: str | None) -> bool:
        """Проверяет серверную область без доверия к атрибутам запроса."""
        if Role.CENTRAL_DISPATCHER in self.roles:
            return True
        district_allowed = district is not None and district in self.allowed_districts
        complex_allowed = complex_id is not None and complex_id in self.allowed_complexes
        return district_allowed or complex_allowed

    def can_access_collector(self, collector_district: str) -> bool:
        """Совместимый вызов для существующих read-only маршрутов."""
        return self.can_access_resource(district=collector_district, complex_id=None)
