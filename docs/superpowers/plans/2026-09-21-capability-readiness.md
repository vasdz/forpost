# Prediction Capability Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать готовность пожара, доступа, износа и подтопления машиночитаемой и fail-closed, а погоду подключить через безопасный read-only адаптер без передачи локальных идентификаторов.

**Architecture:** Каждое направление описывается версионированным source contract и readiness report. Capability становится `available` только при одновременном наличии полей, качества источника и валидированного model artifact; иначе разрешены только явно маркированные anomaly/scenario режимы.

**Tech Stack:** Python 3.12, Pydantic 2, FastAPI, стандартный `urllib`/локальный cache boundary, Next.js 15, TypeScript strict, pytest, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-21-ml-champion-system-design.md`

## Global Constraints

- Неполный источник не превращается в probability и не заменяется синтетическими данными.
- Внешняя погода получает только район/координатную сетку, время и метеопараметры; локальные IDs запрещены.
- Все интеграции заказчика работают read-only.
- Capability автоматически меняет состояние только после успешной валидации источника и model artifact.

---

### Task 1: Versioned source contracts and readiness reports

**Files:**
- Create: `packages/prediction/src/forpost_prediction_core/source_contracts.py`
- Modify: `packages/prediction/src/forpost_prediction_core/capabilities.py`
- Create: `ml/source-contracts.yaml`
- Test: `tests/unit/test_ml_source_contracts.py`
- Modify: `tests/unit/test_ml_capabilities.py`

**Interfaces:**
- Produces: `SourceContract`, `SourceValidationReport`, `CapabilityReadiness`, `validate_source_contract(...)`.

- [ ] **Step 1: Write failing contract tests**

```python
@pytest.mark.parametrize("task", ["fire_risk", "unauthorized_access", "infrastructure_wear"])
def test_probability_is_unavailable_without_confirmed_outcome(task: str) -> None:
    report = validate_source_contract(task, observed_fields=contracts[task].required_fields - {"confirmed_outcome"}, artifact=None)
    assert report.maximum_evidence_tier in {EvidenceTier.ANOMALY, EvidenceTier.SCENARIO}
    assert report.available is False

def test_capability_becomes_available_only_with_source_and_artifact() -> None:
    report = assess_readiness(complete_source_report, valid_model_artifact)
    assert report.available is True
```

- [ ] **Step 2: Verify tests fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_ml_source_contracts.py tests/unit/test_ml_capabilities.py -q`

Expected: source contract module missing.

- [ ] **Step 3: Implement exact contracts**

```python
class SourceContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    task: PredictionTask
    version: Annotated[int, Field(ge=1)]
    required_sources: Annotated[tuple[str, ...], Field(min_length=1)]
    required_fields: Annotated[frozenset[str], Field(min_length=1)]
    confirmed_outcome_field: str
    maximum_without_outcome: Literal[EvidenceTier.ANOMALY, EvidenceTier.SCENARIO]
```

Define fire fields (`temperature`, `smoke`, `hot_work_window`, `confirmed_outcome`), access fields (`access_event`, `permit_window`, `investigation_outcome`), wear fields (`asset_id`, `commissioned_at`, `maintenance_at`, `repair_or_replacement`, `confirmed_outcome`).

- [ ] **Step 4: Run and commit**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_ml_source_contracts.py tests/unit/test_ml_capabilities.py -q`

```powershell
git add packages/prediction/src/forpost_prediction_core/source_contracts.py packages/prediction/src/forpost_prediction_core/capabilities.py ml/source-contracts.yaml tests/unit/test_ml_source_contracts.py tests/unit/test_ml_capabilities.py
git commit -m "feat(ml): add prediction source readiness contracts"
```

### Task 2: Read-only weather adapter

**Files:**
- Create: `packages/connectors/src/forpost_connectors/weather.py`
- Test: `tests/unit/test_weather_connector.py`

**Interfaces:**
- Produces: `WeatherQuery(district_code, latitude_bucket, longitude_bucket, start_at, end_at)` and `ReadOnlyWeatherAdapter.fetch(query) -> WeatherSeries`.
- Enforces HTTPS, hostname allow-list, GET-only, timeout, response limit, cache TTL and no local identifiers.

- [ ] **Step 1: Write failing SSRF, privacy and cache tests**

```python
def test_weather_adapter_rejects_non_allowlisted_origin() -> None:
    with pytest.raises(WeatherAdapterError, match="origin"):
        ReadOnlyWeatherAdapter("https://127.0.0.1/weather", transport=fake_transport)

def test_weather_request_contains_no_asset_or_sensor_identifiers() -> None:
    adapter.fetch(query)
    assert set(fake_transport.last_query) == {"latitude", "longitude", "start", "end", "hourly"}

def test_weather_cache_avoids_duplicate_external_request() -> None:
    adapter.fetch(query); adapter.fetch(query)
    assert fake_transport.calls == 1
```

- [ ] **Step 2: Verify tests fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_weather_connector.py -q`

Expected: connector missing.

- [ ] **Step 3: Implement fail-closed GET adapter**

