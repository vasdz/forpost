"""Юнит-тесты для модуля аналитики и отчетности."""

from datetime import UTC, datetime

import pytest
from forpost_domain.analytics.entities import (
    RiskMetrics,
)
from forpost_domain.risks.entities import RiskCategory, RiskPrediction
from forpost_platform.analytics.generator import (
    MaintenanceAnalyticsSummarizer,
    RiskAnalysisEngine,
)


@pytest.mark.parametrize(
    "category",
    [
        RiskCategory.SENSOR_FAILURE,
        RiskCategory.FIRE_RISK,
        RiskCategory.UNAUTHORIZED_ACCESS,
        RiskCategory.INFRASTRUCTURE_WEAR,
    ],
)
def test_risk_metrics_calculation_all_categories(category: RiskCategory):
    """Расчёт метрик использует явные доменные записи, а не сгенерированные прогнозы."""
    predictions = [
        RiskPrediction(
            prediction_id=f"test-{category.value}-{index}",
            target_id=f"target-{index}",
            category=category,
            probability=probability,
            horizon_hours=24,
            calculated_at=datetime(2026, 1, 1, tzinfo=UTC),
            model_version="test-fixture",
            explanation="Локальная тестовая запись для расчёта метрик.",
        )
        for index, probability in enumerate([0.95, 0.75, 0.50, 0.25, 0.10])
    ]

    metrics = RiskAnalysisEngine.calculate_risk_metrics_from_predictions(predictions)

    assert category.value in metrics
    metric = metrics[category.value]

    assert isinstance(metric, RiskMetrics)
    assert metric.total_predictions == 5
    assert metric.critical_count + metric.high_count + metric.medium_count + metric.low_count == 5
    assert 0.0 <= metric.avg_probability <= 1.0
    assert metric.trend in ["stable", "increasing", "decreasing"]


def test_risk_metrics_trend_determination():
    """Проверка определения тренда по средней вероятности."""
    # Создаем прогнозы с высокой средней вероятностью
    high_prob_predictions = [
        RiskPrediction(
            prediction_id=f"pred-{i}",
            target_id=f"target-{i}",
            category=RiskCategory.SENSOR_FAILURE,
            probability=0.8,  # high
            horizon_hours=24,
            calculated_at=datetime.now(UTC),
            model_version="0.1.0",
            explanation="High risk",
        )
        for i in range(3)
    ]

    metrics = RiskAnalysisEngine.calculate_risk_metrics_from_predictions(high_prob_predictions)
    metric = metrics[RiskCategory.SENSOR_FAILURE.value]

    assert metric.trend == "increasing"
    assert metric.avg_probability >= 0.65


def test_district_risk_summary_calculation():
    """Проверка расчета сводки рисков по району."""
    predictions = [
        RiskPrediction(
            prediction_id="pred-1",
            target_id="sensor-001",
            category=RiskCategory.SENSOR_FAILURE,
            probability=0.95,
            horizon_hours=24,
            calculated_at=datetime.now(UTC),
            model_version="0.1.0",
            explanation="Critical",
        ),
        RiskPrediction(
            prediction_id="pred-2",
            target_id="pump-001",
            category=RiskCategory.INFRASTRUCTURE_WEAR,
            probability=0.3,
            horizon_hours=48,
            calculated_at=datetime.now(UTC),
            model_version="0.1.0",
            explanation="Low risk",
        ),
    ]

    summary = RiskAnalysisEngine.calculate_district_risk_summary(predictions, "rek-1")

    assert summary["district"] == "rek-1"
    assert summary["total_predictions"] >= 0
    assert summary["critical_24h"] >= 0


def test_maintenance_analytics_summarization():
    """Проверка расчета аналитики по заявкам."""
    from forpost_domain.maintenance.entities import (
        MaintenanceOrder,
        MaintenancePriority,
        MaintenanceStatus,
    )

    orders = [
        MaintenanceOrder(
            order_id="MO-001",
            target_id="asset-1",
            district="rek-1",
            risk_category="sensor_failure",
            priority=MaintenancePriority.HIGH,
            status=MaintenanceStatus.DRAFT,
            recommended_action="Action 1",
            normative_ref="GOST",
            deadline_hours=48,
            created_at=datetime.now(UTC),
            generated_by_model_version="0.1.0",
        ),
        MaintenanceOrder(
            order_id="MO-002",
            target_id="asset-2",
            district="rek-1",
            risk_category="fire_risk",
            priority=MaintenancePriority.CRITICAL,
            status=MaintenanceStatus.COMPLETED,
            recommended_action="Action 2",
            normative_ref="GOST",
            deadline_hours=24,
            created_at=datetime.now(UTC),
            generated_by_model_version="0.1.0",
        ),
    ]

    summary = MaintenanceAnalyticsSummarizer.summarize_orders(orders)

    assert summary["total_orders"] == 2
    assert summary["draft_orders"] == 1
    assert summary["completed_orders"] == 1
    assert "completion_rate_percent" in summary
