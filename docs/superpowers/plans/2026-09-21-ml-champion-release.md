# ML Champion Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Выпустить честно провалидированную 24-часовую proxy-модель риска прекращения телеметрии с rolling-origin backtesting, калибровкой, фиксированным final test и атомарным model bundle.

**Architecture:** Point-in-time dataset остаётся единственным источником обучения; final test отделяется первым и больше не участвует в выборе. Предшествующая история проходит три expanding-window fold, candidate zoo сравнивается по худшему fold и операционным gates, а победитель переобучается на разрешённой истории и один раз проверяется на test.

**Tech Stack:** Python 3.12, pandas 3, NumPy 2, scikit-learn 1.9.1, skops 0.15, audited CatBoost 1.2.10 and LightGBM 4.7.0 candidates, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-21-ml-champion-system-design.md`

## Global Constraints

- Сырые файлы остаются только в `data/raw`; отчёты и модели остаются в игнорируемых локальных каталогах.
- Final test не используется для выбора признаков, модели, калибровки или threshold.
- Задача называется «риск прекращения телеметрии», evidence tier — `proxy`.
- Публикация требует `precision > 0.70`, `recall > 0.50`, допустимый alert budget и inference менее 300 секунд.
- Все feature-вычисления используют только события строго раньше `prediction_at`.
- Новые бинарные model formats не загружаются через pickle; bundle сериализуется и проверяется существующим skops-контуром.

---

### Task 1: Rolling-origin temporal protocol

**Files:**
- Modify: `packages/prediction/src/forpost_prediction_core/splits.py`
- Test: `tests/unit/test_ml_splits.py`

**Interfaces:**
- Consumes: `pd.DataFrame`, имя временной колонки, число fold и embargo в часах.
- Produces: `RollingFold(index: int, train: pd.DataFrame, validation: pd.DataFrame)` и `make_rolling_origin_folds(...) -> tuple[RollingFold, ...]`.

- [ ] **Step 1: Write failing split tests**

```python
def test_rolling_folds_expand_train_and_keep_horizon_embargo() -> None:
    frame = pd.DataFrame({"at": pd.date_range("2026-01-01", periods=14, freq="24h", tz="UTC")})
    folds = make_rolling_origin_folds(frame, "at", fold_count=3, validation_points=2, purge_hours=24)
    assert len(folds) == 3
    assert [len(fold.train) for fold in folds] == sorted(len(fold.train) for fold in folds)
    assert all(fold.train["at"].max() < fold.validation["at"].min() - pd.Timedelta(hours=24) for fold in folds)

def test_rolling_folds_reject_overlapping_or_empty_partitions() -> None:
    frame = pd.DataFrame({"at": pd.date_range("2026-01-01", periods=5, freq="h", tz="UTC")})
    with pytest.raises(ValueError, match="временных точек"):
        make_rolling_origin_folds(frame, "at", fold_count=3, validation_points=2, purge_hours=24)
```

- [ ] **Step 2: Verify the tests fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_ml_splits.py -q`

Expected: import failure for `make_rolling_origin_folds`.

- [ ] **Step 3: Implement expanding folds**

```python
@dataclass(frozen=True)
class RollingFold:
    index: int
    train: pd.DataFrame
    validation: pd.DataFrame

def make_rolling_origin_folds(
    frame: pd.DataFrame,
    time_column: str,
    *,
    fold_count: int,
    validation_points: int,
    purge_hours: int,
) -> tuple[RollingFold, ...]:
    ordered = frame.sort_values(time_column, kind="stable").reset_index(drop=True)
    points = ordered[time_column].drop_duplicates().sort_values().reset_index(drop=True)
    required = fold_count * validation_points + 2
    if fold_count < 2 or validation_points < 1 or len(points) < required:
        raise ValueError("Недостаточно временных точек для rolling-origin проверки")
    purge = pd.Timedelta(hours=purge_hours)
    first_validation = len(points) - fold_count * validation_points
    folds: list[RollingFold] = []
    for index in range(fold_count):
        start = points.iloc[first_validation + index * validation_points]
        stop_index = first_validation + (index + 1) * validation_points
        stop = points.iloc[stop_index] if stop_index < len(points) else points.iloc[-1] + pd.Timedelta(1, "ns")
        train = ordered.loc[ordered[time_column] < start - purge].copy()
        validation = ordered.loc[(ordered[time_column] >= start) & (ordered[time_column] < stop)].copy()
        if train.empty or validation.empty:
            raise ValueError("Embargo оставляет пустой rolling-origin fold")
        folds.append(RollingFold(index=index + 1, train=train.reset_index(drop=True), validation=validation.reset_index(drop=True)))
    return tuple(folds)
```

