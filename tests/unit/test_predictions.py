from datetime import UTC, datetime

import pytest
from forpost_domain.risks.entities import RiskCategory, RiskPrediction


@pytest.mark.parametrize(
    "category, target_id",
    [
        (RiskCategory.SENSOR_FAILURE, "sensor_gas_42"),
        (RiskCategory.FIRE_RISK, "collector_sector_hot_work"),
        (RiskCategory.UNAUTHORIZED_ACCESS, "hatch_picket_12"),
        (RiskCategory.INFRASTRUCTURE_WEAR, "pump_station_main"),
    ],
)
def test_prediction_contract_supports_all_four_declared_categories(
    category: RiskCategory,
    target_id: str,
):
    """Схема будущего прогноза поддерживает четыре заявленные категории без генератора-заглушки."""
    result = RiskPrediction(
        prediction_id=f"test-{category.value}",
        target_id=target_id,
        category=category,
        probability=0.5,
        horizon_hours=24,
        calculated_at=datetime(2026, 1, 1, tzinfo=UTC),
        model_version="test-fixture",
        explanation="Локальная тестовая запись для проверки доменного контракта.",
    )

    assert isinstance(result, RiskPrediction)
    assert result.target_id == target_id
    assert result.category == category
    assert 0.0 <= result.probability <= 1.0
    assert result.horizon_hours >= 24, "Горизонт прогноза должен быть не менее 24 часов"
    assert len(result.explanation) > 0, "Прогноз обязан содержать объяснение причин"
