"""Регрессии для безопасного fail-closed контура FastAPI."""

# ruff: noqa: S101

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from forpost_api.dependencies import get_current_subject, require_permission
from forpost_api.main import app
from forpost_api.middleware.payload_guard import MAX_PAYLOAD_SIZE, PayloadSizeLimitMiddleware
from forpost_api.middleware.rate_limit import limiter
from forpost_platform.security.identity import Permission, Role, SecuritySubject
from slowapi.middleware import SlowAPIMiddleware

IDENTITY_UNAVAILABLE = {
    "detail": {
        "code": "IDENTITY_PROVIDER_UNAVAILABLE",
        "message": "Проверенный поставщик идентификации пока недоступен.",
    }
}
UNAUTHENTICATED = {
    "detail": {
        "code": "UNAUTHENTICATED",
        "message": "Для доступа требуется Bearer-токен.",
    }
}
ApprovalSubject = Annotated[
    SecuritySubject,
    Depends(require_permission(Permission.APPROVE_SERVICE_ORDER)),
]
AuditSubject = Annotated[
    SecuritySubject,
    Depends(require_permission(Permission.AUDIT_READ)),
]


@pytest.mark.parametrize(
    ("method", "path", "request_kwargs", "forged_headers"),
    [
        ("get", "/api/v1/risks", {}, {"x-role": "chief_engineer"}),
        (
            "get",
            "/api/v1/risks/audit/verify",
            {},
            {"x-role": "auditor", "x-user-id": "forged-auditor"},
        ),
        (
            "post",
            "/api/v1/maintenance/generate-from-prediction",
            {"json": {"risk_prediction_ids": [], "auto_approve": True}},
            {"x-role": "chief_engineer", "x-districts": "rek-1,rek-2"},
        ),
        (
            "patch",
            "/api/v1/maintenance/not-a-real-order/status?new_status=approved",
            {},
            {"x-role": "chief_engineer"},
        ),
        ("get", "/api/v1/analytics/kpi", {}, {"x-role": "admin"}),
        (
            "post",
            "/api/v1/analytics/reports/operational",
            {},
            {"x-role": "chief_engineer"},
        ),
        ("get", "/api/v1/analytics/export", {}, {"x-role": "admin"}),
    ],
)
def test_forged_identity_headers_never_unlock_protected_operations(
    method: str,
    path: str,
    request_kwargs: dict[str, Any],
    forged_headers: dict[str, str],
) -> None:
    """Поддельные заголовки не должны заменять отсутствующую аутентификацию."""

    with TestClient(app) as client:
        response = getattr(client, method)(path, headers=forged_headers, **request_kwargs)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == UNAUTHENTICATED


@pytest.mark.parametrize("authorization", ["Basic user:password", "Bearer", "Bearer   "])
def test_malformed_authorization_is_rejected_as_unauthenticated(authorization: str) -> None:
    """Неверная схема не должна попадать в контур провайдера идентичности."""

    with TestClient(app) as client:
        response = client.get("/api/v1/risks", headers={"authorization": authorization})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == UNAUTHENTICATED


def test_unverified_bearer_does_not_unlock_api_when_identity_provider_is_unavailable() -> None:
    """Bearer без доверенного провайдера не превращается в роль или бизнес-ответ."""

    with TestClient(app) as client:
        response = client.get("/api/v1/risks", headers={"authorization": "Bearer opaque-token"})

    assert response.status_code == 503
    assert response.json() == IDENTITY_UNAVAILABLE


