"""Построение ограниченного локального снимка из принятой CSV-выгрузки."""

from __future__ import annotations

import csv
import hashlib
import heapq
import json
import re
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from typing import Final

import pandas as pd

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[4]
RAW_DATA_ROOT: Final[Path] = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_ROOT: Final[Path] = PROJECT_ROOT / "data" / "processed"
MAX_SUPPLEMENTAL_JOURNAL_BYTES: Final[int] = 32 * 1024 * 1024
MAX_EVENTS: Final[int] = 500
MAX_CSV_FILES: Final[int] = 64
# Ограничения остаются конечными, но учитывают фактические годовые выгрузки.
MAX_CSV_FILE_BYTES: Final[int] = 4 * 1024 * 1024 * 1024
MAX_CSV_TOTAL_BYTES: Final[int] = 32 * 1024 * 1024 * 1024
MAX_CSV_ROWS: Final[int] = 8_000_000
MAX_CSV_TOTAL_ROWS: Final[int] = 8_500_000
MAX_CSV_FIELD_CHARS: Final[int] = 1_024
EVENT_CHUNK_ROWS: Final[int] = 10_000
# Должен совпадать с максимумом, который принимает Next.js-маршрут снимка.
MAX_PUBLIC_SNAPSHOT_BYTES: Final[int] = 8 * 1024 * 1024
YEAR_IN_FILENAME: Final[re.Pattern[str]] = re.compile(r"(?:^|[-_])(\d{4})(?:[-_.]|$)")
CSV_FIELD_LIMIT_LOCK = Lock()

EVENT_HEADERS: Final[frozenset[str]] = frozenset(
    {
        "ид_события",
        "ид_канала_данных",
        "дата",
        "время",
        "тревожное",
        "значение_датчика",
    }
)
CHANNEL_HEADERS: Final[frozenset[str]] = frozenset(
    {
        "ид_канала_данных",
        "тип_инж_системы",
        "тип_датчика",
        "тег_инженерной_системы",
        "название_датчика",
    }
)
UPDATED_CHANNEL_HEADERS: Final[frozenset[str]] = CHANNEL_HEADERS | {"ид_объект"}
OBJECT_HEADERS: Final[frozenset[str]] = frozenset(
    {
        "ид_объект",
        "иерархия_уровень",
        "родитель",
        "вид_объекта",
        "диспетчерское_название_объекта",
    }
)


class SourceSnapshotError(ValueError):
    """Локальная CSV-выгрузка либо путь снимка не удовлетворяет контракту."""


@dataclass(frozen=True)
class SourceMetadata:
    """Агрегаты источника без локальных путей и имён файлов."""

    journal_file_count: int
    selected_journal_file_count: int
    scanned_event_count: int
    skipped_event_count: int
    channel_count: int
    object_count: int
    latest_observed_at: str | None


@dataclass(frozen=True)
class DataQuality:
    """Безопасные агрегаты качества, разрешённые для публичного UI."""

    built_at: str
    latest_observed_at: str | None
    event_count: int
    skipped_timestamp_count: int
    technical_anomaly_count: int
    unmapped_channel_count: int
    object_link_available: bool
    freshness: str


@dataclass(frozen=True)
class ChannelRegistryEntry:
    channel_id: str
    engineering_system_type: str
    sensor_type: str
    engineering_system_tag: str
    sensor_name: str
    object_id: str | None


@dataclass(frozen=True)
class ObjectRegistryEntry:
    object_id: str
    hierarchy_level: str
    parent_id: str | None
    object_kind: str
    dispatcher_name: str


@dataclass(frozen=True)
class ObservedEvent:
    canonical_id: str
    event_id: str
    channel_id: str
    recorded_at: str
    is_alarm: bool | None
    sensor_value: str
    quality_code: str
    analysis_eligible: bool
    provenance: str