- [ ] **Step 4: Run split tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_ml_splits.py tests/unit/test_ml_training.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add packages/prediction/src/forpost_prediction_core/splits.py tests/unit/test_ml_splits.py
git commit -m "feat(ml): add rolling origin validation splits"
```

### Task 2: Causal telemetry feature set

**Files:**
- Modify: `packages/prediction/src/forpost_prediction_core/features.py`
- Modify: `packages/prediction/src/forpost_prediction_core/dataset.py`
- Modify: `ml/config.yaml`
- Test: `tests/unit/test_ml_features.py`
- Test: `tests/unit/test_ml_dataset.py`

**Interfaces:**
- Consumes: event history before cutoff and channel metadata containing `sensor_type` and optional `engineering_system`.
- Produces: stable feature schema v5 with interval normalization, frequency deltas, robust statistics, exponential decay and cyclical time features.

- [ ] **Step 1: Write failing causal and value tests**

```python
def test_features_include_frequency_interval_and_cyclical_signals() -> None:
    result = build_channel_features(events, channels, cutoff, windows=(6, 24))
    expected = {
        "interarrival_median_hours", "interarrival_mad_hours", "silence_to_normal_ratio",
        "frequency_change_6h_to_24h", "value_ewm_mean", "value_ewm_std",
        "hour_sin", "hour_cos", "weekday_sin", "weekday_cos",
    }
    assert expected.issubset(result.columns)

def test_future_rows_cannot_change_past_features() -> None:
    before = build_channel_features(events, channels, cutoff, windows=(6, 24))
    poisoned = pd.concat([events, pd.DataFrame([{ "channel_id": "a", "observed_at": cutoff + pd.Timedelta(hours=1), "sensor_value": 999999 }])], ignore_index=True)
    after = build_channel_features(poisoned, channels, cutoff, windows=(6, 24))
    pd.testing.assert_frame_equal(before, after)
```

- [ ] **Step 2: Verify feature tests fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_ml_features.py tests/unit/test_ml_dataset.py -q`

Expected: missing feature assertions fail.

- [ ] **Step 3: Implement robust interval, decay and seasonality features**

```python
intervals = history.sort_values(["channel_id", "observed_at"], kind="stable")
intervals["interval_hours"] = intervals.groupby("channel_id")["observed_at"].diff().dt.total_seconds().div(3600)
interval_stats = intervals.groupby("channel_id")["interval_hours"].agg(["median", "std", "quantile"])
result["silence_to_normal_ratio"] = result["hours_since_last_event"].div(result["interarrival_median_hours"].clip(lower=1 / 60))
result["frequency_change_6h_to_24h"] = result["event_count_6h"].div(6).sub(result["event_count_24h"].div(24))
hour_angle = 2 * np.pi * local_cutoff.hour / 24
weekday_angle = 2 * np.pi * local_cutoff.weekday() / 7
result["hour_sin"], result["hour_cos"] = np.sin(hour_angle), np.cos(hour_angle)
result["weekday_sin"], result["weekday_cos"] = np.sin(weekday_angle), np.cos(weekday_angle)
```

Use a grouped, time-ordered `ewm(halflife="6h", times="observed_at")` calculation and explicit finite-value replacement. Keep `engineering_system` only when it exists in the channel contract; never infer it from identifiers.

- [ ] **Step 4: Bump the schema and expand windows**

```yaml
feature_schema_version: "5"
feature_windows_hours: [1, 6, 24, 72, 168]
```

