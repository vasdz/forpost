"""Контракт безопасного отчёта и сохранения доказательств обучения."""

import importlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError


@pytest.fixture
def reports():
    name = "forpost_prediction_core.evaluation_report"
    assert importlib.util.find_spec(name) is not None, "Отсутствует отдельный отчёт оценки"
    return importlib.import_module(name)


def report_payload(status="rejected"):
    metrics = {
        "precision": 0.8,
        "recall": 0.7,
        "f1": 0.75,
        "pr_auc": 0.8,
        "roc_auc": 0.85,
        "brier_score": 0.12,
        "expected_calibration_error": 0.1,
        "alert_rate": 0.2,
    }
    return {
        "format_version": 1,
        "task": "sensor_failure",
        "version": "v1",
        "status": status,
        "evidence_tier": "proxy",
        "label_strategy": "silence_horizon_proxy",
        "created_at": "2026-09-21T10:00:00Z",
        "reason_code": "validation_rejected" if status == "rejected" else None,
        "quality_thresholds": {
            "minimum_precision": 0.7,
            "minimum_recall": 0.5,
            "maximum_alert_rate": 0.35,
            "maximum_expected_calibration_error": 0.2,
            "maximum_brier_score": 0.25,
            "minimum_baseline_pr_auc_delta": 0.01,
        },
        "split_sizes": {"fit": 100, "calibration": 30, "validation": 40, "test": 40},
        "baseline_validation_pr_auc": 0.25,
        "validation_metrics": metrics if status == "published" else None,
        "test_metrics": metrics if status == "published" else None,
        "threshold": 0.6 if status == "published" else None,
        "champion_name": "extra_trees_isotonic" if status == "published" else None,
    }


@pytest.mark.parametrize("status", ["rejected", "published"])
def test_report_roundtrip_retains_only_exact_evidence(reports, tmp_path, status):
    path = tmp_path / "nested" / "evaluation.json"
    reports.write_evaluation_report(
        path, reports.EvaluationReport.model_validate(report_payload(status))
    )
    loaded = reports.load_evaluation_report(path)
    assert loaded.model_dump(mode="json") == report_payload(status)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.update(raw_path="C:/private/source.xlsx"),
        lambda p: p.pop("split_sizes"),
        lambda p: p["quality_thresholds"].update(extra=0.5),
        lambda p: p["split_sizes"].update(fit=-1),
        lambda p: p["split_sizes"].update(test=True),
        lambda p: p.update(reason_code="C:/private/source.xlsx"),
        lambda p: p.update(created_at="2026-09-21T10:00:00"),
        lambda p: p.update(test_metrics=report_payload("published")["test_metrics"]),
    ],
)
def test_rejected_report_refuses_unknown_fields_and_unsafe_evidence(reports, mutation):
    payload = report_payload()
    mutation(payload)
    with pytest.raises(ValidationError):
        reports.EvaluationReport.model_validate(payload)


@pytest.mark.parametrize("value", [-0.1, 1.1, float("inf"), float("nan"), "0.8", True])
def test_report_refuses_nonfinite_or_unbounded_metrics(reports, value):
    payload = report_payload("published")
    payload["test_metrics"]["precision"] = value
    with pytest.raises(ValidationError):
        reports.EvaluationReport.model_validate(payload)


@pytest.mark.parametrize(
    "field",
    [
        "test_metrics",
        "validation_metrics",
        "threshold",
        "split_sizes",
        "quality_thresholds",
        "champion_name",
    ],
)
def test_published_report_requires_completed_evidence(reports, field):
    payload = report_payload("published")
    payload[field] = None
    with pytest.raises(ValidationError):
        reports.EvaluationReport.model_validate(payload)


def test_failed_atomic_replace_preserves_previous_report(reports, tmp_path, monkeypatch):
    path = tmp_path / "evaluation.json"
    reports.write_evaluation_report(path, reports.EvaluationReport.model_validate(report_payload()))
    original = path.read_bytes()

    def fail_replace(*_args):
        raise OSError("C:/private/report.json")

    monkeypatch.setattr(reports.os, "replace", fail_replace)
    with pytest.raises(reports.EvaluationReportUnavailableError) as error:
        reports.write_evaluation_report(
            path, reports.EvaluationReport.model_validate(report_payload("published"))
        )
    assert "private" not in str(error.value)
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "content",
    [None, b"{", b"\xff", b" " * (256 * 1024 + 1), b"[]"],
    ids=["missing", "invalid", "encoding", "oversized", "array"],
)
def test_loader_fails_closed_with_safe_errors(reports, tmp_path, content):
    path = tmp_path / "private-evaluation.json"
    if content is not None:
        path.write_bytes(content)
    with pytest.raises(reports.EvaluationReportUnavailableError) as error:
        reports.load_evaluation_report(path)
    assert "private" not in str(error.value)