@dataclass(frozen=True)
class LocalSituationSnapshot:
    """Минимальный локальный снимок наблюдаемых событий, без ML-прогнозов."""

    source_metadata: SourceMetadata
    data_quality: DataQuality
    source_availability: dict[str, bool]
    channels: tuple[ChannelRegistryEntry, ...]
    objects: tuple[ObjectRegistryEntry, ...]
    events: tuple[ObservedEvent, ...]

    def to_dict(self) -> dict[str, object]:
        """Сериализует публичный контракт без путей и агрегатов первичных данных."""
        return {
            "sourceAvailability": self.source_availability,
            "dataQuality": _camel_case(asdict(self.data_quality)),
            "channels": [_camel_case(asdict(channel)) for channel in self.channels],
            "objects": [_camel_case(asdict(obj)) for obj in self.objects],
            "events": [_camel_case(asdict(event)) for event in self.events],
        }


def build_local_snapshot(
    raw_root: Path, output_path: Path, max_events: int = 500
) -> LocalSituationSnapshot:
    """Строит снимок из разрешённой локальной выгрузки, не читая старые журналы."""
    if not 0 < max_events <= MAX_EVENTS:
        raise SourceSnapshotError(f"Лимит наблюдаемых событий должен быть от 1 до {MAX_EVENTS}")

    checked_raw_root = _guard_directory(raw_root, _raw_data_root(), "Каталог источника")
    checked_output_path = _guard_output_path(output_path)
    discovered = _discover_csv_roles(checked_raw_root)
    selected_journals = _select_journals(discovered["journals"])
    _validate_selected_csv_inputs(
        (*selected_journals, discovered["channels"], discovered["objects"])
    )

    objects = _read_objects(discovered["objects"])
    channels, object_link_available = _read_channels(
        discovered["channels"], {item.object_id for item in objects}
    )
    events, scanned_event_count, skipped_event_count = _read_latest_events(
        selected_journals, max_events
    )
    latest_observed_at = events[0].recorded_at if events else None
    snapshot = LocalSituationSnapshot(
        source_metadata=SourceMetadata(
            journal_file_count=len(discovered["journals"]),
            selected_journal_file_count=len(selected_journals),
            scanned_event_count=scanned_event_count,
            skipped_event_count=skipped_event_count,
            channel_count=len(channels),
            object_count=len(objects),
            latest_observed_at=latest_observed_at,
        ),
        data_quality=DataQuality(
            built_at=datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            latest_observed_at=latest_observed_at,
            event_count=len(events),
            skipped_timestamp_count=skipped_event_count,
            technical_anomaly_count=sum(
                event.quality_code in {"technical_anomaly", "alarm_with_technical_value"}
                for event in events
            ),
            unmapped_channel_count=sum(channel.object_id is None for channel in channels),
            object_link_available=object_link_available,
            freshness="historical",
        ),
        source_availability={
            "events": True,
            "channels": True,
            "objects": True,
            "access_events": False,
            "maintenance_history": False,
            "ml_predictions": False,
            "work_permits": False,
        },
        channels=channels,
        objects=objects,
        events=events,
    )
    _write_snapshot(snapshot, checked_output_path)
    return snapshot


def _discover_csv_roles(raw_root: Path) -> dict[str, object]:
    journals: list[Path] = []
    registries: dict[str, Path] = {}
    for checked_path in _discover_bounded_csv_files(raw_root):
        role = _detect_csv_role(checked_path)
        if role == "journal":
            journals.append(checked_path)
            continue
        if role in registries:
            raise SourceSnapshotError("Обнаружен дубликат CSV-справочника одной роли")
        registries[role] = checked_path

    if not journals:
        raise SourceSnapshotError("Не найден журнал событий с документированной схемой")
    if "channels" not in registries or "objects" not in registries:
        raise SourceSnapshotError("Не найдены все обязательные CSV-справочники")
    return {"journals": tuple(journals), **registries}


