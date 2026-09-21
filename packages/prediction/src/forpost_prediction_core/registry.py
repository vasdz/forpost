"""Проверка метаданных локально обученной модели перед serving."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import skops.io as skops_io

from forpost_prediction_core.capabilities import EvidenceTier, PredictionTask


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


@dataclass(frozen=True)
class ModelCard:
    """Проверяемое описание качества и происхождения локальной модели."""

    task: PredictionTask
    version: str
    feature_schema_version: str
    evidence_tier: EvidenceTier
    calibrated: bool
    created_at: datetime
    threshold: float
    feature_columns: tuple[str, ...]
    validation_metrics: dict[str, float]
    test_metrics: dict[str, float]
    label_strategy: str
    horizon_hours: int
    purge_hours: int
    config_sha256: str
    library_versions: dict[str, str]
    dataset_start_at: datetime
    dataset_end_at: datetime
    source_event_count: int
    skipped_source_event_count: int
    history_truncated_before: bool
    fit_row_count: int
    calibration_row_count: int
    validation_row_count: int
    test_row_count: int
    inference_duration_seconds: float


@dataclass(frozen=True)
class ModelBundle:
    """Модель и card после полной проверки целостности."""

    model: Any
    card: ModelCard


_VERSION_PATTERN = re.compile(r"v[1-9]\d*")
_BUNDLE_FILES = ("model.skops", "model-card.json")
_REQUIRED_METRIC_KEYS = frozenset(
    {
        "precision",
        "recall",
        "f1",
        "pr_auc",
        "roc_auc",
        "brier_score",
        "expected_calibration_error",
        "alert_rate",
    }
)
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


def publish_model_bundle(root: Path, model: Any, card: ModelCard) -> Path:
    """Атомарно публикует безопасный локальный bundle с manifest хэшей."""
    return _publish_version(root, model, card, prediction_payload=None)


def publish_model_release(
    root: Path,
    model: Any,
    card: ModelCard,
    prediction_payload: dict[str, object],
) -> Path:
    """Атомарно публикует модель, card, прогнозы и оба manifest одной версией."""
    return _publish_version(root, model, card, prediction_payload=prediction_payload)


def _publish_version(
    root: Path,
    model: Any,
    card: ModelCard,
    *,
    prediction_payload: dict[str, object] | None,
) -> Path:
    _validate_card(card)
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
        skops_io.dump(model, temporary / "model.skops")
        (temporary / "model-card.json").write_text(
            json.dumps(_card_to_dict(card), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        untrusted = skops_io.get_untrusted_types(file=temporary / "model.skops")
        if not set(untrusted) <= _ALLOWED_SKOPS_TYPES:
            raise ModelUnavailableError("Артефакт содержит недоверенные типы модели")
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
            "format_version": 1,
            "task": card.task.value,
            "version": card.version,
            "files": {name: _sha256(temporary / name) for name in _BUNDLE_FILES},
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
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
    """Проверяет manifest, card и типы skops до загрузки модели."""
    unresolved_bundle = Path(bundle_path)
    if unresolved_bundle.is_symlink():
        raise ModelUnavailableError("Каталог модели не прошёл проверку")
    bundle = unresolved_bundle.resolve(strict=True)
    if not bundle.is_dir():
        raise ModelUnavailableError("Каталог модели не прошёл проверку")
    manifest = _read_json(bundle / "manifest.json")
    if manifest.get("format_version") != 1:
        raise ModelUnavailableError("Неизвестная версия manifest модели")
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != set(_BUNDLE_FILES):
        raise ModelUnavailableError("Manifest модели содержит неизвестный набор файлов")
    for name in _BUNDLE_FILES:
        path = _checked_bundle_file(bundle, name)
        if not isinstance(files[name], str) or _sha256(path) != files[name]:
            raise ModelUnavailableError("Нарушена целостность артефактов модели")

    card = _card_from_dict(_read_json(bundle / "model-card.json"))
    _validate_card(card)
    validate_model_metadata(
        ModelMetadata(
            task=card.task,
            version=card.version,
            feature_schema_version=card.feature_schema_version,
            calibrated=card.calibrated,
            created_at=card.created_at,
        ),
        expected_task=expected_task,
        expected_feature_schema_version=expected_feature_schema_version,
    )
    if card.evidence_tier is not maximum_evidence_tier:
        raise ModelUnavailableError("Уровень доказательности модели не соответствует источникам")
    if manifest.get("task") != card.task.value or manifest.get("version") != card.version:
        raise ModelUnavailableError("Manifest модели не соответствует model card")

    model_path = bundle / "model.skops"
    untrusted = skops_io.get_untrusted_types(file=model_path)
    if not set(untrusted) <= _ALLOWED_SKOPS_TYPES:
        raise ModelUnavailableError("Артефакт содержит недоверенные типы модели")
    return ModelBundle(model=skops_io.load(model_path, trusted=untrusted), card=card)


def _validate_card(card: ModelCard) -> None:
    if not _VERSION_PATTERN.fullmatch(card.version):
        raise ModelUnavailableError("Версия модели должна иметь формат vN")
    if card.created_at.tzinfo is None or card.created_at.utcoffset() is None:
        raise ModelUnavailableError("В model card отсутствует часовой пояс")
    if not 0 < card.threshold < 1:
        raise ModelUnavailableError("Рабочий порог модели должен быть от 0 до 1")
    if not card.calibrated and card.evidence_tier in {EvidenceTier.VALIDATED, EvidenceTier.PROXY}:
        raise ModelUnavailableError("Вероятностная модель не прошла калибровку")
    if not card.feature_columns or len(set(card.feature_columns)) != len(card.feature_columns):
        raise ModelUnavailableError("Model card содержит некорректную схему признаков")
    if card.label_strategy != "silence_horizon_proxy":
        raise ModelUnavailableError("Model card содержит неутверждённую стратегию разметки")
    if card.horizon_hours < 24 or card.purge_hours < card.horizon_hours:
        raise ModelUnavailableError("Model card содержит недостаточный temporal embargo")
    if not re.fullmatch(r"[0-9a-f]{64}", card.config_sha256):
        raise ModelUnavailableError("Model card содержит некорректный hash конфига")
    if set(card.library_versions) != {"numpy", "pandas", "scikit-learn", "skops"}:
        raise ModelUnavailableError("Model card не фиксирует версии ML-библиотек")
    if any(not value for value in card.library_versions.values()):
        raise ModelUnavailableError("Model card содержит пустую версию библиотеки")
    if (
        card.dataset_start_at.tzinfo is None
        or card.dataset_end_at.tzinfo is None
        or card.dataset_start_at >= card.dataset_end_at
    ):
        raise ModelUnavailableError("Model card содержит некорректный диапазон данных")
    if (
        card.source_event_count < 1
        or card.skipped_source_event_count < 0
        or type(card.history_truncated_before) is not bool
    ):
        raise ModelUnavailableError("Model card содержит некорректную статистику источника")
    if any(
        value < 1
        for value in (
            card.fit_row_count,
            card.calibration_row_count,
            card.validation_row_count,
            card.test_row_count,
        )
    ):
        raise ModelUnavailableError("Model card содержит пустую часть temporal split")
    if not 0 <= card.inference_duration_seconds < 300:
        raise ModelUnavailableError("Model card не подтверждает inference быстрее 5 минут")
    for metrics in (card.validation_metrics, card.test_metrics):
        if set(metrics) != _REQUIRED_METRIC_KEYS or any(
            not np_is_finite_unit(value) for value in metrics.values()
        ):
            raise ModelUnavailableError("Model card содержит некорректные метрики")


def np_is_finite_unit(value: object) -> bool:
    return isinstance(value, (int, float)) and 0 <= float(value) <= 1


def _card_to_dict(card: ModelCard) -> dict[str, object]:
    payload = asdict(card)
    payload["task"] = card.task.value
    payload["evidence_tier"] = card.evidence_tier.value
    payload["created_at"] = card.created_at.isoformat()
    payload["dataset_start_at"] = card.dataset_start_at.isoformat()
    payload["dataset_end_at"] = card.dataset_end_at.isoformat()
    payload["feature_columns"] = list(card.feature_columns)
    return payload


def _card_from_dict(payload: dict[str, object]) -> ModelCard:
    try:
        allowed = {
            "task",
            "version",
            "feature_schema_version",
            "evidence_tier",
            "calibrated",
            "created_at",
            "threshold",
            "feature_columns",
            "validation_metrics",
            "test_metrics",
            "label_strategy",
            "horizon_hours",
            "purge_hours",
            "config_sha256",
            "library_versions",
            "dataset_start_at",
            "dataset_end_at",
            "source_event_count",
            "skipped_source_event_count",
            "history_truncated_before",
            "fit_row_count",
            "calibration_row_count",
            "validation_row_count",
            "test_row_count",
            "inference_duration_seconds",
        }
        if set(payload) != allowed:
            raise ValueError
        feature_columns = payload["feature_columns"]
        validation_metrics = payload["validation_metrics"]
        test_metrics = payload["test_metrics"]
        if (
            not isinstance(feature_columns, list)
            or not all(isinstance(item, str) for item in feature_columns)
            or not isinstance(validation_metrics, dict)
            or not isinstance(test_metrics, dict)
            or not isinstance(payload["library_versions"], dict)
        ):
            raise ValueError
        return ModelCard(
            task=PredictionTask(str(payload["task"])),
            version=str(payload["version"]),
            feature_schema_version=str(payload["feature_schema_version"]),
            evidence_tier=EvidenceTier(str(payload["evidence_tier"])),
            calibrated=payload["calibrated"] is True,
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            threshold=float(payload["threshold"]),
            feature_columns=tuple(feature_columns),
            validation_metrics={
                str(key): float(value) for key, value in validation_metrics.items()
            },
            test_metrics={str(key): float(value) for key, value in test_metrics.items()},
            label_strategy=str(payload["label_strategy"]),
            horizon_hours=int(payload["horizon_hours"]),
            purge_hours=int(payload["purge_hours"]),
            config_sha256=str(payload["config_sha256"]),
            library_versions={
                str(key): str(value) for key, value in payload["library_versions"].items()
            },
            dataset_start_at=datetime.fromisoformat(str(payload["dataset_start_at"])),
            dataset_end_at=datetime.fromisoformat(str(payload["dataset_end_at"])),
            source_event_count=int(payload["source_event_count"]),
            skipped_source_event_count=int(payload["skipped_source_event_count"]),
            history_truncated_before=payload["history_truncated_before"],
            fit_row_count=int(payload["fit_row_count"]),
            calibration_row_count=int(payload["calibration_row_count"]),
            validation_row_count=int(payload["validation_row_count"]),
            test_row_count=int(payload["test_row_count"]),
            inference_duration_seconds=float(payload["inference_duration_seconds"]),
        )
    except (TypeError, ValueError, KeyError) as error:
        raise ModelUnavailableError("Model card не прошёл проверку схемы") from error


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ModelUnavailableError("Артефакт модели не удалось прочитать") from error
    if not isinstance(value, dict):
        raise ModelUnavailableError("Артефакт модели должен быть JSON-объектом")
    return value


def _checked_bundle_file(bundle: Path, name: str) -> Path:
    unresolved_path = bundle / name
    if unresolved_path.is_symlink():
        raise ModelUnavailableError("Файл модели не прошёл проверку пути")
    path = unresolved_path.resolve(strict=True)
    if path.parent != bundle or not path.is_file():
        raise ModelUnavailableError("Файл модели не прошёл проверку пути")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