- [ ] **Step 5: Run feature, dataset and leakage tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_ml_features.py tests/unit/test_ml_dataset.py tests/unit/test_ml_time_utils.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add packages/prediction/src/forpost_prediction_core/features.py packages/prediction/src/forpost_prediction_core/dataset.py ml/config.yaml tests/unit/test_ml_features.py tests/unit/test_ml_dataset.py
git commit -m "feat(ml): add causal telemetry behavior features"
```

### Task 3: Fold-aware model selection and calibration

**Files:**
- Create: `packages/prediction/src/forpost_prediction_core/candidates.py`
- Modify: `packages/prediction/src/forpost_prediction_core/training.py`
- Modify: `packages/prediction/src/forpost_prediction_core/config.py`
- Modify: `ml/config.yaml`
- Modify: `requirements-prod.in`
- Modify: `requirements-prod.lock`
- Test: `tests/unit/test_ml_candidates.py`
- Test: `tests/unit/test_ml_training.py`

**Interfaces:**
- Produces: `build_candidate_estimators(frame, seed) -> dict[str, BaseEstimator]`, `FoldMetrics`, and `TrainingResult.rolling_folds`.
- Guarantees: threshold/model selection sees validation folds only; test is evaluated after champion freeze.

- [ ] **Step 1: Write failing selection tests**

```python
def test_champion_must_pass_every_validation_fold() -> None:
    folds = {"stable": (passing, passing, passing), "fragile": (excellent, excellent, failing)}
    selected = rank_fold_candidates(folds, config)
    assert selected.name == "stable"

def test_final_test_probabilities_are_not_accepted_by_selector() -> None:
    signature = inspect.signature(rank_fold_candidates)
    assert "test_probabilities" not in signature.parameters
```

- [ ] **Step 2: Verify candidate tests fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_ml_candidates.py tests/unit/test_ml_training.py -q`

Expected: missing candidate module and fold selector failures.

- [ ] **Step 3: Extract a deterministic candidate zoo**

```python
def build_candidate_estimators(frame: pd.DataFrame, seed: int) -> dict[str, BaseEstimator]:
    return {
        "logistic_regression": _pipeline(frame, LogisticRegression(max_iter=2000, class_weight="balanced", random_state=seed)),
        "extra_trees": _pipeline(frame, ExtraTreesClassifier(n_estimators=300, min_samples_leaf=4, class_weight="balanced", n_jobs=-1, random_state=seed)),
        "hist_gradient_boosting": _pipeline(frame, HistGradientBoostingClassifier(max_iter=250, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0, random_state=seed)),
    }
```

Add `CatBoostClassifier(iterations=350, depth=7, learning_rate=0.04, loss_function="Logloss", auto_class_weights="Balanced", random_seed=seed, thread_count=-1, verbose=False, allow_writing_files=False)` and `LGBMClassifier(n_estimators=350, num_leaves=31, learning_rate=0.04, min_child_samples=30, reg_lambda=1.0, class_weight="balanced", random_state=seed, n_jobs=-1, verbosity=-1)` through explicit adapters. Pin `catboost==1.2.10` and `lightgbm==4.7.0`, regenerate hashes, retain their Apache-2.0/MIT notices, then require clean-room install plus `pip-audit` before either candidate is enabled. Disable CatBoost file writes and all optional plotting/telemetry paths.

If a native booster wins, export its documented native model format plus a strict JSON metadata/feature schema and SHA-256 manifest. Loading must dispatch only on an allow-listed `model_format` (`skops`, `catboost_cbm`, `lightgbm_text`) and call the corresponding library loader; never deserialize pickle/joblib. Run an inference parity test before publication:

```python
np.testing.assert_allclose(
    trained.predict_proba(validation_features)[:, 1],
    reloaded.predict_proba(validation_features)[:, 1],
    rtol=1e-10,
    atol=1e-12,
)
```

- [ ] **Step 4: Implement fold aggregation and operating profiles**

