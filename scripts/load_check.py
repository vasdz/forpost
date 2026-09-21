"""Локальная проверка конкурентного чтения ASGI; не нагрузочная сертификация SLA."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import secrets
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypedDict

import httpx
from starlette.types import ASGIApp

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for source_path in (
    "apps/api/src",
    "packages/domain/src",
    "packages/prediction/src",
    "packages/connectors/src",
    "packages/platform/src",
):
    sys.path.insert(0, str(PROJECT_ROOT / source_path))

from forpost_api.main import app  # noqa: E402
from forpost_api.routes import availability, predictions  # noqa: E402
from forpost_api.routes.v1.topology import (  # noqa: E402
    LocalTopologyCatalog,
    get_topology_catalog,
)

# Только GET: не создаём demo-хранилище и не вызываем операции диспетчера.
READ_ROUTES = ("/api/availability", "/api/v1/topology")


@contextmanager
def isolated_application() -> Iterator[tuple[ASGIApp, str]]:
    """Подключает только временные проверочные данные и восстанавливает bindings."""
    with TemporaryDirectory(prefix="forpost-load-check-") as directory:
        root = Path(directory)
        snapshot = root / "local-situation.json"
        snapshot.write_text(
            json.dumps(
                {
                    "objects": [
                        {
                            "objectId": "load-check-complex",
                            "parentId": None,
                            "objectKind": "controlHouse",
                            "dispatcherName": "Проверочный комплекс",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        models = root / "models"
        models.mkdir()
        catalog = LocalTopologyCatalog(snapshot)
        previous_overrides = app.dependency_overrides.copy()
        previous_snapshot = availability.LOCAL_SNAPSHOT_PATH
        previous_models = predictions.ML_MODELS_DIRECTORY
        previous_token = os.environ.get("FORPOST_API_SERVICE_TOKEN")
        # Секрет существует только в этом процессе; не передаётся в CLI или JSON.
        token = secrets.token_hex(32)
        try:
            os.environ["FORPOST_API_SERVICE_TOKEN"] = token
            availability.LOCAL_SNAPSHOT_PATH = snapshot
            predictions.ML_MODELS_DIRECTORY = models
            app.dependency_overrides[get_topology_catalog] = lambda: catalog
            yield app, token
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous_overrides)
            availability.LOCAL_SNAPSHOT_PATH = previous_snapshot
            predictions.ML_MODELS_DIRECTORY = previous_models
            if previous_token is None:
                os.environ.pop("FORPOST_API_SERVICE_TOKEN", None)
            else:
                os.environ["FORPOST_API_SERVICE_TOKEN"] = previous_token


class CheckSummary(TypedDict):
    users: int
    requests: int
    errors: int
    p95_ms: float
    scope: str


def nearest_rank_p95(durations: list[float]) -> float:
    """Выбирает наблюдение ранга ceil(0.95 * N), без интерполяции."""
    return sorted(durations)[math.ceil(0.95 * len(durations)) - 1]


async def run_check(
    *,
    application: ASGIApp,
    token: str,
    users: int = 20,
    requests_per_user: int = 5,
    request_timeout: float = 10,
) -> CheckSummary:
    """Запускает по одной последовательной сессии на каждого виртуального пользователя."""
    if users < 1 or requests_per_user < 1:
        raise ValueError("Число пользователей и запросов должно быть положительным")
    if not math.isfinite(request_timeout) or request_timeout <= 0:
        raise ValueError("Таймаут должен быть конечным положительным числом")
    durations: list[float] = []
    errors = 0
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1",
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    ) as client:

        async def user_session(user: int) -> None:
            nonlocal errors
            for index in range(requests_per_user):
                route = READ_ROUTES[(user + index) % len(READ_ROUTES)]
                started = time.perf_counter()
                try:
                    # Таймаут httpx не ограничивает выполнение in-process ASGI.
                    async with asyncio.timeout(request_timeout):
                        response = await client.get(route)
                    if not 200 <= response.status_code < 300:
                        errors += 1
                except (httpx.HTTPError, TimeoutError):
                    errors += 1
                finally:
                    durations.append((time.perf_counter() - started) * 1000)

        async with asyncio.TaskGroup() as group:
            for user in range(users):
                group.create_task(user_session(user))

    return {
        "users": users,
        "requests": len(durations),
        "errors": errors,
        "p95_ms": round(nearest_rank_p95(durations), 3),
        "scope": "local_asgi_read_only_not_sla",
    }


def exit_code(summary: CheckSummary) -> int:
    """Успех относится именно к непустой проверке на 20 пользователей."""
    return 0 if summary["users"] == 20 and summary["requests"] > 0 and summary["errors"] == 0 else 1


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("Требуется положительное целое число")
    return parsed


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=positive_integer, default=20)
    parser.add_argument("--requests-per-user", type=positive_integer, default=5)
    options = parser.parse_args(arguments)
    with isolated_application() as (application, token):
        summary = asyncio.run(
            run_check(
                application=application,
                token=token,
                users=options.users,
                requests_per_user=options.requests_per_user,
            )
        )
    print(json.dumps(summary, sort_keys=True))
    return exit_code(summary)


if __name__ == "__main__":
    raise SystemExit(main())
