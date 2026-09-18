# Secure Demo Contour Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Реализовать безопасный локальный демонстрационный контур с достоверным происхождением данных, автообновлением, точной RBAC/ABAC-моделью, журналом решений, черновиками заявок и схемной GeoJSON-топологией.

**Architecture:** Локальный адаптер строит контракт v2 из реальных CSV; FastAPI владеет идентичностью и изменяемым бизнес-состоянием; SQLite хранит только решения, черновики и аудит; Next.js работает через BFF. Demo-функции включаются явным окружением, маркируются `simulated` и остаются недоступными в production-режиме.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, stdlib SQLite/HMAC, Next.js 15 App Router, React 19, TypeScript strict, ECharts, Tailwind CSS 4, Vitest, Pytest.

**Spec:** `docs/SECURE_DEMO_CONTOUR.md`

## Global Constraints

- Работать непосредственно в `main`; новые ветки и worktree не создавать.
- Реальные файлы из `data/raw` и производные файлы из `data/processed` не коммитить и не передавать внешним сервисам.
- UI-тексты и комментарии писать на русском, идентификаторы — на английском.
- Стиль сохранять строго плоским по `docs/SPEC.md`: без blur, glass, градиентов и больших скруглений.
- Любое синтетическое значение маркировать `provenance: "simulated"`; наблюдение источника — `observed`.
- Production-режим по умолчанию остаётся fail-closed.
- Новое поведение разрабатывать через RED → GREEN → REFACTOR.

---

### Task 1: Контракт локальных данных v2 и правила качества

**Files:**
- Modify: `packages/connectors/src/forpost_connectors/local_snapshot.py`
- Modify: `tests/unit/test_local_snapshot.py`
- Modify: `src/data/localSituationContract.ts`
- Modify: `src/data/localSituation.test.ts`
- Modify: `src/data/localSituationContract.test.ts`

**Interfaces:**
- Produces: `ChannelRegistryEntry.object_id: str | None`
- Produces: `ObservedEvent.canonical_id`, `quality_code`, `analysis_eligible`, `provenance`
- Produces: `LocalSituationSnapshot.data_quality`
- Produces: TypeScript `DataQuality`, `Provenance`, expanded channel/event contracts

- [ ] **Step 1: Write failing Python tests** for old/new channel schemas, referential integrity, canonical IDs, sentinel handling and the 2021 policy.

```python
def test_non_alarm_technical_value_is_not_eligible_for_analytics(tmp_path: Path):
    snapshot = build_fixture_snapshot(tmp_path, alarm="f", sensor_value="-3276")
    assert snapshot.events[0].quality_code == "technical_anomaly"
    assert snapshot.events[0].analysis_eligible is False
```

- [ ] **Step 2: Run the focused tests and verify RED.**

Run: `python -m pytest tests/unit/test_local_snapshot.py -q`

- [ ] **Step 3: Implement strict dual channel schemas and quality classification.**

```python
def classify_event_quality(sensor_value: str, is_alarm: bool | None, recorded_at: datetime) -> tuple[str, bool]:
    if is_technical_value(sensor_value, recorded_at):
        return ("alarm_with_technical_value", True) if is_alarm else ("technical_anomaly", False)
    if recorded_at.year == 2021:
        return "monitoring_system_migration", False
    return "valid", True
```

- [ ] **Step 4: Write failing TypeScript contract tests, implement the exact v2 validator, and verify GREEN.**

Run: `npm test -- src/data/localSituation.test.ts src/data/localSituationContract.test.ts`

- [ ] **Step 5: Rebuild the ignored local snapshot, run Python and TypeScript focused tests, then commit.**

Commit: `feat: add source quality contract v2`

### Task 2: Автообновление и last-known-good

**Files:**
- Modify: `src/data/localSituationClient.ts`
- Modify: `src/data/LocalSituationProvider.tsx`
- Modify: `src/data/LocalSituationProvider.test.tsx`
- Modify: `src/components/layout/Header.tsx`
- Modify: `src/components/layout/Header.test.ts`

