# Каталог API локального стенда

Все browser endpoints расположены на `http://127.0.0.1:3000`, отвечают без
кэширования и проксируют или нормализуют локальный FastAPI. Форматы строго
валидируются. Документ перечисляет реализованный публичный для UI контракт, а
не обещание будущего production API.

## Чтение

| Метод и путь BFF | Назначение | Успех | Недоступность |
| --- | --- | --- | --- |
| `GET /api/local-situation` | ограниченный снимок событий/каналов/объектов | 200 | 503 |
| `GET /api/availability` | доступность источников | 200 | 401/503 |
| `GET /api/topology` | условный GeoJSON объектов | 200 | 401/503 |
| `GET /api/predictions` | текущий проверенный ML-экспорт | 200 | 503 pending |
| `GET /api/model-evaluation` | агрегированный отчёт качества | 200 | 401/503 |
| `GET /api/incidents/{sha256}/decisions` | история решений по сработке | 200 | 404/503 |
| `GET /api/service-request-drafts` | локальные simulated-черновики | 200 | 401/503 |
| `GET /api/demo-session` | состояние browser demo-сессии | 200 | — |

`model-evaluation` требует пользовательскую demo-сессию. Остальные read BFF,
кроме локального снимка, используют внутренний service credential; FastAPI всё
равно выполняет permission checks.

## Изменения состояния

Все POST требуют same-origin запрос. После входа клиент передаёт
`X-Forpost-CSRF`; identity находится только в HttpOnly cookie.

### `POST /api/demo-session`

Тело: `{"profile":"central-dispatcher"}`. Допустимы также
`district-dispatcher`, `technician`, `admin`. Успех `201` устанавливает cookies
на 5 минут и возвращает CSRF. Профили имеют `simulated` provenance.

### `POST /api/predictions/{id}/decisions`

Тело содержит только `decision` (`confirmed|rejected|escalated`) и `reason`
длиной 3–1000 символов. FastAPI повторно проверяет наличие ID в текущем
валидном экспорте и пишет audit record. Успех `201`:
`status`, `prediction_id`, `audit_record_id`.

### `POST /api/predictions/{id}/service-request-drafts`

Тело — пустой JSON-объект. Маршрут доступен human-only центральному диспетчеру
после последнего решения `confirmed` или `escalated`. Более новое отклонение,
закрытый статус и истёкший горизонт блокируют операцию. FastAPI повторно читает прогноз и выводит
из него `targetId`, `priority`, `recommendedAction` и `dueAt`; UI не задаёт эти
поля. `incidentId` — стабильный SHA-256 от ID прогноза. Успех `201` возвращает
полный `ServiceRequestDraft` с `provenance: simulated`; безопасный retry
возвращает тот же черновик, не создавая дубль.

### `POST /api/incidents/{sha256}/decisions`

Тело: `status`, `reason`, необязательный `correctsDecisionId`; нужен уникальный
`Idempotency-Key`. Используется для observed-сработок, не для ML-прогнозов.

### `POST /api/service-request-drafts`

Тело: `incidentId`, `targetId`, `category`, `priority`, `recommendedAction`,
`dueAt`. Backend проверяет, что observed-инцидент и target связаны. Используется
карточкой сработки; прогнозы используют специализированный endpoint выше.

## Общие ошибки

`401` — нет identity; `403` — permission/Origin/CSRF; `404` — текущая сущность
не найдена; `409` — конфликт записи; `413` — размер; `415` — Content-Type;
`422` — схема/бизнес-инвариант; `429` — rate limit; `503` — источник или
защищённый механизм не настроен. Клиент обязан сохранять отказ и не подставлять
mock/fallback значения.
