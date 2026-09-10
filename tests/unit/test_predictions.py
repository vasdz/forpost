import pytest
from forpost_domain.risks.entities import RiskCategory, RiskPrediction
from forpost_prediction_core.mock_predictor import MockRiskPredictor


@pytest.mark.parametrize(
    "category, target_id",
    [
        (RiskCategory.SENSOR_FAILURE, "sensor_gas_42"),
        (RiskCategory.FIRE_RISK, "collector_sector_hot_work"),
        (RiskCategory.UNAUTHORIZED_ACCESS, "hatch_picket_12"),
        (RiskCategory.INFRASTRUCTURE_WEAR, "pump_station_main"),
    ],
)
def test_all_four_prediction_modules_contract(category: RiskCategory, target_id: str):
    """Проверка единого контракта для всех 4 задач Москоллектора."""
    predictor = MockRiskPredictor(category)
    result = predictor.predict(target_id=target_id, context_data={})

    assert isinstance(result, RiskPrediction)
    assert result.target_id == target_id
    assert result.category == category
    assert 0.0 <= result.probability <= 1.0
    assert result.horizon_hours >= 24, "Горизонт прогноза должен быть не менее 24 часов"
    assert len(result.explanation) > 0, "Прогноз обязан содержать объяснение причин"
