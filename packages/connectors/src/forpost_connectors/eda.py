"""Потоковый разведочный анализ локальной выгрузки СМВУ."""

from __future__ import annotations

import csv
import html
import json
import math
import os
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Final

import numpy as np
import pandas as pd

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[4]
EVENT_HEADERS: Final[frozenset[str]] = frozenset(
    {"ид_события", "ид_канала_данных", "дата", "время", "тревожное", "значение_датчика"}
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
OBJECT_HEADERS: Final[frozenset[str]] = frozenset(
    {"ид_объект", "иерархия_уровень", "родитель", "вид_объекта", "диспетчерское_название_объекта"}
)
TRUE_VALUES: Final[frozenset[str]] = frozenset(
    {"1", "true", "да", "yes", "on", "тревога", "истина", "есть"}
)
FALSE_VALUES: Final[frozenset[str]] = frozenset(
    {"0", "false", "нет", "no", "off", "норма", "ложь", "нет тревоги"}
)
NON_FINITE_VALUE_TOKENS: Final[frozenset[str]] = frozenset(
    {"nan", "+nan", "-nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}
)
WEEKDAY_LABELS: Final[tuple[str, ...]] = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
MONTH_LABELS: Final[tuple[str, ...]] = (
    "Янв",
    "Фев",
    "Мар",
    "Апр",
    "Май",
    "Июн",
    "Июл",
    "Авг",
    "Сен",
    "Окт",
    "Ноя",
    "Дек",
)
DEFAULT_MAX_BITMAP_BYTES: Final[int] = 2 * 1024 * 1024 * 1024
MAX_CHUNK_SIZE: Final[int] = 1_000_000
DEFAULT_MAX_CSV_FILES: Final[int] = 512
DEFAULT_MAX_DISCOVERY_ENTRIES: Final[int] = 50_000
DEFAULT_MAX_INPUT_BYTES: Final[int] = 256 * 1024 * 1024 * 1024
DEFAULT_MAX_REGISTRY_ROWS: Final[int] = 2_000_000
EXTERNAL_DUPLICATE_MIN_BUCKET_COUNT: Final[int] = 64
EXTERNAL_DUPLICATE_BUCKET_MAX_BYTES: Final[int] = 256 * 1024 * 1024
EXTERNAL_DUPLICATE_DISK_RESERVE_BYTES: Final[int] = 256 * 1024 * 1024


class EdaError(ValueError):
    """Источник или выход EDA не удовлетворяет локальному контракту."""


@dataclass(frozen=True)
class EdaConfig:
    allowed_raw_root: Path = PROJECT_ROOT / "data" / "raw"
    allowed_interim_root: Path = PROJECT_ROOT / "data" / "interim"
    allowed_docs_root: Path = PROJECT_ROOT / "docs"
    chunk_size: int = 500_000
    silent_days: int = 30
    outlier_z: float = 5.0
    max_bitmap_bytes: int = DEFAULT_MAX_BITMAP_BYTES
    max_csv_files: int = DEFAULT_MAX_CSV_FILES
    max_discovery_entries: int = DEFAULT_MAX_DISCOVERY_ENTRIES
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES
    max_registry_rows: int = DEFAULT_MAX_REGISTRY_ROWS

    def __post_init__(self) -> None:
        try:
            raw_root = self.allowed_raw_root.resolve(strict=False)
            interim_root = self.allowed_interim_root.resolve(strict=False)
        except (OSError, RuntimeError) as error:
            raise EdaError("Не удалось проверить локальные корни EDA") from error
        if interim_root != raw_root.parent / "interim":
            raise EdaError("Корень промежуточных результатов должен быть data/interim")
        if self.chunk_size < 1:
            raise EdaError("Размер порции должен быть положительным")
        if self.chunk_size > MAX_CHUNK_SIZE:
            raise EdaError("Размер порции превышает безопасный лимит")
        if self.silent_days < 1:
            raise EdaError("Порог тишины должен быть положительным")
        if not math.isfinite(self.outlier_z) or self.outlier_z <= 0:
            raise EdaError("Порог z-score должен быть положительным конечным числом")
        if self.max_bitmap_bytes < 1:
            raise EdaError("Лимит битовой карты должен быть положительным")
        if self.max_csv_files < 3:
            raise EdaError("Лимит CSV должен учитывать журналы и два справочника")
        if self.max_discovery_entries < self.max_csv_files:
            raise EdaError("Лимит обхода должен быть не меньше лимита CSV")
        if self.max_input_bytes < 1:
            raise EdaError("Лимит входных данных должен быть положительным")
        if self.max_registry_rows < 1:
            raise EdaError("Лимит строк справочника должен быть положительным")


@dataclass(frozen=True)
class ChannelMetric:
    channel_id: str
    sensor_type: str
    event_count: int
    timed_event_count: int
    undated_event_count: int
    active_day_count: int
    events_per_active_day: float
    first_at: str | None
    last_at: str | None
    numeric_count: int
    numeric_mean: float | None
    numeric_std: float | None
    numeric_min: float | None
    numeric_max: float | None
    statistical_outlier_count: int
    is_never_seen: bool
    is_silent: bool
    silence_status: str
    is_noisy: bool


@dataclass(frozen=True)
class SourceMetric:
    name: str
    row_count: int
    valid_timestamp_count: int
    invalid_timestamp_count: int


@dataclass(frozen=True)
class EdaResult:
    total_rows: int
    valid_timestamp_rows: int
    invalid_timestamp_rows: int
    earliest_at: str | None
    latest_at: str | None
    max_event_id: int
    bitmap_bytes: int
    journal_file_count: int
    channel_count: int
    object_count: int
    unknown_channel_event_count: int
    invalid_event_id_count: int
    duplicate_event_id_count: int
    missing_counts: dict[str, int]
    alarm_true_count: int
    alarm_false_count: int
    alarm_unknown_count: int
    numeric_value_count: int
    non_numeric_value_count: int
    non_finite_value_count: int
    statistical_outlier_count: int
    events_by_year: dict[int, int]
    events_by_hour: dict[int, int]
    events_by_weekday: dict[int, int]
    events_by_month: dict[int, int]
    events_by_sensor_type: dict[str, int]
    channel_type_counts: dict[str, int]
    silent_channel_count: int
    never_seen_channel_count: int
    silence_undetermined_channel_count: int
    noisy_channel_count: int
    noise_q1: float
    noise_q3: float
    noise_iqr: float
    noise_threshold: float
    coverage_years: float
    largest_observed_gap_days: int
    largest_gap_starts_at: str | None
    largest_gap_ends_at: str | None
    false_positive_rate: None
    source_metrics: tuple[SourceMetric, ...]
    channel_metrics: tuple[ChannelMetric, ...]
    parameters: dict[str, int | float]

    def profile_dict(self) -> dict[str, object]:
        """Возвращает агрегированный профиль без поканальных идентификаторов."""
        payload = asdict(self)
        payload.pop("channel_metrics")
        return payload


@dataclass
class _Accumulator:
    channel_ids: tuple[str, ...]
    sensor_types: tuple[str, ...]
    channel_index: dict[str, int]
    total_rows: int = 0
    valid_timestamp_rows: int = 0
    invalid_timestamp_rows: int = 0
    earliest: pd.Timestamp | None = None
    latest: pd.Timestamp | None = None
    max_event_id: int = 0
    invalid_event_id_count: int = 0
    unknown_channel_event_count: int = 0
    missing_counts: dict[str, int] = field(
        default_factory=lambda: dict.fromkeys(sorted(EVENT_HEADERS), 0)
    )
    alarm_true_count: int = 0
    alarm_false_count: int = 0
    alarm_unknown_count: int = 0
    numeric_value_count: int = 0
    non_numeric_value_count: int = 0
    non_finite_value_count: int = 0
    events_by_year: dict[int, int] = field(default_factory=dict)
    events_by_hour: dict[int, int] = field(default_factory=dict)
    events_by_weekday: dict[int, int] = field(default_factory=dict)
    events_by_month: dict[int, int] = field(default_factory=dict)
    events_by_sensor_type: dict[str, int] = field(default_factory=dict)
    source_metrics: list[SourceMetric] = field(default_factory=list)
    active_days: dict[int, np.ndarray] = field(default_factory=dict)
    observed_days: set[date] = field(default_factory=set)

    def __post_init__(self) -> None:
        size = len(self.channel_ids)
        self.event_count = np.zeros(size, dtype=np.int64)
        self.timed_event_count = np.zeros(size, dtype=np.int64)
        self.numeric_count = np.zeros(size, dtype=np.int64)
        self.numeric_sum = np.zeros(size, dtype=np.float64)
        self.numeric_sum_squares = np.zeros(size, dtype=np.float64)
        self.numeric_min = np.full(size, np.inf, dtype=np.float64)
        self.numeric_max = np.full(size, -np.inf, dtype=np.float64)
        self.first_ns = np.full(size, np.iinfo(np.int64).max, dtype=np.int64)
        self.last_ns = np.full(size, np.iinfo(np.int64).min, dtype=np.int64)


def analyze_dataset(
    raw_root: Path,
    config: EdaConfig | None = None,
    *,
    duplicate_temp_root: Path | None = None,
) -> EdaResult:
    """Выполняет два точных потоковых прохода по всем журналам выгрузки."""
    settings = config or EdaConfig()
    checked_root = _guard_directory(raw_root, settings.allowed_raw_root, "Источник")
    journals, channels_path, objects_path = _discover_sources(checked_root, settings)
    channels = _read_registry(
        channels_path, CHANNEL_HEADERS, "ид_канала_данных", settings.max_registry_rows
    )
    objects = _read_registry(objects_path, OBJECT_HEADERS, "ид_объект", settings.max_registry_rows)
    channel_ids = tuple(row["ид_канала_данных"] for row in channels)
    sensor_types = tuple(row["тип_датчика"] for row in channels)
    accumulator = _Accumulator(
        channel_ids=channel_ids,
        sensor_types=sensor_types,
        channel_index={channel_id: index for index, channel_id in enumerate(channel_ids)},
    )

    for journal in journals:
        _first_pass(journal, accumulator, settings)

    bitmap_bytes = accumulator.max_event_id // 8 + 1
    duplicate_count, outlier_counts = _second_pass(
        journals,
        accumulator,
        settings,
        duplicate_temp_root=duplicate_temp_root,
    )
    return _build_result(
        accumulator,
        len(journals),
        len(objects),
        bitmap_bytes,
        duplicate_count,
        outlier_counts,
        settings,
    )


def _discover_sources(raw_root: Path, config: EdaConfig) -> tuple[tuple[Path, ...], Path, Path]:
    journals: list[Path] = []
    registries: dict[str, Path] = {}
    csv_paths: list[Path] = []
    discovered_entries = 0
    input_bytes = 0
    try:
        for current_root, directory_names, file_names in os.walk(raw_root, followlinks=False):
            directory_names.sort()
            file_names.sort()
            discovered_entries += len(directory_names) + len(file_names)
            if discovered_entries > config.max_discovery_entries:
                raise EdaError("Превышен лимит элементов рекурсивного обхода")
            for file_name in file_names:
                if not file_name.casefold().endswith(".csv"):
                    continue
                path = Path(current_root) / file_name
                csv_paths.append(path)
                if len(csv_paths) > config.max_csv_files:
                    raise EdaError("Превышен лимит CSV-файлов")
                input_bytes += path.stat().st_size
                if input_bytes > config.max_input_bytes:
                    raise EdaError("Превышен лимит объёма входных CSV")
    except OSError as error:
        raise EdaError("Не удалось безопасно обойти источник EDA") from error

    for path in csv_paths:
        checked = _guard_file(path, config.allowed_raw_root, "CSV-файл")
        role = _detect_role(checked)
        if role == "journal":
            journals.append(checked)
        elif role in registries:
            raise EdaError("Обнаружено несколько справочников одной роли")
        else:
            registries[role] = checked
    if not journals or "channels" not in registries or "objects" not in registries:
        raise EdaError("Не найден полный комплект журналов и справочников")
    return tuple(sorted(journals)), registries["channels"], registries["objects"]


def _detect_role(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            header = next(csv.reader(stream), None)
    except (OSError, UnicodeError) as error:
        raise EdaError("CSV-файл не удалось прочитать") from error
    normalized = tuple(value.removeprefix("\ufeff") for value in header or ())
    if len(normalized) != len(set(normalized)):
        raise EdaError("CSV содержит повторные заголовки")
    fields = frozenset(normalized)
    if fields == EVENT_HEADERS:
        return "journal"
    if fields == CHANNEL_HEADERS:
        return "channels"
    if fields == OBJECT_HEADERS:
        return "objects"
    raise EdaError("CSV содержит неизвестную схему")


def _read_registry(
    path: Path, headers: frozenset[str], key: str, max_rows: int
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    identifiers: set[str] = set()
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if frozenset(reader.fieldnames or ()) != headers:
                raise EdaError("Справочник не соответствует ожидаемой схеме")
            for row in reader:
                if len(records) >= max_rows:
                    raise EdaError("Превышен лимит строк справочника")
                if None in row or any(value is None or value == "" for value in row.values()):
                    raise EdaError("Справочник содержит пустое или лишнее поле")
                identifier = row[key]
                if identifier in identifiers:
                    raise EdaError("Справочник содержит повторный идентификатор")
                identifiers.add(identifier)
                records.append({name: str(value) for name, value in row.items()})
    except (OSError, UnicodeError, csv.Error) as error:
        raise EdaError("Справочник не удалось прочитать") from error
    return records


def _read_chunks(path: Path, chunk_size: int, *, validate_structure: bool = False):
    if validate_structure:
        yield from _read_validated_chunks(path, chunk_size)
        return
    try:
        chunks = pd.read_csv(
            path,
            encoding="utf-8-sig",
            dtype=str,
            keep_default_na=False,
            chunksize=chunk_size,
            engine="c",
        )
        for chunk in chunks:
            chunk.columns = [str(column).removeprefix("\ufeff") for column in chunk.columns]
            if frozenset(chunk.columns) != EVENT_HEADERS:
                raise EdaError("Журнал не соответствует ожидаемой схеме")
            yield chunk
    except (OSError, UnicodeError, pd.errors.ParserError) as error:
        raise EdaError("Журнал событий не удалось потоково прочитать") from error


def _read_validated_chunks(path: Path, chunk_size: int):
    """Читает CSV порциями и проверяет структуру в том же проходе."""
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream)
            header = next(reader, None)
            normalized_header = tuple(value.removeprefix("\ufeff") for value in header or ())
            if frozenset(normalized_header) != EVENT_HEADERS or len(normalized_header) != len(
                EVENT_HEADERS
            ):
                raise EdaError("Журнал не соответствует ожидаемой схеме")
            rows: list[list[str]] = []
            for row in reader:
                if len(row) != len(EVENT_HEADERS):
                    raise EdaError("Строка журнала имеет неверное число полей")
                rows.append(row)
                if len(rows) == chunk_size:
                    yield pd.DataFrame.from_records(rows, columns=normalized_header)
                    rows = []
            if rows:
                yield pd.DataFrame.from_records(rows, columns=normalized_header)
    except (OSError, UnicodeError, csv.Error) as error:
        raise EdaError("Журнал событий не удалось потоково прочитать") from error


def _parse_timestamps(chunk: pd.DataFrame) -> pd.Series:
    combined = chunk["дата"] + "T" + chunk["время"]
    result = pd.Series(pd.NaT, index=chunk.index, dtype="datetime64[ns]")
    for pattern in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%d.%m.%YT%H:%M:%S",
        "%d.%m.%YT%H:%M",
    ):
        unresolved = result.isna()
        if not unresolved.any():
            break
        result.loc[unresolved] = pd.to_datetime(
            combined.loc[unresolved], format=pattern, errors="coerce"
        )
    return result


def _parse_event_ids(series: pd.Series) -> tuple[np.ndarray, int]:
    """Возвращает корректные uint64 ID и число повреждённых значений без потери строк EDA."""
    values = series.astype(str).str.strip()
    digit_mask = values.str.fullmatch(r"\d+")
    canonical = values.str.lstrip("0").mask(lambda value: value.eq(""), "0")
    lengths = canonical.str.len()
    in_range = (lengths < 20) | (lengths.eq(20) & canonical.le("18446744073709551615"))
    valid = digit_mask & in_range
    return canonical.loc[valid].to_numpy(dtype=np.uint64), int((~valid).sum())


def _increment(target: dict[int, int], values: pd.Series) -> None:
    for key, count in values.value_counts().items():
        integer_key = int(key)
        target[integer_key] = target.get(integer_key, 0) + int(count)


def _first_pass(path: Path, acc: _Accumulator, config: EdaConfig) -> None:
    file_rows = 0
    file_valid = 0
    for chunk in _read_chunks(path, config.chunk_size):
        row_count = len(chunk)
        file_rows += row_count
        acc.total_rows += row_count
        for name in EVENT_HEADERS:
            acc.missing_counts[name] += int((chunk[name] == "").sum())

        event_ids, invalid_event_ids = _parse_event_ids(chunk["ид_события"])
        acc.invalid_event_id_count += invalid_event_ids
        if len(event_ids):
            acc.max_event_id = max(acc.max_event_id, int(event_ids.max()))

        channel_indices = chunk["ид_канала_данных"].map(acc.channel_index)
        known_channels = channel_indices.notna()
        acc.unknown_channel_event_count += int((~known_channels).sum())
        if known_channels.any():
            indices = channel_indices.loc[known_channels].to_numpy(dtype=np.int64)
            np.add.at(acc.event_count, indices, 1)

        alarm_values = chunk["тревожное"].str.strip().str.casefold()
        true_mask = alarm_values.isin(TRUE_VALUES)
        false_mask = alarm_values.isin(FALSE_VALUES)
        numeric_alarm = pd.to_numeric(
            alarm_values.str.replace(",", ".", regex=False), errors="coerce"
        )
        numeric_finite = np.isfinite(numeric_alarm.to_numpy(dtype=np.float64, na_value=np.nan))
        numeric_true = pd.Series(numeric_finite, index=chunk.index) & numeric_alarm.ne(0)
        numeric_false = pd.Series(numeric_finite, index=chunk.index) & numeric_alarm.eq(0)
        true_mask |= numeric_true
        false_mask |= numeric_false
        acc.alarm_true_count += int(true_mask.sum())
        acc.alarm_false_count += int(false_mask.sum())
        acc.alarm_unknown_count += int((~true_mask & ~false_mask).sum())

        raw_values = chunk["значение_датчика"]
        normalized_values = raw_values.str.strip().str.casefold()
        empty_values = normalized_values.eq("")
        numeric_values = pd.to_numeric(
            normalized_values.str.replace(",", ".", regex=False), errors="coerce"
        )
        numeric_array = numeric_values.to_numpy(dtype=np.float64, na_value=np.nan)
        finite_values = np.isfinite(numeric_array)
        explicit_non_finite = normalized_values.isin(NON_FINITE_VALUE_TOKENS)
        parsed_values = numeric_values.notna() | explicit_non_finite
        acc.numeric_value_count += int(finite_values.sum())
        acc.non_finite_value_count += int(
            (parsed_values & ~pd.Series(finite_values, index=chunk.index)).sum()
        )
        acc.non_numeric_value_count += int((~empty_values & ~parsed_values).sum())
        finite_known = finite_values & known_channels.to_numpy()
        if finite_known.any():
            idx = channel_indices.to_numpy(dtype=np.float64)[finite_known].astype(np.int64)
            vals = numeric_array[finite_known]
            np.add.at(acc.numeric_count, idx, 1)
            np.add.at(acc.numeric_sum, idx, vals)
            np.add.at(acc.numeric_sum_squares, idx, vals * vals)
            np.minimum.at(acc.numeric_min, idx, vals)
            np.maximum.at(acc.numeric_max, idx, vals)

        timestamps = _parse_timestamps(chunk)
        valid_time = timestamps.notna()
        valid_count = int(valid_time.sum())
        file_valid += valid_count
        acc.valid_timestamp_rows += valid_count
        acc.invalid_timestamp_rows += row_count - valid_count
        if not valid_count:
            continue
        valid_ts = timestamps.loc[valid_time]
        chunk_min = valid_ts.min()
        chunk_max = valid_ts.max()
        acc.earliest = chunk_min if acc.earliest is None else min(acc.earliest, chunk_min)
        acc.latest = chunk_max if acc.latest is None else max(acc.latest, chunk_max)
        _increment(acc.events_by_year, valid_ts.dt.year)
        _increment(acc.events_by_hour, valid_ts.dt.hour)
        _increment(acc.events_by_weekday, valid_ts.dt.weekday)
        _increment(acc.events_by_month, valid_ts.dt.month)
        acc.observed_days.update(
            pd.Timestamp(value).date() for value in valid_ts.dt.normalize().unique()
        )

        valid_channel_indices = channel_indices.loc[valid_time]
        valid_known = valid_channel_indices.notna()
        if valid_known.any():
            known_index = valid_channel_indices.loc[valid_known].to_numpy(dtype=np.int64)
            known_ts = valid_ts.loc[valid_known]
            np.add.at(acc.timed_event_count, known_index, 1)
            ns_values = known_ts.astype("int64").to_numpy(dtype=np.int64)
            np.minimum.at(acc.first_ns, known_index, ns_values)
            np.maximum.at(acc.last_ns, known_index, ns_values)
            types = pd.Series(
                np.asarray(acc.sensor_types, dtype=object)[known_index], index=known_ts.index
            )
            for sensor_type, count in types.value_counts().items():
                key = str(sensor_type)
                acc.events_by_sensor_type[key] = acc.events_by_sensor_type.get(key, 0) + int(count)
            day_frame = pd.DataFrame(
                {
                    "channel": known_index,
                    "year": known_ts.dt.year.to_numpy(dtype=np.int16),
                    "day": known_ts.dt.dayofyear.to_numpy(dtype=np.int16) - 1,
                }
            ).drop_duplicates()
            for year, group in day_frame.groupby("year", sort=False):
                matrix = acc.active_days.setdefault(
                    int(year), np.zeros((len(acc.channel_ids), 366), dtype=np.bool_)
                )
                matrix[group["channel"].to_numpy(), group["day"].to_numpy()] = True

    acc.source_metrics.append(
        SourceMetric(
            name=path.name,
            row_count=file_rows,
            valid_timestamp_count=file_valid,
            invalid_timestamp_count=file_rows - file_valid,
        )
    )


def _second_pass(
    journals: tuple[Path, ...],
    acc: _Accumulator,
    config: EdaConfig,
    *,
    duplicate_temp_root: Path | None,
) -> tuple[int, np.ndarray]:
    if acc.max_event_id // 8 + 1 <= config.max_bitmap_bytes:
        return _second_pass_dense(journals, acc, config)
    temporary_root = (
        duplicate_temp_root or config.allowed_interim_root / "eda" / ".duplicate-id-runs"
    )
    return _second_pass_external(journals, acc, config, temporary_root)


def _outlier_parameters(acc: _Accumulator) -> tuple[np.ndarray, np.ndarray]:
    means = np.divide(
        acc.numeric_sum,
        acc.numeric_count,
        out=np.zeros_like(acc.numeric_sum),
        where=acc.numeric_count > 0,
    )
    variances = (
        np.divide(
            acc.numeric_sum_squares,
            acc.numeric_count,
            out=np.zeros_like(acc.numeric_sum_squares),
            where=acc.numeric_count > 0,
        )
        - means * means
    )
    return means, np.sqrt(np.maximum(variances, 0.0))


def _accumulate_outliers(
    chunk: pd.DataFrame,
    acc: _Accumulator,
    config: EdaConfig,
    means: np.ndarray,
    stds: np.ndarray,
    outlier_counts: np.ndarray,
) -> None:
    channel_indices = chunk["ид_канала_данных"].map(acc.channel_index)
    values = pd.to_numeric(
        chunk["значение_датчика"].str.replace(",", ".", regex=False), errors="coerce"
    ).to_numpy(dtype=np.float64, na_value=np.nan)
    known_finite = channel_indices.notna().to_numpy() & np.isfinite(values)
    if not known_finite.any():
        return
    idx = channel_indices.to_numpy(dtype=np.float64)[known_finite].astype(np.int64)
    vals = values[known_finite]
    eligible = stds[idx] > 0
    outliers = eligible & (np.abs(vals - means[idx]) > config.outlier_z * stds[idx])
    np.add.at(outlier_counts, idx[outliers], 1)


def _second_pass_dense(
    journals: tuple[Path, ...], acc: _Accumulator, config: EdaConfig
) -> tuple[int, np.ndarray]:
    try:
        bitmap = np.zeros(acc.max_event_id // 8 + 1, dtype=np.uint8)
    except MemoryError as error:
        raise EdaError("Недостаточно локальной памяти для точной карты идентификаторов") from error
    duplicate_count = 0
    outlier_counts = np.zeros(len(acc.channel_ids), dtype=np.int64)
    means, stds = _outlier_parameters(acc)
    for path in journals:
        for chunk in _read_chunks(path, config.chunk_size, validate_structure=True):
            ids, _ = _parse_event_ids(chunk["ид_события"])
            unique_ids, occurrences = np.unique(ids, return_counts=True)
            byte_indices = (unique_ids // 8).astype(np.int64)
            masks = np.left_shift(np.uint8(1), (unique_ids % 8).astype(np.uint8))
            duplicate_count += int((occurrences - 1).sum())
            duplicate_count += int(np.count_nonzero(bitmap[byte_indices] & masks))
            np.bitwise_or.at(bitmap, byte_indices, masks)
            _accumulate_outliers(chunk, acc, config, means, stds, outlier_counts)
    return duplicate_count, outlier_counts


def _external_bucket_count(total_rows: int) -> int:
    """Подбирает степень двойки, чтобы раздел оставался в лимите локальной памяти."""
    total_bytes = total_rows * np.dtype(np.uint64).itemsize
    required = (total_bytes + EXTERNAL_DUPLICATE_BUCKET_MAX_BYTES - 1) // (
        EXTERNAL_DUPLICATE_BUCKET_MAX_BYTES
    )
    return max(EXTERNAL_DUPLICATE_MIN_BUCKET_COUNT, 1 << (required - 1).bit_length())


def _external_bucket_indices(ids: np.ndarray, bucket_count: int) -> np.ndarray:
    """Равномерно распределяет uint64 ID по фиксированному числу локальных файлов."""
    mixed = ids.copy()
    mixed ^= mixed >> np.uint64(30)
    mixed *= np.uint64(0xBF58476D1CE4E5B9)
    mixed ^= mixed >> np.uint64(27)
    mixed *= np.uint64(0x94D049BB133111EB)
    mixed ^= mixed >> np.uint64(31)
    return (mixed & np.uint64(bucket_count - 1)).astype(np.intp)


def _second_pass_external(
    journals: tuple[Path, ...],
    acc: _Accumulator,
    config: EdaConfig,
    temporary_root: Path,
) -> tuple[int, np.ndarray]:
    root = _guard_output_directory(temporary_root, config.allowed_interim_root, "data/interim")
    required_bytes = (
        acc.total_rows * np.dtype(np.uint64).itemsize + EXTERNAL_DUPLICATE_DISK_RESERVE_BYTES
    )
    try:
        if shutil.disk_usage(root).free < required_bytes:
            raise EdaError("Недостаточно локального места для точного подсчёта дублей")
    except OSError as error:
        raise EdaError("Не удалось проверить место для точного подсчёта дублей") from error

    run_root = root / f"duplicate-id-run-{uuid.uuid4().hex}"
    run_root.mkdir()
    bucket_count = _external_bucket_count(acc.total_rows)
    partial_paths = [run_root / f"{index:04x}.partial" for index in range(bucket_count)]
    final_paths = [path.with_suffix(".bin") for path in partial_paths]
    streams = []
    completed = False
    try:
        streams = [path.open("wb") for path in partial_paths]
        outlier_counts = np.zeros(len(acc.channel_ids), dtype=np.int64)
        means, stds = _outlier_parameters(acc)
        for path in journals:
            for chunk in _read_chunks(path, config.chunk_size, validate_structure=True):
                ids, _ = _parse_event_ids(chunk["ид_события"])
                buckets = _external_bucket_indices(ids, bucket_count)
                for bucket in np.unique(buckets):
                    selected = np.ascontiguousarray(ids[buckets == bucket], dtype="<u8")
                    streams[int(bucket)].write(selected.tobytes())
                _accumulate_outliers(chunk, acc, config, means, stds, outlier_counts)
        for stream in streams:
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
        streams = []
        for partial_path, final_path in zip(partial_paths, final_paths, strict=True):
            os.replace(partial_path, final_path)

        duplicate_count = 0
        for path in final_paths:
            size = path.stat().st_size
            if size % np.dtype(np.uint64).itemsize or size > EXTERNAL_DUPLICATE_BUCKET_MAX_BYTES:
                raise EdaError("Временный раздел ID превышает безопасный размер")
            ids = np.fromfile(path, dtype="<u8")
            if len(ids) > 1:
                ids.sort()
                duplicate_count += int(np.count_nonzero(ids[1:] == ids[:-1]))
        completed = True
        return duplicate_count, outlier_counts
    except MemoryError as error:
        raise EdaError("Недостаточно локальной памяти для точного подсчёта дублей") from error
    finally:
        try:
            for stream in streams:
                stream.close()
        finally:
            try:
                _remove_duplicate_run(root, run_root)
            except EdaError:
                if completed:
                    raise


def _remove_duplicate_run(root: Path, run_root: Path) -> None:
    """Удаляет только успешно обработанный UUID-каталог внутри разрешённого корня."""
    resolved_root = root.resolve(strict=False)
    resolved_run = run_root.resolve(strict=False)
    if (
        run_root.parent != root
        or not run_root.name.startswith("duplicate-id-run-")
        or not resolved_run.is_relative_to(resolved_root)
    ):
        raise EdaError("Небезопасный путь временного раздела ID")
    try:
        shutil.rmtree(run_root)
    except OSError as error:
        raise EdaError("Не удалось удалить обработанный временный раздел ID") from error


def _iso_from_ns(value: int, sentinel: int) -> str | None:
    if value == sentinel:
        return None
    return pd.Timestamp(value).isoformat()


def _build_result(
    acc: _Accumulator,
    journal_count: int,
    object_count: int,
    bitmap_bytes: int,
    duplicate_count: int,
    outlier_counts: np.ndarray,
    config: EdaConfig,
) -> EdaResult:
    active_day_counts = np.zeros(len(acc.channel_ids), dtype=np.int64)
    for matrix in acc.active_days.values():
        active_day_counts += matrix.sum(axis=1, dtype=np.int64)
    rates = np.divide(
        acc.timed_event_count,
        active_day_counts,
        out=np.zeros(len(acc.channel_ids), dtype=np.float64),
        where=active_day_counts > 0,
    )
    active_rates = rates[active_day_counts > 0]
    q1 = float(np.quantile(active_rates, 0.25)) if len(active_rates) else 0.0
    q3 = float(np.quantile(active_rates, 0.75)) if len(active_rates) else 0.0
    iqr = q3 - q1
    noise_threshold = q3 + 1.5 * iqr
    latest = acc.latest.to_pydatetime() if acc.latest is not None else None
    cutoff = latest - timedelta(days=config.silent_days) if latest else None
    coverage_years = _coverage_years(acc.earliest, acc.latest)
    largest_gap_days, largest_gap_starts_at, largest_gap_ends_at = _largest_observed_gap(
        acc.observed_days
    )
    max_sentinel = np.iinfo(np.int64).max
    min_sentinel = np.iinfo(np.int64).min
    channel_metrics: list[ChannelMetric] = []
    for index, channel_id in enumerate(acc.channel_ids):
        count = int(acc.numeric_count[index])
        mean = float(acc.numeric_sum[index] / count) if count else None
        variance = float(acc.numeric_sum_squares[index] / count - mean * mean) if count else None
        std = math.sqrt(max(variance, 0.0)) if variance is not None else None
        last_at = _iso_from_ns(int(acc.last_ns[index]), min_sentinel)
        never_seen = int(acc.event_count[index]) == 0
        undated_event_count = int(acc.event_count[index] - acc.timed_event_count[index])
        has_recent_valid_event = bool(
            cutoff is not None and last_at is not None and datetime.fromisoformat(last_at) >= cutoff
        )
        if never_seen:
            silence_status = "не наблюдался"
        elif has_recent_valid_event:
            silence_status = "активен"
        elif undated_event_count:
            silence_status = "неопределён"
        elif cutoff and last_at and datetime.fromisoformat(last_at) < cutoff:
            silence_status = "молчит"
        else:
            silence_status = "активен"
        silent = silence_status in {"не наблюдался", "молчит"}
        channel_metrics.append(
            ChannelMetric(
                channel_id=channel_id,
                sensor_type=acc.sensor_types[index],
                event_count=int(acc.event_count[index]),
                timed_event_count=int(acc.timed_event_count[index]),
                undated_event_count=undated_event_count,
                active_day_count=int(active_day_counts[index]),
                events_per_active_day=float(rates[index]),
                first_at=_iso_from_ns(int(acc.first_ns[index]), max_sentinel),
                last_at=last_at,
                numeric_count=count,
                numeric_mean=mean,
                numeric_std=std,
                numeric_min=float(acc.numeric_min[index]) if count else None,
                numeric_max=float(acc.numeric_max[index]) if count else None,
                statistical_outlier_count=int(outlier_counts[index]),
                is_never_seen=never_seen,
                is_silent=silent,
                silence_status=silence_status,
                is_noisy=bool(active_day_counts[index] and rates[index] > noise_threshold),
            )
        )
    type_counts: dict[str, int] = {}
    for sensor_type in acc.sensor_types:
        type_counts[sensor_type] = type_counts.get(sensor_type, 0) + 1
    return EdaResult(
        total_rows=acc.total_rows,
        valid_timestamp_rows=acc.valid_timestamp_rows,
        invalid_timestamp_rows=acc.invalid_timestamp_rows,
        earliest_at=acc.earliest.isoformat() if acc.earliest is not None else None,
        latest_at=acc.latest.isoformat() if acc.latest is not None else None,
        max_event_id=acc.max_event_id,
        bitmap_bytes=bitmap_bytes,
        journal_file_count=journal_count,
        channel_count=len(acc.channel_ids),
        object_count=object_count,
        unknown_channel_event_count=acc.unknown_channel_event_count,
        invalid_event_id_count=acc.invalid_event_id_count,
        duplicate_event_id_count=duplicate_count,
        missing_counts=dict(sorted(acc.missing_counts.items())),
        alarm_true_count=acc.alarm_true_count,
        alarm_false_count=acc.alarm_false_count,
        alarm_unknown_count=acc.alarm_unknown_count,
        numeric_value_count=acc.numeric_value_count,
        non_numeric_value_count=acc.non_numeric_value_count,
        non_finite_value_count=acc.non_finite_value_count,
        statistical_outlier_count=int(outlier_counts.sum()),
        events_by_year=dict(sorted(acc.events_by_year.items())),
        events_by_hour={key: acc.events_by_hour.get(key, 0) for key in range(24)},
        events_by_weekday={key: acc.events_by_weekday.get(key, 0) for key in range(7)},
        events_by_month={key: acc.events_by_month.get(key, 0) for key in range(1, 13)},
        events_by_sensor_type=dict(sorted(acc.events_by_sensor_type.items())),
        channel_type_counts=dict(sorted(type_counts.items())),
        silent_channel_count=sum(metric.is_silent for metric in channel_metrics),
        never_seen_channel_count=sum(metric.is_never_seen for metric in channel_metrics),
        silence_undetermined_channel_count=sum(
            metric.silence_status == "неопределён" for metric in channel_metrics
        ),
        noisy_channel_count=sum(metric.is_noisy for metric in channel_metrics),
        noise_q1=q1,
        noise_q3=q3,
        noise_iqr=iqr,
        noise_threshold=noise_threshold,
        coverage_years=coverage_years,
        largest_observed_gap_days=largest_gap_days,
        largest_gap_starts_at=largest_gap_starts_at,
        largest_gap_ends_at=largest_gap_ends_at,
        false_positive_rate=None,
        source_metrics=tuple(acc.source_metrics),
        channel_metrics=tuple(channel_metrics),
        parameters={
            "chunk_size": config.chunk_size,
            "silent_days": config.silent_days,
            "outlier_z": config.outlier_z,
        },
    )


def _coverage_years(earliest: pd.Timestamp | None, latest: pd.Timestamp | None) -> float:
    if earliest is None or latest is None:
        return 0.0
    return max(0.0, (latest - earliest).total_seconds() / (365.2425 * 86_400))


def _largest_observed_gap(observed_days: set[date]) -> tuple[int, str | None, str | None]:
    ordered_days = sorted(observed_days)
    if len(ordered_days) < 2:
        return 0, None, None
    largest_gap_days = 0
    largest_starts_at: date | None = None
    largest_ends_at: date | None = None
    for earlier, later in zip(ordered_days, ordered_days[1:], strict=False):
        gap_days = (later - earlier).days - 1
        if gap_days > largest_gap_days:
            largest_gap_days = gap_days
            largest_starts_at = earlier + timedelta(days=1)
            largest_ends_at = later - timedelta(days=1)
    return (
        largest_gap_days,
        largest_starts_at.isoformat() if largest_starts_at else None,
        largest_ends_at.isoformat() if largest_ends_at else None,
    )


def write_interim_outputs(result: EdaResult, interim_root: Path, config: EdaConfig) -> None:
    """Атомарно сохраняет подробные результаты только в `data/interim`."""
    try:
        root = _guard_output_directory(interim_root, config.allowed_interim_root, "data/interim")
        _atomic_text(
            root / "profile.json",
            json.dumps(result.profile_dict(), ensure_ascii=False, indent=2) + "\n",
        )
        _atomic_csv(
            root / "channel_metrics.csv",
            [asdict(metric) for metric in result.channel_metrics],
        )
    except OSError as error:
        raise EdaError("Не удалось записать локальные промежуточные агрегаты") from error


def write_report(
    result: EdaResult,
    report_path: Path,
    figures_root: Path,
    config: EdaConfig,
    *,
    command: str,
) -> None:
    """Создаёт локальные агрегаты и SVG только внутри `data/interim`."""
    try:
        _write_report_artifacts(result, report_path, figures_root, config, command=command)
    except OSError as error:
        raise EdaError("Не удалось записать отчёт или диаграммы EDA") from error


def _write_report_artifacts(
    result: EdaResult,
    report_path: Path,
    figures_root: Path,
    config: EdaConfig,
    *,
    command: str,
) -> None:
    report = _guard_output_file(report_path, config.allowed_interim_root, "data/interim", ".md")
    figures = _guard_output_directory(figures_root, config.allowed_interim_root, "data/interim")
    figures_link = Path(os.path.relpath(figures, report.parent)).as_posix()
    period = f"{result.earliest_at or 'нет данных'} — {result.latest_at or 'нет данных'}"
    charts = {
        "events_by_year.svg": (
            "События по годам",
            "Год",
            "События, шт.",
            [str(key) for key in result.events_by_year],
            list(result.events_by_year.values()),
        ),
        "events_by_hour.svg": (
            "Сезонность по часу",
            "Час суток",
            "События, шт.",
            [str(key) for key in range(24)],
            [result.events_by_hour[key] for key in range(24)],
        ),
        "events_by_weekday.svg": (
            "Сезонность по дню недели",
            "День недели",
            "События, шт.",
            list(WEEKDAY_LABELS),
            [result.events_by_weekday[key] for key in range(7)],
        ),
        "events_by_month.svg": (
            "Сезонность по месяцу",
            "Месяц",
            "События, шт.",
            list(MONTH_LABELS),
            [result.events_by_month[key] for key in range(1, 13)],
        ),
        "channel_type_distribution.svg": (
            "Распределение типов каналов",
            "Исходный тип датчика",
            "Каналы, шт.",
            list(result.channel_type_counts),
            list(result.channel_type_counts.values()),
        ),
    }
    top_metrics = sorted(
        result.channel_metrics, key=lambda item: item.events_per_active_day, reverse=True
    )[:10]
    charts["top_noisy_channels.svg"] = (
        "Каналы с наибольшей частотой",
        "Ранг канала",
        "События на активный день, шт./день",
        [f"№{index}" for index in range(1, len(top_metrics) + 1)],
        [metric.events_per_active_day for metric in top_metrics],
    )
    for filename, (title, x_label, y_label, labels, values) in charts.items():
        _atomic_text(figures / filename, _bar_svg(title, x_label, y_label, labels, values, period))

    rows_by_source = "\n".join(
        f"| `{metric.name}` | {metric.row_count:,} | {metric.valid_timestamp_count:,} | {metric.invalid_timestamp_count:,} |".replace(
            ",", " "
        )
        for metric in result.source_metrics
    )
    type_rows = "\n".join(
        f"| {sensor_type} | {count:,} | {result.events_by_sensor_type.get(sensor_type, 0):,} |".replace(
            ",", " "
        )
        for sensor_type, count in result.channel_type_counts.items()
    )
    missing_rows = "\n".join(
        f"| `{name}` | {count:,} |".replace(",", " ")
        for name, count in result.missing_counts.items()
    )
    coverage_statement = (
        "Требование глубины не менее 12 лет выполнено."
        if result.coverage_years >= 12
        else (
            "Требование глубины не менее 12 лет не выполнено: "
            f"наблюдаемая длительность {result.coverage_years:.2f} года."
        )
    )
    gap_statement = (
        "Календарных разрывов между днями с наблюдениями не обнаружено."
        if result.largest_observed_gap_days == 0
        else (
            "Наибольший календарный разрыв между днями с наблюдениями: "
            f"{result.largest_gap_starts_at} — {result.largest_gap_ends_at} "
            f"({result.largest_observed_gap_days} суток)."
        )
    )
    markdown = f"""# Отчёт EDA реальных данных СМВУ

Дата формирования: {datetime.now().isoformat(timespec="seconds")}.

## Покрытие и объём

- Полный обработанный объём: {result.total_rows:,} строк в {result.journal_file_count} журналах.
- Валидное время: {result.valid_timestamp_rows:,} строк; неразбираемое время: {result.invalid_timestamp_rows:,} строк.
- Период валидных наблюдений: {period}.
- Каналы в справочнике: {result.channel_count:,}; объекты: {result.object_count:,}.
- {coverage_statement}
- {gap_statement}

![События по годам]({figures_link}/events_by_year.svg)

| Источник | Строки, шт. | С валидным временем, шт. | Неразбираемое время, шт. |
| --- | ---: | ---: | ---: |
{rows_by_source}

## Качество данных

| Поле | Пустые значения, шт. |
| --- | ---: |
{missing_rows}

- Повторные вхождения ID события: {result.duplicate_event_id_count:,} шт.
- Некорректные ID события: {result.invalid_event_id_count:,} шт.; они учтены в остальных агрегатах и исключены только из дедупликации.
- События неизвестных справочнику каналов: {result.unknown_channel_event_count:,} шт.
- Состояния тревоги: true — {result.alarm_true_count:,}, false — {result.alarm_false_count:,}, нераспознанные — {result.alarm_unknown_count:,}.
- Доля ложных срабатываний: **Недоступно** — в выгрузке нет результата верификации; `тревожное = false` не считается ложным срабатыванием.

## Типы каналов

| Исходный тип датчика | Каналы, шт. | События с валидным временем, шт. |
| --- | ---: | ---: |
{type_rows}

![Распределение типов каналов]({figures_link}/channel_type_distribution.svg)

## Частотность каналов

- Никогда не наблюдались: {result.never_seen_channel_count:,} каналов.
- Молчащие по порогу {config.silent_days} суток: {result.silent_channel_count:,} каналов.
- Каналы с невалидным временем, для которых статус тишины не определён: {result.silence_undetermined_channel_count:,}.
- Шумящие по правилу Q3 + 1,5×IQR: {result.noisy_channel_count:,} каналов.
- Q1 = {result.noise_q1:.3f}, Q3 = {result.noise_q3:.3f}, IQR = {result.noise_iqr:.3f}, порог = {result.noise_threshold:.3f} события на активный день.

![Наиболее частые каналы]({figures_link}/top_noisy_channels.svg)

## Сезонность

Сезонность рассчитана только по строкам с валидным временем. Показатели являются частотами событий, а не оценками риска.

![События по часу]({figures_link}/events_by_hour.svg)
![События по дню недели]({figures_link}/events_by_weekday.svg)
![События по месяцу]({figures_link}/events_by_month.svg)

## Аномалии значений

- Числовые конечные значения: {result.numeric_value_count:,} шт.
- Нечисловые непустые значения: {result.non_numeric_value_count:,} шт.
- NaN и бесконечности: {result.non_finite_value_count:,} шт.
- Статистические выбросы `|z| > {config.outlier_z:g}` внутри канала: {result.statistical_outlier_count:,} шт.

Z-выбросы — описательный статистический сигнал. Физические пороги не применялись без утверждённых единиц и нормативов.

## Ограничения и риски следующих фаз

- Ограничения периода и временные разрывы определены по фактическим датам выше; их нельзя заменять ожиданиями по составу архива.
- Нет журналов верификации, ОДС, АРМ-Контроль, ремонтов, ТО/ППР и метеоданных.
- `тип_датчика` — исходная строка справочника, а не канонический ID типа из Приложения 1.
- Тишина и шум определены статистическими правилами; перед использованием как лейблов требуется согласование с эксплуатационными экспертами.

## Воспроизводимость

Команда: `{command}`

Параметры: chunk size — {config.chunk_size:,} строк; тишина — {config.silent_days} суток; порог выброса — {config.outlier_z:g}σ.
Подробные поканальные агрегаты сохранены локально в `data/interim/eda` и не входят в Git.
""".replace(",", " ")
    _atomic_text(report, markdown)


def _bar_svg(
    title: str,
    x_label: str,
    y_label: str,
    labels: list[str],
    values: list[int | float],
    period: str,
) -> str:
    width, height = 1000, 560
    left, top, plot_width, plot_height = 105, 80, 840, 370
    maximum = max((float(value) for value in values), default=0.0)
    scale_max = maximum if maximum > 0 else 1.0
    count = max(len(values), 1)
    slot = plot_width / count
    bar_width = max(2.0, slot * 0.68)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" data-y-min="0">',
        f"<title>{html.escape(title)}</title>",
        f"<desc>{html.escape(y_label)}; период {html.escape(period)}; ось Y начинается с нуля.</desc>",
        '<rect width="1000" height="560" fill="#ffffff"/>',
        f'<text x="500" y="34" text-anchor="middle" font-family="sans-serif" font-size="22" fill="#172033">{html.escape(title)}</text>',
        f'<text x="500" y="56" text-anchor="middle" font-family="sans-serif" font-size="13" fill="#526078">Период: {html.escape(period)}</text>',
    ]
    for tick in range(6):
        ratio = tick / 5
        y = top + plot_height * (1 - ratio)
        value = scale_max * ratio
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_width}" y2="{y:.1f}" stroke="#d8dee9"/>'
        )
        parts.append(
            f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" font-family="sans-serif" font-size="11" fill="#344054">{value:,.0f}</text>'
        )
    for index, (label, value) in enumerate(zip(labels, values, strict=False)):
        numeric = float(value)
        bar_height = plot_height * numeric / scale_max
        x = left + index * slot + (slot - bar_width) / 2
        y = top + plot_height - bar_height
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" fill="#1769aa"><title>{html.escape(label)}: {numeric:,.3g}</title></rect>'
        )
        if len(labels) <= 24:
            parts.append(
                f'<text x="{x + bar_width / 2:.1f}" y="{top + plot_height + 18}" text-anchor="middle" font-family="sans-serif" font-size="10" fill="#344054">{html.escape(label)}</text>'
            )
    parts.extend(
        [
            f'<text x="{left + plot_width / 2}" y="520" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#172033">{html.escape(x_label)}</text>',
            f'<text x="24" y="{top + plot_height / 2}" transform="rotate(-90 24 {top + plot_height / 2})" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#172033">{html.escape(y_label)}</text>',
            "</svg>\n",
        ]
    )
    return "".join(parts)


