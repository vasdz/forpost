"""CLI для создания локального снимка из принятой обезличенной CSV-выгрузки."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for source_path in (
    REPOSITORY_ROOT / "packages" / "domain" / "src",
    REPOSITORY_ROOT / "packages" / "connectors" / "src",
):
    if str(source_path) not in sys.path:
        sys.path.insert(0, str(source_path))

from forpost_connectors.local_snapshot import (
    PROJECT_ROOT,
    SourceSnapshotError,
    build_local_snapshot,
)


def parse_arguments() -> argparse.Namespace:
    """Разбирает только локальные пути по умолчанию в рабочем дереве проекта."""
    parser = argparse.ArgumentParser(description="Создать ограниченный локальный снимок ситуации")
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=PROJECT_ROOT / "data" / "raw" / "extracted",
        help="Каталог локальной извлечённой CSV-выгрузки",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "local-situation.json",
        help="Путь производного JSON-снимка",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=500,
        help="Максимальное число последних наблюдаемых событий",
    )
    return parser.parse_args()


def main() -> int:
    """Создаёт снимок, не раскрывая метаданные локальных данных в выводе CLI."""
    arguments = parse_arguments()
    try:
        build_local_snapshot(arguments.raw_root, arguments.output, arguments.max_events)
    except (csv.Error, OSError, UnicodeError, ValueError, SourceSnapshotError):
        print(
            "Не удалось создать локальный снимок. Проверьте локальные пути и формат входных CSV.",
            file=sys.stderr,
        )
        return 1
    print("Локальный снимок создан.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
