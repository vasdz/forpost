import os
import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from forpost_platform.security.demo_identity import DemoIdentityError, verify_demo_assertion
from forpost_platform.security.identity import Permission, Role, SecuritySubject

IDENTITY_PROVIDER_UNAVAILABLE_CODE = "IDENTITY_PROVIDER_UNAVAILABLE"
IDENTITY_PROVIDER_UNAVAILABLE_MESSAGE = "Проверенный поставщик идентификации пока недоступен."
UNAUTHENTICATED_CODE = "UNAUTHENTICATED"
UNAUTHENTICATED_MESSAGE = "Для доступа требуется Bearer-токен."


def identity_provider_unavailable_detail() -> dict[str, str]:
    """Формирует единый безопасный ответ при отсутствии доверенной идентификации."""

    return {
        "code": IDENTITY_PROVIDER_UNAVAILABLE_CODE,
        "message": IDENTITY_PROVIDER_UNAVAILABLE_MESSAGE,
    }


def unauthenticated_detail() -> dict[str, str]:
    """Формирует ответ при отсутствии или некорректной схеме аутентификации."""

    return {
        "code": UNAUTHENTICATED_CODE,
        "message": UNAUTHENTICATED_MESSAGE,
    }


def is_bearer_authorization(authorization: str | None) -> bool:
    """Проверяет только форму Bearer-учётных данных до подключения провайдера."""

    if authorization is None:
        return False
    parts = authorization.split()
    return len(parts) == 2 and parts[0].casefold() == "bearer" and bool(parts[1])


async def get_current_subject(
    authorization: Annotated[str | None, Header()] = None,
) -> SecuritySubject:
    """Принимает только серверный BFF-токен; роли из запроса игнорируются."""

    if not is_bearer_authorization(authorization):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=unauthenticated_detail(),
            headers={"WWW-Authenticate": "Bearer"},
        )

    presented_token = authorization.split(maxsplit=1)[1]
    demo_secret = os.environ.get("FORPOST_DEMO_ASSERTION_SECRET", "")
    if presented_token.startswith("demo."):
        if os.environ.get("FORPOST_DEMO_MODE") != "1":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=identity_provider_unavailable_detail(),
            )
        try:
            return verify_demo_assertion(presented_token.removeprefix("demo."), demo_secret)
        except DemoIdentityError as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=unauthenticated_detail(),
                headers={"WWW-Authenticate": "Bearer"},
            ) from error

    configured_token = os.environ.get("FORPOST_API_SERVICE_TOKEN", "")
    if len(configured_token) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=identity_provider_unavailable_detail(),
        )

    if not secrets.compare_digest(presented_token, configured_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=unauthenticated_detail(),
            headers={"WWW-Authenticate": "Bearer"},
        )

    return SecuritySubject(
        user_id="local-bff",
        username="local-bff",
        roles=frozenset({Role.CENTRAL_DISPATCHER}),
        allowed_districts=frozenset(),
        allowed_complexes=frozenset(),
        ip_address="127.0.0.1",
    )


async def get_current_human_subject(
    authorization: Annotated[str | None, Header()] = None,
) -> SecuritySubject:
    """Отклоняет write-операции до подключения проверенной личности пользователя."""

    if not is_bearer_authorization(authorization):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=unauthenticated_detail(),
            headers={"WWW-Authenticate": "Bearer"},
        )
    subject = await get_current_subject(authorization)
    if subject.user_id == "local-bff":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=identity_provider_unavailable_detail(),
        )
    return subject


def require_permission(perm: Permission):
    """Возвращает зависимость RBAC, сохраняющую проверенного субъекта для маршрута."""

    async def permission_checker(
        subject: Annotated[SecuritySubject, Depends(get_current_subject)],
    ) -> SecuritySubject:
        if not subject.has_permission(perm):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для выполнения операции",
            )
        return subject

    return permission_checker
