import csv
import importlib.util
import json
import sqlite3
import subprocess
import sys
from bisect import bisect_right
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from forpost_connectors.local_snapshot import (
    SourceSnapshotError,
    build_local_snapshot,
    cleanup_training_window,
    load_training_context,
    load_training_window,
)

EVENT_HEADERS = [
    "ид_события",
    "ид_канала_данных",
    "дата",
    "время",
    "тревожное",
    "значение_датчика",
]
CHANNEL_HEADERS = [
    "ид_канала_данных",
    "тип_инж_системы",
    "тип_датчика",
    "тег_инженерной_системы",
    "название_датчика",
]
UPDATED_CHANNEL_HEADERS = [*CHANNEL_HEADERS, "ид_объект"]
OBJECT_HEADERS = [
    "ид_объект",
    "иерархия_уровень",
    "родитель",
    "вид_объекта",
    "диспетчерское_название_объекта",
]


def configure_local_roots(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    """Изолирует проверку путей от локального набора данных разработчика."""
    import forpost_connectors.local_snapshot as local_snapshot

    project_root = tmp_path / "project"
    raw_root = project_root / "data" / "raw" / "extracted"
    output_path = project_root / "data" / "processed" / "local-situation.json"
    raw_root.mkdir(parents=True)
    output_path.parent.mkdir(parents=True)
    monkeypatch.setattr(local_snapshot, "PROJECT_ROOT", project_root)
    return raw_root, output_path


def write_csv(
    path: Path, headers: list[str], rows: list[dict[str, str]], *, bom: bool = False
) -> None:
    with path.open("w", encoding="utf-8-sig" if bom else "utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def write_valid_sources(raw_root: Path, events: list[dict[str, str]] | None = None) -> None:
    write_csv(
        raw_root / "ext-journal-2026.csv",
        EVENT_HEADERS,
        events
        or [
            {
                "ид_события": "900",
                "ид_канала_данных": "20",
                "дата": "2026-08-01",
                "время": "10:00:00",
                "тревожное": "1",
                "значение_датчика": "7",
            }
        ],
    )
    write_csv(
        raw_root / "channels.csv",
        CHANNEL_HEADERS,
        [
            {
                "ид_канала_данных": "20",
                "тип_инж_системы": "ventilation",
                "тип_датчика": "smoke",
                "тег_инженерной_системы": "node-20",
                "название_датчика": "Smoke 20",
            }
        ],
        bom=True,
    )
    write_csv(
        raw_root / "objects.csv",
        OBJECT_HEADERS,
        [
            {
                "ид_объект": "5",
                "иерархия_уровень": "1",
                "родитель": "",
                "вид_объекта": "collector",
                "диспетчерское_название_объекта": "Object 5",
            }
        ],
        bom=True,
    )


def test_training_window_uses_guarded_sources_without_public_snapshot_limit(monkeypatch, tmp_path):
    """ML-reader остаётся локальным, но не обрезает окно публичным лимитом UI."""
    raw_root, _ = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(raw_root)

    window = load_training_window(raw_root, max_events=1_000)

    assert len(window.events) == 1
    assert len(window.channels) == 1
    assert window.scanned_event_count == 1


def test_weekly_feature_training_accepts_bounded_larger_tail(monkeypatch, tmp_path):
    raw_root, _ = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(raw_root)
    window = load_training_window(raw_root, max_events=3_000_000)
    assert len(window.events) == 1
    with pytest.raises(SourceSnapshotError):
        load_training_window(raw_root, max_events=3_000_001)


def test_training_window_keeps_contiguous_latest_tail_and_marks_truncation(monkeypatch, tmp_path):
    raw_root, _ = configure_local_roots(monkeypatch, tmp_path)
    events = [
        {
            "ид_события": str(index),
            "ид_канала_данных": "20",
            "дата": f"2026-01-{index + 1:02d}",
            "время": "10:00:00",
            "тревожное": "0",
            "значение_датчика": str(index),
        }
        for index in range(10)
    ]
    write_valid_sources(raw_root, events)

    window = load_training_window(raw_root, max_events=3)

    assert [event.event_id for event in window.events] == ["9", "8", "7"]
    assert window.truncated_before is True


def test_training_window_reads_all_year_labelled_journals(monkeypatch, tmp_path):
    raw_root, _ = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(raw_root)
    write_csv(
        raw_root / "ext-journal-2025.csv",
        EVENT_HEADERS,
        [
            {
                "ид_события": "800",
                "ид_канала_данных": "20",
                "дата": "2025-08-01",
                "время": "10:00:00",
                "тревожное": "0",
                "значение_датчика": "6",
            }
        ],
    )

    window = load_training_window(raw_root, max_events=10)

    assert {event.event_id for event in window.events} == {"800", "900"}
    assert window.truncated_before is False


def test_training_window_stops_before_older_partition_after_tail_is_complete(monkeypatch, tmp_path):
    """Старые партиции не должны перечитываться после набора непрерывного хвоста."""
    raw_root, _ = configure_local_roots(monkeypatch, tmp_path)
    events = [
        {
            "ид_события": str(index),
            "ид_канала_данных": "20",
            "дата": f"2026-08-{index + 1:02d}",
            "время": "10:00:00",
            "тревожное": "0",
            "значение_датчика": str(index),
        }
        for index in range(5)
    ]
    write_valid_sources(raw_root, events)
    older = raw_root / "ext-journal-2025.csv"
    with older.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(EVENT_HEADERS)
        writer.writerow(["old", "20", "2025-01-01", "10:00:00", "0", "1", "extra"])

    window = load_training_window(raw_root, max_events=3)

    assert [event.event_id for event in window.events] == ["4", "3", "2"]
    assert window.truncated_before is True


def test_training_window_samples_exact_uniform_calendar_contexts(monkeypatch, tmp_path):
    """Ловит возврат к последнему хвосту вместо полных окон по календарю."""
    raw_root, _ = configure_local_roots(monkeypatch, tmp_path)
    events = [
        {
            "ид_события": event_id,
            "ид_канала_данных": "20",
            "дата": date,
            "время": "10:00:00",
            "тревожное": "0",
            "значение_датчика": "1",
        }
        for event_id, date in (
            ("start", "2026-01-02"),
            ("outside", "2026-03-01"),
            ("middle", "2026-07-03"),
            ("end", "2026-12-31"),
        )
    ]
    write_valid_sources(raw_root, events)

    window = load_training_window(
        raw_root,
        max_events=100,
        cutoff_count=3,
        context_before_hours=24,
        context_after_hours=24,
    )

    assert window.prediction_cutoffs == (
        "2026-01-02T00:00:00",
        "2026-07-02T12:00:00",
        "2026-12-31T00:00:00",
    )
    try:
        selected = {
            event.recorded_at
            for cutoff in window.prediction_cutoffs
            for event in load_training_context(
                window, cutoff, context_before_hours=24, context_after_hours=24
            )
        }
        assert "2026-07-03T10:00:00" in selected
        assert "2026-03-01T10:00:00" not in selected
        assert window.truncated_before is False
    finally:
        cleanup_training_window(window)


def test_training_calendar_density_increase_preserves_existing_anchors(tmp_path):
    """Ловит замену зрелых окон при увеличении label-free плотности календаря."""
    import forpost_connectors.local_snapshot as local_snapshot

    journals = tuple(tmp_path / f"events-{year}.csv" for year in range(2015, 2027))

    baseline = local_snapshot._calendar_cutoffs_from_partitions(
        journals,
        cutoff_count=64,
        context_before_hours=168,
        context_after_hours=24,
    )
    expanded = local_snapshot._calendar_cutoffs_from_partitions(
        journals,
        cutoff_count=192,
        context_before_hours=168,
        context_after_hours=24,
    )

    assert len(expanded) == 192
    assert set(baseline).issubset(expanded)
    assert expanded == tuple(sorted(expanded))


def test_training_calendar_rejects_inexact_window_truncation(monkeypatch, tmp_path):
    """Ловит молчаливое усечение событий внутри выбранных календарных окон."""
    raw_root, _ = configure_local_roots(monkeypatch, tmp_path)
    events = [
        {
            "ид_события": str(index),
            "ид_канала_данных": "20",
            "дата": "2026-01-01",
            "время": f"{index:02d}:00:00",
            "тревожное": "0",
            "значение_датчика": str(index),
        }
        for index in range(8)
    ]
    write_valid_sources(raw_root, events)

    with pytest.raises(SourceSnapshotError, match="контекста"):
        load_training_window(
            raw_root,
            max_events=2,
            cutoff_count=2,
            context_before_hours=1,
            context_after_hours=1,
        )


def test_training_calendar_quarantines_event_from_wrong_year_partition(monkeypatch, tmp_path):
    """Ловит остановку полной истории из-за единичной строки не своей партиции."""
    raw_root, _ = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(
        raw_root,
        [
            {
                "ид_события": "valid-1",
                "ид_канала_данных": "20",
                "дата": "2026-01-01",
                "время": "00:00:00",
                "тревожное": "0",
                "значение_датчика": "1",
            },
            {
                "ид_события": "wrong-partition",
                "ид_канала_данных": "20",
                "дата": "2027-01-01",
                "время": "00:00:00",
                "тревожное": "0",
                "значение_датчика": "1",
            },
            {
                "ид_события": "valid-2",
                "ид_канала_данных": "20",
                "дата": "2026-12-31",
                "время": "23:00:00",
                "тревожное": "0",
                "значение_датчика": "1",
            },
        ],
    )

    window = load_training_window(
        raw_root,
        max_events=100,
        cutoff_count=2,
        context_before_hours=1,
        context_after_hours=1,
    )

    try:
        selected = {
            event.recorded_at
            for cutoff in window.prediction_cutoffs
            for event in load_training_context(
                window, cutoff, context_before_hours=1, context_after_hours=1
            )
        }
        assert selected == {"2026-01-01T00:00:00", "2026-12-31T23:00:00"}
        assert window.skipped_event_count == 1
    finally:
        cleanup_training_window(window)


def test_training_calendar_has_separate_bounded_full_archive_row_limit(monkeypatch, tmp_path):
    """Ловит применение меньшего UI-лимита к полному локальному ML-архиву."""
    import forpost_connectors.local_snapshot as local_snapshot

    raw_root, _ = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(
        raw_root,
        [
            {
                "ид_события": str(index),
                "ид_канала_данных": "20",
                "дата": "2026-01-01",
                "время": f"0{index}:00:00",
                "тревожное": "0",
                "значение_датчика": "1",
            }
            for index in range(3)
        ],
    )
    monkeypatch.setattr(local_snapshot, "MAX_CSV_TOTAL_ROWS", 2)
    monkeypatch.setattr(local_snapshot, "MAX_TRAINING_SOURCE_ROWS", 3, raising=False)

    window = load_training_window(
        raw_root,
        max_events=10,
        cutoff_count=2,
        context_before_hours=1,
        context_after_hours=1,
    )

    assert window.scanned_event_count == 3
    cleanup_training_window(window)


def test_training_calendar_spools_total_above_per_context_limit(monkeypatch, tmp_path):
    """Ловит возврат общего RAM-лимита вместо bounded per-cutoff контекстов."""
    raw_root, _ = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(
        raw_root,
        [
            {
                "ид_события": event_id,
                "ид_канала_данных": "20",
                "дата": date,
                "время": time,
                "тревожное": "0",
                "значение_датчика": "1",
            }
            for event_id, date, time in (
                ("start", "2026-01-01", "01:00:00"),
                ("middle", "2026-07-02", "12:00:00"),
                ("end", "2026-12-31", "23:00:00"),
            )
        ],
    )

    window = load_training_window(
        raw_root,
        max_events=1,
        cutoff_count=3,
        context_before_hours=1,
        context_after_hours=1,
    )

    assert window.selected_event_count == 3
    assert all(
        len(load_training_context(window, cutoff, context_before_hours=1, context_after_hours=1))
        == 1
        for cutoff in window.prediction_cutoffs
    )
    spool_path = window.spool_path
    cleanup_training_window(window)
    assert spool_path is not None and not spool_path.exists()


def test_training_calendar_spool_uses_compressed_ml_only_blocks(monkeypatch, tmp_path):
    """Ловит возврат raw identifiers и SQLite-overhead на каждое событие."""
    raw_root, _ = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(
        raw_root,
        [
            {
                "ид_события": "raw-id-must-not-be-spooled",
                "ид_канала_данных": "20",
                "дата": "2026-01-01",
                "время": "01:00:00",
                "тревожное": "0",
                "значение_датчика": "1.5",
            }
        ],
    )

    window = load_training_window(
        raw_root,
        max_events=10,
        cutoff_count=2,
        context_before_hours=1,
        context_after_hours=1,
    )

    try:
        assert window.spool_path is not None
        connection = sqlite3.connect(window.spool_path)
        try:
            tables = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
                )
            )
            columns = tuple(
                row[1] for row in connection.execute("PRAGMA table_info(context_blocks)")
            )
            stored = connection.execute(
                "SELECT context_index, payload FROM context_blocks"
            ).fetchone()
        finally:
            connection.close()
        assert tables == ("context_blocks",)
        assert columns == ("context_index", "payload")
        assert stored is not None and stored[0] == 0
        assert b"raw-id-must-not-be-spooled" not in stored[1]
        context = load_training_context(
            window,
            window.prediction_cutoffs[0],
            context_before_hours=1,
            context_after_hours=1,
        )
        assert context[0].channel_id == "20"
        assert context[0].sensor_value == "1.5"
    finally:
        cleanup_training_window(window)


