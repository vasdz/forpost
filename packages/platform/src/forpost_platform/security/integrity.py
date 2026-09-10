import hashlib
from pathlib import Path


class IntegrityVerifier:
    """Проверка контрольных сумм кодовой базы (ГОСТ Р 56939 / Приказ ФСТЭК № 239)."""

    @staticmethod
    def calculate_dir_hash(target_dir: Path) -> str:
        """Рекурсивный расчет хеша sha256 всех .py файлов в директории."""
        hasher = hashlib.sha256()
        for file_path in sorted(target_dir.rglob("*.py")):
            if "__pycache__" in file_path.parts:
                continue
            hasher.update(file_path.read_bytes())
        return hasher.hexdigest()

    @classmethod
    def verify(cls, base_path: Path, expected_hash: str | None = None) -> bool:
        current_hash = cls.calculate_dir_hash(base_path)
        if expected_hash is None:
            # В dev-режиме генерирует актуальный отпечаток
            return True
        return current_hash == expected_hash