def _discover_bounded_csv_files(raw_root: Path) -> tuple[Path, ...]:
    """Ограничивает перечисление и объём до чтения заголовков CSV."""
    discovered: list[Path] = []
    total_size = 0
    for path in raw_root.rglob("*.csv"):
        if len(discovered) >= MAX_CSV_FILES:
            raise SourceSnapshotError("Превышено допустимое число CSV-файлов")
        checked_path = _guard_file(path, _raw_data_root(), "Файл источника")
        try:
            size = checked_path.stat().st_size
        except OSError as error:
            raise SourceSnapshotError("Не удалось проверить размер CSV-файла") from error
        if size > MAX_CSV_FILE_BYTES:
            raise SourceSnapshotError("Превышен допустимый размер CSV-файла")
        total_size += size
        if total_size > MAX_CSV_TOTAL_BYTES:
            raise SourceSnapshotError("Превышен допустимый совокупный размер CSV")
        discovered.append(checked_path)
    return tuple(sorted(discovered))


def _detect_csv_role(path: Path) -> str:
    with _bounded_csv_field_limit(), path.open("r", encoding="utf-8-sig", newline="") as stream:
        header = next(csv.reader(stream), None)
    if header is None:
        raise SourceSnapshotError("Пустой CSV не соответствует документированной схеме")
    normalized_header = tuple(_normalize_header(value) for value in header)
    if len(set(normalized_header)) != len(normalized_header):
        raise SourceSnapshotError("CSV содержит дублирующиеся заголовки")
    headers = frozenset(normalized_header)
    if headers == EVENT_HEADERS:
        return "journal"
    if headers in {CHANNEL_HEADERS, UPDATED_CHANNEL_HEADERS}:
        return "channels"
    if headers == OBJECT_HEADERS:
        return "objects"
    raise SourceSnapshotError("Обнаружен CSV с неизвестной схемой заголовков")


def _validate_selected_csv_inputs(paths: tuple[Path, ...]) -> None:
    """Проверяет строки и поля только файлов, которые будут переданы парсерам."""
    total_rows = 0
    for path in paths:
        total_rows += _count_bounded_csv_rows(path)
        if total_rows > MAX_CSV_TOTAL_ROWS:
            raise SourceSnapshotError("Превышено допустимое совокупное число строк CSV")


def _count_bounded_csv_rows(path: Path) -> int:
    row_count = 0
    with _bounded_csv_field_limit(), path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        next(reader, None)
        for row in reader:
            if not row:
                continue
            row_count += 1
            if row_count > MAX_CSV_ROWS:
                raise SourceSnapshotError("Превышено допустимое число строк CSV")
    return row_count


def _select_journals(journals: tuple[Path, ...]) -> tuple[Path, ...]:
    year_labelled: list[tuple[int, Path]] = []
    supplemental: list[Path] = []
    for path in journals:
        match = YEAR_IN_FILENAME.search(path.name)
        if match:
            year_labelled.append((int(match.group(1)), path))
        elif path.stat().st_size <= MAX_SUPPLEMENTAL_JOURNAL_BYTES:
            supplemental.append(path)
    if not year_labelled:
        raise SourceSnapshotError("Не найден журнал с годовой меткой в имени")
    latest_year = max(year for year, _ in year_labelled)
    latest = tuple(path for year, path in year_labelled if year == latest_year)
    if len(latest) != 1:
        raise SourceSnapshotError("Обнаружен дубликат последнего годового журнала")
    return (*latest, *sorted(supplemental))


