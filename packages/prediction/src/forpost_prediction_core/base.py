from abc import ABC, abstractmethod
from typing import Any

from forpost_domain.risks.entities import RiskCategory, RiskPrediction


class BaseRiskPredictor(ABC):
    """Базовый контракт для всех 4 моделей.

    Любая ML-модель или эвристика обязана реализовать только этот метод.
    API и воркеры работают исключительно через этот интерфейс.
    """

    category: RiskCategory

    @abstractmethod
    def predict(self, target_id: str, context_data: dict[str, Any]) -> RiskPrediction:
        """Расчет риска для указанного объекта инфраструктуры."""
        pass
