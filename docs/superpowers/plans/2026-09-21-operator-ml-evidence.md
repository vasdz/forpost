# Operator ML Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить оператору проверяемый экран «прогноз против факта», безопасные профили модели и детерминированные рекомендации с полным аудитом.

**Architecture:** Offline ML-job экспортирует обезличенный outcome ledger с manifest; FastAPI проверяет размер, путь, схему и хеш и рассчитывает фильтрованные агрегаты. Настройки и решения хранятся append-only в существующей SQLite operations repository, а BFF пропускает записи только из доверенной human-сессии.

**Tech Stack:** FastAPI, Pydantic 2, SQLite, Next.js 15 App Router, React 19, TypeScript strict, ECharts 6, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-09-21-ml-champion-system-design.md`

## Global Constraints

- Несозревший прогноз не считается отрицательным исходом.
- Service token остаётся read-only; mutation требует human identity, CSRF, idempotency и audit chain.
- Порог выбирается только из заранее провалидированных operating profiles model card.
- Графики имеют табличную WCAG 2.1 AA альтернативу.
- UI строго отличает факт, proxy, anomaly, scenario и simulation.

---

### Task 1: Outcome ledger domain and metrics

**Files:**
- Create: `packages/prediction/src/forpost_prediction_core/outcomes.py`
- Test: `tests/unit/test_ml_outcomes.py`

**Interfaces:**
- Produces: `PredictionOutcome`, `OutcomeFilters`, `OutcomeSummary`, `summarize_outcomes(...)`.

- [ ] **Step 1: Write failing maturity and confusion tests**

```python
def test_unmatured_prediction_is_excluded_from_confusion_matrix() -> None:
    summary = summarize_outcomes([matured_tp, pending], filters=OutcomeFilters(), now=NOW)
    assert summary.total_matured == 1
    assert (summary.tp, summary.fp, summary.fn, summary.tn) == (1, 0, 0, 0)

def test_summary_builds_calibration_and_lift_bins() -> None:
    summary = summarize_outcomes(outcomes, filters=OutcomeFilters(), now=NOW)
    assert sum(bin.count for bin in summary.calibration_bins) == summary.total_matured
    assert {point.top_fraction for point in summary.lift} == {0.01, 0.05, 0.10, 0.20}
```

- [ ] **Step 2: Verify outcome tests fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_ml_outcomes.py -q`

Expected: module import failure.

- [ ] **Step 3: Implement exact immutable outcome models**

```python
class PredictionOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    prediction_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9._:-]{1,128}$")]
    model_version: Annotated[str, Field(pattern=r"^v[1-9]\d*$")]
    entity_hash: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    predicted_at: datetime
    matures_at: datetime
    probability: Annotated[float, Field(ge=0, le=1)]
    threshold: Annotated[float, Field(gt=0, lt=1)]
    actual_outcome: bool | None
    sensor_type: str | None
    engineering_system: str | None
```

- [ ] **Step 4: Implement metrics, calibration and lift**

```python
matured = [item for item in filtered if item.matures_at <= now and item.actual_outcome is not None]
truth = np.asarray([item.actual_outcome for item in matured], dtype=int)
scores = np.asarray([item.probability for item in matured], dtype=float)
predicted = scores >= np.asarray([item.threshold for item in matured])
tp = int(np.sum(predicted & (truth == 1)))
```

Reuse `evaluate_binary_probabilities`; return `None` for undefined metrics instead of fabricating zero. Lead time exists only when an observed positive event time is available.