def _read_channels(
    path: Path, object_ids: set[str]
) -> tuple[tuple[ChannelRegistryEntry, ...], bool]:
    records: list[ChannelRegistryEntry] = []
    identifiers: set[str] = set()
    object_link_available = _read_header_set(path) == UPDATED_CHANNEL_HEADERS
    for row in _read_rows(path):
        channel_id = _required(row, "ид_канала_данных")
        if channel_id in identifiers:
            raise SourceSnapshotError("Справочник каналов содержит дубликат идентификатора")
        identifiers.add(channel_id)
        object_id = row.get("ид_объект") or None
        if object_id is not None and object_id not in object_ids:
            raise SourceSnapshotError("Справочник каналов ссылается на несуществующий объект")
        records.append(
            ChannelRegistryEntry(
                channel_id=channel_id,
                engineering_system_type=_required(row, "тип_инж_системы"),
                sensor_type=_required(row, "тип_датчика"),
                engineering_system_tag=_required(row, "тег_инженерной_системы"),
                sensor_name=_required(row, "название_датчика"),
                object_id=object_id,
            )
        )
    return tuple(records), object_link_available


def _read_objects(path: Path) -> tuple[ObjectRegistryEntry, ...]:
    records: list[ObjectRegistryEntry] = []
    identifiers: set[str] = set()
    for row in _read_rows(path):
        object_id = _required(row, "ид_объект")
        if object_id in identifiers:
            raise SourceSnapshotError("Справочник объектов содержит дубликат идентификатора")
        identifiers.add(object_id)
        parent_id = row["родитель"]
        records.append(
            ObjectRegistryEntry(
                object_id=object_id,
                hierarchy_level=_required(row, "иерархия_уровень"),
                parent_id=parent_id if parent_id else None,
                object_kind=_required(row, "вид_объекта"),
                dispatcher_name=_required(row, "диспетчерское_название_объекта"),
            )
        )
    return tuple(records)


def _read_latest_events(
    journals: tuple[Path, ...], max_events: int
) -> tuple[tuple[ObservedEvent, ...], int, int]:
    heap: list[tuple[datetime, int, ObservedEvent]] = []
    scanned_event_count = 0
    skipped_event_count = 0
    for path in journals:
        for chunk in _read_event_chunks(path):
            scanned_event_count += len(chunk)
            complete_rows = (
                chunk[list(EVENT_HEADERS)]
                .fillna("")
                .apply(lambda column: column.astype(str).str.len() > 0)
                .all(axis=1)
            )
            timestamps = _parse_chunk_timestamps(chunk)
            invalid_rows = timestamps.isna() | ~complete_rows
            skipped_event_count += int(invalid_rows.sum())
            timestamps = timestamps.loc[~invalid_rows]
            for offset, index in enumerate(
                timestamps.nlargest(min(max_events, len(chunk))).index, start=1
            ):
                recorded_at = timestamps.loc[index].to_pydatetime()
                event_id = _required_value(chunk.at[index, "ид_события"])
                channel_id = _required_value(chunk.at[index, "ид_канала_данных"])
                is_alarm = _parse_alarm(chunk.at[index, "тревожное"])
                sensor_value = _required_value(chunk.at[index, "значение_датчика"])
                quality_code, analysis_eligible = _classify_event_quality(
                    sensor_value, is_alarm, recorded_at
                )
                event = ObservedEvent(
                    canonical_id=_canonical_event_id(event_id, channel_id, recorded_at),
                    event_id=event_id,
                    channel_id=channel_id,
                    recorded_at=recorded_at.isoformat(timespec="seconds"),
                    is_alarm=is_alarm,
                    sensor_value=sensor_value,
                    quality_code=quality_code,
                    analysis_eligible=analysis_eligible,
                    provenance="observed",
                )
                candidate = (recorded_at, scanned_event_count - len(chunk) + offset, event)
                if len(heap) < max_events:
                    heapq.heappush(heap, candidate)
                elif candidate[:2] > heap[0][:2]:
                    heapq.heapreplace(heap, candidate)
    return (
        tuple(item[2] for item in sorted(heap, reverse=True)),
        scanned_event_count,
        skipped_event_count,
    )


