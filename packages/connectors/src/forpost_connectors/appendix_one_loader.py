"""Строгая загрузка локальных таблиц Appendix 1 в доменные записи мониторинга."""

from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Final

import pandas as pd
from forpost_domain.monitoring import (
    CHANNEL_TYPE_SLUGS,
    ChannelType,
    DataChannel,
    EventJournalEntry,
    MonitoringImport,
    ObjectSystemTreeNode,
)

from forpost_connectors.secure_file import SecureFileInspector, SecurityError

MAX_XLSX_FILE_BYTES: Final[int] = 32 * 1024 * 1024
MAX_TABLE_ROWS: Final[int] = 100_000


class SourceSchemaError(ValueError):
    """Источник не соответствует контракту Appendix 1."""


class AppendixOneExcelLoader:
    """Загружает локальные XLSX Приложения 1 в ограниченных ресурсах.

    Каждый файл ограничен 32 МиБ в сжатом виде, каждая читаемая таблица —
    100 000 строками. Ограничения ZIP-структуры и распакованного размера
    дополнительно применяет :class:`SecureFileInspector`.
    """

    EVENT_COLUMNS: Final[dict[str, str]] = {
        "ИД записи журнала": "event_id",
        "ИД канала данных": "channel_id",
        "ИД типа канала данных": "channel_type_id",
        "Текущее значение": "current_value",
        "Дата записи": "recorded_at",
    }
    CHANNEL_COLUMNS: Final[dict[str, str]] = {
        "ИД канала данных": "channel_id",
        "Тег в дереве объектов": "object_tag",
    }
    CHANNEL_TYPE_COLUMNS: Final[dict[str, str]] = {
        "ИД типа канала датчика": "type_id",
        "Название": "name",
        "Диспетчерское название": "dispatch_name",
    }
    TREE_COLUMNS: Final[dict[str, str]] = {
        "ИД записи": "record_id",
        "ИД системы": "system_id",
        "Диспетчерское название": "dispatch_name",
        "Название": "name",
    }
    TIMESTAMP_FORMAT: Final[str] = "%d.%m.%Y %H:%M"
    TIMESTAMP_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}$")

    def __init__(self, *, allowed_root: str | Path | None = None) -> None:
        """Ограничивает импорт текущим рабочим деревом или явно разрешённым каталогом."""
        root = Path.cwd() if allowed_root is None else Path(allowed_root)
        if not root.is_dir():
            raise SourceSchemaError("Разрешённый каталог импорта не существует")
        self._allowed_root = root.resolve()

    def load(
        self,
        *,
        events_path: str | Path,
        channels_path: str | Path,
        channel_types_path: str | Path,
        tree_path: str | Path,
    ) -> MonitoringImport:
        """Возвращает согласованный импорт из четырёх таблиц Appendix 1."""
        events_frame = self._read_table(events_path, "журнал событий", self.EVENT_COLUMNS)
        channels_frame = self._read_table(channels_path, "каналы данных", self.CHANNEL_COLUMNS)
        types_frame = self._read_table(
            channel_types_path, "типы каналов", self.CHANNEL_TYPE_COLUMNS
        )
        tree_frame = self._read_table(tree_path, "дерево систем", self.TREE_COLUMNS)

        channel_types = tuple(self._to_channel_type(row) for _, row in types_frame.iterrows())
        channels = tuple(self._to_channel(row) for _, row in channels_frame.iterrows())
        events = tuple(self._to_event(row) for _, row in events_frame.iterrows())
        object_tree = tuple(self._to_tree_node(row) for _, row in tree_frame.iterrows())

        self._validate_unique(channel_types, "type_id", "типы каналов")
        self._validate_unique(channels, "channel_id", "каналы данных")
        self._validate_unique(events, "event_id", "журнал событий")
        self._validate_unique(object_tree, "record_id", "дерево систем")
        self._validate_references(events, channels, channel_types)

        return MonitoringImport(
            channel_types=channel_types,
            channels=channels,
            events=events,
            object_tree=object_tree,
        )

    def _read_table(
        self, path_value: str | Path, table_name: str, columns: dict[str, str]
    ) -> pd.DataFrame:
        raw_path = str(path_value)
        if raw_path.startswith(("\\\\", "//")):
            raise SourceSchemaError(f"{table_name}: UNC-пути не допускаются")

        path = Path(path_value).resolve(strict=False)
        if not path.is_relative_to(self._allowed_root):
            raise SourceSchemaError(
                f"{table_name}: путь находится вне разрешённого локального каталога"
            )
        if path.suffix.lower() != ".xlsx" or not path.is_file():
            raise SourceSchemaError(f"{table_name}: ожидается существующий локальный файл .xlsx")
        try:
            with path.open("rb") as source:
                payload = source.read(MAX_XLSX_FILE_BYTES + 1)
        except OSError as error:
            raise SourceSchemaError(f"{table_name}: файл не удалось безопасно прочитать") from error
        if len(payload) > MAX_XLSX_FILE_BYTES:
            raise SourceSchemaError(f"{table_name}: размер файла превышает допустимый предел")

        try:
            SecureFileInspector.validate_excel_archive(payload)
        except SecurityError as error:
            raise SourceSchemaError(f"{table_name}: файл не удалось безопасно прочитать") from error
        try:
            frame = pd.read_excel(BytesIO(payload), dtype=object, nrows=MAX_TABLE_ROWS + 1)
        except Exception as error:
            raise SourceSchemaError(f"{table_name}: файл не удалось безопасно прочитать") from error
        if len(frame.index) > MAX_TABLE_ROWS:
            raise SourceSchemaError(f"{table_name}: число строк превышает допустимый предел")
        frame = SecureFileInspector.sanitize_dataframe(frame)

        normalized_columns = [self._normalize_header(value) for value in frame.columns]
        if len(set(normalized_columns)) != len(normalized_columns):
            raise SourceSchemaError(f"{table_name}: дублирующиеся колонки после нормализации")

        actual_columns = set(normalized_columns)
        expected_columns = set(columns)
        missing = sorted(expected_columns - actual_columns)
        extra = sorted(actual_columns - expected_columns)
        if missing or extra:
            details = []
            if missing:
                details.append(f"отсутствуют колонки: {', '.join(missing)}")
            if extra:
                details.append(f"лишние колонки: {', '.join(extra)}")
            raise SourceSchemaError(f"{table_name}: {'; '.join(details)}")

        frame.columns = normalized_columns
        return frame.rename(columns=columns)

    @staticmethod
    def _normalize_header(value: Any) -> str:
        if not isinstance(value, str):
            raise SourceSchemaError("Заголовок колонки должен быть строкой")
        return " ".join(value.replace("\u00a0", " ").split())

    @classmethod
    def _to_channel_type(cls, row: pd.Series) -> ChannelType:
        type_id = cls._integer(row["type_id"], "ИД типа канала датчика")
        if type_id not in CHANNEL_TYPE_SLUGS:
            raise SourceSchemaError(
                f"Типы каналов: неподдерживаемый ИД типа канала датчика {type_id}"
            )
        return ChannelType(
            type_id=type_id,
            name=cls._text(row["name"], "Название"),
            dispatch_name=cls._text(row["dispatch_name"], "Диспетчерское название"),
            slug=CHANNEL_TYPE_SLUGS[type_id],
        )

    @classmethod
    def _to_channel(cls, row: pd.Series) -> DataChannel:
        return DataChannel(
            channel_id=cls._integer(row["channel_id"], "ИД канала данных"),
            object_tag=cls._text(row["object_tag"], "Тег в дереве объектов"),
        )

    @classmethod
    def _to_event(cls, row: pd.Series) -> EventJournalEntry:
        raw_timestamp = row["recorded_at"]
        if not isinstance(raw_timestamp, str):
            raise SourceSchemaError("Дата записи должна соответствовать формату dd.MM.yyyy HH:mm")
        if not raw_timestamp or not cls.TIMESTAMP_PATTERN.fullmatch(raw_timestamp):
            raise SourceSchemaError("Дата записи должна соответствовать формату dd.MM.yyyy HH:mm")
        try:
            recorded_at = datetime.strptime(raw_timestamp, cls.TIMESTAMP_FORMAT)
        except ValueError as error:
            raise SourceSchemaError(
                "Дата записи должна соответствовать формату dd.MM.yyyy HH:mm"
            ) from error
        return EventJournalEntry(
            event_id=cls._integer(row["event_id"], "ИД записи журнала"),
            channel_id=cls._integer(row["channel_id"], "ИД канала данных"),
            channel_type_id=cls._integer(row["channel_type_id"], "ИД типа канала данных"),
            current_value=cls._text(row["current_value"], "Текущее значение"),
            recorded_at=recorded_at,
        )

    @classmethod
    def _to_tree_node(cls, row: pd.Series) -> ObjectSystemTreeNode:
        return ObjectSystemTreeNode(
            record_id=cls._integer(row["record_id"], "ИД записи"),
            system_id=cls._integer(row["system_id"], "ИД системы"),
            dispatch_name=cls._text(row["dispatch_name"], "Диспетчерское название"),
            name=cls._text(row["name"], "Название"),
        )

    @staticmethod
    def _text(value: Any, column_name: str) -> str:
        if pd.isna(value):
            raise SourceSchemaError(f"{column_name}: значение обязательно")
        text = str(value).strip()
        if not text:
            raise SourceSchemaError(f"{column_name}: значение обязательно")
        return text

    @classmethod
    def _integer(cls, value: Any, column_name: str) -> int:
        if isinstance(value, bool) or pd.isna(value):
            raise SourceSchemaError(f"{column_name}: ожидается целочисленный идентификатор")
        if isinstance(value, int):
            identifier = value
        elif isinstance(value, float) and value.is_integer():
            identifier = int(value)
        else:
            text = cls._text(value, column_name)
            if not text.isdecimal():
                raise SourceSchemaError(f"{column_name}: ожидается целочисленный идентификатор")
            identifier = int(text)
        if identifier <= 0:
            raise SourceSchemaError(f"{column_name}: ожидается целочисленный идентификатор")
        return identifier

    @staticmethod
    def _validate_unique(records: tuple[Any, ...], field_name: str, table_name: str) -> None:
        identifiers = [getattr(record, field_name) for record in records]
        if len(identifiers) != len(set(identifiers)):
            raise SourceSchemaError(f"{table_name}: обнаружен дубликат идентификатора")

    @staticmethod
    def _validate_references(
        events: tuple[EventJournalEntry, ...],
        channels: tuple[DataChannel, ...],
        channel_types: tuple[ChannelType, ...],
    ) -> None:
        channel_ids = {channel.channel_id for channel in channels}
        type_ids = {channel_type.type_id for channel_type in channel_types}
        for event in events:
            if event.channel_id not in channel_ids:
                raise SourceSchemaError(
                    f"Журнал событий: ссылка на отсутствующий канал {event.channel_id}"
                )
            if event.channel_type_id not in type_ids:
                raise SourceSchemaError(
                    f"Журнал событий: ссылка на отсутствующий тип {event.channel_type_id}"
                )
