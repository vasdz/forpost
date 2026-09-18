from datetime import UTC, datetime

import pytest
from forpost_prediction_core.capabilities import PredictionTask
from forpost_prediction_core.registry import (
    ModelMetadata,
    ModelUnavailableError,
    validate_model_metadata,
)


def test_metadata_validation_accepts_matching_task_and_feature_schema() -> None:
    """Ловит serving модели с другой задачей или другой схемой признаков."""
    metadata = ModelMetadata(
        task=PredictionTask.SENSOR_FAILURE,
        version="local-test",
        feature_schema_version="1",
        calibrated=True,
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
    )

    validate_model_metadata(
        metadata,
        expected_task=PredictionTask.SENSOR_FAILURE,
        expected_feature_schema_version="1",
    )


def test_metadata_validation_rejects_uncalibrated_or_mismatched_model() -> None:
    """Ловит выдачу raw score как вероятности из несовместимого артефакта."""
    metadata = ModelMetadata(
        task=PredictionTask.FIRE_RISK,
        version="local-test",
        feature_schema_version="2",
        calibrated=False,
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(ModelUnavailableError, match="калибровку"):
        validate_model_metadata(
            metadata,
            expected_task=PredictionTask.FIRE_RISK,
            expected_feature_schema_version="2",
        )
    with pytest.raises(ModelUnavailableError, match="Модель"):
        validate_model_metadata(
            metadata,
            expected_task=PredictionTask.SENSOR_FAILURE,
            expected_feature_schema_version="2",
        )