**Interfaces:**
- Produces: `LocalSituationLoadState` with `refreshedAt`, `isRefreshing`, `refreshError`
- Produces: polling every `60_000` ms and immediate refresh on `visibilitychange`

- [ ] **Step 1: Write failing fake-timer tests** proving 60-second refresh, no overlapping requests and last-known-good retention.

```tsx
expect(fetcher).toHaveBeenCalledTimes(1);
await vi.advanceTimersByTimeAsync(60_000);
expect(fetcher).toHaveBeenCalledTimes(2);
expect(screen.getByText('Исторический источник')).toBeInTheDocument();
```

- [ ] **Step 2: Run the provider test and verify RED.**

Run: `npm test -- src/data/LocalSituationProvider.test.tsx`

- [ ] **Step 3: Implement an abortable scheduler and preserve the last ready snapshot on refresh failure.**

- [ ] **Step 4: Add the compact freshness indicator to Header and verify focused tests GREEN.**

- [ ] **Step 5: Run frontend tests, typecheck and lint, then commit.**

Commit: `feat: refresh local situation safely`

### Task 3: Exact demo identity and RBAC/ABAC

**Files:**
- Modify: `packages/platform/src/forpost_platform/security/identity.py`
- Create: `packages/platform/src/forpost_platform/security/demo_identity.py`
- Modify: `apps/api/src/forpost_api/dependencies.py`
- Create: `apps/api/src/forpost_api/routes/v1/demo_session.py`
- Modify: `apps/api/src/forpost_api/main.py`
- Modify: `tests/integration/test_api_abac.py`
- Create: `tests/security/test_demo_identity.py`

**Interfaces:**
- Produces: roles `district_dispatcher`, `central_dispatcher`, `technician`, `admin`
- Produces: `SecuritySubject.roles: frozenset[Role]`, `allowed_districts`, `allowed_complexes`
- Produces: HMAC demo assertions accepted only when `FORPOST_DEMO_MODE=1`

- [ ] **Step 1: Write failing matrix tests** for additive permissions, scope unions, expiration, audience, signature and production rejection.

```python
def test_admin_alone_cannot_record_business_decision():
    subject = SecuritySubject(user_id="admin", roles={Role.ADMIN})
    assert not subject.has_permission(Permission.RECORD_DECISION)
```

- [ ] **Step 2: Run security/ABAC tests and verify RED.**

- [ ] **Step 3: Implement the role matrix and stdlib HMAC assertion codec with constant-time verification.**

- [ ] **Step 4: Implement the loopback-only demo session route with safe configuration failures.**

- [ ] **Step 5: Run focused security and integration tests, Ruff and Bandit, then commit.**

Commit: `feat: add fail-closed demo identity`

### Task 4: Persistent incident decisions, drafts and audit

**Files:**
- Create: `packages/domain/src/forpost_domain/incidents/entities.py`
- Create: `packages/platform/src/forpost_platform/operations/sqlite_repository.py`
- Create: `apps/api/src/forpost_api/routes/v1/incidents.py`
- Modify: `apps/api/src/forpost_api/routes/v1/maintenance.py`
- Modify: `apps/api/src/forpost_api/main.py`
- Create: `tests/unit/test_sqlite_operations.py`
- Create: `tests/integration/test_incidents_api.py`

**Interfaces:**
- Produces: `SqliteOperationsRepository.record_decision(decision: IncidentDecision, idempotency_key: str) -> IncidentDecision`
- Produces: `SqliteOperationsRepository.create_draft(draft: ServiceRequestDraft) -> ServiceRequestDraft`
- Produces: idempotent POST `/api/v1/incidents/{incident_id}/decisions`
- Produces: GET/POST `/api/v1/service-request-drafts`

