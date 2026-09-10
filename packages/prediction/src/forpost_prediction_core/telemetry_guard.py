from pydantic import BaseModel


class TelemetryBoundaryGuard(BaseModel):
    """Физические диапазоны датчиков коллекторов Москоллектора."""

    # Диапазоны нормальных показаний для предотвращения отравления ML-моделей
    TEMP_MIN: float = -30.0  # Зимой в неотапливаемых вентшахтах
    TEMP_MAX: float = 70.0  # Выше 70°C в нормальном режиме кабельного коллектора быть не может
    GAS_MAX_CH4_PPM: float = 5000.0  # Метан

    @classmethod
    def validate_reading(cls, sensor_type: str, raw_value: float) -> bool:
        """Отсечение аномалий, фаззинга и аппаратных сбоев (Break-in-wire)."""
        if sensor_type == "temperature":
            return cls.TEMP_MIN <= raw_value <= cls.TEMP_MAX
        if sensor_type == "gas":
            return 0.0 <= raw_value <= cls.GAS_MAX_CH4_PPM
        return True
