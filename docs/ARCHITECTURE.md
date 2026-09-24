# Архитектура локального стенда «ФОРПОСТ»

## Назначение и границы

Стенд поддерживает решение диспетчера на обезличенных локальных данных. Он не
управляет оборудованием, не отправляет заявки во внешнюю help-desk и не является
промышленным контуром. Единственная обучаемая задача сейчас — proxy прекращения
телеметрии датчика; остальные направления fail-closed недоступны.

## Функциональная схема

```text
data/raw (только машина владельца)
  -> Python connectors -> data/processed/local-situation.json
  -> Next.js /api/local-situation -> React UI

local-situation.json -> causal ML pipeline -> immutable model release
  -> predictions.json + manifest + model-card
  -> FastAPI /api/predictions -> Next.js BFF -> /notifications

/notifications -> demo session + CSRF
  -> решение диспетчера -> hash-chain audit
  -> prediction-derived draft -> SQLite -> /applications
```

Данные в React-компоненты попадают только через `src/data` и route handlers.
UI не читает `data/` и ML-артефакты напрямую и не пересчитывает метрики модели.

## Компоненты

| Компонент | Ответственность | Состояние данных |
| --- | --- | --- |
| `packages/connectors` | строгая нормализация локальных файлов | observed |
| `scripts/build_local_snapshot.py` | ограниченный атомарный снимок | observed |
| `ml` и `packages/prediction` | признаки, temporal split, calibration, gates | derived |
| FastAPI `apps/api` | RBAC/ABAC, валидация ML-релиза, аудит, SQLite demo-операции | observed/derived/simulated |
| Next.js BFF `src/app/api` | same-origin, CSRF, cookies, service credential | без хранения предметных данных |
| React `src/components` | доступное представление и действия оператора | только ответы API |

## Сквозной сценарий прогноза

1. FastAPI выдаёт только экспорт с валидными manifest/model card и контрактом.
2. Центр уведомлений принимает только `validated`/`proxy`, `qualityStatus=passed`
   и непустую вероятность; критичность и время задают порядок.
3. Карточка показывает вероятность, горизонт, версию, факторы, ограничения и
   до пяти последних observed-событий того же канала.
4. Решение требует human-only demo assertion, права диспетчера и CSRF; история
   сохраняется в SQLite и дублируется в audit ledger.
5. После последнего подтверждения или эскалации backend повторно находит
   непросроченный активный прогноз в текущем экспорте и сам
   формирует simulated-черновик: целевой объект, приоритет, действие и срок
   нельзя подменить из браузера. ID связи — SHA-256 от ID прогноза.
6. Повторный запрос возвращает тот же черновик; он хранится в локальной SQLite
   и виден в разделе «Заявки». Более новое отклонение блокирует создание.

## Защитные границы

- Listener доступен только на `127.0.0.1`; LAN/reverse proxy не поддерживаются.
- Чтение BFF использует одноразовый service token; запись — только demo identity.
- Cookies `HttpOnly`, `SameSite=Strict`; mutation-маршруты проверяют Origin и CSRF.
- Контракты и размеры входа ограничены; повреждённые данные дают отказ, а не fallback.
- `data/raw`, `data/processed` и `ml/models` не входят в Git.
- SHA-256 проверяет целостность локального ML-релиза, но не удостоверяет издателя.

## Интеграция и замена компонентов

Контракты BFF отделяют UI от FastAPI. Для промышленной интеграции сохраняются
типы `src/data`, а локальная demo identity заменяется корпоративным IdP; SQLite —
PostgreSQL/неизменяемым аудитом; service-request repository — адаптером help-desk.
До согласования этих контрактов текущие endpoints нельзя публиковать наружу.

Подробности данных: [DATA_MAPPING.md](DATA_MAPPING.md). ML:
[ML_METHODS.md](ML_METHODS.md). Защита: [THREAT_MODEL.md](THREAT_MODEL.md).
