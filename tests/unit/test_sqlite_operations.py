from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest
from forpost_domain.incidents.entities import (
    IncidentDecision,
    IncidentStatus,
    PredictionDecisionRecord,
    ServiceRequestDraft,
)
from forpost_platform.operations.sqlite_repository import (
    IdempotencyConflictError,
    SqliteOperationsRepository,
)

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


def decision(
    *, reason: str = "Проверка назначена", decision_id: str = "decision-1"
) -> IncidentDecision:
    return IncidentDecision(
        decision_id=decision_id,
        incident_id="a" * 64,
        status=IncidentStatus.CREW_DISPATCH,
        reason=reason,
        actor_id="dispatcher-1",
        created_at=NOW,
    )


def test_repository_persists_idempotent_decision_after_reopen(tmp_path: Path):
    """Повтор команды после рестарта не должен создать второе решение."""
    path = tmp_path / "operations.sqlite3"
    first = SqliteOperationsRepository(path)
    stored = first.record_decision(decision(), "key-1")
    first.close()

    reopened = SqliteOperationsRepository(path)
    repeated = reopened.record_decision(decision(), "key-1")

    assert repeated == stored
    assert reopened.list_decisions("a" * 64) == [stored]
    assert reopened.verify_audit_chain()


def test_repository_constructor_commits_migrations(tmp_path: Path):
    repository = SqliteOperationsRepository(tmp_path / "operations.sqlite3")

    assert not repository._connection.in_transaction  # noqa: SLF001


def test_repository_rejects_idempotency_key_reuse_with_other_payload(tmp_path: Path):
    """Один ключ не должен подтверждать два разных бизнес-решения."""
    repository = SqliteOperationsRepository(tmp_path / "operations.sqlite3")
    repository.record_decision(decision(), "key-1")

    with pytest.raises(IdempotencyConflictError):
        repository.record_decision(decision(reason="Другая причина"), "key-1")


def test_correction_appends_history_instead_of_overwriting(tmp_path: Path):
    """Исправление обязано оставить исходное решение доступным для аудита."""
    repository = SqliteOperationsRepository(tmp_path / "operations.sqlite3")
    original = repository.record_decision(decision(), "key-1")
    correction = IncidentDecision(
        decision_id="decision-2",
        incident_id=original.incident_id,
        status=IncidentStatus.FALSE_ALARM,
        reason="Результат выезда уточнён",
        actor_id="dispatcher-1",
        created_at=NOW,
        corrects_decision_id=original.decision_id,
    )

    repository.record_decision(correction, "key-2")

    assert repository.list_decisions(original.incident_id) == [original, correction]
    assert repository.verify_audit_chain()


def test_repository_persists_simulated_service_draft(tmp_path: Path):
    """Черновик demo help-desk должен пережить перезапуск и сохранить provenance."""
    path = tmp_path / "operations.sqlite3"
    repository = SqliteOperationsRepository(path)
    draft = ServiceRequestDraft(
        draft_id="draft-1",
        incident_id="a" * 64,
        target_id="channel-20",
        category="sensor_check",
        priority="high",
        recommended_action="Проверить канал и линию связи",
        due_at=NOW,
        author_id="dispatcher-1",
        created_at=NOW,
    )

    stored = repository.create_draft(draft)
    repository.close()
    reopened = SqliteOperationsRepository(path)

    assert reopened.list_drafts() == [stored]
    assert stored.provenance == "simulated"
    assert reopened.verify_audit_chain()


def test_repository_persists_latest_prediction_decision_after_reopen(tmp_path: Path):
    path = tmp_path / "operations.sqlite3"
    repository = SqliteOperationsRepository(path)
    confirmed = repository.record_prediction_decision(
        prediction_id="prediction-1",
        decision="confirmed",
        reason="Назначена проверка объекта",
        actor_id="dispatcher-1",
        created_at=NOW,
    )
    rejected = repository.record_prediction_decision(
        prediction_id="prediction-1",
        decision="rejected",
        reason="Проверка не подтвердила риск",
        actor_id="dispatcher-1",
        created_at=NOW,
    )
    repository.close()

    reopened = SqliteOperationsRepository(path)

    assert isinstance(confirmed, PredictionDecisionRecord)
    assert reopened.latest_prediction_decision("prediction-1", "dispatcher-1") == rejected


def test_prediction_draft_is_idempotent_by_prediction_incident(tmp_path: Path):
    repository = SqliteOperationsRepository(tmp_path / "operations.sqlite3")
    draft = ServiceRequestDraft(
        draft_id="draft-1",
        incident_id="b" * 64,
        target_id="channel-20",
        category="prediction_follow_up",
        priority="high",
        recommended_action="Проверить канал и линию связи",
        due_at=NOW,
        author_id="dispatcher-1",
        created_at=NOW,
    )
    duplicate = draft.model_copy(update={"draft_id": "draft-2"})

    assert repository.create_prediction_draft(draft) == draft
    assert repository.create_prediction_draft(duplicate) == draft
    assert repository.list_drafts() == [draft]


def test_audit_integrity_detects_persisted_record_tampering(tmp_path: Path):
    """Изменение сохранённого события должно разорвать проверяемую хеш-цепочку."""
    repository = SqliteOperationsRepository(tmp_path / "operations.sqlite3")
    repository.record_decision(decision(), "key-1")

    repository._connection.execute(  # noqa: SLF001 -- намеренная проверка tamper detection.
        "UPDATE audit_log SET details_json = ? WHERE sequence = 1", ('{"tampered":true}',)
    )
    repository._connection.commit()  # noqa: SLF001 -- намеренная проверка tamper detection.

    assert not repository.verify_audit_chain()


def test_twenty_parallel_writers_are_serialized_without_lost_decisions(tmp_path: Path):
    """SQLite demo-контур обязан выдержать заявленную параллельность записи."""
    path = tmp_path / "operations.sqlite3"
    bootstrap = SqliteOperationsRepository(path)
    bootstrap.close()

    def write(index: int) -> None:
        repository = SqliteOperationsRepository(path)
        try:
            repository.record_decision(
                decision(decision_id=f"decision-{index}"), f"parallel-key-{index}"
            )
        finally:
            repository.close()

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(write, range(20)))

    repository = SqliteOperationsRepository(path)
    assert len(repository.list_decisions("a" * 64)) == 20
    assert repository.verify_audit_chain()
