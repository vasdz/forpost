"""Локальная конкурентная проверка не должна выдавать ошибки API за успех."""

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest
from forpost_api.main import app
from forpost_api.routes import availability, predictions
from forpost_api.routes.v1.topology import LocalTopologyCatalog, get_topology_catalog

SERVICE_TOKEN = "load-check-test-service-token-1234567890"  # noqa: S105


def load_runner():
    path = Path(__file__).resolve().parents[2] / "scripts" / "load_check.py"
    assert path.is_file(), "Отсутствует воспроизводимый read-only runner"
    spec = importlib.util.spec_from_file_location("load_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def isolated_app(tmp_path, monkeypatch):
    snapshot = tmp_path / "local-situation.json"
    snapshot.write_text(
        json.dumps(
            {
                "objects": [
                    {
                        "objectId": "complex-1",
                        "parentId": None,
                        "objectKind": "controlHouse",
                        "dispatcherName": "Учебный комплекс",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("FORPOST_API_SERVICE_TOKEN", SERVICE_TOKEN)
    monkeypatch.setattr(availability, "LOCAL_SNAPSHOT_PATH", snapshot)
    monkeypatch.setattr(predictions, "ML_MODELS_DIRECTORY", tmp_path / "models")
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_topology_catalog] = lambda: LocalTopologyCatalog(snapshot)
    try:
        yield app, snapshot
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_twenty_users_make_exactly_one_hundred_concurrent_gets(isolated_app):
    runner = load_runner()
    application, snapshot = isolated_app
    before = snapshot.read_bytes()
    requests = []
    active = 0
    maximum_active = 0

    async def observed(scope, receive, send):
        nonlocal active, maximum_active
        requests.append((scope["method"], scope["path"]))
        active += 1
        maximum_active = max(maximum_active, active)
        try:
            await asyncio.sleep(0)
            await application(scope, receive, send)
        finally:
            active -= 1

    summary = asyncio.run(
        runner.run_check(
            application=observed,
            token=SERVICE_TOKEN,
            users=20,
            requests_per_user=5,
        )
    )

    assert summary["users"] == 20
    assert summary["requests"] == 100
    assert summary["errors"] == 0
    assert summary["p95_ms"] >= 0
    assert summary["scope"] == "local_asgi_read_only_not_sla"
    assert runner.exit_code(summary) == 0
    assert len(requests) == 100
    assert {method for method, _ in requests} == {"GET"}
    assert {path for _, path in requests} == {"/api/availability", "/api/v1/topology"}
    assert maximum_active == 20
    assert snapshot.read_bytes() == before


@pytest.mark.parametrize("failure", ["missing_snapshot", "unauthorized", "exception"])
def test_failed_requests_cannot_pass_readiness(isolated_app, failure):
    runner = load_runner()
    application, snapshot = isolated_app
    token = SERVICE_TOKEN
    if failure == "missing_snapshot":
        snapshot.unlink()
    elif failure == "unauthorized":
        token = "wrong-token"  # noqa: S105
    else:

        def unavailable_catalog():
            raise RuntimeError("Тестовая неисправность")

        app.dependency_overrides[get_topology_catalog] = unavailable_catalog

    summary = asyncio.run(
        runner.run_check(
            application=application,
            token=token,
            users=20,
            requests_per_user=5,
        )
    )

    assert summary["requests"] == 100
    assert summary["errors"] == (100 if failure == "unauthorized" else 50)
    assert runner.exit_code(summary) == 1


def test_cli_outputs_only_json_and_propagates_failure(isolated_app, capsys):
    runner = load_runner()
    _, snapshot = isolated_app
    assert runner.main(["--users", "20", "--requests-per-user", "5"]) == 0
    assert json.loads(capsys.readouterr().out)["requests"] == 100
    snapshot.unlink()
    assert runner.main(["--users", "20", "--requests-per-user", "5"]) == 1
    assert json.loads(capsys.readouterr().out)["errors"] == 50


def test_smaller_check_is_not_twenty_user_success(isolated_app):
    runner = load_runner()
    summary = asyncio.run(
        runner.run_check(
            application=isolated_app[0],
            token=SERVICE_TOKEN,
            users=1,
            requests_per_user=1,
        )
    )
    assert summary["errors"] == 0
    assert runner.exit_code(summary) == 1


@pytest.mark.parametrize("users, requests_per_user", [(0, 5), (20, 0), (-1, 5)])
def test_empty_or_negative_workload_is_rejected(isolated_app, users, requests_per_user):
    runner = load_runner()
    with pytest.raises(ValueError):
        asyncio.run(
            runner.run_check(
                application=isolated_app[0],
                token=SERVICE_TOKEN,
                users=users,
                requests_per_user=requests_per_user,
            )
        )


def test_p95_uses_nearest_rank_not_interpolation():
    runner = load_runner()
    assert runner.nearest_rank_p95(list(range(1, 101))) == 95
    assert runner.nearest_rank_p95([100, 1, 2]) == 100
