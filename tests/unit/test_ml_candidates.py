from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from forpost_prediction_core.candidates import (
    NativeBoosterClassifier,
    assert_prediction_parity,
    build_candidate_estimators,
    candidate_model_format,
)
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator


@pytest.mark.parametrize("backend", ["catboost", "lightgbm"])
@pytest.mark.parametrize("exception_type", [ImportError, ModuleNotFoundError])
@pytest.mark.parametrize("operation", ["fit", "load"])
def test_native_dependency_error_is_sanitized(
    backend, exception_type, operation, monkeypatch, tmp_path
):
    import builtins

    from forpost_prediction_core.training import TrainingUnavailableError

    original_import = builtins.__import__

    def unavailable(name, *args, **kwargs):
        if name == backend:
            raise exception_type("C:/private-source/secret-native-library.dll")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", unavailable)
    with pytest.raises(TrainingUnavailableError) as error:
        if operation == "fit":
            NativeBoosterClassifier(backend).fit(np.array([[0.0], [1.0]]), np.array([0, 1]))
        else:
            NativeBoosterClassifier.load_native(
                tmp_path / "unavailable-model", model_format=candidate_model_format(backend)
            )
    assert "private-source" not in str(error.value)
    assert "secret-native-library" not in str(error.value)
    assert error.value.__suppress_context__


@pytest.mark.parametrize(
    "name", ["logistic_regression", "extra_trees", "hist_gradient_boosting", "catboost", "lightgbm"]
)
def test_candidates_fit_clone_calibrate_and_handle_unseen_categories(name, tmp_path, monkeypatch):
    """Ловит несовместимые sklearn tags, утечку категорий и файловые побочные эффекты."""
    monkeypatch.chdir(tmp_path)
    features = pd.DataFrame({"value": np.tile([0.0, 1.0], 40), "kind": ["a", "b"] * 40})
    labels = np.tile([0, 1], 40)
    estimator = build_candidate_estimators(features, 73)[name]
    first = clone(estimator).fit(features, labels)
    second = clone(estimator).fit(features, labels)
    unknown = features.iloc[:4].assign(kind="new")
    assert_prediction_parity(first, second, unknown)
    calibrated = CalibratedClassifierCV(FrozenEstimator(first), method="sigmoid", ensemble=False)
    calibrated.fit(features, labels)
    probabilities = calibrated.predict_proba(unknown)
    assert probabilities.shape == (4, 2)
    assert np.isfinite(probabilities).all()
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "name,model_format", [("catboost", "catboost_cbm"), ("lightgbm", "lightgbm_text")]
)
def test_native_adapter_roundtrip_preserves_probabilities(name, model_format, tmp_path):
    features = np.tile([[0.0, 0.2], [1.0, 0.8]], (40, 1))
    labels = np.tile([0, 1], 40)
    adapter = NativeBoosterClassifier(name, seed=73).fit(features, labels)
    path = tmp_path / "native-model"
    adapter.save_native(path)
    restored = NativeBoosterClassifier.load_native(path, model_format=model_format)
    assert_prediction_parity(adapter, restored, features)
    assert candidate_model_format(f"{name}_sigmoid") == model_format


def test_unknown_native_format_fails_before_reading_a_file(tmp_path):
    with pytest.raises(ValueError, match="формат"):
        NativeBoosterClassifier.load_native(Path(tmp_path / "absent"), model_format="pickle")


def test_parity_detects_different_predictions():
    features = pd.DataFrame({"x": np.tile([0.0, 1.0], 30)})
    labels = np.tile([0, 1], 30)
    first = build_candidate_estimators(features, 73)["logistic_regression"].fit(features, labels)
    second = clone(first).fit(features, 1 - labels)
    with pytest.raises(ValueError, match="совпадают"):
        assert_prediction_parity(first, second, features)
