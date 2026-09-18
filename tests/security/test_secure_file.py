import zipfile

import pandas as pd
import pytest
from forpost_connectors.secure_file import SecureFileInspector, SecurityError


def test_sanitize_dataframe_prevents_formula_injection():
    """Тест защиты от выполнения вредоносных формул в таблицах диспетчеров."""
    raw_data = {
        "sensor_id": [
            "=CMD|' /C calc'!A0",
            "+12345",
            "-cmd|' /C notepad'!A0",
            "@SUM(A1:A2)",
            "normal_id_101",
        ]
    }
    df = pd.DataFrame(raw_data)
    sanitized_df = SecureFileInspector.sanitize_dataframe(df)

    # Все формульные префиксы должны экранироваться одинарным апострофом
    assert sanitized_df["sensor_id"][0] == "'=CMD|' /C calc'!A0"
    assert sanitized_df["sensor_id"][1] == "'+12345"
    assert sanitized_df["sensor_id"][2] == "'-cmd|' /C notepad'!A0"
    assert sanitized_df["sensor_id"][3] == "'@SUM(A1:A2)"
    assert sanitized_df["sensor_id"][4] == "normal_id_101"


def test_invalid_archive_preserves_the_zip_cause_without_exposing_a_legacy_exception_name():
    """Потеря первопричины сделает расследование отказа загрузчика непроверяемым."""

    with pytest.raises(SecurityError) as error:
        SecureFileInspector.validate_excel_archive(b"not-an-archive")

    assert isinstance(error.value.__cause__, zipfile.BadZipFile)
