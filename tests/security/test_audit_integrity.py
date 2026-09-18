from forpost_platform.audit.ledger import AuditSeverity, ImmutableAuditLedger


def test_audit_ledger_detects_tampering():
    """Проверка математической целостности журнала событий безопасности."""
    ledger = ImmutableAuditLedger()

    ledger.append("USER_LOGIN", AuditSeverity.INFO, "disp-01", "/login", {"ip": "10.0.0.1"})
    ledger.append(
        "ALARM_CONFIRMED", AuditSeverity.WARNING, "disp-01", "sensor-99", {"code": "FIRE"}
    )

    assert ledger.verify_integrity() is True, "Журнал должен быть валиден при штатной записи"

    # Имитация несанкционированной правки в базе данных злоумышленником
    ledger._chain[1].details["code"] = "FALSE_ALARM"

    assert ledger.verify_integrity() is False, "Любая модификация записи обязана ломать хеш-цепочку"


def test_audit_ledger_detects_tail_truncation_when_head_is_retained():
    """Ловит удаление последней записи без изменения сохранённой головы цепочки."""
    ledger = ImmutableAuditLedger()
    ledger.append("USER_LOGIN", AuditSeverity.INFO, "disp-01", "/login", {})
    ledger.append("ALARM_CONFIRMED", AuditSeverity.WARNING, "disp-01", "sensor-99", {})

    ledger._chain.pop()

    assert ledger.verify_integrity() is False
