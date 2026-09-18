from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_PAYLOAD_SIZE = 10 * 1024 * 1024  # Лимит 10 МБ на один запрос
INVALID_CONTENT_LENGTH_MESSAGE = "Некорректный заголовок Content-Length"
PAYLOAD_TOO_LARGE_MESSAGE = "Полезная нагрузка превышает допустимый размер (макс. 10МБ)"


def _declared_content_length(scope: Scope) -> int | None:
    """Возвращает единственную корректную длину тела или отклоняет неоднозначный заголовок."""

    values = [value for name, value in scope["headers"] if name.lower() == b"content-length"]
    if not values:
        return None
    if len(values) != 1:
        raise ValueError

    try:
        value = values[0].decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError from exc

    if not value.isdecimal():
        raise ValueError
    return int(value)


async def _send_error(
    scope: Scope, receive: Receive, send: Send, status_code: int, message: str
) -> None:
    response = JSONResponse(status_code=status_code, content={"error": message})
    await response(scope, receive, send)


async def _read_bounded_body(receive: Receive, max_payload_size: int) -> bytes | None:
    """Считывает конечное HTTP-тело до обработчика, не позволяя начать частичный ответ."""

    chunks: list[bytes] = []
    received_size = 0
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return None
        if message["type"] != "http.request":
            continue

        body = message.get("body", b"")
        received_size += len(body)
        if received_size > max_payload_size:
            raise ValueError
        chunks.append(body)
        if not message.get("more_body", False):
            return b"".join(chunks)


class PayloadSizeLimitMiddleware:
    """Ограничивает заявленный и фактически полученный размер тела ASGI-запроса."""

    def __init__(self, app: ASGIApp, max_payload_size: int = MAX_PAYLOAD_SIZE) -> None:
        self.app = app
        self.max_payload_size = max_payload_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            content_length = _declared_content_length(scope)
        except ValueError:
            await _send_error(scope, receive, send, 400, INVALID_CONTENT_LENGTH_MESSAGE)
            return

        if content_length is not None and content_length > self.max_payload_size:
            await _send_error(scope, receive, send, 413, PAYLOAD_TOO_LARGE_MESSAGE)
            return

        try:
            body = await _read_bounded_body(receive, self.max_payload_size)
        except ValueError:
            await _send_error(scope, receive, send, 413, PAYLOAD_TOO_LARGE_MESSAGE)
            return

        if body is None:
            return

        body_sent = False

        async def buffered_receive() -> Message:
            nonlocal body_sent
            if body_sent:
                return {"type": "http.disconnect"}
            body_sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, buffered_receive, send)
