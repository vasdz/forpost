import csv
import json
from dataclasses import replace
from pathlib import Path

import forpost_connectors.eda as eda
import pytest
from forpost_connectors.eda import (
    EdaConfig,
    EdaError,
    analyze_dataset,
    write_interim_outputs,
    write_report,
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
OBJECT_HEADERS = [
    "ид_объект",
    "иерархия_уровень",
    "родитель",
    "вид_объекта",
    "диспетчерское_название_объекта",
]


def write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def build_fixture(tmp_path: Path) -> tuple[Path, EdaConfig]:
    project_root = tmp_path / "project"
    raw_root = project_root / "data" / "raw" / "extracted"
    write_csv(
        raw_root / "channels.csv",
        CHANNEL_HEADERS,
        [
            {
                "ид_канала_данных": "10",
                "тип_инж_системы": "СМВУ",
                "тип_датчика": "temperature",
                "тег_инженерной_системы": "МК-1",
                "название_датчика": "T",
            },
            {
                "ид_канала_данных": "20",
                "тип_инж_системы": "СМВУ",
                "тип_датчика": "smoke",
                "тег_инженерной_системы": "МК-2",
                "название_датчика": "S",
            },
            {
                "ид_канала_данных": "30",
                "тип_инж_системы": "СМВУ",
                "тип_датчика": "gas",
                "тег_инженерной_системы": "МК-3",
                "название_датчика": "G",
            },
            {
                "ид_канала_данных": "40",
                "тип_инж_системы": "СМВУ",
                "тип_датчика": "contact",
                "тег_инженерной_системы": "МК-4",
                "название_датчика": "C",
            },
        ],
    )
    write_csv(
        raw_root / "objects.csv",
        OBJECT_HEADERS,
        [
            {
                "ид_объект": "1",
                "иерархия_уровень": "1",
                "родитель": "0",
                "вид_объекта": "коллектор",
                "диспетчерское_название_объекта": "Объект",
            }
        ],
    )
    write_csv(
        raw_root / "ext-journal-2019.csv",
        EVENT_HEADERS,
        [
            {
                "ид_события": "1",
                "ид_канала_данных": "10",
                "дата": "2019-01-01",
                "время": "00:00:00",
                "тревожное": "0",
                "значение_датчика": "10",
            },
            {
                "ид_события": "2",
                "ид_канала_данных": "10",
                "дата": "2019-01-02",
                "время": "12:00:00",
                "тревожное": "1",
                "значение_датчика": "12",
            },
            {
                "ид_события": "3",
                "ид_канала_данных": "20",
                "дата": "broken",
                "время": "10:00:00",
                "тревожное": "1",
                "значение_датчика": "bad",
            },
        ],
    )
    write_csv(
        raw_root / "ext-journal-2020.csv",
        EVENT_HEADERS,
        [
            {
                "ид_события": "3",
                "ид_канала_данных": "20",
                "дата": "2020-02-03",
                "время": "23:00:00",
                "тревожное": "1",
                "значение_датчика": "inf",
            },
            {
                "ид_события": "4",
                "ид_канала_данных": "30",
                "дата": "2020-02-04",
                "время": "23:00:00",
                "тревожное": "0",
                "значение_датчика": "0",
            },
            {
                "ид_события": "5",
                "ид_канала_данных": "30",
                "дата": "2020-02-04",
                "время": "23:10:00",
                "тревожное": "0",
                "значение_датчика": "0",
            },
            {
                "ид_события": "6",
                "ид_канала_данных": "30",
                "дата": "2020-02-04",
                "время": "23:20:00",
                "тревожное": "1",
                "значение_датчика": "100",
            },
        ],
    )
    return raw_root, EdaConfig(
        allowed_raw_root=project_root / "data" / "raw",
        allowed_interim_root=project_root / "data" / "interim",
        allowed_docs_root=project_root / "docs",
        chunk_size=2,
        silent_days=30,
        outlier_z=1.0,
        max_bitmap_bytes=1024,
    )


def test_analyze_dataset_builds_exact_streaming_aggregates(tmp_path: Path) -> None:
    """Ловит пропуск файлов, строк, календарных корзин и типов при chunked-чтении."""
    raw_root, config = build_fixture(tmp_path)

    result = analyze_dataset(raw_root, config)

    assert result.total_rows == 7
    assert result.valid_timestamp_rows == 6
    assert result.invalid_timestamp_rows == 1
    assert result.earliest_at == "2019-01-01T00:00:00"
    assert result.latest_at == "2020-02-04T23:20:00"
    assert result.events_by_year == {2019: 2, 2020: 4}
    assert result.events_by_hour[23] == 4
    assert result.events_by_month[1] == 2
    assert result.events_by_month[2] == 4
    assert result.events_by_sensor_type == {"gas": 3, "smoke": 1, "temperature": 2}
    assert result.channel_type_counts == {"contact": 1, "gas": 1, "smoke": 1, "temperature": 1}
    assert result.silent_channel_count == 2
    assert result.never_seen_channel_count == 1
    assert result.silence_undetermined_channel_count == 0
    smoke_metric = next(metric for metric in result.channel_metrics if metric.channel_id == "20")
    assert smoke_metric.event_count == 2
    assert smoke_metric.timed_event_count == 1
    assert smoke_metric.events_per_active_day == 1.0
    assert smoke_metric.silence_status == "активен"
    assert result.false_positive_rate is None


def test_recent_valid_event_overrides_an_undated_event_for_silence_status(tmp_path: Path) -> None:
    """Свежая валидная отметка доказывает активность канала при повреждённой строке."""
    raw_root, config = build_fixture(tmp_path)
    journal = raw_root / "ext-journal-2020.csv"
    with journal.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["7", "30", "broken", "00:00:00", "0", "1"])

    result = analyze_dataset(raw_root, config)

    gas_metric = next(metric for metric in result.channel_metrics if metric.channel_id == "30")
    assert gas_metric.undated_event_count == 1
    assert gas_metric.silence_status == "активен"