def _read_event_chunks(path: Path):
    """Потоково читает журнал C-парсером фиксированными порциями, не сохраняя журнал в памяти."""
    try:
        _validate_journal_rows(path)
        chunks = pd.read_csv(
            path,
            encoding="utf-8-sig",
            dtype=str,
            keep_default_na=False,
            chunksize=EVENT_CHUNK_ROWS,
        )
        for chunk in chunks:
            chunk.columns = [_normalize_header(column) for column in chunk.columns]
            yield chunk
    except (OSError, UnicodeError, pd.errors.ParserError, KeyError) as error:
        raise SourceSnapshotError("Журнал событий не удалось потоково прочитать") from error


def _parse_chunk_timestamps(chunk: pd.DataFrame) -> pd.Series:
    combined = chunk["дата"] + "T" + chunk["время"]
    timestamps = pd.Series(pd.NaT, index=combined.index, dtype="datetime64[ns]")
    for timestamp_format in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%d.%m.%YT%H:%M:%S",
        "%d.%m.%YT%H:%M",
    ):
        unresolved = timestamps.isna()
        if not unresolved.any():
            break
        timestamps.loc[unresolved] = pd.to_datetime(
            combined.loc[unresolved], format=timestamp_format, errors="coerce"
        )
    return timestamps


def _validate_journal_rows(path: Path) -> None:
    """Отклоняет строки журнала с иным числом полей до передачи их Pandas."""
    with _bounded_csv_field_limit(), path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader, None)
        normalized_header = tuple(_normalize_header(value) for value in header) if header else ()
        if (
            len(normalized_header) != len(EVENT_HEADERS)
            or frozenset(normalized_header) != EVENT_HEADERS
        ):
            raise SourceSnapshotError("Журнал событий не соответствует документированной схеме")
        for row in reader:
            if len(row) > len(EVENT_HEADERS):
                raise SourceSnapshotError("Строка журнала имеет неверное число полей")


def _read_rows(path: Path):
    with _bounded_csv_field_limit(), path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise SourceSnapshotError("Пустой CSV не соответствует документированной схеме")
        normalized_headers = [_normalize_header(value) for value in reader.fieldnames]
        if len(set(normalized_headers)) != len(normalized_headers):
            raise SourceSnapshotError("CSV содержит дублирующиеся заголовки")
        reader.fieldnames = normalized_headers
        for row in reader:
            if None in row:
                raise SourceSnapshotError("Строка CSV содержит больше значений, чем заголовков")
            yield row


@contextmanager
def _bounded_csv_field_limit():
    """Сериализует временный лимит глобального CSV-парсера Python."""
    with CSV_FIELD_LIMIT_LOCK:
        previous_limit = csv.field_size_limit()
        csv.field_size_limit(MAX_CSV_FIELD_CHARS)
        try:
            yield
        except csv.Error as error:
            raise SourceSnapshotError("Превышен допустимый размер поля CSV") from error
        finally:
            csv.field_size_limit(previous_limit)


def _parse_recorded_at(row: dict[str, str | None]) -> datetime:
    date_value = _required(row, "дата")
    time_value = _required(row, "время")
    combined_value = f"{date_value}T{time_value}"
    try:
        return datetime.fromisoformat(combined_value)
    except ValueError:
        pass
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(f"{date_value} {time_value}", pattern)
        except ValueError:
            continue
    raise SourceSnapshotError("Дата и время журнала не соответствуют документированному формату")


def _parse_alarm(value: str | None) -> bool | None:
    normalized = _required_value(value).strip().casefold()
    if normalized in {
        "1",
        "true",
        "да",
        "yes",
        "on",
        "тревога",
        "истина",
        "есть",
    }:
        return True
    if normalized in {
        "0",
        "false",
        "нет",
        "no",
        "off",
        "норма",
        "ложь",
        "нет тревоги",
    }:
        return False
    try:
        numeric_value = Decimal(normalized.replace(",", "."))
    except InvalidOperation:
        numeric_value = None
    if numeric_value is None or not numeric_value.is_finite():
        return None
    return numeric_value != Decimal(0)


