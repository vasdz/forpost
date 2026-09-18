import io
import zipfile

import pandas as pd


class SecurityError(Exception):
    pass


class SecureFileInspector:
    """Контур безопасного приема файлов для закрытого периметра КИИ."""

    # Запрещенные формульные префиксы (CWE-1236: Improper Neutralization of Formula Elements)
    INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
    MAX_UNCOMPRESSED_SIZE = 100 * 1024 * 1024  # Максимум 100 МБ в распакованном виде
    MAX_FILES_COUNT = 500

    @classmethod
    def validate_excel_archive(cls, file_bytes: bytes) -> None:
        """Защита от ZIP-бомб и скрытых исполняемых макросов."""
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                total_uncompressed_size = 0
                for info in z.infolist():
                    # Блокировка макросов VBA
                    if "vbaProject.bin" in info.filename:
                        raise SecurityError("Обнаружен запрещенный исполняемый макрос VBA")

                    total_uncompressed_size += info.file_size
                    if total_uncompressed_size > cls.MAX_UNCOMPRESSED_SIZE:
                        raise SecurityError(
                            "Подозрение на архивную бомбу: превышен лимит распаковки"
                        )

                if len(z.infolist()) > cls.MAX_FILES_COUNT:
                    raise SecurityError("Аномальное количество внутренних дескрипторов в файле")
        except zipfile.BadZipFile as error:
            raise SecurityError("Нарушена структура формата данных") from error

    @classmethod
    def sanitize_dataframe(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Обезвреживание формульных инъекций во всех строковых ячейках."""

        def clean_cell(val):
            if isinstance(val, str) and val.startswith(cls.INJECTION_PREFIXES):
                # Экранирование апострофом по стандартам безопасного экспорта
                return f"'{val}"
            return val

        return df.map(clean_cell)