- [ ] **Step 5: Run and commit**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_ml_outcomes.py -q`

```powershell
git add packages/prediction/src/forpost_prediction_core/outcomes.py tests/unit/test_ml_outcomes.py
git commit -m "feat(ml): calculate prediction outcome evidence"
```

### Task 2: Signed local outcome export and read-only API

**Files:**
- Create: `packages/prediction/src/forpost_prediction_core/outcome_export.py`
- Create: `apps/api/src/forpost_api/routes/outcomes.py`
- Modify: `apps/api/src/forpost_api/main.py`
- Test: `tests/unit/test_ml_outcome_export.py`
- Test: `tests/integration/test_outcomes_api.py`

**Interfaces:**
- GET `/api/model-outcomes?from=&to=&sensor_type=&engineering_system=&model_version=`.
- Response: exact `summary`, `calibration_bins`, `lift`, `rows`, `available_filters`.

- [ ] **Step 1: Write failing tamper and API filter tests**

```python
def test_outcome_export_rejects_hash_mismatch(tmp_path: Path) -> None:
    path = write_outcome_fixture(tmp_path)
    path.write_text('{"outcomes":[]}', encoding="utf-8")
    with pytest.raises(OutcomeExportError, match="целостност"):
        load_outcome_export(tmp_path)

def test_outcomes_api_filters_server_side(client: TestClient, export_root: Path) -> None:
    response = client.get("/api/model-outcomes?sensor_type=temperature")
    assert response.status_code == 200
    assert {row["sensor_type"] for row in response.json()["rows"]} == {"temperature"}
```

- [ ] **Step 2: Verify tests fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_ml_outcome_export.py tests/integration/test_outcomes_api.py -q`

Expected: missing loader and route.

- [ ] **Step 3: Implement guarded export loading**

```python
MAX_OUTCOME_EXPORT_BYTES = 16 * 1024 * 1024
def load_outcome_export(root: Path) -> tuple[PredictionOutcome, ...]:
    export = checked_regular_file(root / "outcomes.json", root, MAX_OUTCOME_EXPORT_BYTES)
    manifest = OutcomeManifest.model_validate_json(checked_regular_file(root / "outcomes-manifest.json", root, 16_384).read_bytes())
    content = export.read_bytes()
    if not hmac.compare_digest(hashlib.sha256(content).hexdigest(), manifest.sha256):
        raise OutcomeExportError("Нарушена целостность outcome export")
    return OutcomeExport.model_validate_json(content).outcomes
```

- [ ] **Step 4: Implement authorization, filters and no-store route**

```python
@router.get("/api/model-outcomes", response_model=OutcomeResponse)
async def get_model_outcomes(subject: Annotated[Subject, Depends(require_permission(Permission.VIEW_PREDICTIONS))], filters: Annotated[OutcomeQuery, Query()]) -> OutcomeResponse:
    outcomes = load_outcome_export(OUTCOME_DIRECTORY)
    return build_outcome_response(outcomes, filters, datetime.now(UTC))
```

- [ ] **Step 5: Run and commit**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_ml_outcome_export.py tests/integration/test_outcomes_api.py -q`

```powershell
git add packages/prediction/src/forpost_prediction_core/outcome_export.py apps/api/src/forpost_api/routes/outcomes.py apps/api/src/forpost_api/main.py tests/unit/test_ml_outcome_export.py tests/integration/test_outcomes_api.py
git commit -m "feat(api): expose verified prediction outcomes"
```

### Task 3: Versioned safe operating settings

**Files:**
- Create: `packages/domain/src/forpost_domain/risks/settings.py`
- Modify: `packages/platform/src/forpost_platform/operations/sqlite_repository.py`
- Create: `apps/api/src/forpost_api/routes/model_settings.py`
- Modify: `apps/api/src/forpost_api/main.py`
- Test: `tests/unit/test_model_settings.py`
- Test: `tests/integration/test_model_settings_api.py`

**Interfaces:**
- GET `/api/model-settings`; POST `/api/model-settings` with `horizon_hours`, `profile`, `maximum_alert_rate`, `sensor_types`, `engineering_systems`.
- Produces append-only `ModelSettingsVersion` and never accepts arbitrary numeric threshold.

- [ ] **Step 1: Write failing policy tests**

```python
def test_settings_reject_unpublished_horizon() -> None:
    with pytest.raises(SettingsPolicyError, match="опубликован"):
        validate_settings(request(horizon_hours=72), catalog=only_24h)

