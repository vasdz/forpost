"""Проверка метаданных локально обученной модели перед serving."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal, Self

import numpy as np
import skops.io as skops_io
from pydantic import AwareDatetime, Field, model_validator
from sklearn.calibration import CalibratedClassifierCV, _SigmoidCalibration
from sklearn.compose import ColumnTransformer
from sklearn.frozen import FrozenEstimator
from sklearn.isotonic import IsotonicRegression
from sklearn.pipeline import Pipeline

from forpost_prediction_core.candidates import NativeBoosterClassifier, assert_prediction_parity
from forpost_prediction_core.capabilities import EvidenceTier, PredictionTask
from forpost_prediction_core.evaluation_report import (
    EvaluationMetrics,
    EvaluationVersion,
    EvidenceString,
    Sha256,
    ValidationEvidence,
)

MAX_MODEL_FILE_BYTES = 256 * 1024 * 1024
MAX_METADATA_BYTES = 256 * 1024
PositiveInt = Annotated[int, Field(strict=True, gt=0)]


class ModelUnavailableError(ValueError):
    """Артефакт нельзя использовать для формирования вероятностей."""


@dataclass(frozen=True)
class ModelMetadata:
    """Минимальный model card, необходимый для безопасного serving."""

    task: PredictionTask
    version: str
    feature_schema_version: str
    calibrated: bool
    created_at: datetime


class ModelCard(ValidationEvidence):
    """Проверяемое описание качества и происхождения локальной модели."""

    task: PredictionTask
    format_version: Literal[2]
    model_format: Literal["skops", "catboost_cbm", "lightgbm_text"]
    version: EvaluationVersion
    feature_schema_version: EvidenceString
    evidence_tier: EvidenceTier
    calibrated: Annotated[bool, Field(strict=True)]
    created_at: AwareDatetime
    threshold: Annotated[float, Field(strict=True, gt=0, lt=1)]
    feature_columns: tuple[EvidenceString, ...]
    validation_metrics: EvaluationMetrics
    test_metrics: EvaluationMetrics
    label_strategy: Literal["cadence_adjusted_silence_horizon_proxy_v2"]
    horizon_hours: Annotated[int, Field(strict=True, ge=24, le=8760)]
    purge_hours: PositiveInt
    config_sha256: Sha256
    dataset_start_at: AwareDatetime
    dataset_end_at: AwareDatetime
    source_event_count: PositiveInt
    skipped_source_event_count: Annotated[int, Field(strict=True, ge=0)]
    history_truncated_before: Annotated[bool, Field(strict=True)]
    fit_row_count: PositiveInt
    calibration_row_count: PositiveInt
    validation_row_count: PositiveInt
    test_row_count: PositiveInt
    inference_duration_seconds: Annotated[float, Field(strict=True, ge=0, lt=300)]

    @model_validator(mode="after")
    def validate_release_evidence(self) -> Self:
        self.require_complete(self.threshold, self.validation_metrics, self.validation_row_count)
        if (
            self.task != PredictionTask.SENSOR_FAILURE
            or not self.calibrated
            or not self.feature_columns
            or len(set(self.feature_columns)) != len(self.feature_columns)
            or self.purge_hours < self.horizon_hours
            or self.dataset_start_at >= self.dataset_end_at
        ):
            raise ValueError("Model card не соответствует контракту задачи")
        return self


@dataclass(frozen=True)
class ModelBundle:
    """Модель и card после полной проверки целостности."""

    model: Any
    card: ModelCard


_FORMAT_FILES = {
    "skops": ("model.skops", "model-card.json"),
    "catboost_cbm": ("model.cbm", "preprocess.skops", "calibration.skops", "model-card.json"),
    "lightgbm_text": ("model.txt", "preprocess.skops", "calibration.skops", "model-card.json"),
}
_ALLOWED_SKOPS_TYPES = frozenset(
    {
        "numpy.dtype",
        "sklearn.calibration._CalibratedClassifier",
        "sklearn.calibration._SigmoidCalibration",
        "sklearn.ensemble._hist_gradient_boosting.predictor.TreePredictor",
        "sklearn.tree._tree.Tree",
    }
)


def validate_model_metadata(
    metadata: ModelMetadata,
    *,
    expected_task: PredictionTask,
    expected_feature_schema_version: str,
) -> None:
    """Не допускает в serving несовместимую или некалиброванную модель."""
    if metadata.task != expected_task:
        raise ModelUnavailableError("Модель не соответствует требуемой задаче")
    if metadata.feature_schema_version != expected_feature_schema_version:
        raise ModelUnavailableError("Модель не соответствует версии схемы признаков")
    if not metadata.calibrated:
        raise ModelUnavailableError("Модель не прошла обязательную калибровку вероятностей")
    if not metadata.version:
        raise ModelUnavailableError("У модели отсутствует локальная версия")
    if metadata.created_at.tzinfo is None:
        raise ModelUnavailableError("У метаданных модели отсутствует часовой пояс")


def publish_model_bundle(root: Path, model: Any, card: ModelCard, *, parity_features=None) -> Path:
    """Атомарно публикует безопасный локальный bundle с manifest хэшей."""
    return _publish_version(
        root, model, card, prediction_payload=None, parity_features=parity_features
    )


def publish_model_release(
    root: Path,
    model: Any,
    card: ModelCard,
    prediction_payload: dict[str, object],
    *,
    parity_features=None,
) -> Path:
    """Атомарно публикует модель, card, прогнозы и оба manifest одной версией."""
    return _publish_version(
        root, model, card, prediction_payload=prediction_payload, parity_features=parity_features
    )


def _publish_version(
    root: Path,
    model: Any,
    card: ModelCard,
    *,
    prediction_payload: dict[str, object] | None,
    parity_features,
) -> Path:
    _validate_card(card)
    if parity_features is None or len(parity_features) == 0:
        raise ModelUnavailableError("Для публикации необходима проверка roundtrip вероятностей")
    if tuple(parity_features.columns) != card.feature_columns:
        raise ModelUnavailableError("Проверочные признаки не соответствуют model card")
    if prediction_payload is not None:
        _validate_prediction_payload(prediction_payload, card)
    registry_root = Path(root).resolve(strict=False)
    registry_root.mkdir(parents=True, exist_ok=True)
    task_root = registry_root / card.task.value
    task_root.mkdir(parents=True, exist_ok=True)
    target = task_root / card.version
    if target.exists():
        raise ModelUnavailableError("Версия модели уже существует")
    temporary = task_root / f".{card.version}-{uuid.uuid4().hex}.tmp"
    try:
        temporary.mkdir(parents=False)
        _save_model(temporary, model, card)
        (temporary / "model-card.json").write_text(
            json.dumps(_card_to_dict(card), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        if prediction_payload is not None:
            encoded = (
                json.dumps(
                    prediction_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                )
                + "\n"
            ).encode("utf-8")
            (temporary / "predictions.json").write_bytes(encoded)
            (temporary / "predictions-manifest.json").write_text(
                json.dumps(
                    {
                        "format_version": 1,
                        "task": card.task.value,
                        "version": card.version,
                        "sha256": hashlib.sha256(encoded).hexdigest(),
                        "model_card_sha256": _sha256(temporary / "model-card.json"),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        manifest = {
            "format_version": 2,
            "task": card.task.value,
            "version": card.version,
            "model_format": card.model_format,
            "feature_schema_version": card.feature_schema_version,
            "files": {name: _sha256(temporary / name) for name in _FORMAT_FILES[card.model_format]},
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        restored = load_model_bundle(
            temporary,
            expected_task=card.task,
            expected_feature_schema_version=card.feature_schema_version,
            maximum_evidence_tier=card.evidence_tier,
        )
        assert_prediction_parity(model, restored.model, parity_features)
        temporary.replace(target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise ModelUnavailableError("Модель не прошла безопасную публикацию") from None
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return target


def _validate_prediction_payload(payload: dict[str, object], card: ModelCard) -> None:
    predictions = payload.get("predictions")
    if set(payload) != {"predictions"} or not isinstance(predictions, list):
        raise ModelUnavailableError("Экспорт прогнозов не соответствует схеме release")
    for item in predictions:
        if not isinstance(item, dict):
            raise ModelUnavailableError("Экспорт прогнозов содержит некорректную запись")
        if (
            item.get("prediction_type") != card.task.value
            or item.get("model_version") != card.version
            or item.get("evidence_tier") != card.evidence_tier.value
            or item.get("calibrated") is not card.calibrated
        ):
            raise ModelUnavailableError("Прогноз не соответствует model card")
        exported_metrics = item.get("model_metrics")
        if not isinstance(exported_metrics, dict) or any(
            exported_metrics.get(key) != card.test_metrics[key]
            for key in ("precision", "recall", "f1", "pr_auc", "brier_score")
        ):
            raise ModelUnavailableError("Метрики прогноза не соответствуют model card")


def load_model_bundle(
    bundle_path: Path,
    *,
    expected_task: PredictionTask,
    expected_feature_schema_version: str,
    maximum_evidence_tier: EvidenceTier,
) -> ModelBundle:
    """Проверяет ограниченные файлы, точный manifest и card до десериализации."""
    try:
        unresolved = Path(bundle_path)
        if any(path.is_symlink() for path in (unresolved, *unresolved.parents)):
            raise ModelUnavailableError("Каталог модели не прошёл проверку")
        bundle = unresolved.resolve(strict=True)
        if not bundle.is_dir():
            raise ModelUnavailableError("Каталог модели не прошёл проверку")
        manifest = _read_json(_read_bundle_bytes(bundle, "manifest.json"))
        if (
            set(manifest)
            != {
                "format_version",
                "task",
                "version",
                "model_format",
                "feature_schema_version",
                "files",
            }
            or type(manifest["format_version"]) is not int
            or manifest["format_version"] != 2
        ):
            raise ModelUnavailableError("Неизвестная схема manifest модели")
        model_format = manifest["model_format"]
        if not isinstance(model_format, str) or model_format not in _FORMAT_FILES:
            raise ModelUnavailableError("Неизвестный формат модели")
        files = manifest["files"]
        if not isinstance(files, dict) or set(files) != set(_FORMAT_FILES[model_format]):
            raise ModelUnavailableError("Manifest модели содержит неизвестный набор файлов")
        snapshot = {}
        for name, digest in files.items():
            content = _read_bundle_bytes(bundle, name)
            if (
                not isinstance(digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or hashlib.sha256(content).hexdigest() != digest
            ):
                raise ModelUnavailableError("Нарушена целостность артефактов модели")
            snapshot[name] = content
        card = _card_from_dict(_read_json(snapshot["model-card.json"]))
        validate_model_metadata(
            ModelMetadata(
                card.task,
                card.version,
                card.feature_schema_version,
                card.calibrated,
                card.created_at,
            ),
            expected_task=expected_task,
            expected_feature_schema_version=expected_feature_schema_version,
        )
        if card.evidence_tier is not maximum_evidence_tier:
            raise ModelUnavailableError(
                "Уровень доказательности модели не соответствует источникам"
            )
        if any(
            manifest[key] != value
            for key, value in {
                "task": card.task.value,
                "version": card.version,
                "model_format": card.model_format,
                "feature_schema_version": card.feature_schema_version,
            }.items()
        ):
            raise ModelUnavailableError("Manifest модели не соответствует model card")
        model = _load_model(snapshot, card)
        _check_model_schema(model, card)
        return ModelBundle(model=model, card=card)
    except ModelUnavailableError:
        raise
    except Exception:
        raise ModelUnavailableError("Артефакт модели не прошёл безопасную загрузку") from None


@dataclass(frozen=True)
class _NativeCalibratedModel:
    """Явная композиция проверенных компонентов, не сериализуемый Python-объект."""

    preprocess: Any
    classifier: NativeBoosterClassifier
    calibrator: Any

    @property
    def feature_names_in_(self):
        return self.preprocess.feature_names_in_

    def predict_proba(self, features):
        transformed = self.preprocess.transform(features)
        raw = self.classifier.predict_proba(transformed)[:, 1]
        probabilities = self.calibrator.predict(raw)
        return np.column_stack((1 - probabilities, probabilities))

    def predict(self, features):
        return (self.predict_proba(features)[:, 1] >= 0.5).astype(int)


def _calibrated_parts(model):
    if (
        type(model) is not CalibratedClassifierCV
        or len(model.calibrated_classifiers_) != 1
        or not np.array_equal(model.classes_, [0, 1])
    ):
        raise ModelUnavailableError("Требуется одна калиброванная бинарная модель")
    calibrated = model.calibrated_classifiers_[0]
    if len(calibrated.calibrators) != 1 or type(calibrated.calibrators[0]) not in {
        IsotonicRegression,
        _SigmoidCalibration,
    }:
        raise ModelUnavailableError("Неизвестная калибровка модели")
    estimator = calibrated.estimator
    if type(estimator) is FrozenEstimator:
        estimator = estimator.estimator
    return estimator, calibrated.calibrators[0]


def _check_model_schema(model, card):
    names = getattr(model, "feature_names_in_", None)
    if names is None or tuple(names) != card.feature_columns:
        raise ModelUnavailableError("Схема признаков модели не соответствует model card")


def _save_model(bundle, model, card):
    _check_model_schema(model, card)
    estimator, calibrator = _calibrated_parts(model)
    if card.model_format == "skops":
        skops_io.dump(model, bundle / "model.skops")
        return
    if type(estimator) is not Pipeline or tuple(estimator.named_steps) != (
        "preprocess",
        "classifier",
    ):
        raise ModelUnavailableError("Нативный бустер требует явный preprocessing и calibration")
    preprocess, classifier = estimator.named_steps.values()
    backend = {"catboost_cbm": "catboost", "lightgbm_text": "lightgbm"}[card.model_format]
    if (
        type(preprocess) is not ColumnTransformer
        or type(classifier) is not NativeBoosterClassifier
        or classifier.backend != backend
    ):
        raise ModelUnavailableError("Нативный pipeline не соответствует формату модели")
    classifier.save_native(bundle / _FORMAT_FILES[card.model_format][0])
    skops_io.dump(preprocess, bundle / "preprocess.skops")
    skops_io.dump(calibrator, bundle / "calibration.skops")


def _safe_skops(content: bytes):
    untrusted = skops_io.get_untrusted_types(data=content)
    if not set(untrusted) <= _ALLOWED_SKOPS_TYPES:
        raise ModelUnavailableError("Артефакт содержит недоверенные типы модели")
    return skops_io.loads(content, trusted=untrusted)


def _load_model(snapshot, card):
    if card.model_format == "skops":
        model = _safe_skops(snapshot["model.skops"])
        _calibrated_parts(model)
        return model
    preprocess = _safe_skops(snapshot["preprocess.skops"])
    calibrator = _safe_skops(snapshot["calibration.skops"])
    if type(preprocess) is not ColumnTransformer or type(calibrator) not in {
        IsotonicRegression,
        _SigmoidCalibration,
    }:
        raise ModelUnavailableError("Нативный bundle содержит неизвестные компоненты")
    name = _FORMAT_FILES[card.model_format][0]
    with tempfile.TemporaryDirectory(prefix="forpost-model-snapshot-") as directory:
        private = Path(directory)
        _protect_snapshot_directory(private)
        native_path = private / name
        descriptor = os.open(
            native_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(snapshot[name])
        # Windows запрещает замену/запись, пока native parser использует путь.
        # POSIX защищает каталог mode 0700; повторно используется только наша копия.
        with _opened_regular_file(native_path, MAX_MODEL_FILE_BYTES) as stream:
            if stream.read(MAX_MODEL_FILE_BYTES + 1) != snapshot[name]:
                raise ModelUnavailableError("Снимок нативной модели повреждён")
            classifier = NativeBoosterClassifier.load_native(
                native_path, model_format=card.model_format
            )
    return _NativeCalibratedModel(preprocess, classifier, calibrator)


def _validate_card(card: ModelCard) -> None:
    try:
        ModelCard.model_validate(card.model_dump(mode="json"))
    except (ValueError, TypeError, AttributeError):
        raise ModelUnavailableError("Model card не прошёл проверку схемы") from None


def _card_to_dict(card: ModelCard) -> dict[str, object]:
    return card.model_dump(mode="json")


def _card_from_dict(payload: dict[str, object]) -> ModelCard:
    try:
        return ModelCard.model_validate(payload)
    except (ValueError, TypeError):
        raise ModelUnavailableError("Model card не прошёл проверку схемы") from None


def _read_json(content: bytes) -> dict[str, object]:
    try:
        if len(content) > MAX_METADATA_BYTES:
            raise ValueError
        value = json.loads(content)
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (OSError, UnicodeError, ValueError):
        raise ModelUnavailableError("Артефакт модели не удалось прочитать") from None


def _checked_bundle_file(bundle: Path, name: str) -> Path:
    unresolved_path = bundle / name
    limit = MAX_METADATA_BYTES if name.endswith(".json") else MAX_MODEL_FILE_BYTES
    if unresolved_path.is_symlink():
        raise ModelUnavailableError("Файл модели не прошёл проверку пути")
    path = unresolved_path.resolve(strict=True)
    if path.parent != bundle or not path.is_file() or path.stat().st_size > limit:
        raise ModelUnavailableError("Файл модели не прошёл проверку пути или размера")
    return path


def _read_bundle_bytes(bundle: Path, name: str) -> bytes:
    """Единственный ограниченный снимок: hash и parser получают те же bytes."""
    path = _checked_bundle_file(bundle, name)
    limit = MAX_METADATA_BYTES if name.endswith(".json") else MAX_MODEL_FILE_BYTES
    with _opened_regular_file(path, limit) as stream:
        content = stream.read(limit + 1)
        if len(content) > limit:
            raise ModelUnavailableError("Файл модели превышает допустимый размер")
        return content


@contextmanager
def _opened_regular_file(path: Path, limit: int):
    """Проверяет открытый handle и запрещает следование финальному symlink."""
    descriptor = _open_readonly_nofollow(path)
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        linked = path.lstat()
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_size > limit
            or not os.path.samestat(opened, linked)
            or stat.S_ISLNK(linked.st_mode)
            or getattr(linked, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ):
            raise ModelUnavailableError("Открытый файл модели не прошёл проверку")
        yield stream


def _open_readonly_nofollow(path: Path) -> int:
    if os.name != "nt":
        # Каждый каталог открывается относительно уже закреплённого descriptor.
        parts = path.absolute().parts
        directory = os.open(parts[0], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for component in parts[1:-1]:
                child = os.open(
                    component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
                )
                os.close(directory)
                directory = child
            return os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        finally:
            os.close(directory)
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create.restype = wintypes.HANDLE
    # GENERIC_READ, FILE_SHARE_READ, OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT.
    handle = create(str(path), 0x80000000, 1, None, 3, 0x00200000, None)
    if handle == wintypes.HANDLE(-1).value:
        raise OSError("Не удалось безопасно открыть файл модели")
    try:
        final_path = kernel.GetFinalPathNameByHandleW
        final_path.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        final_path.restype = wintypes.DWORD
        capacity = final_path(handle, None, 0, 0)
        if capacity == 0:
            raise OSError("Не удалось проверить путь открытого файла")
        buffer = ctypes.create_unicode_buffer(capacity + 1)
        written = final_path(handle, buffer, len(buffer), 0)
        if not 0 < written < len(buffer):
            raise OSError("Не удалось проверить путь открытого файла")
        actual = buffer.value
        if actual.startswith("\\\\?\\UNC\\"):
            actual = "\\\\" + actual[8:]
        else:
            actual = actual.removeprefix("\\\\?\\")
        if os.path.normcase(actual) != os.path.normcase(str(path.absolute())):
            raise OSError("Открытый файл перенаправлен за пределы проверенного пути")
        return msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        close = kernel.CloseHandle
        close.argtypes = [wintypes.HANDLE]
        close(handle)
        raise


def _protect_snapshot_directory(path: Path) -> None:
    """Даёт доступ к временной native-копии только владельцу (и SYSTEM в Windows)."""
    if os.name != "nt":
        path.chmod(0o700)
        return
    import ctypes
    from ctypes import wintypes

    security = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    convert = security.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPVOID),
        wintypes.LPVOID,
    ]
    convert.restype = wintypes.BOOL
    apply = security.SetFileSecurityW
    apply.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPVOID]
    apply.restype = wintypes.BOOL
    release = kernel.LocalFree
    release.argtypes = [wintypes.LPVOID]
    descriptor = wintypes.LPVOID()
    if not convert("D:P(A;OICI;FA;;;OW)(A;OICI;FA;;;SY)", 1, ctypes.byref(descriptor), None):
        raise OSError("Не удалось защитить каталог снимка модели")
    try:
        if not apply(str(path), 0x80000004, descriptor):
            raise OSError("Не удалось защитить каталог снимка модели")
    finally:
        release(descriptor)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
