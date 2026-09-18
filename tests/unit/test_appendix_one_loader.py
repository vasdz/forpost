from datetime import datetime

import forpost_connectors.appendix_one_loader as appendix_loader_module
import pandas as pd
import pytest
from forpost_connectors.appendix_one_loader import AppendixOneExcelLoader, SourceSchemaError
from forpost_connectors.secure_file import SecureFileInspector
from pydantic import ValidationError

EVENT_COLUMNS = [
    "ИД записи журнала",
    "ИД канала данных",
    "ИД типа канала данных",
    "Текущее значение",
    "Дата записи",
]
CHANNEL_COLUMNS = ["ИД канала данных", "Тег в дереве объектов"]
CHANNEL_TYPE_COLUMNS = [
    "ИД типа канала датчика",
    "Название",
    "Диспетчерское название",
]
TREE_COLUMNS = ["ИД записи", "ИД системы", "Диспетчерское название", "Название"]


def write_appendix_one_files(
    tmp_path, *, events=None, channels=None, channel_types=None, tree=None
):
    """Создаёт полный синтетический комплект файлов Appendix 1 для контрактного теста."""
    tables = {
        "events": (
            EVENT_COLUMNS,
            events
            or [
                {
                    "ИД записи журнала": 101,
                    "ИД канала данных": 11,
                    "ИД типа канала данных": 2,
                    "Текущее значение": "1",
                    "Дата записи": "15.09.2026 14:30",
                }
            ],
        ),
        "channels": (
            CHANNEL_COLUMNS,
            channels or [{"ИД канала данных": 11, "Тег в дереве объектов": "СМВУ.01.ДВ.11"}],
        ),
        "channel_types": (
            CHANNEL_TYPE_COLUMNS,
            channel_types
            or [
                {
                    "ИД типа канала датчика": type_id,
                    "Название": f"Тип {type_id}",
                    "Диспетчерское название": f"Диспетчерский тип {type_id}",
                }
                for type_id in (2, 3, 4, 5, 6, 7, 8, 9, 12)
            ],
        ),
        "tree": (
            TREE_COLUMNS,
            [
                {
                    "ИД записи": 1,
                    "ИД системы": 1001,
                    "Диспетчерское название": "СМВУ-01",
                    "Название": "Система мониторинга 01",
                }
            ]
            if tree is None
            else tree,
        ),
    }
    paths = {}
    for name, (columns, rows) in tables.items():
        path = tmp_path / f"{name}.xlsx"
        pd.DataFrame(rows, columns=columns).to_excel(path, index=False)
        paths[name] = path
    return paths


def load_synthetic_appendix_one(tmp_path, **tables):
    paths = write_appendix_one_files(tmp_path, **tables)
    return AppendixOneExcelLoader(allowed_root=tmp_path).load(
        events_path=paths["events"],
        channels_path=paths["channels"],
        channel_types_path=paths["channel_types"],
        tree_path=paths["tree"],
    )


def test_loader_builds_immutable_monitoring_records_from_canonical_appendix_one_headers(tmp_path):
    """Ловит потерю точного маппинга полей или формата даты в журнале событий."""
    imported = load_synthetic_appendix_one(tmp_path)

    assert imported.events[0].event_id == 101
    assert imported.events[0].recorded_at == datetime(2026, 9, 15, 14, 30)
    assert imported.channels[0].object_tag == "СМВУ.01.ДВ.11"
    with pytest.raises(ValidationError):
        imported.events[0].event_id = 999


@pytest.mark.parametrize(
    ("type_id", "expected_slug"),
    [
        (2, "contact-unlock-norm"),
        (3, "switch"),
        (4, "smoke"),
        (5, "movement"),
        (6, "gas"),
        (7, "pump"),
        (8, "fan"),
        (9, "phase"),
        (12, "temperature"),
    ],
)
def test_loader_assigns_each_allowed_channel_type_its_contract_slug(
    tmp_path, type_id, expected_slug
):
    """Ловит неверное соответствие ID типа датчика и доменного slug."""
    imported = load_synthetic_appendix_one(
        tmp_path,
        events=[
            {
                "ИД записи журнала": 101,
                "ИД канала данных": 11,
                "ИД типа канала данных": type_id,
                "Текущее значение": "1",
                "Дата записи": "15.09.2026 14:30",
            }
        ],
    )

    channel_type = next(item for item in imported.channel_types if item.type_id == type_id)
    assert channel_type.slug == expected_slug


