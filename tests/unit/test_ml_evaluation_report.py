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
        "format_version": 2,
        "task": "sensor_failure",
        "version": "v1",
        "status": status,
        "evidence_tier": "proxy",
        "label_strategy": "cadence_adjusted_silence_horizon_proxy_v2",
        "horizon_hours": 48,
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
        "split_sizes": {"fit": 100, "calibration": 30, "validation": 120, "test": 40},
        "baseline_validation_pr_auc": 0.25,
        "validation_metrics": metrics if status == "published" else None,
        "test_metrics": metrics if status == "published" else None,
        "threshold": 0.6 if status == "published" else None,
        "champion_name": "extra_trees_isotonic" if status == "published" else None,
        "task_semantics": "risk_of_unexpected_telemetry_silence_within_horizon",
        "feature_schema_version": "6",
        "config_sha256": "a" * 64,
        "library_versions": dict.fromkeys(
            ("numpy", "pandas", "scikit-learn", "skops", "catboost", "lightgbm"), "1.0"
        ),
        "rolling_folds": [
            {
                "index": index,
                "train_rows": 100,
                "calibration_rows": 30,
                "validation_rows": 40,
                "threshold": 0.6,
                "metrics": dict(metrics),
            }
            for index in range(1, 4)
        ]
        if status == "published"
        else [],
        "operating_profiles": {
            name: {"threshold": 0.6, "precision": 0.8, "recall": 0.7, "alert_rate": 0.2}
            for name in ("high_precision", "balanced", "high_recall")
        }
        if status == "published"
        else {},
        "validation_confidence_intervals": {
            name: {
                "lower": value,
                "upper": value,
                "level": 0.95,
                "method": "student_t_across_rolling_folds",
            }
            for name, value in metrics.items()
        }
        if status == "published"
        else {},
    }


@pytest.mark.parametrize("status", ["rejected", "published"])
def test_report_roundtrip_retains_only_exact_evidence(reports, tmp_path, status):
    path = tmp_path / "nested" / "evaluation.json"
    reports.write_evaluation_report(
        path, reports.EvaluationReport.model_validate(report_payload(status))
    )
    loaded = reports.load_evaluation_report(path)
    assert loaded.model_dump(mode="json") == report_payload(status)


def test_report_rejects_non_current_feature_schema(reports):
    payload = report_payload()
    payload["feature_schema_version"] = "7"

    with pytest.raises(ValidationError):
        reports.EvaluationReport.model_validate(payload)


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
        "horizon_hours",
    ],
)
def test_published_report_requires_completed_evidence(reports, field):
    payload = report_payload("published")
    payload[field] = None
    with pytest.raises(ValidationError):
        reports.EvaluationReport.model_validate(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("rolling_folds", []),
        ("operating_profiles", {}),
        ("validation_confidence_intervals", {}),
        ("config_sha256", None),
        ("feature_schema_version", None),
        ("library_versions", {}),
    ],
)
def test_published_v2_report_requires_rolling_and_schema_evidence(reports, field, value):
    payload = report_payload("published")
    payload[field] = value
    with pytest.raises(ValidationError):
        reports.EvaluationReport.model_validate(payload)


def test_report_rejects_duplicate_folds_and_inconsistent_balanced_threshold(reports):
    payload = report_payload("published")
    payload["rolling_folds"][1]["index"] = 1
    with pytest.raises(ValidationError):
        reports.EvaluationReport.model_validate(payload)
    payload = report_payload("published")
    payload["operating_profiles"]["balanced"]["threshold"] = 0.9
    with pytest.raises(ValidationError):
        reports.EvaluationReport.model_validate(payload)


