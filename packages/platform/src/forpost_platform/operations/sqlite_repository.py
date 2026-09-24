"""Транзакционное SQLite-хранилище решений, черновиков и хеш-аудита."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from threading import RLock

from forpost_domain.incidents.entities import (
    IncidentDecision,
    PredictionDecisionRecord,
    ServiceRequestDraft,
)

GENESIS_HASH = "GENESIS_FORPOST_DEMO_OPERATIONS_V1"


class IdempotencyConflictError(ValueError):
    """Idempotency-Key уже использован для другого содержимого."""


class OperationsConflictError(ValueError):
    """Операция нарушает неизменяемую историю домена."""


class SqliteOperationsRepository:
    """Минимальное устойчивое demo-хранилище со строгими транзакциями."""

    def __init__(self, database_path: Path):
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def close(self) -> None:
        self._connection.close()

    def record_decision(
        self,
        decision: IncidentDecision,
        idempotency_key: str,
        idempotency_payload: object | None = None,
    ) -> IncidentDecision:
        fingerprint = _fingerprint(
            decision.model_dump(mode="json") if idempotency_payload is None else idempotency_payload
        )
        with self._lock, self._connection:
            known = self._connection.execute(
                "SELECT fingerprint, resource_id FROM idempotency_keys WHERE key = ?",
                (idempotency_key,),
            ).fetchone()
            if known is not None:
                if known["fingerprint"] != fingerprint:
                    raise IdempotencyConflictError("Idempotency-Key уже использован")
                return self._get_decision(known["resource_id"])

            if decision.corrects_decision_id is not None:
                original = self._connection.execute(
                    "SELECT incident_id FROM incident_decisions WHERE decision_id = ?",
                    (decision.corrects_decision_id,),
                ).fetchone()
                if original is None or original["incident_id"] != decision.incident_id:
                    raise OperationsConflictError("Исправляемое решение не найдено")

            payload = _canonical_json(decision.model_dump(mode="json"))
            self._connection.execute(
                """INSERT INTO incident_decisions
                   (decision_id, incident_id, created_at, payload_json)
                   VALUES (?, ?, ?, ?)""",
                (
                    decision.decision_id,
                    decision.incident_id,
                    decision.created_at.isoformat(),
                    payload,
                ),
            )
            self._connection.execute(
                "INSERT INTO idempotency_keys (key, fingerprint, resource_id) VALUES (?, ?, ?)",
                (idempotency_key, fingerprint, decision.decision_id),
            )
            self._append_audit(
                "INCIDENT_DECISION_RECORDED",
                decision.actor_id,
                decision.incident_id,
                {"decisionId": decision.decision_id, "status": decision.status.value},
                decision.created_at.isoformat(),
            )
        return decision

    def list_decisions(self, incident_id: str) -> list[IncidentDecision]:
        rows = self._connection.execute(
            "SELECT payload_json FROM incident_decisions WHERE incident_id = ? ORDER BY created_at, decision_id",
            (incident_id,),
        ).fetchall()
        return [IncidentDecision.model_validate_json(row["payload_json"]) for row in rows]

    def record_prediction_decision(
        self,
        *,
        prediction_id: str,
        decision: str,
        reason: str,
        actor_id: str,
        created_at: datetime,
    ) -> PredictionDecisionRecord:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """INSERT INTO prediction_decisions
                   (prediction_id, actor_id, created_at, decision, reason)
                   VALUES (?, ?, ?, ?, ?)""",
                (prediction_id, actor_id, created_at.isoformat(), decision, reason),
            )
            sequence = int(cursor.lastrowid)
            record = PredictionDecisionRecord(
                sequence=sequence,
                prediction_id=prediction_id,
                decision=decision,
                reason=reason,
                actor_id=actor_id,
                created_at=created_at,
            )
            self._append_audit(
                "PREDICTION_DECISION_RECORDED",
                actor_id,
                prediction_id,
                {"decision": decision, "predictionDecisionSequence": str(sequence)},
                created_at.isoformat(),
            )
        return record

    def latest_prediction_decision(
        self, prediction_id: str, actor_id: str
    ) -> PredictionDecisionRecord | None:
        row = self._connection.execute(
            """SELECT sequence, prediction_id, decision, reason, actor_id, created_at
               FROM prediction_decisions
               WHERE prediction_id = ? AND actor_id = ?
               ORDER BY sequence DESC LIMIT 1""",
            (prediction_id, actor_id),
        ).fetchone()
        if row is None:
            return None
        return PredictionDecisionRecord(
            sequence=row["sequence"],
            prediction_id=row["prediction_id"],
            decision=row["decision"],
            reason=row["reason"],
            actor_id=row["actor_id"],
            created_at=row["created_at"],
        )

    def create_draft(self, draft: ServiceRequestDraft) -> ServiceRequestDraft:
        payload = _canonical_json(draft.model_dump(mode="json"))
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO service_request_drafts
                   (draft_id, incident_id, category, created_at, payload_json)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    draft.draft_id,
                    draft.incident_id,
                    draft.category,
                    draft.created_at.isoformat(),
                    payload,
                ),
            )
            self._append_audit(
                "SERVICE_DRAFT_CREATED",
                draft.author_id,
                draft.draft_id,
                {"incidentId": draft.incident_id, "priority": draft.priority},
                draft.created_at.isoformat(),
            )
        return draft

    def create_prediction_draft(self, draft: ServiceRequestDraft) -> ServiceRequestDraft:
        """Идемпотентно создаёт один черновик для стабильного ID прогноза."""
        with self._lock:
            row = self._connection.execute(
                """SELECT payload_json FROM service_request_drafts
                   WHERE incident_id = ? AND category = 'prediction_follow_up'
                   ORDER BY created_at, draft_id LIMIT 1""",
                (draft.incident_id,),
            ).fetchone()
            if row is not None:
                return ServiceRequestDraft.model_validate_json(row["payload_json"])
            try:
                return self.create_draft(draft)
            except sqlite3.IntegrityError:
                row = self._connection.execute(
                    """SELECT payload_json FROM service_request_drafts
                       WHERE incident_id = ? AND category = 'prediction_follow_up'
                       ORDER BY created_at, draft_id LIMIT 1""",
                    (draft.incident_id,),
                ).fetchone()
                if row is None:
                    raise
                return ServiceRequestDraft.model_validate_json(row["payload_json"])

    def list_drafts(self) -> list[ServiceRequestDraft]:
        rows = self._connection.execute(
            "SELECT payload_json FROM service_request_drafts ORDER BY created_at, draft_id"
        ).fetchall()
        return [ServiceRequestDraft.model_validate_json(row["payload_json"]) for row in rows]

    def verify_audit_chain(self) -> bool:
        previous = GENESIS_HASH
        rows = self._connection.execute(
            """SELECT sequence, created_at, event_type, actor_id, resource_id,
                      details_json, previous_hash, record_hash
               FROM audit_log ORDER BY sequence"""
        ).fetchall()
        for row in rows:
            if row["previous_hash"] != previous:
                return False
            expected = _audit_hash(
                row["sequence"],
                row["created_at"],
                row["event_type"],
                row["actor_id"],
                row["resource_id"],
                row["details_json"],
                row["previous_hash"],
            )
            if hashlib.sha256(expected.encode("utf-8")).hexdigest() != row["record_hash"]:
                return False
            previous = row["record_hash"]
        return True

    def _get_decision(self, decision_id: str) -> IncidentDecision:
        row = self._connection.execute(
            "SELECT payload_json FROM incident_decisions WHERE decision_id = ?", (decision_id,)
        ).fetchone()
        if row is None:
            raise OperationsConflictError("Решение не найдено")
        return IncidentDecision.model_validate_json(row["payload_json"])

    def _append_audit(
        self,
        event_type: str,
        actor_id: str,
        resource_id: str,
        details: dict[str, str],
        created_at: str,
    ) -> None:
        tail = self._connection.execute(
            "SELECT sequence, record_hash FROM audit_log ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        sequence = 1 if tail is None else int(tail["sequence"]) + 1
        previous_hash = GENESIS_HASH if tail is None else str(tail["record_hash"])
        details_json = _canonical_json(details)
        record_hash = hashlib.sha256(
            _audit_hash(
                sequence,
                created_at,
                event_type,
                actor_id,
                resource_id,
                details_json,
                previous_hash,
            ).encode("utf-8")
        ).hexdigest()
        self._connection.execute(
            """INSERT INTO audit_log
               (sequence, created_at, event_type, actor_id, resource_id,
                details_json, previous_hash, record_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sequence,
                created_at,
                event_type,
                actor_id,
                resource_id,
                details_json,
                previous_hash,
                record_hash,
            ),
        )

    def _migrate(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS incident_decisions (
                decision_id TEXT PRIMARY KEY,
                incident_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_decisions_incident
                ON incident_decisions (incident_id, created_at);
            CREATE TABLE IF NOT EXISTS service_request_drafts (
                draft_id TEXT PRIMARY KEY,
                incident_id TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS prediction_decisions (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                prediction_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_prediction_decisions_latest
                ON prediction_decisions (prediction_id, actor_id, sequence DESC);
            CREATE TABLE IF NOT EXISTS idempotency_keys (
                key TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                resource_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                sequence INTEGER PRIMARY KEY,
                created_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                details_json TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                record_hash TEXT NOT NULL
            );
            INSERT OR IGNORE INTO schema_migrations (version) VALUES (1);
            """
        )
        with self._connection:
            columns = {
                row["name"]
                for row in self._connection.execute("PRAGMA table_info(service_request_drafts)")
            }
            if "category" not in columns:
                self._connection.execute(
                    "ALTER TABLE service_request_drafts ADD COLUMN category TEXT NOT NULL DEFAULT ''"
                )
            self._connection.execute(
                """UPDATE service_request_drafts
                   SET category = json_extract(payload_json, '$.category')
                   WHERE category = ''"""
            )
            self._connection.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS idx_prediction_draft_incident
                   ON service_request_drafts (incident_id)
                   WHERE category = 'prediction_follow_up'"""
            )


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _audit_hash(
    sequence: int,
    created_at: str,
    event_type: str,
    actor_id: str,
    resource_id: str,
    details_json: str,
    previous_hash: str,
) -> str:
    return _canonical_json(
        {
            "actorId": actor_id,
            "createdAt": created_at,
            "details": details_json,
            "eventType": event_type,
            "previousHash": previous_hash,
            "resourceId": resource_id,
            "sequence": sequence,
        }
    )
