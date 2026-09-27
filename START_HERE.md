# START HERE — ФОРПОСТ

Этот файл предназначен для эксперта, впервые открывшего репозиторий.

**ФОРПОСТ** — локальный ситуационный центр, который показывает обезличенные
наблюдения, выпускает только проверенный 24-часовой proxy-прогноз риска тишины
телеметрии и оставляет решение диспетчеру.

## Что реально работает

Локальный Next.js/FastAPI-контур, snapshot-адаптер, `sensor_failure` proxy
release `v10`, observed telemetry, объяснение факторов, human-in-the-loop,
audit trail, simulated draft, RBAC/ABAC и проверки безопасности. Три других
направления fail-closed: для них нет подтверждённых источников и target labels.

## Основной маршрут

**наблюдение → прогноз → факторы → observed telemetry → решение → audit → simulated draft**

Откройте `/`, `/sensor-failure`, `/notifications`, `/journals`,
`/applications`, затем `/topology`. Маршрут и ожидаемое поведение кратко
описаны в [README.md](README.md), демонстрация — в
[docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

## Где смотреть UI

`/` — dashboard и observed telemetry; `/sensor-failure` — proxy prediction;
`/notifications` — factors и решение; `/journals` — журнал; `/applications` —
simulated draft; `/topology` — негеографическая структура объектов.

## Где смотреть доказательства

Security-first маршрут: 1) этот файл — контекст, 2) UI и proxy prediction —
разделение факта/прогноза, 3) [Security by Design](docs/SECURITY_BY_DESIGN.md)
— границы decision pipeline, 4) [Security Evidence](docs/SECURITY_EVIDENCE.md)
— конкретный код и проверки, 5) [Threat Model](docs/THREAT_MODEL.md) —
остаточные риски, 6) ML Methods, 7) TZ Compliance.

- Состояние, фактические метрики `v10` и ограничения: [PROJECT_PASSPORT.md](PROJECT_PASSPORT.md).
- Архитектура и поток данных: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- ML-методика, temporal split, calibration и final test: [docs/ML_METHODS.md](docs/ML_METHODS.md).
- Доступность четырёх направлений: [docs/ML_CAPABILITIES.md](docs/ML_CAPABILITIES.md).
- Сверка с ТЗ и способы проверки: [docs/TZ_COMPLIANCE.md](docs/TZ_COMPLIANCE.md).
- Security, data perimeter и аудит: [docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md).
- Security by Design: [docs/SECURITY_BY_DESIGN.md](docs/SECURITY_BY_DESIGN.md).
- Security evidence matrix: [docs/SECURITY_EVIDENCE.md](docs/SECURITY_EVIDENCE.md).
- Тесты и ручный приёмочный маршрут: [docs/TEST_PROTOCOL.md](docs/TEST_PROTOCOL.md).

## Как запустить локально

```powershell
.\scripts\setup-demo.ps1
.\.venv\Scripts\Activate.ps1
npm run dev:stack
```

Затем используйте `npm run verify:submission:fast`; полный локальный pipeline
— `npm run verify:submission:full`. Обе команды работают без доступа к
`data/raw`. Детали безопасной работы с локальными данными — в
[docs/LOCAL_VERIFY.md](docs/LOCAL_VERIFY.md).

## Важные ограничения

Proxy не равен физическому отказу, local demo-действие не является production
workflow, simulated topology не является GIS-картой, а отсутствие источника
не превращается в synthetic prediction.