@pytest.mark.parametrize(
    ("table_name", "columns"),
    [
        ("events", EVENT_COLUMNS[:-1]),
        ("channels", [*CHANNEL_COLUMNS, "Лишняя колонка"]),
    ],
)
def test_loader_rejects_source_table_with_missing_or_extra_columns(tmp_path, table_name, columns):
    """Ловит неявную подмену схемы источника организатора."""
    paths = write_appendix_one_files(tmp_path)
    pd.read_excel(paths[table_name]).reindex(columns=columns).to_excel(
        paths[table_name], index=False
    )

    with pytest.raises(SourceSchemaError, match="колон"):
        AppendixOneExcelLoader(allowed_root=tmp_path).load(
            events_path=paths["events"],
            channels_path=paths["channels"],
            channel_types_path=paths["channel_types"],
            tree_path=paths["tree"],
        )


@pytest.mark.parametrize(
    ("table_name", "rows"),
    [
        (
            "events",
            [
                {
                    "ИД записи журнала": 101,
                    "ИД канала данных": 11,
                    "ИД типа канала данных": 2,
                    "Текущее значение": "1",
                    "Дата записи": "15.09.2026 14:30",
                },
                {
                    "ИД записи журнала": 101,
                    "ИД канала данных": 11,
                    "ИД типа канала данных": 2,
                    "Текущее значение": "0",
                    "Дата записи": "15.09.2026 14:31",
                },
            ],
        ),
        (
            "channels",
            [
                {"ИД канала данных": 11, "Тег в дереве объектов": "СМВУ.01.ДВ.11"},
                {"ИД канала данных": 11, "Тег в дереве объектов": "СМВУ.01.ДВ.12"},
            ],
        ),
    ],
)
def test_loader_rejects_duplicate_primary_identifiers(tmp_path, table_name, rows):
    """Ловит дубли идентификаторов, которые сделали бы импорт неоднозначным."""
    with pytest.raises(SourceSchemaError, match="дубликат"):
        load_synthetic_appendix_one(tmp_path, **{table_name: rows})


@pytest.mark.parametrize(
    "events",
    [
        [
            {
                "ИД записи журнала": 101,
                "ИД канала данных": 999,
                "ИД типа канала данных": 2,
                "Текущее значение": "1",
                "Дата записи": "15.09.2026 14:30",
            }
        ],
        [
            {
                "ИД записи журнала": 101,
                "ИД канала данных": 11,
                "ИД типа канала данных": 999,
                "Текущее значение": "1",
                "Дата записи": "15.09.2026 14:30",
            }
        ],
    ],
)
def test_loader_rejects_event_with_broken_channel_or_type_reference(tmp_path, events):
    """Ловит события, ссылающиеся на отсутствующий канал либо тип датчика."""
    with pytest.raises(SourceSchemaError, match="ссыл"):
        load_synthetic_appendix_one(tmp_path, events=events)


def test_loader_rejects_timestamp_outside_appendix_one_exact_format(tmp_path):
    """Ловит Excel-дату, не соответствующую точному контракту dd.MM.yyyy HH:mm."""
    with pytest.raises(SourceSchemaError, match="Дата записи"):
        load_synthetic_appendix_one(
            tmp_path,
            events=[
                {
                    "ИД записи журнала": 101,
                    "ИД канала данных": 11,
                    "ИД типа канала данных": 2,
                    "Текущее значение": "1",
                    "Дата записи": "2026-09-15 14:30",
                }
            ],
        )


@pytest.mark.parametrize("timestamp", ["5.9.2026 4:03", "15.09.2026 14:3"])
def test_loader_rejects_timestamp_that_does_not_use_exact_zero_padded_grammar(tmp_path, timestamp):
    """Ловит неявное принятие strptime однозначных дня, месяца, часа или минуты."""
    with pytest.raises(SourceSchemaError, match="Дата записи"):
        load_synthetic_appendix_one(
            tmp_path,
            events=[
                {
                    "ИД записи журнала": 101,
                    "ИД канала данных": 11,
                    "ИД типа канала данных": 2,
                    "Текущее значение": "1",
                    "Дата записи": timestamp,
                }
            ],
        )


@pytest.mark.parametrize("timestamp", [" 15.09.2026 14:30", "15.09.2026 14:30 "])
def test_loader_rejects_timestamp_with_surrounding_whitespace(tmp_path, timestamp):
    """Ловит неявное удаление пробелов вокруг точного значения даты источника."""
    with pytest.raises(SourceSchemaError, match="Дата записи"):
        load_synthetic_appendix_one(
            tmp_path,
            events=[
                {
                    "ИД записи журнала": 101,
                    "ИД канала данных": 11,
                    "ИД типа канала данных": 2,
                    "Текущее значение": "1",
                    "Дата записи": timestamp,
                }
            ],
        )


