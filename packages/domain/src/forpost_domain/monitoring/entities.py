"""Неизменяемые записи мониторинга, импортируемые из Appendix 1."""

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from pydantic import BaseModel, ConfigDict, Field


class ChannelTypeSlug(StrEnum):
    """Допустимые категории каналов датчиков в Appendix 1."""

    CONTACT_UNLOCK_NORM = "contact-unlock-norm"
    SWITCH = "switch"
    SMOKE = "smoke"
    MOVEMENT = "movement"
    GAS = "gas"
    PUMP = "pump"
    FAN = "fan"
    PHASE = "phase"
    TEMPERATURE = "temperature"


CHANNEL_TYPE_SLUGS: Final[Mapping[int, ChannelTypeSlug]] = MappingProxyType(
    {
        2: ChannelTypeSlug.CONTACT_UNLOCK_NORM,
        3: ChannelTypeSlug.SWITCH,
        4: ChannelTypeSlug.SMOKE,
        5: ChannelTypeSlug.MOVEMENT,
        6: ChannelTypeSlug.GAS,
        7: ChannelTypeSlug.PUMP,
        8: ChannelTypeSlug.FAN,
        9: ChannelTypeSlug.PHASE,
        12: ChannelTypeSlug.TEMPERATURE,
    }
)


class ChannelType(BaseModel):
    """Справочный тип канала датчика."""

    model_config = ConfigDict(frozen=True)

    type_id: int = Field(..., ge=1)
    name: str = Field(..., min_length=1)
    dispatch_name: str = Field(..., min_length=1)
    slug: ChannelTypeSlug


class DataChannel(BaseModel):
    """Канал данных и его тег в дереве объектов."""

    model_config = ConfigDict(frozen=True)

    channel_id: int = Field(..., ge=1)
    object_tag: str = Field(..., min_length=1)


class EventJournalEntry(BaseModel):
    """Запись журнала событий СМВУ."""

    model_config = ConfigDict(frozen=True)

    event_id: int = Field(..., ge=1)
    channel_id: int = Field(..., ge=1)
    channel_type_id: int = Field(..., ge=1)
    current_value: str
    recorded_at: datetime


class ObjectSystemTreeNode(BaseModel):
    """Узел дерева систем объектов."""

    model_config = ConfigDict(frozen=True)

    record_id: int = Field(..., ge=1)
    system_id: int = Field(..., ge=1)
    dispatch_name: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)


class MonitoringImport(BaseModel):
    """Согласованный комплект данных мониторинга из локальных таблиц."""

    model_config = ConfigDict(frozen=True)

    channel_types: tuple[ChannelType, ...]
    channels: tuple[DataChannel, ...]
    events: tuple[EventJournalEntry, ...]
    object_tree: tuple[ObjectSystemTreeNode, ...]