```python
@dataclass(frozen=True)
class FoldValidation:
    fold_index: int
    threshold: float
    metrics: BinaryMetrics

def rank_fold_candidates(results: dict[str, tuple[FoldValidation, ...]], config: TrainingConfig) -> CandidateValidation:
    eligible = [(name, folds) for name, folds in results.items() if len(folds) >= config.minimum_validation_folds and all(_passes(f.metrics, config) for f in folds)]
    if not eligible:
        raise TrainingUnavailableError("Ни один кандидат не прошёл все rolling-origin folds")
    name, folds = max(eligible, key=lambda item: (min(f.metrics.f1 for f in item[1]), np.mean([f.metrics.pr_auc for f in item[1]]), item[0]))
    threshold = float(np.median([fold.threshold for fold in folds]))
    return CandidateValidation(name=name, threshold=threshold, metrics=_mean_metrics(folds))
```

Add `minimum_validation_folds: 3`, `validation_points_per_fold: 4`, and named profile constraints (`high_precision`, `balanced`, `high_recall`) to the strict YAML schema. Each profile stores a validation-approved threshold; the published default remains balanced.

- [ ] **Step 5: Refactor `train_champion` around frozen test**

```python
development, test = split_development_and_test(frame, time_column, test_fraction=config.test_fraction, purge_hours=config.purge_hours)
folds = make_rolling_origin_folds(development, time_column, fold_count=config.minimum_validation_folds, validation_points=config.validation_points_per_fold, purge_hours=config.purge_hours)
candidate_results = _evaluate_candidates_on_folds(folds, label_column, feature_columns, config)
champion = rank_fold_candidates(candidate_results, config)
frozen_model = _fit_and_calibrate_champion(development, champion.name, label_column, feature_columns, config)
test_metrics = evaluate_binary_probabilities(test_labels, frozen_model.predict_proba(test_features)[:, 1], champion.threshold)
_require_quality_gate(test_metrics, config, partition="test")
```

- [ ] **Step 6: Run focused ML tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_ml_candidates.py tests/unit/test_ml_training.py tests/unit/test_ml_evaluation.py -q`

Expected: PASS and no call path from test data into candidate selection.

- [ ] **Step 7: Commit**

```powershell
git add packages/prediction/src/forpost_prediction_core/candidates.py packages/prediction/src/forpost_prediction_core/training.py packages/prediction/src/forpost_prediction_core/config.py ml/config.yaml requirements-prod.in requirements-prod.lock tests/unit/test_ml_candidates.py tests/unit/test_ml_training.py
git commit -m "feat(ml): select champion across rolling folds"
```

### Task 4: Evaluation evidence and model card v2

**Files:**
- Modify: `packages/prediction/src/forpost_prediction_core/evaluation_report.py`
- Modify: `packages/prediction/src/forpost_prediction_core/registry.py`
- Modify: `scripts/train_sensor_failure.py`
- Test: `tests/unit/test_ml_evaluation_report.py`
- Test: `tests/unit/test_ml_registry.py`

**Interfaces:**
- Produces: report format v2 with folds, operating profiles, confidence intervals and immutable test evidence.
- Produces: model card fields `task_semantics`, `rolling_folds`, `operating_profiles`, `feature_schema_version` and hashes.

- [ ] **Step 1: Write failing strict-schema tests**

```python
def test_published_report_requires_three_folds_and_operating_profiles() -> None:
    with pytest.raises(ValidationError):
        EvaluationReport.model_validate({**published_payload, "rolling_folds": [], "operating_profiles": {}})

def test_rejected_validation_report_never_contains_test_metrics() -> None:
    with pytest.raises(ValidationError):
        EvaluationReport.model_validate({**rejected_payload, "test_metrics": passing_metrics})
```

- [ ] **Step 2: Verify report tests fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_ml_evaluation_report.py tests/unit/test_ml_registry.py -q`

Expected: format-v2 fields are missing.

- [ ] **Step 3: Add exact Pydantic evidence models**

```python
class FoldEvidence(ExactModel):
    index: Annotated[int, Field(ge=1, le=20)]
    train_rows: Annotated[int, Field(gt=0)]
    validation_rows: Annotated[int, Field(gt=0)]
    threshold: Probability
    metrics: EvaluationMetrics

class OperatingProfile(ExactModel):
    threshold: Probability
    precision: Probability
    recall: Probability
    alert_rate: Probability
```

Add a model validator enforcing at least three folds for `published`, all evidence for published reports, and `test_metrics is None` for validation rejection.