def _classify_event_quality(
    sensor_value: str, is_alarm: bool | None, recorded_at: datetime
) -> tuple[str, bool]:
    """Применяет утверждённые правила пригодности без изменения исходного значения."""
    if recorded_at.year == 2021:
        return "monitoring_system_migration", False
    normalized = sensor_value.strip().casefold()
    if normalized in {
        "-3276",
        "-127",
        "-100",
        "-255",
        "01.01.1970 03:00:00",
        "1970-01-01t03:00:00",
    }:
        if is_alarm is True:
            return "alarm_with_technical_value", True
        return "technical_anomaly", False
    return "valid", True


def _canonical_event_id(event_id: str, channel_id: str, recorded_at: datetime) -> str:
    identity = "\0".join(
        ("smvu-v1", event_id, channel_id, recorded_at.isoformat(timespec="seconds"))
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _required(row: dict[str, str | None], field: str) -> str:
    return _required_value(row[field])


def _required_value(value: str | None) -> str:
    if value is None or not value:
        raise SourceSnapshotError("Обязательное поле CSV не заполнено")
    return value


def _normalize_header(value: str) -> str:
    return value.removeprefix("\ufeff")


def _read_header_set(path: Path) -> frozenset[str]:
    with _bounded_csv_field_limit(), path.open("r", encoding="utf-8-sig", newline="") as stream:
        header = next(csv.reader(stream), None)
    if header is None:
        raise SourceSnapshotError("Пустой CSV не соответствует документированной схеме")
    return frozenset(_normalize_header(value) for value in header)


def _guard_directory(value: Path, allowed_root: Path, label: str) -> Path:
    path = _guard_path(value, allowed_root, label)
    if not path.is_dir():
        raise SourceSnapshotError(f"{label} не существует")
    return path


def _guard_file(value: Path, allowed_root: Path, label: str) -> Path:
    path = _guard_path(value, allowed_root, label)
    if not path.is_file():
        raise SourceSnapshotError(f"{label} не существует")
    return path


def _guard_output_path(value: Path) -> Path:
    path = _guard_path(value, _processed_data_root(), "Путь снимка")
    if path.suffix.lower() != ".json":
        raise SourceSnapshotError("Путь снимка должен указывать на файл JSON в data/processed")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _guard_path(value: Path, allowed_root: Path, label: str) -> Path:
    raw_value = str(value)
    if raw_value.startswith(("\\\\", "//")):
        raise SourceSnapshotError(f"{label}: UNC-пути не допускаются")
    allowed = allowed_root.resolve(strict=False)
    resolved = Path(value).resolve(strict=False)
    if not resolved.is_relative_to(allowed):
        raise SourceSnapshotError(f"{label} должен находиться в data/processed или data/raw")
    return resolved


def _raw_data_root() -> Path:
    return PROJECT_ROOT / "data" / "raw"


def _processed_data_root() -> Path:
    return PROJECT_ROOT / "data" / "processed"


def _write_snapshot(snapshot: LocalSituationSnapshot, output_path: Path) -> None:
    temporary_path: Path | None = None
    written_bytes = 0
    encoder = json.JSONEncoder(ensure_ascii=False, indent=2, sort_keys=True)
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=output_path.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            for fragment in (*encoder.iterencode(snapshot.to_dict()), "\n"):
                encoded_fragment = fragment.encode("utf-8")
                written_bytes += len(encoded_fragment)
                if written_bytes > MAX_PUBLIC_SNAPSHOT_BYTES:
                    raise SourceSnapshotError("Превышен допустимый размер публичного снимка")
                temporary.write(fragment)
        temporary_path.replace(output_path)
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def _camel_case(record: dict[str, object]) -> dict[str, object]:
    return {_snake_to_camel(key): value for key, value in record.items()}


def _snake_to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)
