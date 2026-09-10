import pandas as pd


class ColumnMapper:
    """Изолирует изменения названий колонок в файлах организаторов.

    Когда выдадут файлы, мы просто поправим словарь DEFAULT_MAPPING,
    не трогая ни строчки бизнес-логики.
    """

    DEFAULT_MAPPING = {
        # СМВУ
        "Идентификатор": "sensor_id",
        "ID датчика": "sensor_id",
        "sensor_id": "sensor_id",
        "Тип": "sensor_type",
        "Тип датчика": "sensor_type",
        "Время события": "timestamp",
        "Дата/Время": "timestamp",
        "Значение": "raw_value",
        "Результат проверки": "status",
        "Пикет": "picket",
        "Коллектор": "collector_id",
    }

    @classmethod
    def normalize_dataframe(
        cls, df: pd.DataFrame, custom_mapping: dict[str, str] | None = None
    ) -> pd.DataFrame:
        mapping = {**cls.DEFAULT_MAPPING, **(custom_mapping or {})}
        # Переименовываем только те колонки, которые совпали
        rename_dict = {col: mapping[col] for col in df.columns if col in mapping}
        return df.rename(columns=rename_dict)
