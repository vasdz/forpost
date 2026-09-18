from pathlib import Path

from fastapi.testclient import TestClient
from forpost_api.dependencies import get_current_human_subject
from forpost_api.main import app
from forpost_api.routes.v1.incidents import (
    IncidentScope,
    get_incident_catalog,
    get_operations_repository,
)
from forpost_platform.operations.sqlite_repository import SqliteOperationsRepository
from forpost_platform.security.identity import Role, SecuritySubject

INCIDENT_ID = "a" * 64


class FixedIncidentCatalog:
    def get(self, incident_id: str) -> IncidentScope:
        return IncidentScope(
            incident_id=incident_id,
            channel_id="channel-20",
            complex_id="complex-1",
        )


def subject(role: Role, *, allowed_complexes: frozenset[str] = frozenset()) -> SecuritySubject:
    return SecuritySubject(
        user_id=f"test-{role.value}",
        username="Тестовый пользователь",
        roles=frozenset({role}),
        allowed_complexes=allowed_complexes,
    )


def configure(
    repository: SqliteOperationsRepository,
    role: Role,
    *,
    allowed_complexes: frozenset[str] = frozenset(),
) -> None:
    app.dependency_overrides[get_operations_repository] = lambda: repository
    app.dependency_overrides[get_current_human_subject] = lambda: subject(
        role, allowed_complexes=allowed_complexes
    )
    app.dependency_overrides[get_incident_catalog] = FixedIncidentCatalog


def teardown(repository: SqliteOperationsRepository) -> None:
    app.dependency_overrides.clear()
    repository.close()


def test_central_dispatcher_records_idempotent_decision(tmp_path: Path):
    """Повтор POST с тем же ключом возвращает одну сохранённую запись."""
    repository = SqliteOperationsRepository(tmp_path / "operations.sqlite3")
    configure(repository, Role.CENTRAL_DISPATCHER)
    headers = {"Idempotency-Key": "decision-command-1"}
    payload = {"status": "crew_dispatch", "reason": "Назначен выезд бригады"}
    try:
        with TestClient(app) as client:
            first = client.post(
                f"/api/v1/incidents/{INCIDENT_ID}/decisions", headers=headers, json=payload
            )
            repeated = client.post(
                f"/api/v1/incidents/{INCIDENT_ID}/decisions", headers=headers, json=payload
            )
        stored_count = len(repository.list_decisions(INCIDENT_ID))
    finally:
        teardown(repository)

    assert first.status_code == 201
    assert repeated.status_code == 201
    assert repeated.json() == first.json()
    assert stored_count == 1


def test_admin_cannot_record_business_decision(tmp_path: Path):
    """Системная роль не должна превращаться в диспетчерскую через маршрут."""
    repository = SqliteOperationsRepository(tmp_path / "operations.sqlite3")
    configure(repository, Role.SYSTEM_ADMIN)
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/incidents/{INCIDENT_ID}/decisions",
                headers={"Idempotency-Key": "decision-command-1"},
                json={"status": "false_alarm", "reason": "Проверка не подтвердила тревогу"},
            )
        stored = repository.list_decisions(INCIDENT_ID)
    finally:
        teardown(repository)

    assert response.status_code == 403
    assert stored == []


def test_district_dispatcher_cannot_decide_foreign_incident(tmp_path: Path):
    """Роль района не заменяет серверную проверку области комплекса."""
    repository = SqliteOperationsRepository(tmp_path / "operations.sqlite3")
    configure(
        repository,
        Role.DISTRICT_DISPATCHER,
        allowed_complexes=frozenset({"complex-2"}),
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/incidents/{INCIDENT_ID}/decisions",
                headers={"Idempotency-Key": "foreign-decision-1"},
                json={"status": "in_review", "reason": "Начата проверка тревоги"},
            )
        stored = repository.list_decisions(INCIDENT_ID)
    finally:
        teardown(repository)

    assert response.status_code == 403
    assert stored == []


def test_district_dispatcher_decides_assigned_incident(tmp_path: Path):
    repository = SqliteOperationsRepository(tmp_path / "operations.sqlite3")
    configure(
        repository,
        Role.DISTRICT_DISPATCHER,
        allowed_complexes=frozenset({"complex-1"}),
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/incidents/{INCIDENT_ID}/decisions",
                headers={"Idempotency-Key": "assigned-decision-1"},
                json={"status": "in_review", "reason": "Начата проверка тревоги"},
            )
    finally:
        teardown(repository)

    assert response.status_code == 201


def test_dispatcher_creates_persistent_simulated_draft(tmp_path: Path):
    """Demo-черновик маркируется и сохраняется без ложной отправки во внешнюю ИС."""
    repository = SqliteOperationsRepository(tmp_path / "operations.sqlite3")
    configure(repository, Role.CENTRAL_DISPATCHER)
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/v1/service-request-drafts",
                json={
                    "incidentId": INCIDENT_ID,
                    "targetId": "channel-20",
                    "category": "sensor_check",
                    "priority": "high",
                    "recommendedAction": "Проверить канал и линию связи",
                    "dueAt": "2026-09-19T12:00:00Z",
                },
            )
            listed = client.get("/api/v1/service-request-drafts")
    finally:
        teardown(repository)

    assert created.status_code == 201
    assert created.json()["provenance"] == "simulated"
    assert listed.status_code == 200
    assert listed.json() == [created.json()]


def test_draft_target_must_belong_to_incident(tmp_path: Path):
    repository = SqliteOperationsRepository(tmp_path / "operations.sqlite3")
    configure(repository, Role.CENTRAL_DISPATCHER)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/service-request-drafts",
                json={
                    "incidentId": INCIDENT_ID,
                    "targetId": "unrelated-target",
                    "category": "sensor_check",
                    "priority": "high",
                    "recommendedAction": "Проверить канал и линию связи",
                    "dueAt": "2026-09-19T12:00:00Z",
                },
            )
    finally:
        teardown(repository)

    assert response.status_code == 422