def test_configured_local_service_token_unlocks_dispatcher_read_only_api(monkeypatch) -> None:
    """BFF получает минимальные права только по серверному секрету достаточной длины."""

    token = "x" * 40
    monkeypatch.setenv("FORPOST_API_SERVICE_TOKEN", token)

    with TestClient(app) as client:
        response = client.get(
            "/api/availability",
            headers={"authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200


def test_wrong_local_service_token_is_rejected(monkeypatch) -> None:
    """Наличие настроенного BFF-секрета не превращает любой Bearer в доверенный."""

    monkeypatch.setenv(
        "FORPOST_API_SERVICE_TOKEN",
        "x" * 40,
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/availability",
            headers={"authorization": f"Bearer {'y' * 40}"},
        )

    assert response.status_code == 401
    assert response.json() == UNAUTHENTICATED


def test_local_service_token_cannot_record_dispatcher_decision(monkeypatch) -> None:
    """Сервисный BFF-токен не должен подменять личность человека в журнале решений."""

    token = "x" * 40
    monkeypatch.setenv("FORPOST_API_SERVICE_TOKEN", token)

    with TestClient(app) as client:
        response = client.post(
            "/api/predictions/prediction-001/decisions",
            headers={"authorization": f"Bearer {token}"},
            json={"decision": "confirmed", "reason": "Проверка назначена."},
        )

    assert response.status_code == 503
    assert response.json() == IDENTITY_UNAVAILABLE


def test_root_health_reports_not_ready_instead_of_a_healthy_protected_service() -> None:
    """Ответ 200/ok скроет неготовность контура от оркестратора и оператора."""

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "system": "forpost",
        "message": "Сервис не готов к обработке защищённых запросов.",
    }


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_api_schema_endpoints_are_not_exposed_while_identity_is_unavailable(path: str) -> None:
    """Открытая схема раскрыла бы структуру защищённого контура до аутентификации."""

    with TestClient(app) as client:
        response = client.get(path)

    assert response.status_code == 404


def test_security_headers_cover_fail_closed_api_response() -> None:
    """Отсутствующие заголовки на ошибке оставят клиент без защиты именно в ошибочном сценарии."""

    with TestClient(app) as client:
        response = client.get("/api/v1/risks")

    assert response.headers["content-security-policy"] == (
        "default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none';"
    )
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate, private"


def test_registered_rate_limiter_returns_project_handler_after_global_quota() -> None:
    """Если limiter не включён в ASGI-цепочку, 121-й запрос останется неконтролируемым."""

    limiter.reset()
    try:
        with TestClient(app) as client:
            for _ in range(120):
                response = client.get("/health")
                assert response.status_code == 503
            response = client.get("/health")
    finally:
        limiter.reset()

    assert response.status_code == 429
    assert response.json() == {
        "error": "Слишком много запросов",
        "detail": "Превышен допустимый лимит обращений к узлу мониторинга КИИ.",
    }


def test_rate_limiter_runs_before_payload_body_is_buffered() -> None:
    """Исчерпанный лимит должен остановить запрос до чтения потенциально большого тела."""

    middleware_order = [middleware.cls for middleware in app.user_middleware]

    assert middleware_order.index(SlowAPIMiddleware) < middleware_order.index(
        PayloadSizeLimitMiddleware
    )


def test_permission_dependency_blocks_dispatcher_from_future_approval_path() -> None:
    """Возврат разрешения вместо субъекта сделает будущий approve-роут некорректным и небезопасным."""

    isolated_app = FastAPI()

    @isolated_app.get("/approval")
    async def approval_path(subject: ApprovalSubject) -> dict[str, str]:
        return {"user_id": subject.user_id}

    isolated_app.dependency_overrides[get_current_subject] = lambda: SecuritySubject(
        user_id="dispatcher",
        username="dispatcher",
        role=Role.DISPATCHER,
        allowed_districts=["rek-1"],
    )

    with TestClient(isolated_app) as client:
        response = client.get("/approval")

    assert response.status_code == 403
    assert response.json() == {"detail": "Недостаточно прав для выполнения операции"}


def test_permission_dependency_allows_analyst_to_read_audit() -> None:
    """Отсутствующая роль analyst лишит верификацию прогноза требуемой стороны контроля."""

    isolated_app = FastAPI()

    @isolated_app.get("/audit")
    async def audit_path(subject: AuditSubject) -> dict[str, str]:
        return {"user_id": subject.user_id}

    isolated_app.dependency_overrides[get_current_subject] = lambda: SecuritySubject(
        user_id="analyst",
        username="analyst",
        role=Role.ANALYST,
        allowed_districts=["rek-1"],
    )

    with TestClient(isolated_app) as client:
        response = client.get("/audit")

    assert response.status_code == 200
    assert response.json() == {"user_id": "analyst"}


async def _consume_request_body(
    scope: dict[str, Any],
    receive: Callable[[], Awaitable[dict[str, Any]]],
    send: Callable[[dict[str, Any]], Awaitable[None]],
) -> None:
    """Минимальное ASGI-приложение, читающее тело целиком, как JSON-парсер FastAPI."""

    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return
        if message["type"] == "http.request" and not message.get("more_body", False):
            break

    await send({"type": "http.response.start", "status": 204, "headers": []})
    await send({"type": "http.response.body", "body": b""})


async def _respond_before_consuming_body(
    scope: dict[str, Any],
    receive: Callable[[], Awaitable[dict[str, Any]]],
    send: Callable[[dict[str, Any]], Awaitable[None]],
) -> None:
    """Имитирует будущий streaming-обработчик, ошибочно начинающий ответ до чтения body."""

    await send({"type": "http.response.start", "status": 204, "headers": []})
    await send({"type": "http.response.body", "body": b"", "more_body": True})
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return
        if message["type"] == "http.request" and not message.get("more_body", False):
            return


def _invoke_asgi(
    application: Callable[..., Awaitable[None]],
    headers: list[tuple[bytes, bytes]],
    chunks: list[bytes],
) -> list[dict[str, Any]]:
    """Выполняет ASGI-запрос с управляемыми фрагментами тела без HTTP-клиента."""

    messages = iter(
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    )
    sent: list[dict[str, Any]] = []
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/upload",
        "raw_path": b"/upload",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "root_path": "",
    }

    async def receive() -> dict[str, Any]:
        return next(messages, {"type": "http.disconnect"})

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    asyncio.run(application(scope, receive, send))
    return sent


