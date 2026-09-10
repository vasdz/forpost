from fastapi.testclient import TestClient
from forpost_api.main import app

client = TestClient(app)


def test_dispatcher_receives_only_assigned_districts():
    """Диспетчер rek-1 видит только объекты rek-1."""
    response = client.get(
        "/api/v1/risks",
        headers={
            "x-user-id": "disp-01",
            "x-role": "dispatcher",
            "x-districts": "rek-1",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert {item["target_id"] for item in data} == {"sensor-deg-014", "collector-sector-9"}


def test_access_denied_for_unauthorized_role():
    """Пользователь с ролью аудитора не имеет прав на просмотр оперативных рисков."""
    response = client.get(
        "/api/v1/risks",
        headers={
            "x-user-id": "sec-auditor-01",
            "x-role": "auditor",
            "x-districts": "rek-1",
        },
    )

    assert response.status_code == 403
    assert "недостаточный уровень привилегий" in response.json()["detail"]
