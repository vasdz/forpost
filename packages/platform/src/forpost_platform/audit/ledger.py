import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel


class AuditSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ALERT = "ALERT"  # Несанкционированный доступ, попытка вторжения
    CRITICAL = "CRITICAL"  # Аномалия оборудования, инцидент КИИ


class AuditRecord(BaseModel):
    index: int
    timestamp: str
    severity: AuditSeverity
    event_type: str
    user_id: str
    resource_id: str
    details: dict
    prev_hash: str
    record_hash: str

    def to_cef(self) -> str:
        """Форматирование в Common Event Format для SIEM и ГосСОПКА."""
        return (
            f"CEF:0|Forpost|CoreSecurity|1.0|{self.event_type}|{self.event_type}|"
            f"{self.severity.value}|src={self.details.get('ip', 'unknown')} "
            f"suser={self.user_id} cs1={self.resource_id} cs2={self.record_hash}"
        )


class ImmutableAuditLedger:
    """Внутрипроцессный криптографический реестр без WORM-гарантий.

    Реализация хранит цепочку только в памяти и не является неизменяемым
    production-хранилищем аудита.
    """

    def __init__(self):
        self._chain: list[AuditRecord] = []
        self._last_hash = "GENESIS_BLOCK_FORPOST_KII_2026"

    def append(
        self,
        event_type: str,
        severity: AuditSeverity,
        user_id: str,
        resource_id: str,
        details: dict,
    ) -> AuditRecord:
        timestamp = datetime.now(UTC).isoformat()
        index = len(self._chain)

        # Нормализация данных для детерминированного хеша
        payload = json.dumps(
            {
                "index": index,
                "timestamp": timestamp,
                "severity": severity.value,
                "event_type": event_type,
                "user_id": user_id,
                "resource_id": resource_id,
                "details": details,
                "prev_hash": self._last_hash,
            },
            sort_keys=True,
        )

        current_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        record = AuditRecord(
            index=index,
            timestamp=timestamp,
            severity=severity,
            event_type=event_type,
            user_id=user_id,
            resource_id=resource_id,
            details=details,
            prev_hash=self._last_hash,
            record_hash=current_hash,
        )

        self._chain.append(record)
        self._last_hash = current_hash
        return record

    def verify_integrity(self) -> bool:
        """Проверяет записи и совпадение хвоста с сохранённой головой цепочки.

        Проверка обнаруживает локальное усечение, пока ``_last_hash`` хранится
        отдельно от списка записей. Для доказательства против одновременной
        подмены списка и головы production-хранилище обязано закреплять голову
        во внешнем WORM-хранилище или доверенной системе аудита.
        """
        expected_prev = "GENESIS_BLOCK_FORPOST_KII_2026"
        for rec in self._chain:
            if rec.prev_hash != expected_prev:
                return False
            payload = json.dumps(
                {
                    "index": rec.index,
                    "timestamp": rec.timestamp,
                    "severity": rec.severity.value,
                    "event_type": rec.event_type,
                    "user_id": rec.user_id,
                    "resource_id": rec.resource_id,
                    "details": rec.details,
                    "prev_hash": rec.prev_hash,
                },
                sort_keys=True,
            )
            if hashlib.sha256(payload.encode("utf-8")).hexdigest() != rec.record_hash:
                return False
            expected_prev = rec.record_hash
        return expected_prev == self._last_hash


# Глобальный инстанс реестра аудита
audit_ledger = ImmutableAuditLedger()