def test_settings_resolve_threshold_from_model_card() -> None:
    resolved = validate_settings(request(profile="high_precision"), catalog=catalog)
    assert resolved.threshold == catalog[24].operating_profiles["high_precision"].threshold
```

- [ ] **Step 2: Verify tests fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_model_settings.py tests/integration/test_model_settings_api.py -q`

Expected: domain and route missing.

- [ ] **Step 3: Implement strict settings policy**

```python
class OperatingProfile(StrEnum):
    HIGH_PRECISION = "high_precision"
    BALANCED = "balanced"
    HIGH_RECALL = "high_recall"

class ModelSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    horizon_hours: Literal[24, 48, 72]
    profile: OperatingProfile
    maximum_alert_rate: Annotated[float, Field(gt=0, le=0.35)]
    sensor_types: Annotated[tuple[str, ...], Field(max_length=32)]
    engineering_systems: Annotated[tuple[str, ...], Field(max_length=32)]
```

- [ ] **Step 4: Persist append-only versions and audit writes**

```sql
CREATE TABLE IF NOT EXISTS model_settings_versions (
  id TEXT PRIMARY KEY,
  version INTEGER NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  previous_version INTEGER
)
```

Require `get_current_human_subject`, `Idempotency-Key`, mutation rate limit and audit event `MODEL_SETTINGS_CHANGED`.

- [ ] **Step 5: Run and commit**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_model_settings.py tests/integration/test_model_settings_api.py tests/security/test_api_hardening.py -q`

```powershell
git add packages/domain/src/forpost_domain/risks/settings.py packages/platform/src/forpost_platform/operations/sqlite_repository.py apps/api/src/forpost_api/routes/model_settings.py apps/api/src/forpost_api/main.py tests/unit/test_model_settings.py tests/integration/test_model_settings_api.py
git commit -m "feat(settings): add guarded model operating profiles"
```

### Task 4: Deterministic recommendation engine

**Files:**
- Create: `packages/prediction/src/forpost_prediction_core/recommendations.py`
- Create: `packages/prediction/src/forpost_prediction_core/rules/sensor_failure.yaml`
- Modify: `apps/api/src/forpost_api/schemas/predictions.py`
- Modify: `apps/api/src/forpost_api/routes/predictions.py`
- Test: `tests/unit/test_recommendations.py`
- Test: `tests/integration/test_predictions_api.py`

**Interfaces:**
- Produces: `Recommendation(rule_id, rule_version, reason_facts, actions, respond_within_minutes, priority, source)`.
- Rule source is `internal_forpost_rule` until a signed normative mapping is supplied.

- [ ] **Step 1: Write failing determinism and provenance tests**

```python
def test_connectivity_rule_has_explainable_ordered_actions() -> None:
    recommendation = engine.evaluate(prediction, facts={"silence_to_normal_ratio": 4.2, "recent_alarm_ratio": 0.0})
    assert recommendation.actions == ("Проверить канал связи", "Проверить питание", "Назначить диагностику датчика")
    assert recommendation.source.kind == "internal_forpost_rule"

def test_no_matching_rule_returns_explicit_absence() -> None:
    assert engine.evaluate(low_risk_prediction, facts={}) is None
```

- [ ] **Step 2: Verify tests fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_recommendations.py -q`

Expected: recommendation module missing.

- [ ] **Step 3: Implement exact rule schema and evaluator**

```python
class RecommendationRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: Annotated[str, Field(pattern=r"^[a-z0-9_]{1,64}$")]
    version: Annotated[int, Field(ge=1)]
    minimum_probability: Annotated[float, Field(ge=0, le=1)]
    required_facts: tuple[str, ...]
    actions: Annotated[tuple[str, ...], Field(min_length=1, max_length=8)]
    respond_within_minutes: Annotated[int, Field(ge=5, le=10080)]
    priority: Literal["low", "medium", "high"]
    source: Literal["internal_forpost_rule"]
```

Evaluate rules in stable priority/id order; include only allow-listed numeric facts in `reason_facts`; do not execute expressions from YAML.