def test_analyze_dataset_counts_exact_duplicates_and_value_anomalies(tmp_path: Path) -> None:
    """Ловит приблизительный подсчёт дублей и смешение нечисловых значений с z-выбросами."""
    raw_root, config = build_fixture(tmp_path)

    result = analyze_dataset(raw_root, config)

    assert result.duplicate_event_id_count == 1
    assert result.non_numeric_value_count == 1
    assert result.non_finite_value_count == 1
    assert result.numeric_value_count == 5
    assert result.statistical_outlier_count == 1


def test_analyze_dataset_separates_empty_non_numeric_and_non_finite_values(tmp_path: Path) -> None:
    """Ловит ошибочную подмену явных NaN и бесконечностей нечисловыми значениями."""
    raw_root, config = build_fixture(tmp_path)
    journal = raw_root / "ext-journal-2020.csv"
    with journal.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerows(
            [
                ["7", "10", "2020-02-05", "00:00:00", "0", "NaN"],
                ["8", "10", "2020-02-05", "00:10:00", "0", "-inf"],
                ["9", "10", "2020-02-05", "00:20:00", "0", ""],
                ["10", "10", "2020-02-05", "00:30:00", "0", "not-a-number"],
            ]
        )

    result = analyze_dataset(raw_root, config)

    assert result.numeric_value_count == 5
    assert result.non_numeric_value_count == 2
    assert result.non_finite_value_count == 3
    assert result.missing_counts["значение_датчика"] == 1
    assert (
        result.numeric_value_count
        + result.non_numeric_value_count
        + result.non_finite_value_count
        + result.missing_counts["значение_датчика"]
        == result.total_rows
    )


def test_analyze_dataset_counts_duplicate_identifiers_inside_one_chunk(tmp_path: Path) -> None:
    """Ловит потерю повторов ID, расположенных внутри одной порции чтения."""
    raw_root, config = build_fixture(tmp_path)
    journal = raw_root / "ext-journal-2020.csv"
    with journal.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerows(
            [
                ["7", "30", "2020-02-05", "00:00:00", "0", "1"],
                ["7", "30", "2020-02-05", "00:10:00", "0", "1"],
            ]
        )

    result = analyze_dataset(raw_root, config)

    assert result.duplicate_event_id_count == 2


