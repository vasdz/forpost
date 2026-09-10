"""Юнит-тесты для модуля превентивного обслуживания."""

import pytest
from datetime import UTC, datetime

from forpost_domain.maintenance.entities import (
    MaintenanceOrder,
    MaintenancePriority,
    MaintenanceStatus,
)
from forpost_domain.risks.entities import RiskCategory, RiskPrediction
from forpost_platform.maintenance.generator import (
    MaintenanceRegulator,
    MaintenanceOrderStore,
)
from forpost_prediction_core.mock_predictor import MockRiskPredictor


@pytest.mark.parametrize(
    "probability, expected_priority",
    [
        (0.95, MaintenancePriority.CRITICAL),
        (0.75, MaintenancePriority.HIGH),
        (0.50, MaintenancePriority.MEDIUM),
        (0.25, MaintenancePriority.LOW),
    ],
)
def test_priority_from_probability(probability: float, expected_priority: MaintenancePriority):
    """Проверка автоматического определения приоритета по вероятности."""
    priority = MaintenanceRegulator.get_priority_from_probability(probability)
    assert priority == expected_priority


@pytest.mark.parametrize(
    "category",
    [
        RiskCategory.SENSOR_FAILURE,
        RiskCategory.FIRE_RISK,
        RiskCategory.UNAUTHORIZED_ACCESS,
        RiskCategory.INFRASTRUCTURE_WEAR,
    ],
)
def test_order_generation_from_all_categories(category: RiskCategory):
    """Проверка генерации заявок по всем 4 категориям рисков."""
    predictor = MockRiskPredictor(category)
    prediction = predictor.predict(target_id="test-target", context_data={})

    order = MaintenanceRegulator.generate_order_from_risk(prediction, model_version="0.1.0")

    assert isinstance(order, MaintenanceOrder)
    assert order.order_id.startswith("MO-")
    assert order.target_id == "test-target"
    assert order.risk_category == category.value
    assert order.priority in [
        MaintenancePriority.LOW,
        MaintenancePriority.MEDIUM,
        MaintenancePriority.HIGH,
        MaintenancePriority.CRITICAL,
    ]
    assert order.status == MaintenanceStatus.DRAFT
    assert len(order.recommended_action) > 0
    assert len(order.normative_ref) > 0
    assert order.deadline_hours > 0
    assert order.generated_by_model_version == "0.1.0"


def test_maintenance_order_store_save_and_retrieve():
    """Проверка сохранения и извлечения заявок из хранилища."""
    store = MaintenanceOrderStore()

    order = MaintenanceOrder(
        order_id="MO-TEST001",
        target_id="test-asset",
        district="rek-1",
        risk_category="sensor_failure",
        priority=MaintenancePriority.HIGH,
        status=MaintenanceStatus.DRAFT,
        recommended_action="Test action",
        normative_ref="GOST 1234",
        deadline_hours=48,
        created_at=datetime.now(UTC),
        generated_by_model_version="0.1.0",
    )

    saved_order = store.save(order)
    assert saved_order == order

    retrieved = store.get_by_id("MO-TEST001")
    assert retrieved is not None
    assert retrieved.order_id == "MO-TEST001"
    assert retrieved.target_id == "test-asset"


def test_maintenance_order_store_get_by_district():
    """Проверка фильтрации заявок по эксплуатационному района."""
    store = MaintenanceOrderStore()

    order1 = MaintenanceOrder(
        order_id="MO-001",
        target_id="asset-1",
        district="rek-1",
        risk_category="sensor_failure",
        priority=MaintenancePriority.LOW,
        status=MaintenanceStatus.DRAFT,
        recommended_action="Action 1",
        normative_ref="GOST 1",
        deadline_hours=24,
        created_at=datetime.now(UTC),
        generated_by_model_version="0.1.0",
    )

    order2 = MaintenanceOrder(
        order_id="MO-002",
        target_id="asset-2",
        district="rek-3",
        risk_category="fire_risk",
        priority=MaintenancePriority.MEDIUM,
        status=MaintenanceStatus.DRAFT,
        recommended_action="Action 2",
        normative_ref="GOST 2",
        deadline_hours=36,
        created_at=datetime.now(UTC),
        generated_by_model_version="0.1.0",
    )

    store.save(order1)
    store.save(order2)

    rek1_orders = store.get_by_district("rek-1")
    assert len(rek1_orders) == 1
    assert rek1_orders[0].order_id == "MO-001"

    rek3_orders = store.get_by_district("rek-3")
    assert len(rek3_orders) == 1
    assert rek3_orders[0].order_id == "MO-002"


def test_maintenance_order_status_update():
    """Проверка обновления статуса заявки."""
    store = MaintenanceOrderStore()

    order = MaintenanceOrder(
        order_id="MO-STATUS-TEST",
        target_id="asset",
        district="rek-1",
        risk_category="unauthorized_access",
        priority=MaintenancePriority.MEDIUM,
        status=MaintenanceStatus.DRAFT,
        recommended_action="Action",
        normative_ref="GOST",
        deadline_hours=48,
        created_at=datetime.now(UTC),
        generated_by_model_version="0.1.0",
    )

    store.save(order)

    updated = store.update_status("MO-STATUS-TEST", MaintenanceStatus.APPROVED)
    assert updated is not None
    assert updated.status == MaintenanceStatus.APPROVED

    # Проверяем, что оно обновилось в хранилище
    retrieved = store.get_by_id("MO-STATUS-TEST")
    assert retrieved.status == MaintenanceStatus.APPROVED
