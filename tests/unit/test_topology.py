from decimal import Decimal

import pytest
from forpost_platform.security.identity import Role, SecuritySubject
from forpost_platform.topology.generator import (
    TopologyError,
    TopologyObject,
    build_schematic_feature_collection,
    pickets_to_metres,
)


def subject(role: Role, *, complexes: frozenset[str] = frozenset()) -> SecuritySubject:
    return SecuritySubject(
        user_id="dispatcher-1",
        username="Диспетчер",
        roles=frozenset({role}),
        allowed_complexes=complexes,
    )


OBJECTS = (
    TopologyObject(
        object_id="district-1",
        parent_id="external-root",
        object_kind="district",
        dispatcher_name="Район 1",
    ),
    TopologyObject(
        object_id="complex-1",
        parent_id="district-1",
        object_kind="controlHouse",
        dispatcher_name="Комплекс 1",
    ),
    TopologyObject(
        object_id="sensor-group-1",
        parent_id="complex-1",
        object_kind="guardObject",
        dispatcher_name="Объект охраны 1",
    ),
    TopologyObject(
        object_id="complex-2",
        parent_id="district-1",
        object_kind="controlHouse",
        dispatcher_name="Комплекс 2",
    ),
)


def test_pickets_are_converted_to_metres_exactly():
    assert pickets_to_metres(Decimal("88.5")) == Decimal("885.0")


def test_topology_is_deterministic_and_explicitly_schematic():
    dispatcher = subject(Role.CENTRAL_DISPATCHER)

    first = build_schematic_feature_collection(OBJECTS, dispatcher)
    reversed_input = build_schematic_feature_collection(tuple(reversed(OBJECTS)), dispatcher)

    assert first == reversed_input
    assert first["type"] == "FeatureCollection"
    assert all(feature["geometry"]["type"] == "MultiLineString" for feature in first["features"])
    assert all(
        feature["properties"]["geometrySource"] == "synthetic"
        and feature["properties"]["coordinateProvenance"] == "simulated"
        for feature in first["features"]
    )


def test_assigned_complex_includes_only_its_subtree():
    scoped = subject(Role.DISTRICT_DISPATCHER, complexes=frozenset({"complex-1"}))

    result = build_schematic_feature_collection(OBJECTS, scoped)

    assert {feature["properties"]["objectId"] for feature in result["features"]} == {
        "complex-1",
        "sensor-group-1",
    }


def test_cycle_is_rejected_instead_of_recursing_forever():
    cyclic = (
        TopologyObject("one", "two", "node", "Один"),
        TopologyObject("two", "one", "node", "Два"),
    )

    with pytest.raises(TopologyError, match="цикл"):
        build_schematic_feature_collection(cyclic, subject(Role.CENTRAL_DISPATCHER))
