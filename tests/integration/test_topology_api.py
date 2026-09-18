from fastapi.testclient import TestClient
from forpost_api.dependencies import get_current_subject
from forpost_api.main import app
from forpost_api.routes.v1.topology import get_topology_catalog
from forpost_platform.security.identity import Role, SecuritySubject
from forpost_platform.topology.generator import TopologyObject


class FixedTopologyCatalog:
    def list_objects(self) -> tuple[TopologyObject, ...]:
        return (
            TopologyObject("complex-1", None, "controlHouse", "Комплекс 1"),
            TopologyObject("complex-2", None, "controlHouse", "Комплекс 2"),
        )


def subject(role: Role, *, complexes: frozenset[str] = frozenset()) -> SecuritySubject:
    return SecuritySubject(
        user_id=f"test-{role.value}",
        username="Тестовый пользователь",
        roles=frozenset({role}),
        allowed_complexes=complexes,
    )


def configure(current_subject: SecuritySubject) -> None:
    app.dependency_overrides[get_current_subject] = lambda: current_subject
    app.dependency_overrides[get_topology_catalog] = FixedTopologyCatalog


def test_topology_api_filters_district_scope():
    configure(subject(Role.DISTRICT_DISPATCHER, complexes=frozenset({"complex-1"})))
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/topology")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [feature["properties"]["objectId"] for feature in response.json()["features"]] == [
        "complex-1"
    ]


def test_admin_cannot_read_business_topology():
    configure(subject(Role.SYSTEM_ADMIN))
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/topology")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
