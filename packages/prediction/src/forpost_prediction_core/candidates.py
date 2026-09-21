"""Кандидаты с единым preprocessing и явными адаптерами нативных бустеров."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.utils.validation import check_is_fitted

MODEL_FORMATS = {"catboost": "catboost_cbm", "lightgbm": "lightgbm_text"}
CANDIDATE_COMPLEXITY = {
    "logistic_regression": 0,
    "hist_gradient_boosting": 1,
    "extra_trees": 2,
    "lightgbm": 3,
    "catboost": 4,
}


class NativeBoosterClassifier(ClassifierMixin, BaseEstimator):
    """Приводит native fit/predict к sklearn API без pickle-сериализации."""

    def __init__(self, backend: str, seed: int = 20260915):
        self.backend = backend
        self.seed = seed

    def fit(self, X: np.ndarray, y: np.ndarray) -> NativeBoosterClassifier:  # noqa: N803
        self.classes_ = np.unique(y)
        if not np.array_equal(self.classes_, [0, 1]):
            raise ValueError("Бустер требует оба бинарных класса")
        values = np.asarray(X, dtype=np.float64)
        self.n_features_in_ = values.shape[1]
        if self.backend == "catboost":
            from catboost import CatBoostClassifier

            self.native_model_ = CatBoostClassifier(
                iterations=350,
                depth=7,
                learning_rate=0.04,
                loss_function="Logloss",
                auto_class_weights="Balanced",
                random_seed=self.seed,
                thread_count=-1,
                verbose=False,
                allow_writing_files=False,
            )
            self.native_model_.fit(values, y, plot=False)
        elif self.backend == "lightgbm":
            from lightgbm import LGBMClassifier

            estimator = LGBMClassifier(
                n_estimators=350,
                num_leaves=31,
                learning_rate=0.04,
                min_child_samples=30,
                reg_lambda=1.0,
                class_weight="balanced",
                random_state=self.seed,
                n_jobs=-1,
                verbosity=-1,
                deterministic=True,
                force_col_wise=True,
            ).fit(values, y)
            self.native_model_ = estimator.booster_
        else:
            raise ValueError("Неизвестный кандидат нативного бустера")
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:  # noqa: N803
        check_is_fitted(self, "native_model_")
        values = np.asarray(X, dtype=np.float64)
        if values.ndim != 2 or values.shape[1] != self.n_features_in_:
            raise ValueError("Набор признаков не соответствует нативной модели")
        if self.backend == "catboost":
            return np.asarray(self.native_model_.predict_proba(values), dtype=np.float64)
        probabilities = np.asarray(self.native_model_.predict(values), dtype=np.float64)
        return np.column_stack((1 - probabilities, probabilities))

    def predict(self, X: np.ndarray) -> np.ndarray:  # noqa: N803
        return self.classes_[(self.predict_proba(X)[:, 1] >= 0.5).astype(int)]

    def save_native(self, path: Path) -> None:
        """Сохраняет только бустер; preprocessing и calibration принадлежат registry."""
        check_is_fitted(self, "native_model_")
        if self.backend == "catboost":
            self.native_model_.save_model(str(path), format="cbm")
        elif self.backend == "lightgbm":
            self.native_model_.save_model(str(path))
        else:
            raise ValueError("Неизвестный формат нативной модели")

    @classmethod
    def load_native(cls, path: Path, *, model_format: str) -> NativeBoosterClassifier:
        """Загружает проверенный registry файл только через allow-list форматов."""
        if model_format == "catboost_cbm":
            from catboost import CatBoostClassifier

            adapter = cls("catboost")
            adapter.native_model_ = CatBoostClassifier(allow_writing_files=False, verbose=False)
            adapter.native_model_.load_model(str(path), format="cbm")
            adapter.n_features_in_ = len(adapter.native_model_.feature_names_)
        elif model_format == "lightgbm_text":
            from lightgbm import Booster

            adapter = cls("lightgbm")
            adapter.native_model_ = Booster(model_file=str(path))
            adapter.n_features_in_ = adapter.native_model_.num_feature()
        else:
            raise ValueError("Неизвестный формат нативной модели")
        adapter.classes_ = np.array([0, 1])
        return adapter


def build_candidate_estimators(frame: pd.DataFrame, seed: int) -> dict[str, BaseEstimator]:
    """Фиксирует схему по fit-части; все статистики обучаются только в fit()."""
    numeric = tuple(frame.select_dtypes(include=["number", "bool"]).columns)
    categorical = tuple(column for column in frame.columns if column not in numeric)

    def pipeline(classifier: BaseEstimator) -> Pipeline:
        preprocessing = ColumnTransformer(
            [
                (
                    "numeric",
                    Pipeline(
                        [
                            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
                            ("scale", StandardScaler()),
                        ]
                    ),
                    numeric,
                ),
                (
                    "categorical",
                    Pipeline(
                        [
                            (
                                "imputer",
                                SimpleImputer(strategy="most_frequent", keep_empty_features=True),
                            ),
                            (
                                "one_hot",
                                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                            ),
                        ]
                    ),
                    categorical,
                ),
            ],
            remainder="drop",
        )
        return Pipeline([("preprocess", preprocessing), ("classifier", classifier)])

    return {
        "logistic_regression": pipeline(
            LogisticRegression(
                max_iter=2000,
                class_weight="balanced",
                random_state=seed,
            )
        ),
        "extra_trees": pipeline(
            ExtraTreesClassifier(
                n_estimators=300,
                min_samples_leaf=4,
                class_weight="balanced",
                n_jobs=-1,
                random_state=seed,
            )
        ),
        "hist_gradient_boosting": pipeline(
            HistGradientBoostingClassifier(
                max_iter=250,
                learning_rate=0.05,
                max_leaf_nodes=31,
                l2_regularization=1.0,
                random_state=seed,
            )
        ),
        "catboost": pipeline(NativeBoosterClassifier("catboost", seed)),
        "lightgbm": pipeline(NativeBoosterClassifier("lightgbm", seed)),
    }


def candidate_model_format(name: str) -> str:
    """Сообщает registry требуемый формат, не разрешая публикацию сам по себе."""
    base = name.removesuffix("_sigmoid").removesuffix("_isotonic")
    if base not in CANDIDATE_COMPLEXITY:
        raise ValueError("Неизвестный кандидат модели")
    return MODEL_FORMATS.get(base, "skops")


def assert_prediction_parity(trained: Any, reloaded: Any, features: Any) -> None:
    """Проверяет численную эквивалентность до разрешения публикации."""
    original = np.asarray(trained.predict_proba(features), dtype=np.float64)
    restored = np.asarray(reloaded.predict_proba(features), dtype=np.float64)
    if (
        original.ndim != 2
        or original.shape[1] != 2
        or restored.shape != original.shape
        or not np.isfinite(original).all()
        or not np.isfinite(restored).all()
        or not np.allclose(original, restored, rtol=1e-10, atol=1e-12)
    ):
        raise ValueError("Вероятности сохранённой и исходной модели не совпадают")
