# Security Evidence Matrix

| Threat | Security control | Where implemented | Test / verification | Status |
| --- | --- | --- | --- | --- |
| Forged identity | Server-side Bearer/demo trust boundary | `apps/api/src/forpost_api/dependencies.py`, `packages/platform/src/forpost_platform/security/demo_identity.py` | `tests/security/test_demo_identity.py` | implemented |
| Unauthorized read/write | RBAC/ABAC and scoped subject | `dependencies.py`, `routes/v1/incidents.py` | `tests/security/test_api_hardening.py` | implemented |
| Cross-site write | Origin and CSRF checks | `apps/api/src/forpost_api/middleware/` | `tests/security/test_api_hardening.py` | implemented |
| Request flooding | Rate limiter before body buffering | `apps/api/src/forpost_api/middleware/rate_limit.py` | `tests/security/test_api_hardening.py` | implemented |
| Duplicate operator command | Idempotency fingerprint | `packages/platform/src/forpost_platform/operations/sqlite_repository.py` | `tests/integration/test_incidents_api.py` | implemented |
| Path/symlink escape | Canonical allowed roots and regular-file checks | `packages/connectors/src/forpost_connectors/local_snapshot.py`, `routes/predictions.py` | `tests/unit/test_local_snapshot.py`, `tests/integration/test_predictions_api.py` | implemented |
| Data/secret disclosure | Git perimeter and secret scanning | `scripts/pre-commit-guard.mjs`, `.github/workflows/ci.yml` | `scripts/pre-commit-guard.test.mjs`, `npm run verify:submission:fast` | implemented |
| Model/export substitution | Immutable release and SHA-256 manifest | `packages/prediction/src/forpost_prediction_core/registry.py`, `routes/predictions.py` | `tests/unit/test_ml_registry.py` | implemented |
| Overstated prediction | Evidence-tier contract and fail-closed serving | `capabilities.py`, `schemas/predictions.py` | `tests/unit/test_ml_capabilities.py` | implemented |
| Automated harmful action | Human subject plus server-side command validation | `routes/v1/incidents.py` | `tests/integration/test_incidents_api.py` | implemented |
| Audit tampering | Append-only hash chain verification | `packages/platform/src/forpost_platform/audit/ledger.py` | `tests/security/test_audit_integrity.py` | implemented locally |
| Dependency defect | Pinned dependencies and CI audit | `requirements-prod.lock`, `.github/workflows/ci.yml` | `scripts/ci-config.test.mjs` | implemented |
| Static defect | Ruff, Bandit, Semgrep/TruffleHog in CI | `.github/workflows/ci.yml` | `npm run verify:submission:full` | implemented |

`implemented locally` не означает защищённую сеть или внешний immutable audit.
Residual risks and required production controls are in [THREAT_MODEL.md](THREAT_MODEL.md).