def _guard_directory(path: Path, allowed_root: Path, label: str) -> Path:
    checked = _guard_path(path, allowed_root, label)
    if not checked.is_dir():
        raise EdaError(f"{label} не существует")
    return checked


def _guard_file(path: Path, allowed_root: Path, label: str) -> Path:
    checked = _guard_path(path, allowed_root, label)
    if not checked.is_file():
        raise EdaError(f"{label} не существует")
    return checked


def _guard_output_directory(path: Path, allowed_root: Path, label: str) -> Path:
    checked = _guard_path(path, allowed_root, label)
    checked.mkdir(parents=True, exist_ok=True)
    return checked


def _guard_output_file(path: Path, allowed_root: Path, label: str, suffix: str) -> Path:
    checked = _guard_path(path, allowed_root, label)
    if checked.suffix.lower() != suffix:
        raise EdaError(f"{label}: ожидается файл {suffix}")
    checked.parent.mkdir(parents=True, exist_ok=True)
    return checked


def _guard_path(path: Path, allowed_root: Path, label: str) -> Path:
    raw = str(path)
    if raw.startswith(("\\\\", "//")):
        raise EdaError(f"{label}: UNC-пути запрещены")
    allowed = allowed_root.resolve(strict=False)
    resolved = path.resolve(strict=False)
    if not resolved.is_relative_to(allowed):
        raise EdaError(f"{label}: путь должен находиться внутри {allowed_root.name}")
    return resolved


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            "w", encoding="utf-8", newline="", dir=path.parent, delete=False
        ) as stream:
            stream.write(content)
            temporary = Path(stream.name)
        os.replace(temporary, path)
    except OSError:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _atomic_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            "w", encoding="utf-8", newline="", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            fieldnames = list(rows[0]) if rows else []
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            if fieldnames:
                writer.writeheader()
                writer.writerows(rows)
        os.replace(temporary, path)
    except OSError:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
