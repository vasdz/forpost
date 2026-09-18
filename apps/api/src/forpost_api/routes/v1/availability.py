"""Единый контракт для функций, ожидающих ещё не подключённые источники."""

from typing import NoReturn

from fastapi import HTTPException, status

REAL_DATA_INTEGRATION_UNAVAILABLE_CODE = "REAL_DATA_INTEGRATION_UNAVAILABLE"
REAL_DATA_INTEGRATION_UNAVAILABLE_MESSAGE = (
    "Интеграция с реальными данными и обученной моделью пока недоступна."
)


def unavailable_data_detail() -> dict[str, str]:
    """Возвращает безопасную для клиента причину недоступности без деталей инфраструктуры."""

    return {
        "code": REAL_DATA_INTEGRATION_UNAVAILABLE_CODE,
        "message": REAL_DATA_INTEGRATION_UNAVAILABLE_MESSAGE,
    }


def raise_real_data_integration_unavailable() -> NoReturn:
    """Завершает запрос до генерации прогнозов, отчётов или заявок-заглушек."""

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=unavailable_data_detail(),
    )