def test_analyze_dataset_counts_invalid_identifiers_without_skipping_rows(tmp_path: Path) -> None:
    """Ловит остановку полного EDA из-за повреждённых ID и потерю строк в агрегатах."""
    raw_root, config = build_fixture(tmp_path)
    journal = raw_root / "ext-journal-2020.csv"
    with journal.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerows(
            [
                ["not-an-int", "30", "2020-02-05", "00:00:00", "0", "1"],
                ["18446744073709551616", "30", "2020-02-05", "00:10:00", "0", "1"],
            ]
        )

    result = analyze_dataset(raw_root, config)

    assert result.total_rows == 9
    assert result.invalid_event_id_count == 2
    assert result.duplicate_event_id_count == 1


def test_analyze_dataset_uses_exact_external_duplicate_fallback(tmp_path: Path) -> None:
    """Ловит замену точного счёта дублей приближением при разреженном диапазоне ID."""
    raw_root, config = build_fixture(tmp_path)
    journal = raw_root / "ext-journal-2020.csv"
    with journal.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["8", "30", "2020-02-05", "00:00:00", "0", "1"])

    temporary_runs = config.allowed_interim_root / "eda" / "duplicate-runs"
    result = analyze_dataset(
        raw_root,
        replace(config, max_bitmap_bytes=1),
        duplicate_temp_root=temporary_runs,
    )

    assert result.duplicate_event_id_count == 1
    assert temporary_runs.is_dir()
    assert not list(temporary_runs.iterdir())


def test_external_duplicate_fallback_scales_partition_count_for_large_input() -> None:
    """Ловит фиксированное число разделов, превышающее лимит одного раздела."""
    assert eda._external_bucket_count(2_147_483_649) == 128


def test_external_duplicate_fallback_rejects_temp_root_outside_data_interim(tmp_path: Path) -> None:
    """Временные бинарные ID не могут уйти из игнорируемого локального контура."""
    raw_root, config = build_fixture(tmp_path)
    journal = raw_root / "ext-journal-2020.csv"
    with journal.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["8", "30", "2020-02-05", "00:00:00", "0", "1"])

    with pytest.raises(EdaError, match="data/interim"):
        analyze_dataset(
            raw_root,
            replace(config, max_bitmap_bytes=1),
            duplicate_temp_root=tmp_path / "outside",
        )


def test_external_duplicate_fallback_removes_id_runs_after_processing_error(
    tmp_path: Path, monkeypatch
) -> None:
    """Даже при сбое сортировки временные бинарные ID не занимают локальный диск."""
    raw_root, config = build_fixture(tmp_path)
    journal = raw_root / "ext-journal-2020.csv"
    with journal.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["8", "30", "2020-02-05", "00:00:00", "0", "1"])
    temporary_runs = config.allowed_interim_root / "eda" / "duplicate-runs"

    def fail_read(*_args, **_kwargs):
        raise OSError("simulated read failure")

    monkeypatch.setattr(eda.np, "fromfile", fail_read)

    with pytest.raises(OSError, match="simulated"):
        analyze_dataset(
            raw_root,
            replace(config, max_bitmap_bytes=1),
            duplicate_temp_root=temporary_runs,
        )

    assert temporary_runs.is_dir()
    assert not list(temporary_runs.iterdir())


def test_analyze_dataset_rejects_journal_row_with_wrong_field_count(tmp_path: Path) -> None:
    """Ловит повреждённую короткую строку вместо трактовки её как пропуска."""
    raw_root, config = build_fixture(tmp_path)
    journal = raw_root / "ext-journal-2020.csv"
    with journal.open("a", encoding="utf-8", newline="") as stream:
        stream.write("7,30,2020-02-05,00:00:00,0\n")

    with pytest.raises(EdaError, match="число полей"):
        analyze_dataset(raw_root, config)


