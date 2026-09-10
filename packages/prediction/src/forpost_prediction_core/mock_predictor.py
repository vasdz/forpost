import secrets
from datetime import datetime, timezone

from forpost_domain.risks.entities import RiskCategory, RiskPrediction

from forpost_prediction_core.base import BaseRiskPredictor


class MockRiskPredictor(BaseRiskPredictor):
    def __init__(self, category: RiskCategory):
        self.category = category

    def predict(self, target_id: str, context_data: dict) -> RiskPrediction:
        # Криптографически стойкая генерация псевдовероятности для мока (CWE-330 Compliant)
        prob = round(secrets.randbelow(80) / 100.0 + 0.05, 2)
        return RiskPrediction(
            prediction_id=f"pred-{self.category.value}-{target_id}-{int(datetime.now(timezone.utc).timestamp())}",
            target_id=target_id,
            category=self.category,
            probability=prob,
            horizon_hours=24,
            calculated_at=datetime.now(timezone.utc),
            model_version="baseline-v0.1-mock",
            explanation=f"Сформировано базовым эвристическим контуром для категории {self.category.value}",
        )
