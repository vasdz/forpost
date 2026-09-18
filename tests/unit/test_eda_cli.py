import csv
import json
from pathlib import Path

from forpost_connectors.eda import EdaConfig

import scripts.eda as eda_cli
from scripts.eda import main


def write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(rows)


def test_cli_creates_all_outputs_and_prints_only_safe_summary(tmp_path: Path, capsys) -> None:
    """Ловит CLI без полного набора артефактов либо с выводом исходной строки."""
    project_root = tmp_path / "project"
    raw_root = project_root / "data" / "raw" / "extracted"
    interim_root = project_root / "data" / "interim" / "eda"
    docs_root = project_root / "docs"
    report = interim_root / "report" / "ML_DATA_REPORT.md"
    figures = interim_root / "report" / "assets"
    write_csv(
        raw_root / "channels.csv",
        [
            "ид_канала_данных",
            "тип_инж_системы",
            "тип_датчика",
            "тег_инженерной_системы",
            "название_датчика",
        ],
        [["10", "СМВУ", "temperature", "SECRET-TAG", "SECRET-NAME"]],
    )
    write_csv(
        raw_root / "objects.csv",
        [
            "ид_объект",
            "иерархия_уровень",
            "родитель",
            "вид_объекта",
            "диспетчерское_название_объекта",
        ],
        [["1", "1", "0", "коллектор", "SECRET-OBJECT"]],
    )
    write_csv(
        raw_root / "ext-journal-2026.csv",
        ["ид_события", "ид_канала_данных", "дата", "время", "тревожное", "значение_датчика"],
        [["8", "10", "2026-01-01", "00:00:00", "0", "20"]],
    )
    config = EdaConfig(
        allowed_raw_root=project_root / "data" / "raw",
        allowed_interim_root=project_root / "data" / "interim",
        allowed_docs_root=docs_root,
        chunk_size=1,
        max_bitmap_bytes=1,
    )

    exit_code = main(
        [
            "--raw-root",
            str(raw_root),
            "--interim-root",
            str(interim_root),
            "--report",
            str(report),
            "--figures",
            str(figures),
            "--silent-days",
            "7",
            "--outlier-z",
            "2",
            "--max-bitmap-mib",
            "1",
        ],
        base_config=config,
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "локальные артефакты подготовлены" in output
    assert "строк=" not in output
    assert "SECRET" not in output
    assert report.is_file()
    assert (interim_root / "profile.json").is_file()
    assert (interim_root / "channel_metrics.csv").is_file()
    assert len(list(figures.glob("*.svg"))) == 6
    assert json.loads((interim_root / "profile.json").read_text(encoding="utf-8"))[
        "parameters"
    ] == {
        "chunk_size": 1,
        "outlier_z": 2.0,
        "silent_days": 7,
    }
    assert "по порогу 7 суток" in report.read_text(encoding="utf-8")


def test_cli_returns_safe_error_code_for_invalid_local_path(tmp_path: Path, capsys) -> None:
    """Ловит traceback или успешный код возврата при выходе входного пути за data/raw."""
    project_root = tmp_path / "project"
    config = EdaConfig(
        allowed_raw_root=project_root / "data" / "raw",
        allowed_interim_root=project_root / "data" / "interim",
        allowed_docs_root=project_root / "docs",
    )

    exit_code = main(["--raw-root", str(tmp_path / "outside")], base_config=config)

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "EDA не выполнен" in captured.err
    assert str(tmp_path / "outside") not in captured.err


def test_cli_hides_unexpected_exception_details(tmp_path: Path, capsys, monkeypatch) -> None:
    """Ловит traceback с локальным путём при системном сбое потокового анализа."""
    project_root = tmp_path / "project"
    config = EdaConfig(
        allowed_raw_root=project_root / "data" / "raw",
        allowed_interim_root=project_root / "data" / "interim",
        allowed_docs_root=project_root / "docs",
    )

    def fail_analysis(*_args, **_kwargs):
        raise OSError("C:/private/forpost-data.csv")

    monkeypatch.setattr(eda_cli, "analyze_dataset", fail_analysis)

    exit_code = main([], base_config=config)

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "внутренний сбой локального анализа" in captured.err
    assert "private" not in captured.err


def test_cli_hides_argument_parser_details(tmp_path: Path, capsys) -> None:
    """Ловит стандартную диагностику argparse, повторяющую пользовательское значение."""
    project_root = tmp_path / "project"
    config = EdaConfig(
        allowed_raw_root=project_root / "data" / "raw",
        allowed_interim_root=project_root / "data" / "interim",
        allowed_docs_root=project_root / "docs",
    )

    exit_code = main(["--chunk-size", "private-value"], base_config=config)

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "некорректные параметры запуска" in captured.err
    assert "private-value" not in captured.err


def test_cli_default_config_keeps_the_local_data_roots(monkeypatch) -> None:
    """Характеризует конфигурацию CLI до первого чтения реальной выгрузки."""
    observed = {}

    def stop_after_configuration(_raw_root, config, **_kwargs):
        observed["config"] = config
        raise RuntimeError("stop")

    monkeypatch.setattr(eda_cli, "analyze_dataset", stop_after_configuration)

    assert main([]) == 2
    config = observed["config"]
    assert config.allowed_interim_root == config.allowed_raw_root.parent / "interim"