def test_loader_rejects_excel_datetime_instead_of_appendix_one_timestamp_string(tmp_path):
    """Ловит Excel datetime, который нельзя неявно привести к строковому контракту."""
    with pytest.raises(SourceSchemaError, match="Дата записи"):
        load_synthetic_appendix_one(
            tmp_path,
            events=[
                {
                    "ИД записи журнала": 101,
                    "ИД канала данных": 11,
                    "ИД типа канала данных": 2,
                    "Текущее значение": "1",
                    "Дата записи": datetime(2026, 9, 15, 14, 30),
                }
            ],
        )


@pytest.mark.parametrize(
    ("table_name", "field_name"),
    [
        ("events", "ИД записи журнала"),
        ("events", "ИД канала данных"),
        ("events", "ИД типа канала данных"),
        ("channels", "ИД канала данных"),
        ("channel_types", "ИД типа канала датчика"),
        ("tree", "ИД записи"),
        ("tree", "ИД системы"),
    ],
)
@pytest.mark.parametrize("invalid_identifier", [0, -1])
def test_loader_rejects_zero_and_negative_identifier_in_every_identifier_column(
    tmp_path, table_name, field_name, invalid_identifier
):
    """Ловит передачу невалидного ID в Pydantic вместо ошибки контракта источника."""
    tables = {
        "events": [
            {
                "ИД записи журнала": 101,
                "ИД канала данных": 11,
                "ИД типа канала данных": 2,
                "Текущее значение": "1",
                "Дата записи": "15.09.2026 14:30",
            }
        ],
        "channels": [{"ИД канала данных": 11, "Тег в дереве объектов": "СМВУ.01.ДВ.11"}],
        "channel_types": [
            {
                "ИД типа канала датчика": 2,
                "Название": "Тип 2",
                "Диспетчерское название": "Диспетчерский тип 2",
            }
        ],
        "tree": [
            {
                "ИД записи": 1,
                "ИД системы": 1001,
                "Диспетчерское название": "СМВУ-01",
                "Название": "Система мониторинга 01",
            }
        ],
    }
    tables[table_name][0][field_name] = invalid_identifier

    with pytest.raises(SourceSchemaError, match="целочисленный идентификатор"):
        load_synthetic_appendix_one(tmp_path, **tables)


def test_loader_rejects_unc_path_before_opening_a_source_file(tmp_path):
    """Ловит сетевой UNC-путь до попытки открыть либо проверить файл."""
    paths = write_appendix_one_files(tmp_path)

    with pytest.raises(SourceSchemaError, match="UNC"):
        AppendixOneExcelLoader(allowed_root=tmp_path).load(
            events_path=r"\\fileserver\appendix\events.xlsx",
            channels_path=paths["channels"],
            channel_types_path=paths["channel_types"],
            tree_path=paths["tree"],
        )


def test_loader_rejects_path_outside_configured_local_root_before_opening(tmp_path):
    """Ловит локальный путь за пределами явно разрешённого дерева импорта."""
    paths = write_appendix_one_files(tmp_path)

    with pytest.raises(SourceSchemaError, match="разрешённого"):
        AppendixOneExcelLoader(allowed_root=tmp_path).load(
            events_path=tmp_path.parent / "outside.xlsx",
            channels_path=paths["channels"],
            channel_types_path=paths["channel_types"],
            tree_path=paths["tree"],
        )


def test_loader_rejects_unsupported_channel_type_identifier(tmp_path):
    """Ловит тип канала, для которого нет утверждённого доменного slug."""
    with pytest.raises(SourceSchemaError, match="неподдерживаемый"):
        load_synthetic_appendix_one(
            tmp_path,
            channel_types=[
                {
                    "ИД типа канала датчика": 999,
                    "Название": "Неизвестный тип",
                    "Диспетчерское название": "Неизвестный тип",
                }
            ],
        )


@pytest.mark.parametrize(
    ("table_name", "rows"),
    [
        (
            "channel_types",
            [
                {
                    "ИД типа канала датчика": 2,
                    "Название": "Тип 2",
                    "Диспетчерское название": "Диспетчерский тип 2",
                },
                {
                    "ИД типа канала датчика": 2,
                    "Название": "Повтор типа 2",
                    "Диспетчерское название": "Повтор типа 2",
                },
            ],
        ),
        (
            "tree",
            [
                {
                    "ИД записи": 1,
                    "ИД системы": 1001,
                    "Диспетчерское название": "СМВУ-01",
                    "Название": "Система мониторинга 01",
                },
                {
                    "ИД записи": 1,
                    "ИД системы": 1002,
                    "Диспетчерское название": "СМВУ-02",
                    "Название": "Система мониторинга 02",
                },
            ],
        ),
    ],
)
def test_loader_rejects_duplicate_type_and_tree_identifiers(tmp_path, table_name, rows):
    """Ловит неоднозначные идентификаторы в справочнике типов и дереве систем."""
    with pytest.raises(SourceSchemaError, match="дубликат"):
        load_synthetic_appendix_one(tmp_path, **{table_name: rows})