```python
ALLOWED_WEATHER_HOSTS = frozenset({"api.open-meteo.com"})
MAX_WEATHER_RESPONSE_BYTES = 2 * 1024 * 1024

def _validate_origin(url: URL) -> None:
    if url.scheme != "https" or url.host not in ALLOWED_WEATHER_HOSTS or url.userinfo:
        raise WeatherAdapterError("Недопустимый weather origin")
```

The transport interface accepts only a parsed URL and fixed timeout, rejects redirects, checks `Content-Length` before reading and applies the byte cap while streaming. Cache keys contain only rounded coordinates and date interval.

- [ ] **Step 4: Run and commit**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_weather_connector.py tests/security/test_secure_file.py -q`

```powershell
git add packages/connectors/src/forpost_connectors/weather.py tests/unit/test_weather_connector.py
git commit -m "feat(connectors): add private read only weather adapter"
```

### Task 3: Capability readiness API and UI

**Files:**
- Create: `apps/api/src/forpost_api/routes/capabilities.py`
- Modify: `apps/api/src/forpost_api/main.py`
- Create: `src/app/api/capabilities/route.ts`
- Create: `src/data/capabilitiesClient.ts`
- Modify: `src/components/features/PredictionCapability.tsx`
- Modify: `src/components/features/CapabilityUnavailablePage.tsx`
- Test: `tests/integration/test_capabilities_api.py`
- Test: `src/data/capabilitiesClient.test.ts`
- Test: `src/app/realDataUi.test.tsx`

**Interfaces:**
- GET `/api/capabilities` returns task, status, maximum evidence tier, missing sources/fields, validation timestamp and artifact state.

- [ ] **Step 1: Write failing API/UI tests**

```python
def test_capability_api_does_not_claim_probability_without_artifact(client):
    item = client.get("/api/capabilities").json()["capabilities"]["fire_risk"]
    assert item["available"] is False
    assert item["maximum_evidence_tier"] != "proxy"
```

```tsx
it('shows concrete missing inputs and never renders a zero risk', async () => {
  render(<CapabilityUnavailablePage capability={fireUnavailable} />);
  expect(screen.getByText('Нет подтверждённых исходов')).toBeInTheDocument();
  expect(screen.queryByText('0%')).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Verify tests fail**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_capabilities_api.py -q`

Run: `npm test -- src/data/capabilitiesClient.test.ts src/app/realDataUi.test.tsx`

Expected: routes/clients missing.

- [ ] **Step 3: Implement exact read API and decoder**

```python
class CapabilityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task: PredictionTask
    available: bool
    maximum_evidence_tier: EvidenceTier
    missing_sources: tuple[str, ...]
    missing_fields: tuple[str, ...]
    validation_status: Literal["passed", "failed", "not_run"]
    artifact_status: Literal["valid", "missing", "invalid"]
```

Use no-store responses and the existing prediction-read permission. TypeScript decoder rejects unknown fields and impossible combinations such as `available: true` with a missing artifact.

- [ ] **Step 4: Render operational readiness blocks**

Show: what exists, what is missing, maximum honest evidence tier, required next source, and last validation status. Keep scenario/anomaly call-to-action distinct from production prediction.

- [ ] **Step 5: Run and commit**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_capabilities_api.py -q`

Run: `npm test -- src/data/capabilitiesClient.test.ts src/app/realDataUi.test.tsx`

```powershell
git add apps/api/src/forpost_api/routes/capabilities.py apps/api/src/forpost_api/main.py src/app/api/capabilities/route.ts src/data/capabilitiesClient.ts src/components/features/PredictionCapability.tsx src/components/features/CapabilityUnavailablePage.tsx tests/integration/test_capabilities_api.py src/data/capabilitiesClient.test.ts src/app/realDataUi.test.tsx
git commit -m "feat: expose prediction capability readiness"
```

### Task 4: Final compliance and security verification

**Files:**
- Modify: `docs/ML_TASKS.md`
- Modify: `docs/DATA_MAPPING.md`
- Modify: `docs/TZ_COMPLIANCE.md`
- Modify: `docs/THREAT_MODEL.md`

**Interfaces:**
- Produces a field-level integration checklist and honest claim boundary for every prediction direction.

- [ ] **Step 1: Document source-to-capability mappings**

```markdown
| Направление | Минимальные источники | Подтверждённый исход | Максимальный режим без исхода |
|---|---|---|---|
| Пожар | температура, дым, горячие работы | подтверждённый пожар/проверка | anomaly |
| Доступ | СКУД, допуск | результат расследования | anomaly |
| Износ | реестр, ТО, ремонт | ремонт/замена/дефектовка | scenario |
```

- [ ] **Step 2: Run full verification**

Run: `.venv\Scripts\python.exe -m pytest -q`

Run: `npm test && npm run lint && npm run typecheck && npm run build`

Run: `powershell -ExecutionPolicy Bypass -File .\run_security_audit.ps1`

Expected: all blocking checks pass.

- [ ] **Step 3: Check tracked privacy boundary**

Run: `git ls-files data/raw data/processed ml/models`

Expected: no output.

- [ ] **Step 4: Commit documentation**

```powershell
git add docs/ML_TASKS.md docs/DATA_MAPPING.md docs/TZ_COMPLIANCE.md docs/THREAT_MODEL.md
git commit -m "docs: define capability readiness evidence"
```
