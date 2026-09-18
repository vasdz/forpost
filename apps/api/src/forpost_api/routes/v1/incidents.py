"""Оперативные решения и локальные demo-черновики внешнего help-desk."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Annotated, Literal, Protocol
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from forpost_domain.incidents.entities import (
    IncidentDecision,
    IncidentStatus,
    ServiceRequestDraft,
)
from forpost_platform.operations.sqlite_repository import (
    IdempotencyConflictError,
    OperationsConflictError,
    SqliteOperationsRepository,
)
from forpost_platform.security.identity import Permission, SecuritySubject
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from forpost_api.dependencies import get_current_human_subject, get_current_subject

router = APIRouter(tags=["Incidents"])
PROJECT_ROOT = Path(__file__).resolve().parents[6]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "processed" / "demo-operations.sqlite3"
DEFAULT_SNAPSHOT_PATH = PROJECT_ROOT / "data" / "processed" / "local-situation.json"
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
MAX_CHANNELS = 200_000
MAX_EVENTS = 2_000


class IncidentCatalogError(RuntimeError):
    """Локальный каталог недоступен или нарушает публичный контракт."""


class IncidentNotFoundError(LookupError):
    """Канонический инцидент отсутствует в текущем снимке."""


class IncidentScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    incident_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    channel_id: str = Field(min_length=1, max_length=256)
    complex_id: str | None = Field(default=None, min_length=1, max_length=256)

    def contains_target(self, target_id: str) -> bool:
        return target_id == self.channel_id or target_id == self.complex_id


class IncidentCatalog(Protocol):
    def get(self, incident_id: str) -> IncidentScope: ...


class LocalIncidentCatalog:
    """Индексирует только ограниченный публичный снимок, не читая raw-данные."""

    def __init__(self, snapshot_path: Path):
        self._snapshot_path = snapshot_path
        self._signature: tuple[int, int] | None = None
        self._index: dict[str, IncidentScope] = {}
        self._lock = RLock()

    def get(self, incident_id: str) -> IncidentScope:
        if len(incident_id) != 64 or any(char not in "0123456789abcdef" for char in incident_id):
            raise IncidentNotFoundError
        self._refresh_if_changed()
        try:
            return self._index[incident_id]
        except KeyError as error:
            raise IncidentNotFoundError from error

    def _refresh_if_changed(self) -> None:
        with self._lock:
            try:
                stat = self._snapshot_path.stat()
            except OSError as error:
                raise IncidentCatalogError from error
            if stat.st_size > MAX_SNAPSHOT_BYTES:
                raise IncidentCatalogError
            signature = (stat.st_mtime_ns, stat.st_size)
            if signature == self._signature:
                return
            try:
                raw = self._snapshot_path.read_bytes()
                if len(raw) > MAX_SNAPSHOT_BYTES:
                    raise IncidentCatalogError
                document = json.loads(raw.decode("utf-8"))
                channels = document["channels"]
                events = document["events"]
            except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as error:
                raise IncidentCatalogError from error
            if (
                not isinstance(channels, list)
                or len(channels) > MAX_CHANNELS
                or not isinstance(events, list)
                or len(events) > MAX_EVENTS
            ):
                raise IncidentCatalogError

            channel_objects: dict[str, str | None] = {}
            try:
                for channel in channels:
                    channel_id = channel["channelId"]
                    complex_id = channel["objectId"]
                    if not isinstance(channel_id, str) or not channel_id:
                        raise IncidentCatalogError
                    if complex_id is not None and (
                        not isinstance(complex_id, str) or not complex_id
                    ):
                        raise IncidentCatalogError
                    channel_objects[channel_id] = complex_id

                index: dict[str, IncidentScope] = {}
                for event in events:
                    if event.get("isAlarm") is not True:
                        continue
                    incident_id = event["canonicalId"]
                    channel_id = event["channelId"]
                    if not isinstance(incident_id, str) or not isinstance(channel_id, str):
                        raise IncidentCatalogError
                    if channel_id not in channel_objects:
                        raise IncidentCatalogError
                    index[incident_id] = IncidentScope(
                        incident_id=incident_id,
                        channel_id=channel_id,
                        complex_id=channel_objects[channel_id],
                    )
            except (KeyError, TypeError, ValueError) as error:
                raise IncidentCatalogError from error
            self._index = index
            self._signature = signature


class IncidentDecisionRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    status: IncidentStatus
    reason: str = Field(min_length=5, max_length=1000)
    corrects_decision_id: str | None = Field(default=None, min_length=1, max_length=128)


class ServiceDraftRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    incident_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    target_id: str = Field(min_length=1, max_length=256)
    category: str = Field(min_length=1, max_length=128)
    priority: Literal["low", "medium", "high", "critical"]
    recommended_action: str = Field(min_length=5, max_length=2000)
    due_at: datetime


@lru_cache(maxsize=1)
def _demo_repository() -> SqliteOperationsRepository:
    return SqliteOperationsRepository(DEFAULT_DATABASE_PATH)


def get_operations_repository() -> SqliteOperationsRepository:
    """Не создаёт локальное write-хранилище вне явно включённого demo-режима."""
    if os.environ.get("FORPOST_DEMO_MODE") != "1":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Оперативное demo-хранилище не включено",
        )
    return _demo_repository()


@lru_cache(maxsize=1)
def get_incident_catalog() -> IncidentCatalog:
    return LocalIncidentCatalog(DEFAULT_SNAPSHOT_PATH)


def _require(subject: SecuritySubject, permission: Permission) -> None:
    if not subject.has_permission(permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для выполнения операции",
        )


def _get_authorized_scope(
    catalog: IncidentCatalog, incident_id: str, subject: SecuritySubject
) -> IncidentScope:
    try:
        scope = catalog.get(incident_id)
    except IncidentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Инцидент не найден"
        ) from error
    except IncidentCatalogError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Локальный каталог инцидентов недоступен",
        ) from error
    if not subject.can_access_resource(district=None, complex_id=scope.complex_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Инцидент находится вне разрешённой области",
        )
    return scope


@router.get(
    "/incidents/{incident_id}/decisions",
    response_model=list[IncidentDecision],
    response_model_by_alias=True,
)
async def list_incident_decisions(
    incident_id: str,
    subject: Annotated[SecuritySubject, Depends(get_current_subject)],
    repository: Annotated[SqliteOperationsRepository, Depends(get_operations_repository)],
    catalog: Annotated[IncidentCatalog, Depends(get_incident_catalog)],
) -> list[IncidentDecision]:
    _require(subject, Permission.VIEW_RISKS)
    _get_authorized_scope(catalog, incident_id, subject)
    return repository.list_decisions(incident_id)


@router.post(
    "/incidents/{incident_id}/decisions",
    response_model=IncidentDecision,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def record_incident_decision(
    incident_id: str,
    payload: IncidentDecisionRequest,
    subject: Annotated[SecuritySubject, Depends(get_current_human_subject)],
    repository: Annotated[SqliteOperationsRepository, Depends(get_operations_repository)],
    catalog: Annotated[IncidentCatalog, Depends(get_incident_catalog)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> IncidentDecision:
    _require(subject, Permission.RECORD_DECISION)
    _get_authorized_scope(catalog, incident_id, subject)
    command = {
        "actorId": subject.user_id,
        "correctsDecisionId": payload.corrects_decision_id,
        "incidentId": incident_id,
        "reason": payload.reason,
        "status": payload.status.value,
    }
    decision = IncidentDecision(
        decision_id=f"decision-{uuid4().hex}",
        incident_id=incident_id,
        status=payload.status,
        reason=payload.reason,
        actor_id=subject.user_id,
        created_at=datetime.now(UTC),
        corrects_decision_id=payload.corrects_decision_id,
    )
    try:
        return repository.record_decision(decision, idempotency_key, command)
    except IdempotencyConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except OperationsConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error


@router.get(
    "/service-request-drafts",
    response_model=list[ServiceRequestDraft],
    response_model_by_alias=True,
)
async def list_service_drafts(
    subject: Annotated[SecuritySubject, Depends(get_current_subject)],
    repository: Annotated[SqliteOperationsRepository, Depends(get_operations_repository)],
    catalog: Annotated[IncidentCatalog, Depends(get_incident_catalog)],
) -> list[ServiceRequestDraft]:
    _require(subject, Permission.VIEW_SERVICE_DRAFT)
    drafts = repository.list_drafts()
    if subject.can_access_resource(district=None, complex_id=None):
        return drafts
    visible: list[ServiceRequestDraft] = []
    for draft in drafts:
        try:
            scope = catalog.get(draft.incident_id)
        except (IncidentCatalogError, IncidentNotFoundError):
            continue
        if subject.can_access_resource(district=None, complex_id=scope.complex_id):
            visible.append(draft)
    return visible


@router.post(
    "/service-request-drafts",
    response_model=ServiceRequestDraft,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_service_draft(
    payload: ServiceDraftRequest,
    subject: Annotated[SecuritySubject, Depends(get_current_human_subject)],
    repository: Annotated[SqliteOperationsRepository, Depends(get_operations_repository)],
    catalog: Annotated[IncidentCatalog, Depends(get_incident_catalog)],
) -> ServiceRequestDraft:
    _require(subject, Permission.CREATE_SERVICE_DRAFT)
    scope = _get_authorized_scope(catalog, payload.incident_id, subject)
    if not scope.contains_target(payload.target_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Целевой объект не связан с инцидентом",
        )
    if payload.due_at.tzinfo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Срок должен содержать часовой пояс",
        )
    draft = ServiceRequestDraft(
        draft_id=f"draft-{uuid4().hex}",
        incident_id=payload.incident_id,
        target_id=payload.target_id,
        category=payload.category,
        priority=payload.priority,
        recommended_action=payload.recommended_action,
        due_at=payload.due_at,
        author_id=subject.user_id,
        created_at=datetime.now(UTC),
    )
    try:
        return repository.create_draft(draft)
    except OperationsConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