- [ ] **Step 1: Write failing repository tests** for migrations, persistence, idempotency, correction records and hash-chain verification.

- [ ] **Step 2: Run focused tests and verify RED.**

- [ ] **Step 3: Implement parameterized SQLite transactions under `data/processed`.**

- [ ] **Step 4: Write failing API tests for permissions, scope, payload bounds and stable errors.**

- [ ] **Step 5: Implement routes, verify all focused tests GREEN, then commit.**

Commit: `feat: persist demo operations and audit`

### Task 5: Deterministic GeoJSON topology

**Files:**
- Create: `packages/platform/src/forpost_platform/topology/generator.py`
- Create: `apps/api/src/forpost_api/routes/v1/topology.py`
- Modify: `apps/api/src/forpost_api/main.py`
- Create: `tests/unit/test_topology.py`
- Create: `tests/integration/test_topology_api.py`

**Interfaces:**
- Produces: `build_schematic_feature_collection(objects, subject) -> dict`
- Produces: GET `/api/v1/topology`
- Produces: `pickets_to_metres(pickets: Decimal) -> Decimal`

- [ ] **Step 1: Write failing deterministic geometry and 10-metre picket tests.**

```python
assert pickets_to_metres(Decimal("88.5")) == Decimal("885")
assert result["features"][0]["properties"]["geometrySource"] == "synthetic"
```

- [ ] **Step 2: Verify RED, then implement stable tree layout without geographic claims.**

- [ ] **Step 3: Add ABAC-filtered API and invalid-tree handling.**

- [ ] **Step 4: Run focused tests and commit.**

Commit: `feat: expose schematic collector topology`

### Task 6: Dispatcher workflow UI

**Files:**
- Create: `src/data/operationsClient.ts`
- Create: `src/components/features/SourceBadge.tsx`
- Modify: `src/app/journals/page.tsx`
- Modify: `src/app/applications/page.tsx`
- Create: `src/app/topology/page.tsx`
- Modify: `src/components/layout/Sidebar.tsx`
- Modify: `src/app/realDataUi.test.tsx`
- Create: `src/data/operationsClient.test.ts`

**Interfaces:**
- Consumes: Tasks 1–5 API contracts
- Produces: incident decision modal, persistent draft list, provenance labels, schematic visual plus table

- [ ] **Step 1: Write failing client and UI flow tests** for provenance, decision validation, server error retention and accessible topology fallback.

- [ ] **Step 2: Run tests and verify RED.**

- [ ] **Step 3: Implement BFF clients and strict runtime validators.**

- [ ] **Step 4: Implement journal decisions, drafts and topology in strict flat style.**

- [ ] **Step 5: Run Vitest, typecheck, lint and production build, then commit.**

Commit: `feat: complete dispatcher demo workflow`

### Task 7: Compliance, security scan and release verification

**Files:**
- Modify: `docs/DECISIONS.md`
- Modify: `docs/TZ_COMPLIANCE.md`
- Modify: `docs/SECURITY_AUDIT.md`
- Modify: `docs/DEMO_SCRIPT.md`
- Modify: `README.md`
- Output locally: canonical Codex Security scan artifacts outside versioned source

**Interfaces:**
- Consumes: verified implementation and tool outputs
- Produces: evidence-backed compliance/security state without overstating production readiness

- [ ] **Step 1: Run all Python and frontend tests, typecheck, lint and isolated production build.**

- [ ] **Step 2: Run Ruff check/format check, Bandit, Semgrep, TruffleHog, `pip check` and `npm audit`.**

- [ ] **Step 3: Execute the standard repository-wide Codex Security scan, validate every candidate and fix confirmed in-scope findings through TDD.**

- [ ] **Step 4: Repeat affected tests and security tools after remediation.**

- [ ] **Step 5: Update factual documentation, run `git diff --check`, commit, push and verify `HEAD == origin/main`.**

Commit: `docs: verify secure demo contour delivery`
