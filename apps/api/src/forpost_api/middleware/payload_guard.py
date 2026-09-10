from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

MAX_PAYLOAD_SIZE = 10 * 1024 * 1024  # Лимит 10 МБ на один запрос


class PayloadSizeLimitMiddleware(BaseHTTPMiddleware):
    """Блокировка аномально больших запросов до передачи их в парсер."""

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_PAYLOAD_SIZE:
            return JSONResponse(
                status_code=413,
                content={"error": "Полезная нагрузка превышает допустимый размер (макс. 10МБ)"},
            )
        return await call_next(request)