- [ ] **Step 4: Extend registry serialization and integrity checks**

```python
if card.task_semantics != "risk_of_telemetry_silence_within_horizon":
    raise ModelUnavailableError("Некорректная семантика ML-задачи")
if len(card.rolling_folds) < 3 or set(card.operating_profiles) != {"high_precision", "balanced", "high_recall"}:
    raise ModelUnavailableError("Неполные validation-доказательства")
```

- [ ] **Step 5: Run evidence tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_ml_evaluation_report.py tests/unit/test_ml_registry.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add packages/prediction/src/forpost_prediction_core/evaluation_report.py packages/prediction/src/forpost_prediction_core/registry.py scripts/train_sensor_failure.py tests/unit/test_ml_evaluation_report.py tests/unit/test_ml_registry.py
git commit -m "feat(ml): publish rolling validation evidence"
```

### Task 5: Train, diagnose and publish the 24-hour release

**Files:**
- Modify: `scripts/train_sensor_failure.py`
- Modify: `docs/ML_METHODS.md`
- Modify: `docs/ML_CAPABILITIES.md`
- Local-only output: `data/processed/ml-evaluation.json`
- Local-only output: `ml/models/sensor_failure/v2/`

**Interfaces:**
- Command: `.venv\Scripts\python.exe scripts/train_sensor_failure.py --version v2`.
- Exit 0 only for a published release; exit 1 writes a machine-readable rejection without leaking exception text.

- [ ] **Step 1: Add deterministic diagnostic stages**

```python
stage = "rolling_validation"
result = train_champion(...)
stage = "frozen_test"
stage = "inference"
stage = "release"
```

Map each stage to a stable reason code and keep traceback/raw identifiers out of stdout and the report.

- [ ] **Step 2: Run the release training once**

Run: `.venv\Scripts\python.exe scripts/train_sensor_failure.py --version v2`

Expected: either a published v2 bundle or a rejected report with the last completed validation evidence and no test metrics after validation rejection.

- [ ] **Step 3: Verify the local release atomically**

Run: `.venv\Scripts\python.exe -c "from pathlib import Path; from forpost_prediction_core.registry import load_model_bundle; print(load_model_bundle(Path('ml/models'), 'sensor_failure', 'v2').card.version)"`

Expected when published: `v2`. If rejected, inspect only aggregate local evidence, adjust features/config using validation folds, and rerun under a new version; never reuse final test to select changes.

- [ ] **Step 4: Document exact semantics and limitations**

```markdown
Модель оценивает риск прекращения ожидаемой телеметрии в следующие 24 часа. Это proxy-событие не доказывает физическую поломку. Final test изолирован до заморозки модели и порога; несозревшие исходы не участвуют в оценке.
```

- [ ] **Step 5: Commit tracked code and documentation only**

```powershell
git add scripts/train_sensor_failure.py docs/ML_METHODS.md docs/ML_CAPABILITIES.md
git commit -m "feat(ml): release telemetry silence champion workflow"
```

### Task 6: ML release verification

**Files:**
- Modify: `docs/LOCAL_VERIFY.md`
- Modify: `docs/TZ_COMPLIANCE.md`

**Interfaces:**
- Produces a reproducible local verification recipe without exposing raw or derived local artifacts.

- [ ] **Step 1: Run all Python tests**

Run: `.venv\Scripts\python.exe -m pytest -q`

Expected: PASS.

- [ ] **Step 2: Run static checks**

Run: `.venv\Scripts\python.exe -m ruff check .`

Expected: no findings.

- [ ] **Step 3: Run security checks used by this repository**

Run: `powershell -ExecutionPolicy Bypass -File .\run_security_audit.ps1`

Expected: blocking scanners pass; local ML artifacts remain ignored.

- [ ] **Step 4: Prove privacy boundaries**

Run: `git status --short --ignored data ml/models`

Expected: `data/raw`, `data/processed` and `ml/models` appear only as ignored local paths.

- [ ] **Step 5: Update compliance evidence and commit**

```powershell
git add docs/LOCAL_VERIFY.md docs/TZ_COMPLIANCE.md
git commit -m "docs: record ml champion verification"
```