def training_frame():
    rows = []
    for day in range(80):
        for channel in range(4):
            risk = (day + channel) % 8
            rows.append(
                {
                    "prediction_at": pd.Timestamp("2025-01-01", tz="UTC") + pd.Timedelta(days=day),
                    "channel_id": f"channel-{channel}",
                    "sensor_type": "temperature",
                    "event_count_24h": float(10 - risk),
                    "hours_since_last_event": float(risk),
                    "silence_label": int(risk >= 6),
                }
            )
    return pd.DataFrame(rows)


def test_validation_rejection_records_evidence_without_evaluating_test(monkeypatch):
    from forpost_prediction_core import training

    assert hasattr(training, "TrainingEvidence"), "Обучение не сохраняет доступные доказательства"
    evidence = training.TrainingEvidence()
    frame = training_frame()
    test_start = frame.prediction_at.unique()[64]
    original = training.CalibratedClassifierCV.predict_proba

    # Индексы split сбрасываются, поэтому sentinel-признак маркирует будущие строки.
    frame.loc[frame.prediction_at >= test_start, "hours_since_last_event"] = 999

    def guard_future(model, values):
        assert not np.any(values["hours_since_last_event"] == 999), "Test был оценён"
        return original(model, values)

    monkeypatch.setattr(training.CalibratedClassifierCV, "predict_proba", guard_future)
    with pytest.raises(training.TrainingUnavailableError):
        training.train_champion(
            frame,
            label_column="silence_label",
            time_column="prediction_at",
            config=training.TrainingConfig(
                purge_hours=0,
                minimum_precision=1.0,
                minimum_positive_examples=1,
                minimum_negative_examples=1,
            ),
            evidence=evidence,
        )
    assert evidence.stage == "validation"
    assert evidence.split_sizes == {"fit": 152, "calibration": 40, "validation": 64, "test": 64}
    assert evidence.baseline_validation_pr_auc == 0.25
    assert evidence.validation_metrics is None
    assert not hasattr(evidence, "test_metrics")


def test_training_without_observer_retains_identical_result():
    from forpost_prediction_core import training

    assert hasattr(training, "TrainingEvidence"), "Отсутствует наблюдатель доказательств"
    config = training.TrainingConfig(
        purge_hours=0,
        minimum_precision=0.5,
        minimum_recall=0.5,
        maximum_alert_rate=0.6,
        minimum_positive_examples=1,
        minimum_negative_examples=1,
        maximum_expected_calibration_error=1,
        maximum_brier_score=1,
        minimum_baseline_pr_auc_delta=0,
    )
    evidence = training.TrainingEvidence()
    args = {"label_column": "silence_label", "time_column": "prediction_at", "config": config}
    observed = training.train_champion(training_frame(), evidence=evidence, **args)
    unobserved = training.train_champion(training_frame(), **args)
    assert observed.champion_name == unobserved.champion_name
    assert observed.threshold == unobserved.threshold
    assert observed.test_metrics == unobserved.test_metrics
    assert evidence.validation_metrics == unobserved.validation_metrics