def test_validation_intervals_describe_fold_mean_without_reading_final_test(reports):
    folds = tuple(
        SimpleNamespace(
            fold_index=index,
            threshold=0.6,
            metrics=SimpleNamespace(**dict.fromkeys(reports.EvaluationMetrics.model_fields, value)),
        )
        for index, value in enumerate((0.6, 0.7, 0.8), start=1)
    )
    evidence = SimpleNamespace(
        rolling_folds=folds,
        rolling_fold_sizes=tuple(
            {"train_rows": 100, "calibration_rows": 20, "validation_rows": 40} for _ in folds
        ),
        operating_profiles={
            name: SimpleNamespace(threshold=0.6, rolling_folds=folds)
            for name in ("high_precision", "balanced", "high_recall")
        },
    )
    payload = reports.validation_evidence_payload(evidence)
    interval = payload["validation_confidence_intervals"]["precision"]
    assert interval["lower"] == pytest.approx(0.4515862, abs=1e-6)
    assert interval["upper"] == pytest.approx(0.9484138, abs=1e-6)
    assert interval["level"] == 0.95
    assert "test_metrics" not in payload


def test_published_report_rejects_fabricated_zero_width_student_t_interval(reports):
    payload = report_payload("published")
    for fold, value in zip(payload["rolling_folds"], (0.6, 0.7, 0.8), strict=True):
        fold["metrics"]["precision"] = value
    payload["validation_metrics"]["precision"] = 0.7
    payload["operating_profiles"]["balanced"]["precision"] = 0.7
    payload["validation_confidence_intervals"]["precision"].update(
        lower=0.6999999999999998, upper=0.6999999999999998
    )
    with pytest.raises(ValidationError):
        reports.EvaluationReport.model_validate(payload)


@pytest.mark.parametrize("value", [0, -1, 8761, 1.5, "24", True, float("inf")])
def test_report_rejects_invalid_horizon(reports, value):
    payload = report_payload()
    payload["horizon_hours"] = value
    with pytest.raises(ValidationError):
        reports.EvaluationReport.model_validate(payload)


