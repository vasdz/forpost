# Scoring Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Закрыть наиболее дорогие технические разрывы ТЗ: единый запуск, доказательность ML, проверку 20 пользователей и актуальную документацию.

**Architecture:** Существующие Next.js BFF и FastAPI остаются границами UI и backend. Новый launcher оркестрирует только loopback-процессы; ML-отчёт является отдельным fail-closed read-only артефактом и не даёт права публиковать прогнозы; нагрузочная проверка использует ASGI без внешней сети.

**Tech Stack:** Node.js 22, Next.js 15.5, TypeScript strict, FastAPI, Pydantic, pytest, Vitest, httpx.

**Spec:** `docs/superpowers/specs/2026-09-21-scoring-readiness-design.md`

## Global Constraints

- Весь UI-текст и комментарии на русском; идентификаторы на английском.
- `data/raw`, `data/processed` и `ml/models` не коммитятся и не передаются наружу.
- Прогноз публикуется только из прошедшего действующие quality gates release.
- Все локальные серверы слушают только `127.0.0.1`.
- Не добавлять `TODO`, заглушки, ослабление quality gates или синтетические прогнозы.
- Работа ведётся в `main` по явному требованию пользователя.

---

### Task 1: One-command local stack

**Files:**
- Create: `scripts/run-local-stack.mjs`
- Create: `scripts/run-local-stack.test.mjs`
- Modify: `package.json`
- Modify: `README.md`

**Interfaces:**
- Produces: `getLocalStackLaunches(env)` and `runLocalStack()`; npm script `dev:stack`.

- [ ] **Step 1: Write failing launcher tests**

Test that both launches bind to `127.0.0.1`, share a generated token of at
least 32 characters, API receives the repository Python source paths, arbitrary
arguments are rejected, and no token appears in returned display labels.

- [ ] **Step 2: Run the target test and confirm RED**

Run: `npx vitest run scripts/run-local-stack.test.mjs`

- [ ] **Step 3: Implement the minimal orchestrator**

Spawn `python -m uvicorn forpost_api.main:app --host 127.0.0.1 --port 8000`
and the existing Next launcher, forward a shared random service token, terminate
the sibling when either process exits, and reject extra CLI arguments.

- [ ] **Step 4: Verify GREEN and document the command**

Run: `npx vitest run scripts/run-local-stack.test.mjs scripts/local-bindings.test.mjs`

- [ ] **Step 5: Commit**

Commit message: `feat: add one-command local stack`

### Task 2: Fail-closed ML evaluation evidence

**Files:**
- Create: `packages/prediction/src/forpost_prediction_core/evaluation_report.py`
- Create: `apps/api/src/forpost_api/routes/model_evaluation.py`
- Create: `tests/unit/test_ml_evaluation_report.py`
- Create: `tests/integration/test_model_evaluation_api.py`
- Modify: `apps/api/src/forpost_api/main.py`
- Modify: `scripts/train_sensor_failure.py`

**Interfaces:**
- Produces: `EvaluationReport`, `write_evaluation_report(path, report)`,
  `load_evaluation_report(path)` and authenticated `GET /api/model-evaluation`.

- [ ] **Step 1: Write failing schema, atomic-write and API tests**

Cover exact-field parsing, bounded metrics, rejected reports without test
metrics, published reports with test metrics, invalid/oversized/missing files
returning `503`, and authenticated valid response.

- [ ] **Step 2: Run the target tests and confirm RED**

Run: `pytest tests/unit/test_ml_evaluation_report.py tests/integration/test_model_evaluation_api.py -q`

- [ ] **Step 3: Implement report model, loader, writer and route**

Use Pydantic `extra="forbid"`, atomic temporary-file replacement, a 256 KiB
read limit, finite metrics within `[0, 1]`, safe reason codes and no raw paths.

- [ ] **Step 4: Integrate the training command**

Write a `published` report after a successful release. On a controlled training
failure write `rejected` with a safe reason code and only evidence computed
before the failure; never expose exception text and never evaluate test after a
validation rejection.

- [ ] **Step 5: Verify GREEN**

Run: `pytest tests/unit/test_ml_evaluation_report.py tests/integration/test_model_evaluation_api.py tests/unit/test_ml_training.py tests/integration/test_predictions_api.py -q`

- [ ] **Step 6: Commit**

Commit message: `feat: expose ml evaluation evidence`

### Task 3: ML quality dashboard

**Files:**
- Create: `src/data/modelEvaluationClient.ts`
- Create: `src/data/modelEvaluationClient.test.ts`
- Create: `src/components/features/ModelQualityPanel.tsx`
- Create: `src/components/features/ModelQualityPanel.test.tsx`
- Create: `src/app/api/model-evaluation/route.ts`
- Modify: `src/app/sensor-failure/page.tsx`

**Interfaces:**
- Consumes: `GET /api/model-evaluation` from Task 2 through the existing BFF.
- Produces: strict `ModelEvaluation` client contract and accessible dashboard.

- [ ] **Step 1: Write failing client and component tests**

Cover exact keys, invalid metric rejection, `503` unavailable state, explicit
validation/test labels, quality thresholds, split sizes and rejected status.

- [ ] **Step 2: Run the target tests and confirm RED**

Run: `npx vitest run src/data/modelEvaluationClient.test.ts src/components/features/ModelQualityPanel.test.tsx`

- [ ] **Step 3: Implement BFF, client and panel**

Proxy through `proxyForpostApi`, render semantic cards and a table, and state
that a rejected report is evidence of a blocked release rather than a forecast.

- [ ] **Step 4: Integrate with sensor-failure page and verify GREEN**

Run: `npx vitest run src/data/modelEvaluationClient.test.ts src/components/features/ModelQualityPanel.test.tsx src/app/realDataUi.test.tsx`

- [ ] **Step 5: Commit**

Commit message: `feat: add ml quality dashboard`

### Task 4: Reproducible 20-user check and documentation sync

**Files:**
- Create: `scripts/load_check.py`
- Create: `tests/integration/test_load_check.py`
- Modify: `README.md`
- Modify: `docs/TZ_COMPLIANCE.md`
- Modify: `docs/ML_METHODS.md`
- Modify: `docs/LOCAL_VERIFY.md`
- Modify: `docs/DEMO_SCRIPT.md`

**Interfaces:**
- Produces: CLI JSON summary with `users`, `requests`, `errors`, `p95_ms` and
  exit code 0 only when 20-user read-only check has no errors.

- [ ] **Step 1: Write failing load-runner tests**

Use a temporary snapshot and real ASGI app dependency overrides. Assert 20
users, deterministic request count, zero errors on healthy routes, nonzero exit
on injected failures and no write methods.

- [ ] **Step 2: Run the target test and confirm RED**

Run: `pytest tests/integration/test_load_check.py -q`

- [ ] **Step 3: Implement the read-only concurrent runner**

Use `httpx.AsyncClient` with `ASGITransport`, service-token authentication,
`asyncio.TaskGroup`, `time.perf_counter`, and nearest-rank p95.

- [ ] **Step 4: Verify GREEN and execute the runner**

Run: `pytest tests/integration/test_load_check.py -q`
Run: `python scripts/load_check.py --users 20 --requests-per-user 5`

- [ ] **Step 5: Synchronize factual documentation**

Document the one-command launch, ML evidence endpoint, actual topology and
draft workflows, load-test scope, remaining enterprise integrations and exact
limitations. Remove claims contradicted by current code.

- [ ] **Step 6: Run full verification and commit**

Run frontend tests, Python tests, lint, typecheck, Ruff, Bandit and build.
Commit message: `test: verify scoring readiness`
