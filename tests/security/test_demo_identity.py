from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from forpost_api.main import app
from forpost_platform.security.demo_identity import (
    DemoIdentityError,
    issue_demo_assertion,
    verify_demo_assertion,
)
from forpost_platform.security.identity import Permission, Role, SecuritySubject

SECRET = "s" * 48
NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


def subject(*roles: Role) -> SecuritySubject:
    return SecuritySubject(
        user_id="demo-user",
        username="Демо-пользователь",
        roles=frozenset(roles),
        allowed_districts=frozenset({"РЭК-1"}),
        allowed_complexes=frozenset({"complex-7"}),
    )


def test_role_permissions_are_additive_without_admin_business_access():
    """Администратор не должен получить решение диспетчера из системной роли."""
    admin = subject(Role.SYSTEM_ADMIN)
    combined = subject(Role.DISTRICT_DISPATCHER, Role.TECHNICIAN)

    assert not admin.has_permission(Permission.RECORD_DECISION)
    assert admin.has_permission(Permission.AUDIT_READ)
    assert combined.has_permission(Permission.RECORD_DECISION)
    assert combined.has_permission(Permission.RECORD_INSPECTION)
    assert combined.has_permission(Permission.VIEW_SERVICE_DRAFT)
    assert not subject(Role.TECHNICIAN).has_permission(Permission.CREATE_SERVICE_DRAFT)


def test_subject_scope_combines_assigned_districts_and_complexes():
    """ABAC не должен открыть чужой район или комплекс при сложении ролей."""
    district = subject(Role.DISTRICT_DISPATCHER)
    technician = subject(Role.TECHNICIAN)
    central = subject(Role.CENTRAL_DISPATCHER)

    assert district.can_access_resource(district="РЭК-1", complex_id=None)
    assert not district.can_access_resource(district="РЭК-2", complex_id=None)
    assert technician.can_access_resource(district=None, complex_id="complex-7")
    assert not technician.can_access_resource(district=None, complex_id="complex-8")
    assert central.can_access_resource(district="РЭК-99", complex_id="any")


def test_signed_demo_assertion_round_trip_preserves_server_subject():
    """Подпись должна защищать все роли и области от изменения браузером."""
    original = subject(Role.DISTRICT_DISPATCHER, Role.TECHNICIAN)

    token = issue_demo_assertion(original, SECRET, now=NOW, ttl_seconds=120)
    restored = verify_demo_assertion(token, SECRET, now=NOW + timedelta(seconds=30))

    assert restored == original


def test_demo_assertion_rejects_wrong_secret_and_expiration():
    """Чужая подпись и истёкшее утверждение не должны превращаться в сессию."""
    token = issue_demo_assertion(subject(Role.DISTRICT_DISPATCHER), SECRET, now=NOW)

    with pytest.raises(DemoIdentityError, match="недействительно"):
        verify_demo_assertion(token, "x" * 48, now=NOW)
    with pytest.raises(DemoIdentityError, match="истекло"):
        verify_demo_assertion(token, SECRET, now=NOW + timedelta(minutes=6))


def test_demo_assertion_rejects_wrong_audience_and_short_secret():
    """Токен другого сервиса и слабый ключ не должны приниматься API."""
    token = issue_demo_assertion(subject(Role.CENTRAL_DISPATCHER), SECRET, now=NOW)

    with pytest.raises(DemoIdentityError, match="аудитория"):
        verify_demo_assertion(token, SECRET, now=NOW, audience="another-service")
    with pytest.raises(DemoIdentityError, match="Секрет"):
        issue_demo_assertion(subject(Role.CENTRAL_DISPATCHER), "short", now=NOW)


def test_demo_session_is_hidden_until_explicitly_enabled(monkeypatch):
    """Production-режим не должен раскрывать даже наличие demo-входа."""
    monkeypatch.delenv("FORPOST_DEMO_MODE", raising=False)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/demo/session",
            headers={"X-Demo-Access-Key": "k" * 48},
            json={"profile": "central-dispatcher"},
        )

    assert response.status_code == 404


def test_demo_session_issues_assertion_for_fixed_server_profile(monkeypatch):
    """Клиент выбирает только профиль, но не присылает произвольные роли и области."""
    monkeypatch.setenv("FORPOST_DEMO_MODE", "1")
    monkeypatch.setenv("FORPOST_DEMO_ACCESS_KEY", "k" * 48)
    monkeypatch.setenv("FORPOST_DEMO_ASSERTION_SECRET", SECRET)

    with TestClient(app) as client:
        forged = client.post(
            "/api/v1/demo/session",
            headers={"X-Demo-Access-Key": "k" * 48},
            json={"profile": "district-dispatcher", "roles": ["admin"]},
        )
        response = client.post(
            "/api/v1/demo/session",
            headers={"X-Demo-Access-Key": "k" * 48},
            json={"profile": "district-dispatcher"},
        )

    assert forged.status_code == 422
    assert response.status_code == 200
    payload = response.json()
    restored = verify_demo_assertion(payload["assertion"].removeprefix("demo."), SECRET)
    assert restored.roles == frozenset({Role.DISTRICT_DISPATCHER})
    assert restored.allowed_districts == frozenset({"РЭК-1"})
    assert payload["provenance"] == "simulated"
