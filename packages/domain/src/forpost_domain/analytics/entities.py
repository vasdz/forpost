"""Доменные модели для аналитики и отчетности по рискам."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ReportPeriod(StrEnum):
    """Период отчета."""

    DAILY = "daily"  # За день
    WEEKLY = "weekly"  # За неделю
    MONTHLY = "monthly"  # За месяц
    QUARTERLY = "quarterly"  # За квартал


class RiskMetrics(BaseModel):
    """Метрики по одной категории риска."""

    category: str
    total_predictions: int = Field(ge=0)
    critical_count: int = Field(ge=0)
    high_count: int = Field(ge=0)
    medium_count: int = Field(ge=0)
    low_count: int = Field(ge=0)
    avg_probability: float = Field(ge=0.0, le=1.0)
    trend: str = Field(default="stable")  # stable, increasing, decreasing


class DistrictRiskProfile(BaseModel):
    """Профиль рисков по эксплуатационному району."""

    district: str
    metrics: dict[str, RiskMetrics]
    total_assets: int
    critical_alerts_24h: int
    last_updated: datetime


class MaintenanceAnalytics(BaseModel):
    """Аналитика по заявкам на обслуживание."""

    total_orders: int
    draft_orders: int
    pending_approval: int
    approved_orders: int
    completed_orders: int
    avg_completion_time_hours: float = Field(ge=0)
    overdue_orders: int = Field(ge=0)
    estimated_next_7_days: int = Field(ge=0)


class RiskTrendAnalysis(BaseModel):
    """Анализ тренда по категориям рисков за период."""

    category: str
    period: ReportPeriod
    start_date: datetime
    end_date: datetime
    daily_average: float
    peak_date: datetime
    peak_value: float
    min_date: datetime
    min_value: float
    trend_direction: str  # up, down, stable


class OperationalReport(BaseModel):
    """Сводный операционный отчет."""

    report_id: str
    generated_at: datetime
    period: ReportPeriod
    start_date: datetime
    end_date: datetime
    total_districts: int
    districts: dict[str, DistrictRiskProfile]
    maintenance: MaintenanceAnalytics
    critical_findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    generated_by: str
    classification: str = Field(default="operational")  # operational, confidential


class KPIDashboard(BaseModel):
    """КПИ дашборд для руководства."""

    report_date: datetime
    system_availability_percent: float = Field(ge=0.0, le=100.0)
    mean_time_between_failure_hours: float = Field(ge=0)
    response_time_minutes: float = Field(ge=0)
    maintenance_backlog: int = Field(ge=0)
    risk_score_overall: float = Field(ge=0.0, le=1.0)
    predicted_incidents_24h: int = Field(ge=0)
    predicted_incidents_7d: int = Field(ge=0)
    confidence_level: str = Field(default="high")  # low, medium, high


class ExportFormat(StrEnum):
    """Форматы экспорта отчетов."""

    PDF = "pdf"
    XLSX = "xlsx"
    CSV = "csv"
    JSON = "json"
