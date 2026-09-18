import json
import logging

import pytest
from forpost_platform.logging.formatter import MaskingJsonFormatter


def _record(message: str) -> logging.LogRecord:
    return logging.LogRecord("forpost.test", logging.INFO, __file__, 10, message, (), None)


def test_masking_formatter_formats_plain_message_without_regex_crash():
    """Ловит некорректную regex-подстановку даже для обычного сообщения."""
    payload = json.loads(MaskingJsonFormatter().format(_record("Штатное событие")))

    assert payload["message"] == "Штатное событие"


@pytest.mark.parametrize(
    "message",
    [
        "Authorization: Bearer top.secret-1",
        "token=top-secret-2",
        "Bearer top.secret-3",
    ],
)
def test_masking_formatter_removes_the_complete_credential(message):
    """Ловит утечку хвоста Bearer-токена после частичного маскирования."""
    sanitized = json.loads(MaskingJsonFormatter().format(_record(message)))["message"]

    assert "top.secret" not in sanitized
    assert "top-secret" not in sanitized
    assert "***REDACTED***" in sanitized
