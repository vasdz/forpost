"""Неизменяемые решения по тревогам и demo-черновики заявок."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class IncidentStatus(StrEnum):
    NEW = "new"
    IN_REVIEW = "in_review"
    CREW_DISPATCH = "crew_dispatch"
    FALSE_ALARM = "false_alarm"
    CONFIRMED_INCIDENT = "confirmed_incident"
    CLOSED = "closed"


class IncidentDecision(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True
    )

    decision_id: str = Field(min_length=1, max_length=128)
    incident_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: IncidentStatus
    reason: str = Field(min_length=5, max_length=1000)
    actor_id: str = Field(min_length=1, max_length=128)
    created_at: datetime
    corrects_decision_id: str | None = Field(default=None, min_length=1, max_length=128)
    provenance: Literal["simulated"] = "simulated"


class ServiceRequestDraft(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True
    )

    draft_id: str = Field(min_length=1, max_length=128)
    incident_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    target_id: str = Field(min_length=1, max_length=256)
    category: str = Field(min_length=1, max_length=128)
    priority: Literal["low", "medium", "high", "critical"]
    recommended_action: str = Field(min_length=5, max_length=2000)
    due_at: datetime
    author_id: str = Field(min_length=1, max_length=128)
    created_at: datetime
    provenance: Literal["simulated"] = "simulated"
