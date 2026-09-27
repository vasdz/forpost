# LTC 2026 — guide for reviewer

## 1. Проблема

Диспетчер инженерных коллекторов получает реактивные сработки и должен
разделять подтверждённое наблюдение, ML-сигнал и собственное решение без
подмены одного другим.

## 2. Решение

ФОРПОСТ — локальный ситуационный центр: он показывает обезличенные наблюдения,
безопасно отдаёт единственный доступный 24-часовой proxy ML-release, объясняет
его факторы и фиксирует ручное решение с audit trail и simulated draft.

## 3. Основной пользовательский сценарий

**Наблюдение → прогноз → решение → audit → заявка.** Решение не принимается
автоматически; черновик не отправляется во внешнюю help-desk.

## 4. Где посмотреть это в UI

| Этап | Route | Что проверяется |
| --- | --- | --- |
| Наблюдение | `/` и `/journals` | `observed` события, timeline и неизменность исходного факта. |
| Прогноз | `/sensor-failure` | 24 часа, evidence tier `proxy`, version и quality evidence. |
| Контекст | `/notifications` | Факторы, ограничения и observed telemetry того же канала. |
| Решение | `/notifications` или `/journals` | Human-only demo-session, причина и audit record. |
| Заявка | `/applications` | Связанный `simulated` draft без внешней отправки. |
| Топология | `/topology` | Иерархия из snapshot и явно simulated координаты. |

При отсутствии локального экспортa/снимка соответствующий путь показывает
недоступность, а не synthetic fallback.

## 5. Где посмотреть ML

- UI: `/sensor-failure` и `/notifications`.
- Методика и защита final test: [docs/ML_METHODS.md](docs/ML_METHODS.md).
- Доступность задач и fail-closed: [docs/ML_CAPABILITIES.md](docs/ML_CAPABILITIES.md).
- Фактический `v10` и измеренные метрики: [PROJECT_PASSPORT.md](PROJECT_PASSPORT.md).
- Код train/evaluate/registry: `scripts/train_sensor_failure.py`,
  `packages/prediction/src/forpost_prediction_core/`.

## 6. Где посмотреть безопасность

- Периметр и результаты: [docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md).
- Модель угроз: [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).
- Цепочка data → action и trust boundaries: [docs/SECURITY_BY_DESIGN.md](docs/SECURITY_BY_DESIGN.md).
- Угроза → control → source → test: [docs/SECURITY_EVIDENCE.md](docs/SECURITY_EVIDENCE.md).
- Guards: `scripts/pre-commit-guard.mjs`, `scripts/server-perimeter-guard.mjs`.
- Механизмы: loopback-only, Bearer/RBAC/ABAC, short demo assertions, CSRF,
  origin checks, idempotency, payload/rate limits, SHA-256 manifest и audit ledger.

## 7. Где посмотреть воспроизводимость

```powershell
.\scripts\setup-demo.ps1
npm run verify:submission:fast
npm run verify:submission:full
npm run dev:stack
```

Подробности: [README.md](README.md), [docs/LOCAL_VERIFY.md](docs/LOCAL_VERIFY.md)
и [docs/TEST_PROTOCOL.md](docs/TEST_PROTOCOL.md). Fast suite проверяет
статические controls, full suite добавляет тесты/build/security/load checks.
Verify не читает `data/raw`,
`data/processed` или `ml/models` и не требует внешнего доступа.

## 8. Соответствие ТЗ

[docs/TZ_COMPLIANCE.md](docs/TZ_COMPLIANCE.md) содержит матрицу требований и
экспертскую таблицу «требование → реализация → UI/файл → проверка → ограничение».
Для ML см. № 3, 7, 22, 33 и 57; для сценария диспетчера — № 23, 24, 31 и 60;
для защиты — № 37–42, 51 и 62.

## 9. Что не реализовано

| Направление | Статус | Причина |
| --- | --- | --- |
| Пожарный риск | недоступен | Нет подтверждённых источников и target labels. |
| Несанкционированный доступ | недоступен | Нет подтверждённых источников и target labels. |
| Износ инфраструктуры | недоступен | Нет подтверждённых источников и target labels. |
| Production deployment | не реализован | Нет утверждённых TLS/IdP/SIEM/backup/DB-интеграций. |

## 10. Что важно понимать эксперту

- Proxy ≠ физический отказ датчика.
- Локальные demo-действия ≠ production workflow.
- Simulated topology ≠ реальная GIS-карта.
- Отсутствие источника ≠ synthetic prediction.
- Внутренние release gates ≠ требования ТЗ; измеренные метрики `v10` не скрыты.
