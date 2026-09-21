from pathlib import Path

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
