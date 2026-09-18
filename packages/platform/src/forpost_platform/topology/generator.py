"""Детерминированная GeoJSON-схема подтверждённой иерархии объектов."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal

from forpost_platform.security.identity import SecuritySubject

MAX_TOPOLOGY_DEPTH = 256


class TopologyError(ValueError):
    """Иерархия объектов не может быть безопасно представлена схемой."""


@dataclass(frozen=True)
class TopologyObject:
    object_id: str
    parent_id: str | None
    object_kind: str
    dispatcher_name: str


def pickets_to_metres(pickets: Decimal) -> Decimal:
    """Переводит пикеты в метры по правилу постановщика: 1 пикет = 10 м."""
    return pickets * Decimal(10)


def build_schematic_feature_collection(
    objects: tuple[TopologyObject, ...], subject: SecuritySubject
) -> dict[str, object]:
    """Строит условную схему и отсекает узлы вне серверной области субъекта."""
    objects_by_id = _validate_objects(objects)
    children = _build_children(objects_by_id)
    _validate_acyclic(objects_by_id, children)
    visible_ids = _visible_object_ids(objects_by_id, children, subject)
    positions = _layout(objects_by_id, children, visible_ids)

    features: list[dict[str, object]] = []
    for object_id in sorted(visible_ids):
        item = objects_by_id[object_id]
        x, y = positions[object_id]
        visible_parent = item.parent_id if item.parent_id in visible_ids else None
        if visible_parent is None:
            coordinates = [[[x, y], [round(x + 0.4, 4), y]]]
        else:
            parent_x, parent_y = positions[visible_parent]
            coordinates = [[[parent_x, parent_y], [x, y]]]
        features.append(
            {
                "type": "Feature",
                "id": object_id,
                "geometry": {"type": "MultiLineString", "coordinates": coordinates},
                "properties": {
                    "objectId": object_id,
                    "parentId": visible_parent,
                    "objectKind": item.object_kind,
                    "dispatcherName": item.dispatcher_name,
                    "geometrySource": "synthetic",
                    "provenance": "derived",
                    "coordinateProvenance": "simulated",
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "title": "Схема объектов",
            "geometrySource": "synthetic",
            "coordinateProvenance": "simulated",
        },
    }


def _validate_objects(objects: tuple[TopologyObject, ...]) -> dict[str, TopologyObject]:
    result: dict[str, TopologyObject] = {}
    for item in objects:
        if (
            not item.object_id
            or len(item.object_id) > 256
            or not item.object_kind
            or len(item.object_kind) > 128
            or not item.dispatcher_name
            or len(item.dispatcher_name) > 512
            or (item.parent_id is not None and len(item.parent_id) > 256)
        ):
            raise TopologyError("Некорректный объект топологии")
        if item.object_id in result:
            raise TopologyError("Обнаружен дубликат объекта топологии")
        if item.parent_id == item.object_id:
            raise TopologyError("Обнаружен цикл в иерархии объектов")
        result[item.object_id] = item
    return result


def _build_children(
    objects_by_id: dict[str, TopologyObject],
) -> dict[str, tuple[str, ...]]:
    mutable: dict[str, list[str]] = {object_id: [] for object_id in objects_by_id}
    for item in objects_by_id.values():
        if item.parent_id in objects_by_id:
            mutable[item.parent_id].append(item.object_id)
    return {key: tuple(sorted(value)) for key, value in mutable.items()}


def _validate_acyclic(
    objects_by_id: dict[str, TopologyObject], children: dict[str, tuple[str, ...]]
) -> None:
    indegree = {
        object_id: int(item.parent_id in objects_by_id) for object_id, item in objects_by_id.items()
    }
    queue = deque(sorted(key for key, value in indegree.items() if value == 0))
    visited = 0
    depth = dict.fromkeys(queue, 0)
    while queue:
        current = queue.popleft()
        visited += 1
        for child in children[current]:
            depth[child] = depth[current] + 1
            if depth[child] > MAX_TOPOLOGY_DEPTH:
                raise TopologyError("Иерархия объектов превышает допустимую глубину")
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if visited != len(objects_by_id):
        raise TopologyError("Обнаружен цикл в иерархии объектов")


def _visible_object_ids(
    objects_by_id: dict[str, TopologyObject],
    children: dict[str, tuple[str, ...]],
    subject: SecuritySubject,
) -> set[str]:
    if subject.can_access_resource(district=None, complex_id=None):
        return set(objects_by_id)
    seeds = (subject.allowed_complexes | subject.allowed_districts) & objects_by_id.keys()
    visible: set[str] = set()
    queue = deque(sorted(seeds))
    while queue:
        current = queue.popleft()
        if current in visible:
            continue
        visible.add(current)
        queue.extend(children[current])
    return visible


def _layout(
    objects_by_id: dict[str, TopologyObject],
    children: dict[str, tuple[str, ...]],
    visible_ids: set[str],
) -> dict[str, tuple[float, float]]:
    roots = sorted(
        object_id
        for object_id in visible_ids
        if objects_by_id[object_id].parent_id not in visible_ids
    )
    positions: dict[str, tuple[float, float]] = {}
    next_leaf = 0

    def position(object_id: str, depth: int) -> float:
        nonlocal next_leaf
        visible_children = [child for child in children[object_id] if child in visible_ids]
        if visible_children:
            child_x = [position(child, depth + 1) for child in visible_children]
            x = sum(child_x) / len(child_x)
        else:
            x = float(next_leaf)
            next_leaf += 1
        positions[object_id] = (round(x, 4), float(-depth))
        return x

    for root in roots:
        position(root, 0)
    return positions