@pytest.fixture
def command(tmp_path, monkeypatch):
    from forpost_prediction_core.training import TrainingConfig

    script_path = Path(__file__).resolve().parents[2] / "scripts" / "train_sensor_failure.py"
    spec = importlib.util.spec_from_file_location("evaluation_training_command", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    arguments = SimpleNamespace(
        raw_root=tmp_path / "private-source",
        registry_root=tmp_path / "models",
        version="v1",
        evaluation_report=tmp_path / "evaluation.json",
    )
    config = SimpleNamespace(
        max_training_events=1000,
        horizon_hours=24,
        cutoff_count=80,
        feature_windows_hours=(24,),
        feature_schema_version="sensor-failure-v1",
        label_strategy="silence_horizon_proxy",
        sha256="a" * 64,
        training=TrainingConfig(
            purge_hours=24,
            minimum_precision=0.5,
            minimum_recall=0.5,
            maximum_alert_rate=0.6,
            minimum_positive_examples=1,
            minimum_negative_examples=1,
            maximum_expected_calibration_error=1,
            maximum_brier_score=1,
            minimum_baseline_pr_auc_delta=0,
        ),
    )
    frame = training_frame()
    monkeypatch.setattr(module, "parse_arguments", lambda: arguments)
    monkeypatch.setattr(module, "load_ml_config", lambda _path: config)
    monkeypatch.setattr(
        module,
        "load_training_window",
        lambda *_args, **_kwargs: SimpleNamespace(
            events=[None] * 320, channels=[], skipped_event_count=0, truncated_before=False
        ),
    )
    monkeypatch.setattr(module, "_to_frames", lambda *_args: (frame, frame))
    monkeypatch.setattr(
        module,
        "build_sensor_failure_dataset",
        lambda *_args, **_kwargs: frame.assign(evidence_tier="proxy"),
    )
    monkeypatch.setattr(module, "_current_features", lambda *_args: frame.tail(4))
    return module, arguments, config


def test_command_writes_published_report_only_after_real_release(command, reports):
    module, arguments, _config = command
    assert module.main() == 0
    report = reports.load_evaluation_report(arguments.evaluation_report)
    assert report.status == "published"
    assert report.test_metrics is not None
    card_path = arguments.registry_root / "sensor_failure" / "v1" / "model-card.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    assert report.test_metrics.model_dump() == card["test_metrics"]


def test_command_rejects_validation_without_release_or_test_evidence(command, reports):
    from dataclasses import replace

    module, arguments, config = command
    config.training = replace(config.training, minimum_precision=1.0)
    assert module.main() == 1
    report = reports.load_evaluation_report(arguments.evaluation_report)
    assert report.status == "rejected"
    assert report.reason_code == "validation_rejected"
    assert report.baseline_validation_pr_auc == 0.25
    # Из 16 дней validation один день удалён embargo перед test.
    assert report.split_sizes.validation == 60
    assert report.test_metrics is None
    assert not arguments.registry_root.exists()


def test_command_replaces_stale_report_on_source_failure_without_leaking_error(
    command, reports, monkeypatch, capsys
):
    module, arguments, _config = command
    reports.write_evaluation_report(
        arguments.evaluation_report,
        reports.EvaluationReport.model_validate(report_payload("published")),
    )

    def source_failure(*_args, **_kwargs):
        raise module.SourceSnapshotError("C:/private-source/secret.xlsx")

    monkeypatch.setattr(module, "load_training_window", source_failure)
    assert module.main() == 1
    report = reports.load_evaluation_report(arguments.evaluation_report)
    assert report.status == "rejected"
    assert report.reason_code == "source_unavailable"
    assert report.validation_metrics is None
    assert report.test_metrics is None
    assert "private-source" not in capsys.readouterr().err
    assert "secret.xlsx" not in arguments.evaluation_report.read_text(encoding="utf-8")


def test_command_late_release_failure_does_not_publish_test_evidence(
    command, reports, monkeypatch, capsys
):
    module, arguments, _config = command

    def release_failure(*_args):
        assert not arguments.evaluation_report.exists()
        raise module.ModelUnavailableError("C:/private-registry/secret.skops")

    monkeypatch.setattr(module, "publish_model_release", release_failure)
    assert module.main() == 1
    report = reports.load_evaluation_report(arguments.evaluation_report)
    assert report.status == "rejected"
    assert report.reason_code == "release_unavailable"
    assert report.validation_metrics is not None
    assert report.test_metrics is None
    assert "private-registry" not in capsys.readouterr().err


def test_reused_evidence_does_not_retain_previous_run_when_training_fails():
    from forpost_prediction_core import training

    evidence = training.TrainingEvidence(
        stage="test",
        baseline_validation_pr_auc=0.8,
        split_sizes={"fit": 10, "calibration": 10, "validation": 10, "test": 10},
        threshold=0.6,
        champion_name="extra_trees_isotonic",
    )
    with pytest.raises(training.TrainingUnavailableError):
        training.train_champion(
            pd.DataFrame(), label_column="label", time_column="time", evidence=evidence
        )
    assert evidence == training.TrainingEvidence()


def test_cleanup_failure_does_not_leak_path(reports, tmp_path, monkeypatch):
    path = tmp_path / "evaluation.json"

    def fail_cleanup(*_args, **_kwargs):
        raise OSError("C:/private-source/temporary.json")

    monkeypatch.setattr(Path, "unlink", fail_cleanup)
    with pytest.raises(reports.EvaluationReportUnavailableError) as error:
        reports.write_evaluation_report(
            path, reports.EvaluationReport.model_validate(report_payload())
        )
    assert "private-source" not in str(error.value)
