"""Чистые расчёты аналитики для данных, поступивших из проверенных источников."""

from statistics import mean

from forpost_domain.analytics.entities import (
    RiskMetrics,
)
from forpost_domain.risks.entities import RiskPrediction


class RiskAnalysisEngine:
    """Движок анализа рисков и расчета метрик."""

    @staticmethod
    def calculate_risk_metrics_from_predictions(
        predictions: list[RiskPrediction],
    ) -> dict[str, RiskMetrics]:
        """Рассчитать метрики риска по категориям из прогнозов.

        Args:
            predictions: Список прогнозов рисков

        Returns:
            Словарь метрик по категориям
        """
        metrics_by_category: dict[str, dict] = {}

        for prediction in predictions:
            category_value = prediction.category.value
            if category_value not in metrics_by_category:
                metrics_by_category[category_value] = {
                    "total": 0,
                    "critical": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                    "probabilities": [],
                }

            category_data = metrics_by_category[category_value]
            category_data["total"] += 1
            category_data["probabilities"].append(prediction.probability)

            # Определяем уровень по вероятности
            if prediction.probability >= 0.9:
                category_data["critical"] += 1
            elif prediction.probability >= 0.7:
                category_data["high"] += 1
            elif prediction.probability >= 0.4:
                category_data["medium"] += 1
            else:
                category_data["low"] += 1

        # Конвертируем в RiskMetrics объекты
        result = {}
        for category, data in metrics_by_category.items():
            avg_prob = mean(data["probabilities"]) if data["probabilities"] else 0.0
            trend = "stable"
            if avg_prob > 0.65:
                trend = "increasing"
            elif avg_prob < 0.35:
                trend = "decreasing"

            result[category] = RiskMetrics(
                category=category,
                total_predictions=data["total"],
                critical_count=data["critical"],
                high_count=data["high"],
                medium_count=data["medium"],
                low_count=data["low"],
                avg_probability=round(avg_prob, 3),
                trend=trend,
            )

        return result

    @staticmethod
    def calculate_district_risk_summary(
        predictions: list[RiskPrediction],
        district: str,
    ) -> dict[str, any]:
        """Рассчитать сводку рисков по району.

        Args:
            predictions: Прогнозы для района
            district: Код района (rek-1..rek-4)

        Returns:
            Сводка по риску
        """
        district_predictions = [p for p in predictions if p.target_id.startswith("sensor")]

        metrics = RiskAnalysisEngine.calculate_risk_metrics_from_predictions(district_predictions)

        critical_24h = sum(
            1 for p in district_predictions if p.probability >= 0.9 and p.horizon_hours <= 24
        )

        return {
            "district": district,
            "total_predictions": len(district_predictions),
            "critical_24h": critical_24h,
            "metrics": metrics,
        }


class MaintenanceAnalyticsSummarizer:
    """Движок аналитики по заявкам на обслуживание."""

    @staticmethod
    def summarize_orders(orders: list) -> dict[str, any]:
        """Рассчитать статистику по заявкам.

        Args:
            orders: Список MaintenanceOrder объектов

        Returns:
            Статистика
        """
        from forpost_domain.maintenance.entities import MaintenanceStatus

        draft = sum(1 for o in orders if o.status == MaintenanceStatus.DRAFT)
        pending = sum(1 for o in orders if o.status == MaintenanceStatus.PENDING_APPROVAL)
        approved = sum(1 for o in orders if o.status == MaintenanceStatus.APPROVED)
        completed = sum(1 for o in orders if o.status == MaintenanceStatus.COMPLETED)

        return {
            "total_orders": len(orders),
            "draft_orders": draft,
            "pending_approval": pending,
            "approved_orders": approved,
            "completed_orders": completed,
            "completion_rate_percent": round((completed / len(orders) * 100) if orders else 0.0, 1),
        }
