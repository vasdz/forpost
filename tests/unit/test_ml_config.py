from pathlib import Path

import pytest
import yaml
from forpost_prediction_core.config import load_ml_config


def test_repository_ml_config_is_single_source_for_training_policy():
    root = Path(__file__).resolve().parents[2]

    config = load_ml_config(root / "ml" / "config.yaml")

    assert config.label_strategy == "cadence_adjusted_silence_horizon_proxy_v2"
    assert config.feature_schema_version == "6"
    assert config.feature_windows_hours == (1, 6, 24, 72, 168)
    assert config.horizon_hours == 24
    assert config.cutoff_count == 192
    assert config.training.validation_points_per_fold == 17
    assert config.training.purge_hours >= config.horizon_hours
    assert config.training.minimum_precision == 0.7
    assert config.training.minimum_recall == 0.5
    assert len(config.sha256) == 64
    assert len(config.dataset_sha256) == 64


def test_dataset_fingerprint_ignores_training_only_policy(tmp_path):
    root = Path(__file__).resolve().parents[2]
    payload = yaml.safe_load((root / "ml" / "config.yaml").read_text(encoding="utf-8"))

    base_path = tmp_path / "base.yaml"
    base_path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    training_path = tmp_path / "training.yaml"
    training_payload = payload | {"validation_points_per_fold": 16}
    training_path.write_text(yaml.safe_dump(training_payload), encoding="utf-8")
    dataset_path = tmp_path / "dataset.yaml"
    dataset_payload = payload | {"cutoff_count": 64}
    dataset_path.write_text(yaml.safe_dump(dataset_payload), encoding="utf-8")

    base = load_ml_config(base_path)
    training_only = load_ml_config(training_path)
    dataset_change = load_ml_config(dataset_path)

    assert base.sha256 != training_only.sha256
    assert base.dataset_sha256 == training_only.dataset_sha256
    assert base.dataset_sha256 != dataset_change.dataset_sha256


@pytest.mark.parametrize("content", [b"private_source: [secret.xlsx", b"\xff"])
def test_malformed_yaml_is_translated_to_safe_controlled_error(tmp_path, content):
    config_path = tmp_path / "private-config.yaml"
    config_path.write_bytes(content)

    with pytest.raises(ValueError) as error:
        load_ml_config(config_path)

    assert "private" not in str(error.value)
    assert "secret.xlsx" not in str(error.value)
    assert error.value.__suppress_context__


def test_config_rejects_stale_or_arbitrary_feature_schema(tmp_path):
    root = Path(__file__).resolve().parents[2]
    payload = yaml.safe_load((root / "ml" / "config.yaml").read_text(encoding="utf-8"))
    payload["feature_schema_version"] = "7"
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="схем"):
        load_ml_config(path)


@pytest.mark.parametrize(
    "change", ["fold_type", "too_few", "unknown_profile", "unknown_constraint", "balanced_mismatch"]
)
def test_config_rejects_invalid_fold_and_profile_policy(tmp_path, change):
    root = Path(__file__).resolve().parents[2]
    payload = yaml.safe_load((root / "ml" / "config.yaml").read_text(encoding="utf-8"))
    if change == "fold_type":
        payload["minimum_validation_folds"] = "3"
    elif change == "too_few":
        payload["minimum_validation_folds"] = 2
    elif change == "unknown_profile":
        payload["operating_profiles"]["test_selected"] = payload["operating_profiles"]["balanced"]
    elif change == "unknown_constraint":
        payload["operating_profiles"]["balanced"]["test_threshold"] = 0.5
    else:
        payload["operating_profiles"]["balanced"]["minimum_precision"] = 0.1
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        load_ml_config(path)
