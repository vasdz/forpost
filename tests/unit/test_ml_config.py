from pathlib import Path

import pytest
from forpost_prediction_core.config import load_ml_config


def test_repository_ml_config_is_single_source_for_training_policy():
    root = Path(__file__).resolve().parents[2]

    config = load_ml_config(root / "ml" / "config.yaml")

    assert config.label_strategy == "silence_horizon_proxy"
    assert config.feature_schema_version == "4"
    assert config.feature_windows_hours == (1, 6, 24)
    assert config.horizon_hours == 24
    assert config.training.purge_hours >= config.horizon_hours
    assert config.training.minimum_precision == 0.7
    assert config.training.minimum_recall == 0.5
    assert len(config.sha256) == 64


@pytest.mark.parametrize("content", [b"private_source: [secret.xlsx", b"\xff"])
def test_malformed_yaml_is_translated_to_safe_controlled_error(tmp_path, content):
    config_path = tmp_path / "private-config.yaml"
    config_path.write_bytes(content)

    with pytest.raises(ValueError) as error:
        load_ml_config(config_path)

    assert "private" not in str(error.value)
    assert "secret.xlsx" not in str(error.value)
    assert error.value.__suppress_context__
