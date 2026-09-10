from fastapi import Header, HTTPException, status
from forpost_platform.security.identity import Permission, Role, SecuritySubject


async def get_current_subject(
    x_user_id: str = Header(default="disp-01"),
    x_role: str = Header(default="dispatcher"),
    x_districts: str = Header(default="РЭК-1,РЭК-2", description="Список районов через запятую"),
) -> SecuritySubject:
    """Имитация извлечения доверенного контекста (в бою — из валидированного mTLS / ГОСТ JWT)."""
    try:
        role_enum = Role(x_role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недопустимая роль субъекта доступа",
        )

    return SecuritySubject(
        user_id=x_user_id,
        username=f"user_{x_user_id}",
        role=role_enum,
        allowed_districts=[d.strip() for d in x_districts.split(",") if d.strip()],
    )


def require_permission(perm: Permission):
    """Декоратор/зависимость проверки прав доступа (RBAC)."""

    async def permission_checker(subject: SecuritySubject = None):
        # Будет внедрен через Depends
        return perm

    return permission_checker
