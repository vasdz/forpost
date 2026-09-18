from fastapi import FastAPI, status
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from forpost_api.middleware.payload_guard import PayloadSizeLimitMiddleware
from forpost_api.middleware.rate_limit import limiter, rate_limit_exceeded_handler
from forpost_api.middleware.security_headers import SecurityHeadersMiddleware
from forpost_api.routes.availability import router as availability_router
from forpost_api.routes.predictions import router as predictions_router
from forpost_api.routes.v1.analytics import router as analytics_router
from forpost_api.routes.v1.demo_session import router as demo_session_router
from forpost_api.routes.v1.maintenance import router as maintenance_router
from forpost_api.routes.v1.risks import router as risks_router

app = FastAPI(
    title="Форпост API",
    description="Платформа прогнозирования рисков инженерной инфраструктуры",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Порядок регистрации обратный порядку выполнения: security-заголовки покрывают
# все ответы, rate limit отклоняет запрос до буферизации ограниченного тела.
app.add_middleware(PayloadSizeLimitMiddleware)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(predictions_router)
app.include_router(availability_router)
app.include_router(risks_router, prefix="/api/v1")
app.include_router(maintenance_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(demo_session_router, prefix="/api/v1")


@app.get("/health", status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
async def health() -> dict[str, str]:
    """Не маскирует неготовность защищённого контура положительным health-статусом."""

    return {
        "status": "not_ready",
        "system": "forpost",
        "message": "Сервис не готов к обработке защищённых запросов.",
    }
