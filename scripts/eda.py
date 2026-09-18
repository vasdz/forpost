"""CLI полного потокового EDA локальной выгрузки СМВУ."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONNECTORS_SOURCE = REPOSITORY_ROOT / "packages" / "connectors" / "src"
if str(CONNECTORS_SOURCE) not in sys.path:
    sys.path.insert(0, str(CONNECTORS_SOURCE))

from forpost_connectors.eda import (  # noqa: E402
    EdaConfig,
    EdaError,
    analyze_dataset,
    write_interim_outputs,
    write_report,
)


class _SafeArgumentParser(argparse.ArgumentParser):
    """Не выводит в терминал значения некорректных аргументов запуска."""

    def error(self, message: str) -> None:
        raise ValueError("Некорректные параметры запуска") from None


def parse_arguments(argv: list[str] | None, config: EdaConfig) -> argparse.Namespace:
    """Разбирает воспроизводимые параметры анализа без сетевых источников."""
    parser = _SafeArgumentParser(description="Потоковый EDA локальной выгрузки СМВУ")
    parser.add_argument("--raw-root", type=Path, default=config.allowed_raw_root / "extracted")
    parser.add_argument("--interim-root", type=Path, default=config.allowed_interim_root / "eda")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--figures", type=Path)
    parser.add_argument("--chunk-size", type=int, default=config.chunk_size)
    parser.add_argument("--silent-days", type=int, default=config.silent_days)
    parser.add_argument("--outlier-z", type=float, default=config.outlier_z)
    parser.add_argument("--max-bitmap-mib", type=int)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, base_config: EdaConfig | None = None) -> int:
    """Запускает EDA и выводит только безопасные агрегаты выполнения."""
    initial_config = base_config or EdaConfig()
    try:
        arguments = parse_arguments(argv, initial_config)
        config = replace(
            initial_config,
            chunk_size=arguments.chunk_size,
            silent_days=arguments.silent_days,
            outlier_z=arguments.outlier_z,
            max_bitmap_bytes=(
                arguments.max_bitmap_mib * 1024 * 1024
                if arguments.max_bitmap_mib is not None
                else initial_config.max_bitmap_bytes
            ),
        )
        result = analyze_dataset(
            arguments.raw_root,
            config,
            duplicate_temp_root=arguments.interim_root / ".duplicate-id-runs",
        )
        write_interim_outputs(result, arguments.interim_root, config)
        report_path = arguments.report or arguments.interim_root / "report" / "ML_DATA_REPORT.md"
        figures_root = arguments.figures or arguments.interim_root / "report" / "assets"
        command = (
            "python scripts/eda.py "
            f"--chunk-size {config.chunk_size} --silent-days {config.silent_days} "
            f"--outlier-z {config.outlier_z:g}"
        )
        write_report(result, report_path, figures_root, config, command=command)
    except EdaError as error:
        print(f"EDA не выполнен: {error}", file=sys.stderr)
        return 2
    except (ValueError, argparse.ArgumentError):
        print("EDA не выполнен: некорректные параметры запуска", file=sys.stderr)
        return 2
    except Exception:
        print("EDA не выполнен: внутренний сбой локального анализа", file=sys.stderr)
        return 2
    print("EDA выполнен; локальные артефакты подготовлены.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