def test_analyze_dataset_marks_a_channel_above_iqr_threshold_as_noisy(tmp_path: Path) -> None:
    """Ловит нестрогое сравнение с порогом либо неверный расчёт квартилей частоты."""
    project_root = tmp_path / "project"
    raw_root = project_root / "data" / "raw" / "extracted"
    write_csv(
        raw_root / "channels.csv",
        CHANNEL_HEADERS,
        [
            {
                "ид_канала_данных": str(channel_id),
                "тип_инж_системы": "СМВУ",
                "тип_датчика": "temperature",
                "тег_инженерной_системы": f"МК-{channel_id}",
                "название_датчика": f"T-{channel_id}",
            }
            for channel_id in range(1, 6)
        ],
    )
    write_csv(
        raw_root / "objects.csv",
        OBJECT_HEADERS,
        [
            {
                "ид_объект": "1",
                "иерархия_уровень": "1",
                "родитель": "0",
                "вид_объекта": "коллектор",
                "диспетчерское_название_объекта": "Объект",
            }
        ],
    )
    event_rows = [
        {
            "ид_события": str(channel_id),
            "ид_канала_данных": str(channel_id),
            "дата": "2020-01-01",
            "время": "00:00:00",
            "тревожное": "0",
            "значение_датчика": "1",
        }
        for channel_id in range(1, 5)
    ]
    event_rows.extend(
        {
            "ид_события": str(10 + index),
            "ид_канала_данных": "5",
            "дата": "2020-01-01",
            "время": f"00:{index:02d}:00",
            "тревожное": "0",
            "значение_датчика": "1",
        }
        for index in range(10)
    )
    write_csv(raw_root / "ext-journal-2020.csv", EVENT_HEADERS, event_rows)
    config = EdaConfig(
        allowed_raw_root=project_root / "data" / "raw",
        allowed_interim_root=project_root / "data" / "interim",
        allowed_docs_root=project_root / "docs",
        chunk_size=2,
        max_bitmap_bytes=8,
    )

    result = analyze_dataset(raw_root, config)

    assert result.noise_q1 == 1.0
    assert result.noise_q3 == 1.0
    assert result.noise_iqr == 0.0
    assert result.noise_threshold == 1.0
    assert result.noisy_channel_count == 1
    assert next(metric for metric in result.channel_metrics if metric.channel_id == "5").is_noisy


def test_analyze_dataset_counts_events_for_unknown_channels_without_assigning_type(
    tmp_path: Path,
) -> None:
    """Ловит потерю событий с отсутствующим в реестре каналом при построении агрегатов."""
    raw_root, config = build_fixture(tmp_path)
    journal = raw_root / "ext-journal-2020.csv"
    with journal.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["7", "999", "2020-02-05", "00:00:00", "unknown", "1"])

    result = analyze_dataset(raw_root, config)

    assert result.unknown_channel_event_count == 1
    assert sum(metric.event_count for metric in result.channel_metrics) == result.total_rows - 1
    assert sum(result.events_by_sensor_type.values()) == result.valid_timestamp_rows - 1


def test_outputs_keep_all_dataset_facts_local_and_render_accessible_zero_based_svg(
    tmp_path: Path,
) -> None:
    """Ловит утечку агрегатов в docs и вводящую в заблуждение обрезанную ось."""
    raw_root, config = build_fixture(tmp_path)
    result = analyze_dataset(raw_root, config)
    interim_root = config.allowed_interim_root / "eda"
    report_path = interim_root / "report" / "ML_DATA_REPORT.md"
    figures_root = interim_root / "report" / "assets"

    write_interim_outputs(result, interim_root, config)
    write_report(result, report_path, figures_root, config, command="python scripts/eda.py")

    profile = json.loads((interim_root / "profile.json").read_text(encoding="utf-8"))
    report = report_path.read_text(encoding="utf-8")
    expected_figures = {
        "events_by_year.svg",
        "events_by_hour.svg",
        "events_by_weekday.svg",
        "events_by_month.svg",
        "channel_type_distribution.svg",
        "top_noisy_channels.svg",
    }
    assert profile["total_rows"] == 7
    assert profile["max_event_id"] == 6
    assert profile["bitmap_bytes"] == 1
    assert (interim_root / "channel_metrics.csv").is_file()
    assert "## Покрытие и объём" in report
    assert "Недоступно" in report
    assert "python scripts/eda.py" in report
    assert "МК-1" not in report
    assert "августа 2026" not in report
    assert {path.name for path in figures_root.glob("*.svg")} == expected_figures
    for filename in expected_figures:
        svg = (figures_root / filename).read_text(encoding="utf-8")
        assert 'data-y-min="0"' in svg
        assert "<title>" in svg and "<desc>" in svg
        assert "Период:" in svg