def test_loader_rejects_xlsx_before_reading_when_compressed_file_exceeds_limit(
    tmp_path, monkeypatch
):
    """Ловит чтение всего XLSX в память до проверки размера файла."""
    paths = write_appendix_one_files(tmp_path)
    monkeypatch.setattr(
        appendix_loader_module,
        "MAX_XLSX_FILE_BYTES",
        paths["events"].stat().st_size - 1,
        raising=False,
    )

    with pytest.raises(SourceSchemaError, match="размер"):
        AppendixOneExcelLoader(allowed_root=tmp_path).load(
            events_path=paths["events"],
            channels_path=paths["channels"],
            channel_types_path=paths["channel_types"],
            tree_path=paths["tree"],
        )


def test_loader_rejects_table_that_exceeds_row_limit(tmp_path, monkeypatch):
    """Ловит неограниченную материализацию строк книги в DataFrame."""
    monkeypatch.setattr(appendix_loader_module, "MAX_TABLE_ROWS", 1, raising=False)

    with pytest.raises(SourceSchemaError, match="строк"):
        load_synthetic_appendix_one(
            tmp_path,
            events=[
                {
                    "ИД записи журнала": 101,
                    "ИД канала данных": 11,
                    "ИД типа канала данных": 2,
                    "Текущее значение": "1",
                    "Дата записи": "15.09.2026 14:30",
                },
                {
                    "ИД записи журнала": 102,
                    "ИД канала данных": 11,
                    "ИД типа канала данных": 2,
                    "Текущее значение": "0",
                    "Дата записи": "15.09.2026 14:31",
                },
            ],
        )


def test_loader_translates_archive_resource_rejection_to_public_schema_error(tmp_path, monkeypatch):
    """Ловит утечку внутреннего SecurityError из публичного API загрузчика."""
    paths = write_appendix_one_files(tmp_path)
    monkeypatch.setattr(SecureFileInspector, "MAX_UNCOMPRESSED_SIZE", 1)

    with pytest.raises(SourceSchemaError, match="безопасно"):
        AppendixOneExcelLoader(allowed_root=tmp_path).load(
            events_path=paths["events"],
            channels_path=paths["channels"],
            channel_types_path=paths["channel_types"],
            tree_path=paths["tree"],
        )


def test_loader_parses_the_same_payload_that_passed_archive_validation(tmp_path, monkeypatch):
    """Ловит повторное открытие пути после проверки уже прочитанных байтов XLSX."""
    paths = write_appendix_one_files(tmp_path)
    replacement_path = tmp_path / "replacement.xlsx"
    pd.DataFrame(
        [
            {
                "ИД записи журнала": 999,
                "ИД канала данных": 11,
                "ИД типа канала данных": 2,
                "Текущее значение": "0",
                "Дата записи": "15.09.2026 14:31",
            }
        ],
        columns=EVENT_COLUMNS,
    ).to_excel(replacement_path, index=False)
    original_validate = SecureFileInspector.validate_excel_archive
    replaced = False

    def replace_path_after_validation(payload):
        nonlocal replaced
        original_validate(payload)
        if not replaced:
            replacement_path.replace(paths["events"])
            replaced = True

    monkeypatch.setattr(
        SecureFileInspector,
        "validate_excel_archive",
        staticmethod(replace_path_after_validation),
    )

    imported = AppendixOneExcelLoader(allowed_root=tmp_path).load(
        events_path=paths["events"],
        channels_path=paths["channels"],
        channel_types_path=paths["channel_types"],
        tree_path=paths["tree"],
    )

    assert imported.events[0].event_id == 101


def test_loader_translates_file_read_error_to_public_schema_error(tmp_path, monkeypatch):
    """Ловит выход исходной ошибки чтения файла через публичный контракт загрузчика."""
    paths = write_appendix_one_files(tmp_path)
    original_open = appendix_loader_module.Path.open

    def fail_events_read(path, *args, **kwargs):
        if path == paths["events"]:
            raise OSError("private filesystem failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(appendix_loader_module.Path, "open", fail_events_read)

    with pytest.raises(SourceSchemaError, match="безопасно") as caught:
        AppendixOneExcelLoader(allowed_root=tmp_path).load(
            events_path=paths["events"],
            channels_path=paths["channels"],
            channel_types_path=paths["channel_types"],
            tree_path=paths["tree"],
        )

    assert "private filesystem failure" not in str(caught.value)
