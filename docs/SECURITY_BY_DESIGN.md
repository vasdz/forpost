# Security by Design

## 1. Security objective

Контур защищает целостность цепочки решения: локальные данные → подготовка и
валидация ML → проверенный релиз → прогноз с evidence → решение диспетчера →
audit → локальный draft. Это не заявление о production deployment.

## 2. Trust boundaries

| Граница | Правило |
| --- | --- |
| Репозиторий и CI | raw/processed data, модели и `.env*` не входят в Git; guards проверяют index и push. |
| Локальные данные и preprocessing | адаптеры принимают пути только внутри разрешённых корней; UI не читает `data/` напрямую. |
| Training и release | временная валидация отделена от frozen final test; версия и export проверяются manifest SHA-256. |
| API и BFF | loopback-only, service token только для чтения; write требует отдельного demo subject, origin/CSRF и RBAC/ABAC. |
| Решение и audit | prediction не является решением; сервер проверяет команду, idempotency и записывает hash-chain audit. |

## 3. Core controls

| Control | Threat | Implementation | Evidence |
| --- | --- | --- | --- |
| Fail-closed | Нет либо повреждён snapshot/release/export | `apps/api/src/forpost_api/routes/predictions.py` | `tests/integration/test_predictions_api.py` |
| Least privilege | Подделанное действие оператора | `apps/api/src/forpost_api/dependencies.py`, `routes/v1/incidents.py` | `tests/security/test_api_hardening.py`, `test_demo_identity.py` |
| Model integrity | Подмена bundle или export | `packages/prediction/src/forpost_prediction_core/registry.py` | `tests/unit/test_ml_registry.py` |
| Human-only decision | Автоматическое небезопасное действие | `apps/api/src/forpost_api/routes/v1/incidents.py` | `tests/integration/test_incidents_api.py` |
| Data perimeter | Данные или secret в Git | `scripts/pre-commit-guard.mjs` | `scripts/pre-commit-guard.test.mjs` |

Полная трассировка controls и проверок: [SECURITY_EVIDENCE.md](SECURITY_EVIDENCE.md).

## 4. Observed / Predicted / Simulated

`observed` — факт локального снимка; `predicted` — только proxy risk
unexpected telemetry silence с evidence tier; `simulated` — локальный draft
или условная схема. Ни одна категория не заменяет другую и не является
подтверждением физического отказа или внешним действием.

## 5. Threat model relation

[THREAT_MODEL.md](THREAT_MODEL.md) описывает атакующего, mitigation и остаточный
риск для цепочки dependency/CI → data → features → model → prediction → decision
→ action. Этот документ — краткая карта реализованных границ.

## 6. Production boundary

Это защищённый локальный demo-контур. Enterprise IAM, TLS termination, SIEM,
LDAP/AD, immutable external audit, backup и production deployment не заявлены.
