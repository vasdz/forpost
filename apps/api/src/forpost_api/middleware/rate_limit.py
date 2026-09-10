from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# Лимитер по IP клиента
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Ответ при превышении квот запросов (предотвращение атак отказа в обслуживании)."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "Слишком много запросов",
            "detail": "Превышен допустимый лимит обращений к узлу мониторинга КИИ.",
        },
    )