def test_training_calendar_uses_sorted_interval_lookup_not_repeated_masks(monkeypatch, tmp_path):
    """Ловит возврат O(selected events * cutoff count) boolean-масок."""
    raw_root, _ = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(
        raw_root,
        [
            {
                "ид_события": "selected",
                "ид_канала_данных": "20",
                "дата": "2026-01-01",
                "время": "01:00:00",
                "тревожное": "0",
                "значение_датчика": "1",
            }
        ],
    )

    def forbidden_between(*_args, **_kwargs):
        raise AssertionError("Календарный loader должен использовать sorted interval lookup")

    monkeypatch.setattr(pd.Series, "between", forbidden_between)
    window = load_training_window(
        raw_root,
        max_events=10,
        cutoff_count=3,
        context_before_hours=1,
        context_after_hours=1,
    )

    cleanup_training_window(window)


def test_training_calendar_uses_larger_bounded_csv_chunks(monkeypatch, tmp_path):
    """Ловит возврат к мелким чанкам, делающим full-calendar ingestion CPU-bound."""
    import forpost_connectors.local_snapshot as local_snapshot

    raw_root, _ = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(raw_root)
    original_read_csv = pd.read_csv
    chunk_sizes = []

    def observed_read_csv(*args, **kwargs):
        if "chunksize" in kwargs:
            chunk_sizes.append(kwargs["chunksize"])
        return original_read_csv(*args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", observed_read_csv)
    window = load_training_window(
        raw_root,
        max_events=10,
        cutoff_count=2,
        context_before_hours=1,
        context_after_hours=1,
    )
    try:
        assert local_snapshot.TRAINING_EVENT_CHUNK_ROWS in chunk_sizes
        assert local_snapshot.TRAINING_EVENT_CHUNK_ROWS > local_snapshot.EVENT_CHUNK_ROWS
    finally:
        cleanup_training_window(window)


def test_vectorized_training_blocks_match_scalar_reference_at_boundaries():
    """Проверяет точную эквивалентность vectorized assignment скалярному контракту."""
    import forpost_connectors.local_snapshot as local_snapshot

    intervals = (
        (datetime(2026, 1, 1, 0), datetime(2026, 1, 1, 2)),
        (datetime(2026, 1, 1, 4), datetime(2026, 1, 1, 6)),
    )
    origin = datetime(2026, 1, 1)
    times = tuple(origin + timedelta(hours=hour) for hour in (-1, 0, 2, 3, 4, 6, 7))
    chunk = pd.DataFrame(
        {
            "ид_канала_данных": ["20", "20", "20", "20", "20", "20", "unknown"],
            "тревожное": ["0", "1", "нет", "0", "да", "0", "0"],
            "значение_датчика": ["1", "2", "3", "4", "-127", "6", "7"],
        }
    )
    timestamps = pd.Series(pd.to_datetime(times), index=chunk.index)

    blocks, counts = local_snapshot._encode_training_blocks(
        chunk,
        timestamps,
        context_intervals=intervals,
        channel_indexes={"20": 0},
    )
    actual = {
        context_index: tuple(local_snapshot.TRAINING_EVENT_RECORD.iter_unpack(payload))
        for context_index, payload in blocks.items()
    }

    expected: dict[int, list[tuple[int, int, int, float, int]]] = {}
    starts = tuple(start for start, _ in intervals)
    for index, recorded_at in timestamps.items():
        context_index = bisect_right(starts, recorded_at) - 1
        if context_index < 0 or recorded_at > intervals[context_index][1]:
            continue
        channel_index = {"20": 0}.get(chunk.at[index, "ид_канала_данных"])
        if channel_index is None:
            continue
        alarm = local_snapshot._parse_alarm(chunk.at[index, "тревожное"])
        quality, eligible = local_snapshot._classify_event_quality(
            chunk.at[index, "значение_датчика"], alarm, recorded_at
        )
        if not eligible:
            continue
        expected.setdefault(context_index, []).append(
            (
                channel_index,
                local_snapshot._calendar_second(recorded_at),
                -1 if alarm is None else int(alarm),
                float(chunk.at[index, "значение_датчика"]),
                int(quality != "valid"),
            )
        )

    assert actual == {key: tuple(value) for key, value in expected.items()}
    assert counts == (2, 2)


def test_training_calendar_rejects_extra_csv_fields_in_single_pass(monkeypatch, tmp_path):
    """Ловит принятие malformed-строки после удаления отдельного pre-scan."""
    raw_root, _ = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(raw_root)
    journal_path = raw_root / "ext-journal-2026.csv"
    with journal_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(EVENT_HEADERS)
        writer.writerow(["bad", "20", "2026-01-02", "00:00:00", "0", "1", "extra"])

    with pytest.raises(SourceSnapshotError, match="число полей"):
        load_training_window(
            raw_root,
            max_events=10,
            cutoff_count=2,
            context_before_hours=1,
            context_after_hours=1,
        )


def load_snapshot_script():
    """Загружает CLI для проверки обработки ошибок в изолированном процессе теста."""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "build_local_snapshot.py"
    specification = importlib.util.spec_from_file_location("build_local_snapshot_test", script_path)
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_builder_discovers_only_exact_documented_csv_schemas(monkeypatch, tmp_path):
    """Ловит потерю точного определения трёх ролей CSV и UTF-8 BOM в заголовке."""
    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(raw_root)

    snapshot = build_local_snapshot(raw_root, output_path)
    saved = json.loads(output_path.read_text(encoding="utf-8"))

    assert snapshot.source_metadata.journal_file_count == 1
    assert snapshot.source_availability == {
        "events": True,
        "channels": True,
        "objects": True,
        "access_events": False,
        "maintenance_history": False,
        "ml_predictions": False,
        "work_permits": False,
    }
    assert snapshot.channels[0].channel_id == "20"
    assert snapshot.objects[0].object_id == "5"
    assert snapshot.events[0].recorded_at == "2026-08-01T10:00:00"
    assert "sourceMetadata" not in saved


def test_builder_rejects_unknown_csv_header_set(monkeypatch, tmp_path):
    """Ловит незадокументированную таблицу до чтения её записей."""
    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(raw_root)
    write_csv(raw_root / "unknown.csv", ["unexpected"], [{"unexpected": "fixture"}])

    with pytest.raises(SourceSnapshotError, match="неизвестной схемой"):
        build_local_snapshot(raw_root, output_path)


def test_builder_retains_only_latest_bounded_observed_events(monkeypatch, tmp_path):
    """Ловит замену ограниченной очереди полной загрузкой журнала или неверный порядок дат."""
    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(
        raw_root,
        events=[
            {
                "ид_события": "1",
                "ид_канала_данных": "20",
                "дата": "2026-08-01",
                "время": "08:00:00",
                "тревожное": "0",
                "значение_датчика": "1",
            },
            {
                "ид_события": "2",
                "ид_канала_данных": "20",
                "дата": "2026-08-01",
                "время": "10:00:00",
                "тревожное": "1",
                "значение_датчика": "2",
            },
            {
                "ид_события": "3",
                "ид_канала_данных": "20",
                "дата": "2026-08-01",
                "время": "09:00:00",
                "тревожное": "0",
                "значение_датчика": "3",
            },
        ],
    )

    snapshot = build_local_snapshot(raw_root, output_path, max_events=2)

    assert [event.recorded_at for event in snapshot.events] == [
        "2026-08-01T10:00:00",
        "2026-08-01T09:00:00",
    ]
    assert snapshot.source_metadata.latest_observed_at == "2026-08-01T10:00:00"


def test_builder_reserves_alarm_inside_bounded_public_window(monkeypatch, tmp_path):
    """Редкая тревога не должна исчезнуть из demo-очереди за более свежей телеметрией."""
    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(
        raw_root,
        events=[
            {
                "ид_события": "alarm",
                "ид_канала_данных": "20",
                "дата": "2026-08-01",
                "время": "08:00:00",
                "тревожное": "1",
                "значение_датчика": "1",
            },
            {
                "ид_события": "normal-1",
                "ид_канала_данных": "20",
                "дата": "2026-08-01",
                "время": "09:00:00",
                "тревожное": "0",
                "значение_датчика": "2",
            },
            {
                "ид_события": "normal-2",
                "ид_канала_данных": "20",
                "дата": "2026-08-01",
                "время": "10:00:00",
                "тревожное": "0",
                "значение_датчика": "3",
            },
        ],
    )

    snapshot = build_local_snapshot(raw_root, output_path, max_events=2)

    assert [event.event_id for event in snapshot.events] == ["normal-2", "alarm"]


@pytest.mark.parametrize(
    ("alarm_value", "expected_alarm"),
    [
        ("1.0", True),
        ("0,0", False),
        (" 1.0 ", True),
        ("on", True),
        ("off", False),
        ("Есть", True),
        ("Нет тревоги", False),
        ("-1", True),
    ],
)
def test_builder_normalizes_numeric_alarm_flag_from_csv(
    monkeypatch, tmp_path, alarm_value, expected_alarm
):
    """Ловит отклонение числового CSV-представления тревоги от целого литерала."""
    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(
        raw_root,
        events=[
            {
                "ид_события": "9",
                "ид_канала_данных": "20",
                "дата": "2026-08-01",
                "время": "10:00:00",
                "тревожное": alarm_value,
                "значение_датчика": "7",
            }
        ],
    )

    snapshot = build_local_snapshot(raw_root, output_path)

    assert snapshot.events[0].is_alarm is expected_alarm


def test_builder_preserves_unmapped_alarm_state_as_unavailable(monkeypatch, tmp_path):
    """Ловит выдумывание булева признака тревоги для неутверждённого значения источника."""
    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(
        raw_root,
        events=[
            {
                "ид_события": "9",
                "ид_канала_данных": "20",
                "дата": "2026-08-01",
                "время": "10:00:00",
                "тревожное": "unmapped-fixture-state",
                "значение_датчика": "7",
            }
        ],
    )

    snapshot = build_local_snapshot(raw_root, output_path)

    assert snapshot.events[0].is_alarm is None


def test_builder_skips_event_with_unparseable_timestamp_and_reports_aggregate(
    monkeypatch, tmp_path
):
    """Ловит остановку снимка из-за единичной повреждённой строки журнала."""
    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(
        raw_root,
        events=[
            {
                "ид_события": "1",
                "ид_канала_данных": "20",
                "дата": "invalid-fixture-date",
                "время": "10:00:00",
                "тревожное": "0",
                "значение_датчика": "7",
            },
            {
                "ид_события": "2",
                "ид_канала_данных": "20",
                "дата": "2026-08-01",
                "время": "10:00:00",
                "тревожное": "0",
                "значение_датчика": "7",
            },
        ],
    )

    snapshot = build_local_snapshot(raw_root, output_path)

    assert len(snapshot.events) == 1
    assert snapshot.source_metadata.skipped_event_count == 1


def test_builder_parses_dotted_date_as_russian_day_month_year(monkeypatch, tmp_path):
    """Ловит неоднозначную трактовку 01.02.2026 как 2 января вместо 1 февраля."""
    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(
        raw_root,
        events=[
            {
                "ид_события": "1",
                "ид_канала_данных": "20",
                "дата": "01.02.2026",
                "время": "10:00:00",
                "тревожное": "0",
                "значение_датчика": "7",
            }
        ],
    )

    snapshot = build_local_snapshot(raw_root, output_path)

    assert snapshot.events[0].recorded_at == "2026-02-01T10:00:00"


@pytest.mark.parametrize("alarm_value", ["NaN", "Infinity", "-Infinity"])
def test_builder_marks_nonfinite_decimal_alarm_as_unavailable(monkeypatch, tmp_path, alarm_value):
    """Ловит ложную тревогу из нечислового конечного значения Decimal."""
    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(
        raw_root,
        events=[
            {
                "ид_события": "1",
                "ид_канала_данных": "20",
                "дата": "2026-08-01",
                "время": "10:00:00",
                "тревожное": alarm_value,
                "значение_датчика": "7",
            }
        ],
    )

    snapshot = build_local_snapshot(raw_root, output_path)

    assert snapshot.events[0].is_alarm is None


def test_builder_rejects_journal_row_with_extra_fields(monkeypatch, tmp_path):
    """Ловит сдвиг полей журнала при строке с лишними значениями."""
    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(raw_root)
    journal_path = raw_root / "ext-journal-2026.csv"
    with journal_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(EVENT_HEADERS)
        writer.writerow(["1", "20", "2026-08-01", "10:00:00", "0", "7", "extra"])

    with pytest.raises(SourceSnapshotError, match="число полей"):
        build_local_snapshot(raw_root, output_path)


def test_builder_skips_incomplete_journal_row_and_reports_it(monkeypatch, tmp_path):
    """Не останавливает весь источник из-за одной укороченной строки."""
    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(raw_root)
    journal_path = raw_root / "ext-journal-2026.csv"
    with journal_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(EVENT_HEADERS)
        writer.writerow(["broken", "20", "2026-08-01", "10:00:00"])
        writer.writerow(["valid", "20", "2026-08-01", "10:01:00", "1", "7"])

    snapshot = build_local_snapshot(raw_root, output_path)

    assert [event.event_id for event in snapshot.events] == ["valid"]
    assert snapshot.data_quality.skipped_timestamp_count == 1


def test_builder_rejects_max_events_above_public_snapshot_limit(monkeypatch, tmp_path):
    """Ловит снятие лимита JSON-снимка по пользовательскому аргументу."""
    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(raw_root)

    with pytest.raises(SourceSnapshotError, match="500"):
        build_local_snapshot(raw_root, output_path, max_events=501)


def test_builder_rejects_excess_csv_files_before_role_selection(monkeypatch, tmp_path):
    """Не даёт неограниченному набору CSV дойти до разбора схемы."""
    import forpost_connectors.local_snapshot as local_snapshot

    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(raw_root)
    write_csv(raw_root / "extra.csv", ["unexpected"], [{"unexpected": "fixture"}])
    monkeypatch.setattr(local_snapshot, "MAX_CSV_FILES", 3)

    def fail_role_detection(_: Path) -> str:
        raise AssertionError("Разбор ролей не должен начаться до проверки числа файлов")

    monkeypatch.setattr(local_snapshot, "_detect_csv_role", fail_role_detection)

    with pytest.raises(SourceSnapshotError, match="число CSV-файлов"):
        build_local_snapshot(raw_root, output_path)


def test_builder_rejects_csv_larger_than_input_limit(monkeypatch, tmp_path):
    """Не читает CSV, размер которого выходит за утверждённую границу ввода."""
    import forpost_connectors.local_snapshot as local_snapshot

    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(raw_root)
    (raw_root / "too-large.csv").write_text("x" * 1_025, encoding="utf-8")
    monkeypatch.setattr(local_snapshot, "MAX_CSV_FILE_BYTES", 1_024)

    with pytest.raises(SourceSnapshotError, match="размер CSV-файла"):
        build_local_snapshot(raw_root, output_path)


def test_builder_rejects_csv_input_above_aggregate_byte_limit(monkeypatch, tmp_path):
    """Не допускает обход лимита одного файла множеством небольших CSV."""
    import forpost_connectors.local_snapshot as local_snapshot

    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(raw_root)
    monkeypatch.setattr(local_snapshot, "MAX_CSV_TOTAL_BYTES", 1)

    with pytest.raises(SourceSnapshotError, match="совокупный размер CSV"):
        build_local_snapshot(raw_root, output_path)


def test_builder_rejects_csv_with_too_many_rows_before_snapshot_build(monkeypatch, tmp_path):
    """Не передаёт в построение снимка файл, превысивший лимит строк."""
    import forpost_connectors.local_snapshot as local_snapshot

    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(
        raw_root,
        events=[
            {
                "ид_события": "1",
                "ид_канала_данных": "20",
                "дата": "2026-08-01",
                "время": "10:00:00",
                "тревожное": "0",
                "значение_датчика": "7",
            },
            {
                "ид_события": "2",
                "ид_канала_данных": "20",
                "дата": "2026-08-01",
                "время": "10:01:00",
                "тревожное": "0",
                "значение_датчика": "7",
            },
        ],
    )
    monkeypatch.setattr(local_snapshot, "MAX_CSV_ROWS", 1)

    with pytest.raises(SourceSnapshotError, match="число строк CSV"):
        build_local_snapshot(raw_root, output_path)


def test_builder_rejects_csv_field_larger_than_input_limit(monkeypatch, tmp_path):
    """Не допускает поле CSV, способное расширить память парсера."""
    import forpost_connectors.local_snapshot as local_snapshot

    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(
        raw_root,
        events=[
            {
                "ид_события": "1",
                "ид_канала_данных": "20",
                "дата": "2026-08-01",
                "время": "10:00:00",
                "тревожное": "0",
                "значение_датчика": "x" * 65,
            }
        ],
    )
    monkeypatch.setattr(local_snapshot, "MAX_CSV_FIELD_CHARS", 64)

    with pytest.raises(SourceSnapshotError, match="размер поля CSV"):
        build_local_snapshot(raw_root, output_path)


def test_builder_preserves_previous_snapshot_when_public_output_exceeds_limit(
    monkeypatch, tmp_path
):
    """Не заменяет рабочий снимок слишком большим JSON и удаляет временный файл."""
    import forpost_connectors.local_snapshot as local_snapshot

    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(raw_root)
    output_path.write_text('{"previous":"snapshot"}\n', encoding="utf-8")
    monkeypatch.setattr(local_snapshot, "MAX_PUBLIC_SNAPSHOT_BYTES", 64)

    with pytest.raises(SourceSnapshotError, match="размер публичного снимка"):
        build_local_snapshot(raw_root, output_path)

    assert output_path.read_text(encoding="utf-8") == '{"previous":"snapshot"}\n'
    assert list(output_path.parent.glob("tmp*")) == []


def test_cli_hides_expected_snapshot_error_details_and_exits_nonzero():
    """Ловит трассировку либо путь источника в сообщении CLI об ожидаемой ошибке."""
    completed = subprocess.run(  # noqa: S603 -- запускается текущий интерпретатор с тестовой константой.
        [
            sys.executable,
            "scripts/build_local_snapshot.py",
            "--raw-root",
            r"\\server\forpost",
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "Не удалось создать локальный снимок" in completed.stderr
    assert "Traceback" not in completed.stderr
    assert r"\\server\forpost" not in completed.stderr


def test_cli_hides_csv_field_size_error_from_synthetic_probe(monkeypatch, tmp_path, capsys):
    """Ловит трассировку csv.Error при поле журнала больше лимита csv-модуля."""
    import forpost_connectors.local_snapshot as local_snapshot

    project_root = tmp_path / "project"
    raw_root = project_root / "data" / "raw" / "extracted"
    output_path = project_root / "data" / "processed" / "local-situation.json"
    raw_root.mkdir(parents=True)
    output_path.parent.mkdir(parents=True)
    write_valid_sources(raw_root)
    journal_path = raw_root / "ext-journal-2026.csv"
    with journal_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(EVENT_HEADERS)
        writer.writerow(["x" * (csv.field_size_limit() + 1), "20", "2026-08-01", "10:00", "0", "7"])

    script = load_snapshot_script()
    monkeypatch.setattr(local_snapshot, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(script, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(
        sys,
        "argv",
        ["build_local_snapshot.py", "--raw-root", str(raw_root), "--output", str(output_path)],
    )

    exit_code = script.main()
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Не удалось создать локальный снимок" in captured.err
    assert "Traceback" not in captured.err
    assert str(raw_root) not in captured.err


def test_cli_does_not_print_snapshot_metadata(monkeypatch, tmp_path, capsys):
    """Не даёт локальной CLI вывести агрегаты, даты либо хеш сформированного снимка."""
    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(raw_root)

    script = load_snapshot_script()
    monkeypatch.setattr(
        sys,
        "argv",
        ["build_local_snapshot.py", "--raw-root", str(raw_root), "--output", str(output_path)],
    )

    assert script.main() == 0
    captured = capsys.readouterr()

    assert captured.out == "Локальный снимок создан.\n"
    assert "событий=" not in captured.out
    assert "каналов=" not in captured.out
    assert "объектов=" not in captured.out
    assert "последняя_дата=" not in captured.out
    assert "sha256=" not in captured.out


def test_builder_rejects_duplicate_registry_role_files(monkeypatch, tmp_path):
    """Ловит неоднозначный выбор справочника каналов."""
    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(raw_root)
    write_csv(raw_root / "channels-copy.csv", CHANNEL_HEADERS, [])

    with pytest.raises(SourceSnapshotError, match="дубликат"):
        build_local_snapshot(raw_root, output_path)


def test_builder_rejects_output_path_traversal(monkeypatch, tmp_path):
    """Ловит запись производного снимка за пределами data/processed."""
    raw_root, _ = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(raw_root)
    escaped_output = raw_root.parents[2] / "outside.json"

    with pytest.raises(SourceSnapshotError, match="data/processed"):
        build_local_snapshot(raw_root, escaped_output)


def test_builder_marks_legacy_channels_as_unmapped(monkeypatch, tmp_path):
    """Ловит выдуманную связь канала с объектом для старой схемы справочника."""
    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(raw_root)

    snapshot = build_local_snapshot(raw_root, output_path)

    assert snapshot.channels[0].object_id is None
    assert snapshot.data_quality.object_link_available is False
    assert snapshot.data_quality.unmapped_channel_count == 1


def test_builder_accepts_updated_channel_object_link(monkeypatch, tmp_path):
    """Ловит потерю подтверждённой связи из обновлённого справочника каналов."""
    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(raw_root)
    write_csv(
        raw_root / "channels.csv",
        UPDATED_CHANNEL_HEADERS,
        [
            {
                "ид_канала_данных": "20",
                "тип_инж_системы": "ventilation",
                "тип_датчика": "smoke",
                "тег_инженерной_системы": "node-20",
                "название_датчика": "Smoke 20",
                "ид_объект": "5",
            }
        ],
    )

    snapshot = build_local_snapshot(raw_root, output_path)

    assert snapshot.channels[0].object_id == "5"
    assert snapshot.data_quality.object_link_available is True
    assert snapshot.data_quality.unmapped_channel_count == 0


def test_builder_rejects_unknown_channel_object_link(monkeypatch, tmp_path):
    """Не допускает несуществующий объект через обновлённую связь справочника."""
    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(raw_root)
    write_csv(
        raw_root / "channels.csv",
        UPDATED_CHANNEL_HEADERS,
        [
            {
                "ид_канала_данных": "20",
                "тип_инж_системы": "ventilation",
                "тип_датчика": "smoke",
                "тег_инженерной_системы": "node-20",
                "название_датчика": "Smoke 20",
                "ид_объект": "missing-object",
            }
        ],
    )

    with pytest.raises(SourceSnapshotError, match="несуществующий объект"):
        build_local_snapshot(raw_root, output_path)


@pytest.mark.parametrize(
    ("alarm", "quality_code", "analysis_eligible"),
    [("0", "technical_anomaly", False), ("1", "alarm_with_technical_value", True)],
)
def test_builder_classifies_technical_sensor_values(
    monkeypatch, tmp_path, alarm, quality_code, analysis_eligible
):
    """Защищает различие нетревожной ошибки и тревоги с техническим значением."""
    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(
        raw_root,
        events=[
            {
                "ид_события": "technical-event",
                "ид_канала_данных": "20",
                "дата": "2026-08-01",
                "время": "10:00:00",
                "тревожное": alarm,
                "значение_датчика": "-3276",
            }
        ],
    )

    snapshot = build_local_snapshot(raw_root, output_path)

    assert snapshot.events[0].quality_code == quality_code
    assert snapshot.events[0].analysis_eligible is analysis_eligible
    assert snapshot.events[0].provenance == "observed"
    assert snapshot.data_quality.technical_anomaly_count == 1


def test_builder_excludes_2021_migration_period_from_analytics(monkeypatch, tmp_path):
    """Не даёт загрязнённому миграцией периоду молча войти в ML-набор."""
    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(
        raw_root,
        events=[
            {
                "ид_события": "migration-event",
                "ид_канала_данных": "20",
                "дата": "2021-06-01",
                "время": "10:00:00",
                "тревожное": "1",
                "значение_датчика": "42",
            }
        ],
    )
    (raw_root / "ext-journal-2026.csv").rename(raw_root / "ext-journal-2021.csv")

    snapshot = build_local_snapshot(raw_root, output_path)

    assert snapshot.events[0].quality_code == "monitoring_system_migration"
    assert snapshot.events[0].analysis_eligible is False


def test_builder_creates_stable_composite_event_identity(monkeypatch, tmp_path):
    """Ловит коллизию неуникального исходного ID у разных наблюдений."""
    raw_root, output_path = configure_local_roots(monkeypatch, tmp_path)
    write_valid_sources(
        raw_root,
        events=[
            {
                "ид_события": "duplicate",
                "ид_канала_данных": "20",
                "дата": "2026-08-01",
                "время": "10:00:00",
                "тревожное": "1",
                "значение_датчика": "42",
            },
            {
                "ид_события": "duplicate",
                "ид_канала_данных": "20",
                "дата": "2026-08-01",
                "время": "10:01:00",
                "тревожное": "1",
                "значение_датчика": "43",
            },
        ],
    )

    first = build_local_snapshot(raw_root, output_path)
    second = build_local_snapshot(raw_root, output_path)

    assert first.events[0].canonical_id == second.events[0].canonical_id
    assert first.events[0].canonical_id != first.events[1].canonical_id
    assert len(first.events[0].canonical_id) == 64