- [ ] **Step 4: Replace free-text recommendation with structured output**

Extend prediction schema with `recommendation: Recommendation | None`; keep the compatibility text derived from `actions`, never supplied independently.

- [ ] **Step 5: Run and commit**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_recommendations.py tests/integration/test_predictions_api.py -q`

```powershell
git add packages/prediction/src/forpost_prediction_core/recommendations.py packages/prediction/src/forpost_prediction_core/rules/sensor_failure.yaml apps/api/src/forpost_api/schemas/predictions.py apps/api/src/forpost_api/routes/predictions.py tests/unit/test_recommendations.py tests/integration/test_predictions_api.py
git commit -m "feat(ml): add auditable recommendation rules"
```

### Task 5: Next.js BFF and strict clients

**Files:**
- Create: `src/app/api/model-outcomes/route.ts`
- Create: `src/app/api/model-settings/route.ts`
- Create: `src/data/modelOutcomesClient.ts`
- Create: `src/data/modelSettingsClient.ts`
- Modify: `src/server/forpostApi.ts`
- Test: `src/data/modelOutcomesClient.test.ts`
- Test: `src/data/modelSettingsClient.test.ts`
- Test: `src/app/api/backend-routes.test.ts`

**Interfaces:**
- Read BFF routes proxy only allow-listed query keys.
- Settings POST requires trusted demo/user session, same-origin CSRF token and idempotency key.

- [ ] **Step 1: Write failing parser and route tests**

```typescript
it('rejects an outcome payload with an unknown field', async () => {
  const feed = await fetchModelOutcomes(mockJson({ ...validPayload, injected: true }));
  expect(feed).toEqual({ status: 'unavailable' });
});

it('does not forward arbitrary query parameters', async () => {
  const response = await GET(new Request('http://localhost/api/model-outcomes?redirect=https://evil.test'));
  expect(response.status).toBe(400);
});
```

- [ ] **Step 2: Verify tests fail**

Run: `npm test -- src/data/modelOutcomesClient.test.ts src/data/modelSettingsClient.test.ts src/app/api/backend-routes.test.ts`

Expected: modules/routes missing.

- [ ] **Step 3: Implement exact TypeScript decoders**

```typescript
export type ConfusionClass = 'TP' | 'FP' | 'FN' | 'TN';
export type OutcomeFeed = { status: 'ready'; data: ModelOutcomeResponse } | { status: 'unauthenticated' | 'unavailable' };

function isExactRecord(value: unknown, keys: readonly string[]): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    && Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key));
}
```

- [ ] **Step 4: Implement constrained BFF routes**

```typescript
const allowed = new Set(['from', 'to', 'sensor_type', 'engineering_system', 'model_version']);
if ([...url.searchParams.keys()].some((key) => !allowed.has(key))) return errorResponse(400, 'Недопустимый фильтр');
return proxyForpostApi(`/api/model-outcomes?${url.searchParams.toString()}`);
```

Settings mutation follows the existing trusted demo session and CSRF helpers; service-token fallback returns 503.

- [ ] **Step 5: Run and commit**

Run: `npm test -- src/data/modelOutcomesClient.test.ts src/data/modelSettingsClient.test.ts src/app/api/backend-routes.test.ts`

```powershell
git add src/app/api/model-outcomes/route.ts src/app/api/model-settings/route.ts src/data/modelOutcomesClient.ts src/data/modelSettingsClient.ts src/server/forpostApi.ts src/data/modelOutcomesClient.test.ts src/data/modelSettingsClient.test.ts src/app/api/backend-routes.test.ts
git commit -m "feat(web): connect model evidence and settings APIs"
```

### Task 6: Operator pages and accessible charts

**Files:**
- Create: `src/app/model-evidence/page.tsx`
- Create: `src/app/settings/page.tsx`
- Create: `src/components/features/OutcomeQualityDashboard.tsx`
- Create: `src/components/features/ModelSettingsForm.tsx`
- Create: `src/components/charts/CalibrationChart.tsx`
- Create: `src/components/charts/LiftChart.tsx`
- Modify: `src/components/layout/Sidebar.tsx`
- Modify: `src/components/layout/Header.tsx`
- Test: `src/app/modelEvidence.test.tsx`
- Test: `src/app/modelSettings.test.tsx`
- Test: `src/components/charts/chartAccessibility.test.tsx`

**Interfaces:**
- `/model-evidence` shows prediction-to-observed outcome rows, TP/FP/FN/TN, precision/recall/F1/PR-AUC, calibration and lift.
- `/settings` exposes only published horizons and validated profiles.

- [ ] **Step 1: Write failing UI behavior tests**

```tsx
it('labels pending outcomes and excludes them from confusion counts', async () => {
  render(<OutcomeQualityDashboard data={fixture} />);
  expect(screen.getByText('Ожидает факта')).toBeInTheDocument();
  expect(screen.getByText('Созревших прогнозов: 4')).toBeInTheDocument();
});