def _response_status(messages: list[dict[str, Any]]) -> int:
    return next(
        message["status"] for message in messages if message["type"] == "http.response.start"
    )


def _response_json(messages: list[dict[str, Any]]) -> dict[str, str]:
    body = b"".join(
        message.get("body", b"") for message in messages if message["type"] == "http.response.body"
    )
    return json.loads(body)


@pytest.mark.parametrize("content_length", [b"-1", b"not-a-number"])
def test_payload_guard_rejects_invalid_declared_length_without_server_error(
    content_length: bytes,
) -> None:
    """int() без валидации превращает некорректный заголовок в 500 или принимает отрицательную длину."""

    middleware = PayloadSizeLimitMiddleware(_consume_request_body)
    messages = _invoke_asgi(middleware, [(b"content-length", content_length)], [b"{}"])

    assert _response_status(messages) == 400
    assert _response_json(messages) == {"error": "Некорректный заголовок Content-Length"}


def test_payload_guard_rejects_chunked_body_larger_than_limit() -> None:
    """Проверка только Content-Length позволит обойти лимит chunked-запросом."""

    middleware = PayloadSizeLimitMiddleware(_consume_request_body)
    messages = _invoke_asgi(
        middleware,
        [],
        [b"x" * MAX_PAYLOAD_SIZE, b"x"],
    )

    assert _response_status(messages) == 413
    assert _response_json(messages) == {
        "error": "Полезная нагрузка превышает допустимый размер (макс. 10МБ)"
    }


def test_payload_guard_rejects_oversized_stream_before_downstream_starts_response() -> None:
    """Не допускает частичный успешный ответ от будущего streaming-обработчика."""

    middleware = PayloadSizeLimitMiddleware(_respond_before_consuming_body)
    messages = _invoke_asgi(
        middleware,
        [],
        [b"x" * MAX_PAYLOAD_SIZE, b"x"],
    )

    assert _response_status(messages) == 413
    assert _response_json(messages) == {
        "error": "Полезная нагрузка превышает допустимый размер (макс. 10МБ)"
    }
    assert all(
        message.get("status") != 204
        for message in messages
        if message["type"] == "http.response.start"
    )


def test_payload_guard_rejects_declared_body_larger_than_limit() -> None:
    """Регрессия на ранний отказ до чтения уже объявленного чрезмерного тела."""

    middleware = PayloadSizeLimitMiddleware(_consume_request_body)
    messages = _invoke_asgi(
        middleware,
        [(b"content-length", str(MAX_PAYLOAD_SIZE + 1).encode("ascii"))],
        [b""],
    )

    assert _response_status(messages) == 413
    assert _response_json(messages) == {
        "error": "Полезная нагрузка превышает допустимый размер (макс. 10МБ)"
    }
