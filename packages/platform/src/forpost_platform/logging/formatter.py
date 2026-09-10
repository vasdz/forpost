import json
import logging
import re
from datetime import datetime, timezone


class MaskingJsonFormatter(logging.Formatter):
    """Форматирует логи в JSON и вырезает конфиденциальные данные (КИИ / 152-ФЗ)."""

    SENSITIVE_PATTERNS = [
        re.compile(
            r"(password|token|secret|authorization|bearer)\s*[:=]\s*['\"]?([^'\"\s]+)",
            re.IGNORECASE,
        ),
        re.compile(r"Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*", re.IGNORECASE),
    ]

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": self._sanitize(record.getMessage()),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Проброс атрибутов аудита (request_id, client_ip), если они переданы
        if hasattr(record, "request_id"):
            log_obj["request_id"] = record.request_id
        if hasattr(record, "client_ip"):
            log_obj["client_ip"] = record.client_ip

        return json.dumps(log_obj, ensure_ascii=False)

    def _sanitize(self, message: str) -> str:
        # Защита от Log Injection (замена символов новой строки)
        sanitized = message.replace("\r", " ").replace("\n", " ")
        for pattern in self.SENSITIVE_PATTERNS:
            sanitized = pattern.sub(r"\1=***REDACTED***", sanitized)
        return sanitized
