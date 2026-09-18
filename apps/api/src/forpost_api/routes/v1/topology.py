"""Серверно отфильтрованная условная схема объектов."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, HTTPException, status
from forpost_platform.security.identity import Permission, SecuritySubject
from forpost_platform.topology.generator import (
    TopologyError,
    TopologyObject,
    build_schematic_feature_collection,
)

from forpost_api.dependencies import require_permission

router = APIRouter(tags=["Topology"])
PROJECT_ROOT = Path(__file__).resolve().parents[6]
DEFAULT_SNAPSHOT_PATH = PROJECT_ROOT / "data" / "processed" / "local-situation.json"
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
MAX_OBJECTS = 50_000
Subject = Annotated[SecuritySubject, Depends(require_permission(Permission.VIEW_RISKS))]


class TopologyCatalogError(RuntimeError):
    """Публичный снимок не содержит допустимую иерархию объектов."""


class TopologyCatalog(Protocol):
    def list_objects(self) -> tuple[TopologyObject, ...]: ...


class LocalTopologyCatalog:
    def __init__(self, snapshot_path: Path):
        self._snapshot_path = snapshot_path
        self._signature: tuple[int, int] | None = None
        self._objects: tuple[TopologyObject, ...] = ()
        self._lock = RLock()

    def list_objects(self) -> tuple[TopologyObject, ...]:
        with self._lock:
            try:
                stat = self._snapshot_path.stat()
                if stat.st_size > MAX_SNAPSHOT_BYTES:
                    raise TopologyCatalogError
                signature = (stat.st_mtime_ns, stat.st_size)
                if signature == self._signature:
                    return self._objects
                raw = self._snapshot_path.read_bytes()
                if len(raw) > MAX_SNAPSHOT_BYTES:
                    raise TopologyCatalogError
                document = json.loads(raw.decode("utf-8"))
                records = document["objects"]
            except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as error:
                raise TopologyCatalogError from error
            if not isinstance(records, list) or len(records) > MAX_OBJECTS:
                raise TopologyCatalogError
            try:
                objects = tuple(
                    TopologyObject(
                        object_id=record["objectId"],
                        parent_id=record["parentId"],
                        object_kind=record["objectKind"],
                        dispatcher_name=record["dispatcherName"],
                    )
                    for record in records
                )
            except (KeyError, TypeError) as error:
                raise TopologyCatalogError from error
            self._objects = objects
            self._signature = signature
            return objects


@lru_cache(maxsize=1)
def get_topology_catalog() -> TopologyCatalog:
    return LocalTopologyCatalog(DEFAULT_SNAPSHOT_PATH)


@router.get("/topology", response_model=None)
async def get_topology(
    subject: Subject,
    catalog: Annotated[TopologyCatalog, Depends(get_topology_catalog)],
) -> dict[str, object]:
    try:
        return build_schematic_feature_collection(catalog.list_objects(), subject)
    except (TopologyCatalogError, TopologyError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Схема объектов временно недоступна",
        ) from error