it('offers only thresholds backed by operating profiles', () => {
  render(<ModelSettingsForm catalog={catalog} current={settings} />);
  expect(screen.queryByLabelText('Порог вероятности')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Режим')).toHaveValue('balanced');
});
```

- [ ] **Step 2: Verify UI tests fail**

Run: `npm test -- src/app/modelEvidence.test.tsx src/app/modelSettings.test.tsx src/components/charts/chartAccessibility.test.tsx`

Expected: pages/components missing.

- [ ] **Step 3: Build strict flat Palantir-style dashboard**

Use existing `Card`, `Table`, `Select`, `MultiSelect`, and chart wrappers. Calibration and lift charts must pass both `option` and the same values to `ChartDataTable`; use no decorative 3D, gradients or fake probabilities.

```tsx
<Chart
  option={calibrationOption(data.calibrationBins)}
  ariaLabel="Калибровка: прогнозная вероятность и наблюдаемая доля исходов"
  table={<ChartDataTable ariaLabel="Таблица калибровки" columns={columns} rows={rows} />}
/>
```

- [ ] **Step 4: Add navigation and explicit evidence labels**

Add `Качество прогнозов` and `Настройки модели`; rename the current design-system navigation item to `Компоненты` so settings no longer points at a showcase.

- [ ] **Step 5: Run all frontend gates**

Run: `npm test && npm run lint && npm run typecheck && npm run build`

Expected: all pass.

- [ ] **Step 6: Commit**

```powershell
git add src/app/model-evidence src/app/settings src/components/features/OutcomeQualityDashboard.tsx src/components/features/ModelSettingsForm.tsx src/components/charts/CalibrationChart.tsx src/components/charts/LiftChart.tsx src/components/layout/Sidebar.tsx src/components/layout/Header.tsx src/app/modelEvidence.test.tsx src/app/modelSettings.test.tsx src/components/charts/chartAccessibility.test.tsx
git commit -m "feat(web): add operator model evidence workspace"
```

### Task 7: End-to-end operator evidence verification

**Files:**
- Modify: `docs/ML_METHODS.md`
- Modify: `docs/TZ_COMPLIANCE.md`
- Modify: `docs/LOCAL_VERIFY.md`

**Interfaces:**
- Documents traceability from TЗ criteria to API/UI/tests.

- [ ] **Step 1: Run Python and web suites**

Run: `.venv\Scripts\python.exe -m pytest -q`

Run: `npm test && npm run lint && npm run typecheck && npm run build`

Expected: PASS.

- [ ] **Step 2: Start isolated local stack and smoke read APIs**

Run: `npm run dev:stack`

Expected: loopback-only web/API, authenticated demo flow, no external data transmission.

- [ ] **Step 3: Run security audit and commit evidence docs**

Run: `powershell -ExecutionPolicy Bypass -File .\run_security_audit.ps1`

```powershell
git add docs/ML_METHODS.md docs/TZ_COMPLIANCE.md docs/LOCAL_VERIFY.md
git commit -m "docs: trace operator ml evidence requirements"
```
