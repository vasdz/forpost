import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from forpost_connectors.local_snapshot import SourceSnapshotError, build_local_snapshot

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
