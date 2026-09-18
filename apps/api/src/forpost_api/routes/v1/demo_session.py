"""Выдача внутреннего demo-утверждения только на loopback-стенде."""

import os
import secrets
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Request, status
from forpost_platform.security.demo_identity import DemoIdentityError, issue_demo_assertion
from forpost_platform.security.identity import Role, SecuritySubject
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix="/demo/session", tags=["Demo session"])


class DemoSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: Literal["district-dispatcher", "central-dispatcher", "technician", "admin"]


PROFILES: dict[str, SecuritySubject] = {
    "district-dispatcher": SecuritySubject(
        user_id="demo-district-dispatcher",
        username="Диспетчер РЭК-1",
        roles=frozenset({Role.DISTRICT_DISPATCHER}),
        allowed_districts=frozenset({"РЭК-1"}),
    ),
    "central-dispatcher": SecuritySubject(
        user_id="demo-central-dispatcher",
        username="Диспетчер ОДС",
        roles=frozenset({Role.CENTRAL_DISPATCHER}),
    ),
    "technician": SecuritySubject(
        user_id="demo-technician",
        username="Техник комплекса",
        roles=frozenset({Role.TECHNICIAN}),
        allowed_complexes=frozenset({"demo-complex-1"}),
    ),
    "admin": SecuritySubject(
        user_id="demo-admin",
        username="Администратор ИС",
        roles=frozenset({Role.SYSTEM_ADMIN}),
    ),
}


@router.post("")
async def create_demo_session(
    payload: DemoSessionRequest,
    request: Request,
    access_key: str | None = Header(default=None, alias="X-Demo-Access-Key"),
) -> dict[str, object]:
    """Возвращает короткоживущее утверждение для локального BFF, не cookie браузера."""
    client_host = request.client.host if request.client else ""
    if os.environ.get("FORPOST_DEMO_MODE") != "1" or client_host not in {
        "127.0.0.1",
        "::1",
        "testclient",
    }:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ресурс не найден")
    configured_key = os.environ.get("FORPOST_DEMO_ACCESS_KEY", "")
    if (
        len(configured_key) < 32
        or access_key is None
        or not secrets.compare_digest(access_key, configured_key)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Demo-доступ отклонён")
    try:
        assertion = issue_demo_assertion(
            PROFILES[payload.profile], os.environ.get("FORPOST_DEMO_ASSERTION_SECRET", "")
        )
    except DemoIdentityError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demo-идентификация не настроена",
        ) from error
    return {"assertion": f"demo.{assertion}", "expiresIn": 300, "provenance": "simulated"}