@pytest.mark.parametrize("value", [None, 1, 48, 8760])
def test_rejected_report_retains_nullable_bounded_horizon(reports, value):
    payload = report_payload()
    payload["horizon_hours"] = value
    report = reports.EvaluationReport.model_validate(payload)
    assert report.horizon_hours == value
    assert report.test_metrics is None


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
                maximum_alert_rate=1.0,
                minimum_positive_examples=1,
                minimum_negative_examples=1,
                operating_profiles=tuple(
                    training.ProfileConstraints(
                        name=name,
                        minimum_precision=1.0,
                        minimum_recall=0.5,
                        maximum_alert_rate=1.0,
                    )
                    for name in ("high_precision", "balanced", "high_recall")
                ),
            ),
            evidence=evidence,
        )
    assert evidence.stage == "validation"
    assert evidence.split_sizes == {"fit": 192, "calibration": 48, "validation": 48, "test": 64}
    assert evidence.baseline_validation_pr_auc == 15 / 48
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
    assert evidence.rolling_folds == observed.rolling_folds
    assert evidence.operating_profiles == observed.operating_profiles
    assert len(observed.rolling_fold_sizes) == 3
    assert observed.rolling_fold_sizes[0]["validation_rows"] == 16
    assert (
        observed.rolling_fold_sizes[0]["train_rows"] < observed.rolling_fold_sizes[2]["train_rows"]
    )


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
        horizon_hours=48,
        cutoff_count=80,
        feature_windows_hours=(24,),
        feature_schema_version="6",
        label_strategy="cadence_adjusted_silence_horizon_proxy_v2",
        sha256="a" * 64,
        dataset_sha256="d" * 64,
        training=TrainingConfig(
            purge_hours=48,
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
    monkeypatch.setattr(module, "training_source_fingerprint", lambda _path: "f" * 64)
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
    monkeypatch.setattr(module, "_current_features", lambda *_args, **_kwargs: frame.tail(4))
    return module, arguments, config


def test_command_writes_published_report_only_after_real_release(command, reports):
    module, arguments, _config = command
    assert module.main() == 0
    report = reports.load_evaluation_report(arguments.evaluation_report)
    assert report.status == "published"
    assert report.horizon_hours == 48
    assert report.test_metrics is not None
    card_path = arguments.registry_root / "sensor_failure" / "v1" / "model-card.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    assert report.test_metrics.model_dump() == card["test_metrics"]
    assert report.format_version == card["format_version"] == 2
    assert (
        report.task_semantics
        == card["task_semantics"]
        == "risk_of_unexpected_telemetry_silence_within_horizon"
    )
    assert len(report.rolling_folds) == 3
    assert set(report.operating_profiles) == {"high_precision", "balanced", "high_recall"}
    assert report.model_dump(mode="json")["rolling_folds"] == card["rolling_folds"]
    assert report.model_dump(mode="json")["operating_profiles"] == card["operating_profiles"]
    assert set(report.validation_confidence_intervals) == set(card["validation_metrics"])


def test_command_preserves_calendar_cutoffs_selected_by_source(command, monkeypatch):
    """Ловит потерю full-calendar точек между потоковым loader и dataset."""
    module, _arguments, _config = command
    cutoffs = ("2026-01-02T00:00:00", "2026-02-02T00:00:00")
    monkeypatch.setattr(
        module,
        "load_training_window",
        lambda *_args, **_kwargs: SimpleNamespace(
            events=[None] * 320,
            channels=[],
            skipped_event_count=0,
            truncated_before=False,
            prediction_cutoffs=cutoffs,
        ),
    )
    received = {}

    def capture_cutoffs(*_args, **kwargs):
        received["prediction_cutoffs"] = kwargs.get("prediction_cutoffs")
        return training_frame().assign(evidence_tier="proxy")

    monkeypatch.setattr(module, "build_sensor_failure_dataset", capture_cutoffs)

    assert module.main() == 0
    assert received["prediction_cutoffs"] == cutoffs


def test_command_rejects_validation_without_release_or_test_evidence(command, reports, capsys):
    from dataclasses import replace

    module, arguments, config = command
    config.training = replace(config.training, minimum_precision=1.0)
    assert module.main() == 1
    report = reports.load_evaluation_report(arguments.evaluation_report)
    assert report.status == "rejected"
    assert report.reason_code == "validation_rejected"
    assert report.horizon_hours == 48
    # В трёх validation folds по 16 строк — суммарно 13 положительных proxy-меток.
    assert report.baseline_validation_pr_auc == pytest.approx(13 / 48)
    assert report.split_sizes.validation == 48
    assert report.test_metrics is None
    assert not arguments.registry_root.exists()
    assert "training_validation_selection" in capsys.readouterr().err


def test_derived_dataset_cache_requires_both_dataset_and_source_fingerprints(command, tmp_path):
    module, _arguments, _config = command
    dataset = training_frame().assign(evidence_tier="proxy")
    csv_path = tmp_path / "derived.csv"
    metadata_path = tmp_path / "derived.json"

    module._write_cached_dataset(
        dataset,
        csv_path,
        metadata_path,
        dataset_config_sha256="a" * 64,
        source_fingerprint="b" * 64,
    )

    cached = module._load_cached_dataset(
        csv_path,
        metadata_path,
        dataset_config_sha256="a" * 64,
        source_fingerprint="b" * 64,
    )
    assert cached is not None
    assert len(cached) == len(dataset)
    assert (
        module._load_cached_dataset(
            csv_path,
            metadata_path,
            dataset_config_sha256="c" * 64,
            source_fingerprint="b" * 64,
        )
        is None
    )


def test_derived_dataset_cache_paths_are_content_addressed(command, tmp_path):
    module, _arguments, _config = command
    report_path = tmp_path / "ml-evaluation.json"

    first_paths = module._dataset_cache_paths(report_path, "a" * 64)
    same_paths = module._dataset_cache_paths(report_path, "a" * 64)
    changed_paths = module._dataset_cache_paths(report_path, "b" * 64)

    assert first_paths == same_paths
    assert set(first_paths).isdisjoint(changed_paths)
    assert all(path.parent == report_path.parent for path in (*first_paths, *changed_paths))


@pytest.mark.parametrize(
    ("stage", "reason"),
    [("rolling_validation", "validation_rejected"), ("frozen_test", "test_rejected")],
)
def test_command_sanitizes_stage_failures(command, reports, monkeypatch, capsys, stage, reason):
    module, arguments, _config = command

    def fail_training(*_args, evidence, **_kwargs):
        evidence.stage = stage
        raise RuntimeError("C:/private-source/secret-channel")

    monkeypatch.setattr(module, "train_champion", fail_training)
    assert module.main() == 1
    report = reports.load_evaluation_report(arguments.evaluation_report)
    assert report.reason_code == reason
    assert report.test_metrics is None
    assert not arguments.registry_root.exists()
    captured = capsys.readouterr()
    emitted = captured.out + captured.err + arguments.evaluation_report.read_text(encoding="utf-8")
    assert "secret-channel" not in emitted
    assert "Traceback" not in emitted


def test_inference_budget_includes_current_feature_building(command, reports, monkeypatch):
    module, arguments, _config = command
    elapsed = [0.0]
    current_features = module._current_features

    def slow_features(*args):
        elapsed[0] += 301.0
        return current_features(*args)

    monkeypatch.setattr(module.time, "perf_counter", lambda: elapsed[0])
    monkeypatch.setattr(module, "_current_features", slow_features)
    assert module.main() == 1
    report = reports.load_evaluation_report(arguments.evaluation_report)
    assert report.reason_code == "inference_unavailable"
    assert report.test_metrics is None
    assert not arguments.registry_root.exists()


def test_inference_scores_only_the_cadence_label_target_population():
    """Ловит train-serving skew для нестабильных, duplicate, overdue и long-cadence каналов."""
    from scripts import train_sensor_failure as module

    cutoff = pd.Timestamp("2026-01-10T12:00:00Z")
    channel_times = {
        "eligible": [-3.0, -2.0, -1.0, -0.1],
        "unstable": [-11.0, -10.0, -2.0, -1.0],
        "duplicate": [-1.0, -1.0, -1.0, -1.0],
        "overdue": [-10.0, -9.0, -8.0, -7.0],
        "too_long": [-60.5, -40.5, -20.5, -0.5],
    }
    rows = [
        {
            "channel_id": channel_id,
            "observed_at": cutoff + pd.Timedelta(hours=offset),
            "sensor_value": 1.0,
            "analysis_eligible": True,
        }
        for channel_id, offsets in channel_times.items()
        for offset in offsets
    ]
    # Определяет общий inference cutoff без добавления ещё одного канала.
    rows.append(
        {
            "channel_id": "eligible",
            "observed_at": cutoff - pd.Timedelta(seconds=1),
            "sensor_value": 1.0,
            "analysis_eligible": True,
        }
    )
    events = pd.DataFrame(rows)
    channels = pd.DataFrame({"channel_id": list(channel_times)})

    current = module._current_features(
        events,
        channels,
        ("hours_since_last_event",),
        (1, 24, 72),
        horizon_hours=24,
    )

    assert set(current["channel_id"]) == {"eligible"}


def test_command_writes_exact_local_validation_diagnostics(command, reports):
    from dataclasses import replace

    module, arguments, config = command
    config.training = replace(config.training, minimum_precision=1.0)
    assert module.main() == 1
    path = arguments.evaluation_report.with_name("evaluation-v1-validation.json")
    assert path.is_file()
    diagnostic = json.loads(path.read_text(encoding="utf-8"))
    assert diagnostic["reason_code"] == "validation_rejected"
    assert diagnostic["diagnostics"]["step"] == "validation_selection"
    assert len(diagnostic["diagnostics"]["folds"]) == 3
    assert len(diagnostic["diagnostics"]["candidates"]) == 10
    assert "test_metrics" not in diagnostic
    assert "channel-" not in path.read_text(encoding="utf-8")
    assert (
        "diagnostics"
        not in reports.load_evaluation_report(arguments.evaluation_report).model_dump()
    )


def test_validation_diagnostics_reject_raw_fields_and_preserve_old_file(tmp_path):
    from forpost_prediction_core import validation_diagnostics as diagnostics

    assert hasattr(diagnostics, "ValidationDiagnosticReport")
    payload = {
        "format_version": 1,
        "version": "v3",
        "config_sha256": None,
        "reason_code": "training_unavailable",
        "diagnostics": diagnostics.empty_diagnostics(),
    }
    report = diagnostics.ValidationDiagnosticReport.model_validate(payload)
    path = tmp_path / "validation.json"
    diagnostics.write_validation_diagnostics(path, report)
    assert json.loads(path.read_text(encoding="utf-8")) == payload
    payload["diagnostics"]["raw_path"] = "private-source"
    with pytest.raises(ValidationError):
        diagnostics.ValidationDiagnosticReport.model_validate(payload)
    assert "private-source" not in path.read_text(encoding="utf-8")


def test_command_replaces_stale_report_on_source_failure_without_leaking_error(
    command, reports, monkeypatch, capsys
):
    module, arguments, _config = command
    reports.write_evaluation_report(
        arguments.evaluation_report,
        reports.EvaluationReport.model_validate(report_payload("published")),
    )

    def source_failure(*_args, **_kwargs):
        raise module.SourceSnapshotError(
            "C:/private-source/secret.xlsx", diagnostic_code="calendar_event_limit"
        )

    monkeypatch.setattr(module, "load_training_window", source_failure)
    assert module.main() == 1
    report = reports.load_evaluation_report(arguments.evaluation_report)
    assert report.status == "rejected"
    assert report.reason_code == "source_unavailable"
    assert report.horizon_hours == 48
    assert report.validation_metrics is None
    assert report.test_metrics is None
    stderr = capsys.readouterr().err
    assert "private-source" not in stderr
    assert "calendar_event_limit" in stderr
    assert "secret.xlsx" not in arguments.evaluation_report.read_text(encoding="utf-8")


@pytest.mark.parametrize("backend", ["catboost", "lightgbm"])
def test_command_replaces_stale_report_when_native_dependency_is_unavailable(
    command, reports, monkeypatch, capsys, backend
):
    import builtins

    module, arguments, _config = command
    arguments.evaluation_report = (
        arguments.evaluation_report.parent / "chosen-report" / "result.json"
    )
    reports.write_evaluation_report(
        arguments.evaluation_report,
        reports.EvaluationReport.model_validate(report_payload("published")),
    )
    original_import = builtins.__import__

    def unavailable(name, *args, **kwargs):
        if name == backend:
            raise ImportError("C:/private-source/secret-native-library.dll")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", unavailable)
    assert module.main() == 1
    report = reports.load_evaluation_report(arguments.evaluation_report)
    assert report.status == "rejected"
    assert report.reason_code == "training_unavailable"
    assert report.validation_metrics is None
    assert report.test_metrics is None
    assert report.champion_name is None
    assert not arguments.registry_root.exists()
    captured = capsys.readouterr()
    emitted = captured.out + captured.err + arguments.evaluation_report.read_text(encoding="utf-8")
    assert "private-source" not in emitted
    assert "secret-native-library" not in emitted
    assert "Traceback" not in emitted


def test_command_late_release_failure_does_not_publish_test_evidence(
    command, reports, monkeypatch, capsys
):
    module, arguments, _config = command

    def release_failure(*_args, **_kwargs):
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


def test_missing_library_metadata_produces_sanitized_training_rejection(
    command, reports, monkeypatch, capsys
):
    module, arguments, _config = command

    def missing(_package):
        raise module.importlib.metadata.PackageNotFoundError("C:/private-library/secret")

    monkeypatch.setattr(module.importlib.metadata, "version", missing)
    assert module.main() == 1
    report = reports.load_evaluation_report(arguments.evaluation_report)
    assert report.reason_code == "training_unavailable"
    assert report.test_metrics is None
    assert not arguments.registry_root.exists()
    assert "private-library" not in capsys.readouterr().err


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


def test_malformed_yaml_replaces_stale_published_report(command, reports, monkeypatch, capsys):
    from forpost_prediction_core.config import load_ml_config

    module, arguments, _config = command
    malformed_path = arguments.evaluation_report.parent / "private-config.yaml"
    malformed_path.write_text("private_source: [secret.xlsx", encoding="utf-8")
    reports.write_evaluation_report(
        arguments.evaluation_report,
        reports.EvaluationReport.model_validate(report_payload("published")),
    )
    monkeypatch.setattr(module, "load_ml_config", lambda _path: load_ml_config(malformed_path))

    def prohibit_source(*_args, **_kwargs):
        pytest.fail("Некорректная конфигурация дошла до загрузки данных")

    monkeypatch.setattr(module, "load_training_window", prohibit_source)
    assert module.main() == 1
    report = reports.load_evaluation_report(arguments.evaluation_report)
    assert report.status == "rejected"
    assert report.reason_code == "configuration_invalid"
    assert report.horizon_hours is None
    assert report.quality_thresholds is None
    assert report.test_metrics is None
    captured = capsys.readouterr()
    assert "private" not in captured.err
    assert "secret.xlsx" not in captured.err
    assert "evaluation_write_failed" not in captured.err


@pytest.mark.parametrize("invalid_version", ["v0", "../../private", "", "v" + "9" * 32])
def test_invalid_version_replaces_stale_report_before_loading_data(
    command, reports, monkeypatch, capsys, invalid_version
):
    module, arguments, _config = command
    arguments.version = invalid_version
    reports.write_evaluation_report(
        arguments.evaluation_report,
        reports.EvaluationReport.model_validate(report_payload("published")),
    )

    def prohibit_source(*_args, **_kwargs):
        pytest.fail("Некорректная версия дошла до загрузки данных")

    monkeypatch.setattr(module, "load_training_window", prohibit_source)
    assert module.main() == 1
    report = reports.load_evaluation_report(arguments.evaluation_report)
    assert report.status == "rejected"
    assert report.version == "v1"
    assert report.reason_code == "configuration_invalid"
    assert report.test_metrics is None
    assert not arguments.registry_root.exists()
    captured = capsys.readouterr()
    assert "private" not in captured.err
    assert "evaluation_write_failed" not in captured.err


@pytest.mark.parametrize(
    "field",
    [
        "minimum_precision",
        "minimum_recall",
        "maximum_alert_rate",
        "maximum_expected_calibration_error",
        "maximum_brier_score",
        "minimum_baseline_pr_auc_delta",
    ],
)
@pytest.mark.parametrize("value", [-0.1, 1.1, float("inf"), float("nan")])
def test_invalid_config_threshold_replaces_stale_report_before_loading_data(
    command, reports, monkeypatch, capsys, field, value
):

    module, arguments, config = command
    arguments.version = "v2"
    # Имитируем некорректный ответ загрузчика, обходя проверяемый им dataclass.
    config.training = SimpleNamespace(**(vars(config.training) | {field: value}))
    reports.write_evaluation_report(
        arguments.evaluation_report,
        reports.EvaluationReport.model_validate(report_payload("published")),
    )

    def prohibit_source(*_args, **_kwargs):
        pytest.fail("Непроверенные пороги дошли до загрузки данных")

    monkeypatch.setattr(module, "load_training_window", prohibit_source)
    assert module.main() == 1
    report = reports.load_evaluation_report(arguments.evaluation_report)
    assert report.status == "rejected"
    assert report.version == "v2"
    assert report.reason_code == "configuration_invalid"
    assert report.quality_thresholds is None
    assert report.test_metrics is None
    assert report.validation_metrics is None
    assert "evaluation_write_failed" not in capsys.readouterr().err