def test_output_guards_reject_paths_outside_local_roots(tmp_path: Path) -> None:
    """Ловит запись любых производных фактов вне игнорируемого data/interim."""
    raw_root, config = build_fixture(tmp_path)
    result = analyze_dataset(raw_root, config)

    with pytest.raises(EdaError, match="data/interim"):
        write_interim_outputs(result, tmp_path / "outside", config)
    with pytest.raises(EdaError, match="data/interim"):
        write_report(
            result,
            config.allowed_docs_root / "report.md",
            config.allowed_docs_root / "assets",
            config,
            command="x",
        )


def test_config_rejects_interim_root_outside_the_local_data_layout(tmp_path: Path) -> None:
    """Ловит перенаправление производных ID и агрегатов в произвольный каталог."""
    project_root = tmp_path / "project"

    with pytest.raises(EdaError, match="data/interim"):
        EdaConfig(
            allowed_raw_root=project_root / "data" / "raw",
            allowed_interim_root=project_root / "outside",
            allowed_docs_root=project_root / "docs",
        )


def test_config_rejects_unbounded_chunk_size(tmp_path: Path) -> None:
    """Слишком большая порция не должна разрешать исчерпание памяти одним CSV."""

    project_root = tmp_path / "project"
    with pytest.raises(EdaError, match="Размер порции превышает"):
        EdaConfig(
            allowed_raw_root=project_root / "data" / "raw",
            allowed_interim_root=project_root / "data" / "interim",
            allowed_docs_root=project_root / "docs",
            chunk_size=1_000_001,
        )


def test_discovery_stops_when_file_budget_is_exceeded(tmp_path: Path) -> None:
    """Рекурсивный поиск ограничивает число кандидатов до чтения их содержимого."""

    raw_root, config = build_fixture(tmp_path)
    (raw_root / "extra.csv").write_text("unknown\n", encoding="utf-8")

    with pytest.raises(EdaError, match="лимит CSV"):
        analyze_dataset(raw_root, replace(config, max_csv_files=3))


def test_registry_stops_when_row_budget_is_exceeded(tmp_path: Path) -> None:
    """Реестр не накапливается в памяти сверх заданного бюджета."""

    raw_root, config = build_fixture(tmp_path)

    with pytest.raises(EdaError, match="лимит строк справочника"):
        analyze_dataset(raw_root, replace(config, max_registry_rows=1))


def test_output_write_error_is_exposed_as_domain_diagnostic(tmp_path: Path, monkeypatch) -> None:
    """Ловит необработанный traceback при ошибке записи локальных производных файлов."""
    raw_root, config = build_fixture(tmp_path)
    result = analyze_dataset(raw_root, config)

    def fail_replace(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(eda.os, "replace", fail_replace)

    with pytest.raises(EdaError, match="промежуточные агрегаты"):
        write_interim_outputs(result, config.allowed_interim_root / "eda", config)


def test_repository_report_guide_keeps_dataset_facts_outside_docs() -> None:
    """Публичная документация указывает на локальный отчёт, но не публикует его факты."""
    guide = Path(__file__).resolve().parents[2] / "docs" / "ML_DATA_REPORT.md"

    content = guide.read_text(encoding="utf-8")

    assert "Этот файл намеренно не содержит" in content
    assert "игнорируемом локальном контуре `data/`" in content
    assert "не публикуются в Git, CI-артефактах, чатах" in content
    assert "Полный обработанный объём" not in content
    assert "Период валидных наблюдений" not in content
    assert "События по годам" not in content
