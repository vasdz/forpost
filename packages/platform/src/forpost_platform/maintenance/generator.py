"""Движок генерации заявок на превентивное обслуживание из прогнозов рисков."""

import uuid
from datetime import UTC, datetime

from forpost_domain.maintenance.entities import (
    MaintenanceOrder,
    MaintenancePriority,
    MaintenanceStatus,
)
from forpost_domain.risks.entities import RiskCategory


class MaintenanceRegulator:
    """Справочник нормативных регламентов и действий по превентивному обслуживанию."""

    # Нормативные регламенты по категориям рисков
    REGULATIONS = {
        RiskCategory.SENSOR_FAILURE: {
            "normative_ref": "ГОСТ Р 52434-2005 (датчики контроля параметров сред)",
            "actions": {
                "low": "Плановая калибровка датчика; проверка кабельных соединений.",
                "medium": "Срочная поверка датчика в аккредитованной лаборатории; замена кабелей.",
                "high": "Немедленная замена датчика на резервный; перенос груза на соседний канал.",
                "critical": "АВАРИЙНАЯ ОСТАНОВКА - отключение оборудования; звонок диспетчеру ЭДС.",
            },
            "horizon_multipliers": {"low": 720, "medium": 168, "high": 72, "critical": 24},
        },
        RiskCategory.FIRE_RISK: {
            "normative_ref": "ГОСТ Р 12.1.004-91 / СНиП 21-01-97 (противопожарные требования)",
            "actions": {
                "low": "Техническое обслуживание датчиков задымления; замена фильтров вентиляции.",
                "medium": "Инспекция кабельных трасс на предмет изоляции; расчистка вентиляционных каналов.",
                "high": "Запуск цикла интенсивной вентиляции; выездная проверка ПЧ по месту.",
                "critical": "НЕМЕДЛЕННАЯ ЭВАКУАЦИЯ - приказ начальнику смены; вызов пожарной службы.",
            },
            "horizon_multipliers": {"low": 720, "medium": 168, "high": 48, "critical": 12},
        },
        RiskCategory.UNAUTHORIZED_ACCESS: {
            "normative_ref": "ГОСТ Р 55275-2012 (физическая безопасность объектов КИИ)",
            "actions": {
                "low": "Проверка пломб люков и шахт; ревизия журнала доступа за месяц.",
                "medium": "Техническое обслуживание СКУД; замена батарей в картридерах.",
                "high": "Выездная инспекция СКУД-интеграции; анализ логов несанкционированных попыток.",
                "critical": "ПОЛНОЕ ПЕРЕКРЫТИЕ - закрытие всех люков вручную; служба безопасности ОДС в курсе.",
            },
            "horizon_multipliers": {"low": 480, "medium": 240, "high": 72, "critical": 24},
        },
        RiskCategory.INFRASTRUCTURE_WEAR: {
            "normative_ref": "СНиП 3.04.01-87 (ремонт и содержание конструкций)",
            "actions": {
                "low": "Визуальный осмотр конструкций; обновление защитного покрытия металла.",
                "medium": "Обследование участка эндоскопом; микробиологический анализ воды (коррозия).",
                "high": "Привлечение подрядчика к срочному ремонту секции; локализация с перекрытиями.",
                "critical": "ЗАКРЫТИЕ УЧАСТКА - аварийное перекрытие коллектора; инженерная эвакуация.",
            },
            "horizon_multipliers": {"low": 1440, "medium": 336, "high": 120, "critical": 24},
        },
    }

    @classmethod
    def get_priority_from_probability(cls, probability: float) -> MaintenancePriority:
        """Автоматическое определение приоритета по вероятности риска."""
        if probability >= 0.9:
            return MaintenancePriority.CRITICAL
        elif probability >= 0.7:
            return MaintenancePriority.HIGH
        elif probability >= 0.4:
            return MaintenancePriority.MEDIUM
        else:
            return MaintenancePriority.LOW

    @classmethod
    def generate_order_from_risk(
        cls,
        risk_prediction,
        model_version: str = "0.1.0",
    ) -> MaintenanceOrder:
        """Генерирует заявку на обслуживание из прогноза риска.

        Args:
            risk_prediction: RiskPrediction объект с данными о риске
            model_version: Версия модели-генератора

        Returns:
            MaintenanceOrder: Сгенерированная заявка
        """
        priority = cls.get_priority_from_probability(risk_prediction.probability)

        category_regs = cls.REGULATIONS.get(
            risk_prediction.category,
            cls.REGULATIONS[RiskCategory.SENSOR_FAILURE],  # default fallback
        )

        recommended_action = category_regs["actions"].get(
            priority.value,
            "Требуется техническое обслуживание по плану ТО.",
        )

        horizon_multiplier = category_regs["horizon_multipliers"].get(priority.value, 720)

        return MaintenanceOrder(
            order_id=f"MO-{uuid.uuid4().hex[:8].upper()}",
            target_id=risk_prediction.target_id,
            district="rek-1",  # Будет переписана при включении в API
            risk_category=risk_prediction.category.value,
            priority=priority,
            status=MaintenanceStatus.DRAFT,
            recommended_action=recommended_action,
            normative_ref=category_regs["normative_ref"],
            deadline_hours=min(horizon_multiplier, risk_prediction.horizon_hours),
            created_at=datetime.now(UTC),
            generated_by_model_version=model_version,
        )


class MaintenanceOrderStore:
    """In-memory хранилище заявок на обслуживание (для демонстрации)."""

    def __init__(self):
        self._orders: dict[str, MaintenanceOrder] = {}

    def save(self, order: MaintenanceOrder) -> MaintenanceOrder:
        """Сохранить заявку."""
        self._orders[order.order_id] = order
        return order

    def get_by_id(self, order_id: str) -> MaintenanceOrder | None:
        """Получить заявку по ID."""
        return self._orders.get(order_id)

    def get_all(self) -> list[MaintenanceOrder]:
        """Получить все заявки."""
        return list(self._orders.values())

    def get_by_district(self, district: str) -> list[MaintenanceOrder]:
        """Получить заявки по эксплуатационному району."""
        return [o for o in self._orders.values() if o.district == district]

    def update_status(
        self, order_id: str, new_status: MaintenanceStatus
    ) -> MaintenanceOrder | None:
        """Обновить статус заявки."""
        order = self._orders.get(order_id)
        if order:
            order.status = new_status
        return order


# Глобальный экземпляр хранилища
_maintenance_store = MaintenanceOrderStore()


def get_maintenance_store() -> MaintenanceOrderStore:
    """Получить глобальное хранилище заявок."""
    return _maintenance_store
