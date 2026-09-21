# ФОРПОСТ — ситуационный центр АО «Москоллектор»

ФОРПОСТ — веб-сервис поддержки диспетчерских решений для инженерных
коллекторов Москвы. Платформа показывает только подтверждённые обезличенные
наблюдения из локального снимка и результаты проверенного ML-релиза с явным
уровнем доказательности. Proxy прекращения телеметрии не выдаётся за
подтверждённую поломку, рекомендацию или диагноз.

## Статус

Сейчас готов защищённый локальный контур: интерфейс Next.js, адаптер
обезличенных данных, fail-closed FastAPI, Bearer/RBAC, аудит целостности,
тесты и CI-гейты. Локальный pipeline может обучить только
`sensor_failure` по слабой метке `silence_horizon_proxy`; релиз появляется лишь
после temporal holdout, отдельной калибровки и строгих gates
`precision > 0.70` и `recall > 0.50`. Пожарный риск, доступ и износ остаются
недоступными до появления подтверждённых источников и не заменяются
демонстрационными значениями.

Реализованы условная схема подтверждённой иерархии, локальные demo-решения
диспетчера и черновики заявок в SQLite. Отдельная панель качества показывает
отчёт оценки даже при отклонённом релизе; наличие отчёта не разрешает выдачу
прогнозов. Это локальный стенд, а не промышленная интеграция с help-desk или AD.

## Архитектура

```text
Локальные обезличенные источники (data/raw, не в Git)
    -> connectors / build_local_snapshot.py
    -> ограниченный data/processed/local-situation.json (локально)
    -> GET /api/local-situation (Next.js, no-store, только listener 127.0.0.1)
    -> React UI + Zustand timeline + доступные таблицы и графики

Локальный ML-контур (data не покидает машину владельца)
    -> causal features -> temporal split/purge -> holdout calibration
    -> ml/models/sensor_failure/vN: Skops + model card + SHA-256 manifests
    -> GET /api/predictions: read-only проверка и импорт proxy-экспорта
    -> UI: evidence tier, probability, horizon, глобальные факторы, решение

Локальный браузер -> Next.js BFF -> FastAPI /api/v1
    -> service-token для чтения / короткая demo-сессия для действий
    -> RBAC/ABAC -> demo-решения и черновики в локальной SQLite
    -> audit ledger -> в будущем неизменяемое внешнее хранилище

train_sensor_failure.py -> data/processed/ml-evaluation.json
    -> GET /api/model-evaluation -> пользовательская demo-сессия BFF
    -> панель качества: rejected/published, validation/test отдельно
```

Границы намеренные: UI не читает `data/` напрямую; connectors не вычисляют
прогнозы; только локальная training-команда создаёт новую неизменяемую версию
в `ml/models`; API и внешние интеграции читают её read-only и fail-closed.

## Быстрый локальный запуск

1. Создайте Python-окружение и установите зависимости по
   [docs/LOCAL_VERIFY.md](docs/LOCAL_VERIFY.md). Не выполняйте внешние сканеры
   из рабочей копии с реальными данными.
2. На машине владельца данных вручную соберите ограниченный снимок:

   ```powershell
   & .\.venv\Scripts\python.exe scripts/build_local_snapshot.py
   ```

3. При необходимости создайте первый локальный proxy-релиз. Команда сама
   отменит публикацию, если temporal holdout не прошёл gates:

   ```powershell
   & .\.venv\Scripts\python.exe scripts/train_sensor_failure.py --version v1
   ```

4. Установите frontend-зависимости и запустите локальный стек:

   ```powershell
   npm ci --ignore-scripts
   .\.venv\Scripts\Activate.ps1
   npm run dev:stack
   ```

`npm run dev:stack` запускает FastAPI на `127.0.0.1:8000` и Next.js только на
`127.0.0.1`; им передаётся общий случайно сгенерированный service token. При
остановке одного процесса launcher завершает второй; на Windows завершает
всё принадлежащее ему дерево через `taskkill /PID /T /F`, включая worker Next.js,
на Unix передаёт штатные сигналы. `npm run dev` и `npm run
start` запускают только Next.js на `127.0.0.1`. Публикация порта, reverse proxy
и LAN не поддерживаются для локального снимка.

Для demo-действий и пользовательской панели оценки перед запуском задайте
режим и временные секреты по [LOCAL_VERIFY.md](docs/LOCAL_VERIFY.md), затем
в панели качества на странице отказов датчиков нажмите «Войти в демо-режим ОДС».
Наличие сработок или посещение журнала не требуется; после входа отчёт загружается
повторно. `401` означает необходимость входа, `503` — недоступность отчёта.
Сессия действует 5 минут и не является корпоративной авторизацией.
Demo-режим запрещено публиковать в LAN или Интернет.

«Схема объектов» показывает GeoJSON `MultiLineString` по реальной иерархии с
условными координатами (`simulated`), SVG и табличной альтернативой. Географии
и координат Москвы здесь нет. В «Журналах наблюдений» можно записать решение с
причиной и создать локальный черновик, который виден в «Заявках»; во внешнюю
систему он не отправляется.

## Данные и безопасность

- В Git допускается только [data/README.md](data/README.md); `data/raw` и
  `data/processed` игнорируются и блокируются guard-ом.
- Установите local Git hooks после clone: `npm run hooks:install`.
- CI проверяет периметр до остальных jobs на каждом push и pull request.
- Для фактической защиты Git-хостинга администратор обязан установить
  `pre-receive` из `scripts/server-hooks/`; порядок установки и проверок — в
  [docs/LOCAL_VERIFY.md](docs/LOCAL_VERIFY.md).
- API не принимает роли из клиентских заголовков. Отсутствующая Bearer-схема
  получает `401`; настроенный service-token даёт локальному BFF роль ОДС для
  чтения, но не право human-only записи. Demo-утверждения проверяются отдельно.
  При отсутствии настроенного доверенного механизма API отвечает `503`.
- BFF-чтение topology/availability/прогнозов/черновиков использует service-token
  внутри loopback-стенда. `/api/model-evaluation` в браузере требует собственной
  demo-сессии и передаёт её роль в API. Это ещё не общая корпоративная авторизация.

## Известные риски

Главные незакрытые границы — отсутствие криптографической подписи ML-релиза,
SBOM и доверенного внутреннего registry, внешнего неизменяемого аудита,
корпоративного IdP/MFA и защищённого сетевого deployment. Локальный SHA-256 manifest
обнаруживает изменение артефакта, но не удостоверяет издателя. Модель угроз и
принятые меры описаны в [THREAT_MODEL.md](docs/THREAT_MODEL.md), результаты
последнего инструментального прогона — в
[SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md).

## Проверки

```powershell
npm run lint
npm run typecheck
npm test
npm run build

py -m pytest tests -q
py -m ruff check .
py -m ruff format --check .
py -m bandit -r apps packages scripts -c .bandit.yaml
py scripts/load_check.py --users 20 --requests-per-user 5
```

Последняя команда создаёт собственный временный детерминированный минимальный
снимок и пустой реестр моделей, не читая `data/raw`, `data/processed` или
`ml/models`. Временные артефакты удаляются, bindings и окружение восстанавливаются.
Настоящий FastAPI в одном процессе ASGI обслуживает 20 конкурентных сессий,
100 GET-запросов к topology и
availability. JSON содержит `users`, `requests`, `errors`, `p95_ms` и явную
пометку `local_asgi_read_only_not_sla`. Exit 0 означает ровно 20 пользователей
без ошибок. Это проверка текущей машины, без браузера, Next.js, сети, TLS,
корпоративных пользователей, ML inference и write-нагрузки; промышленный SLA
ею не подтверждается.

Полный безопасный порядок, включая Semgrep и TruffleHog, зафиксирован в
[docs/LOCAL_VERIFY.md](docs/LOCAL_VERIFY.md).

## Документация

- [SPEC.md](docs/SPEC.md) — продуктовые и UI-границы.
- [DATA_MAPPING.md](docs/DATA_MAPPING.md) — контракт локального снимка и
  соответствие Приложению 1 ТЗ.
- [ML_CAPABILITIES.md](docs/ML_CAPABILITIES.md) — доступность четырёх задач и
  evidence tiers.
- [ML_METHODS.md](docs/ML_METHODS.md) — temporal-методика, gates и артефакты.
- [TZ_COMPLIANCE.md](docs/TZ_COMPLIANCE.md) — честная построчная сверка с ТЗ.
- [SECURITY.md](docs/SECURITY.md) — политика безопасной эксплуатации.
- [THREAT_MODEL.md](docs/THREAT_MODEL.md) — цепочка атак, MITRE ATT&CK и риски.
- [PRIVACY.md](docs/PRIVACY.md) — минимизация и локальный периметр данных.
- [SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md) — защита данных и ограничения.
- [DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) — безопасный пятиминутный показ.
- [ROADMAP.md](docs/ROADMAP.md) — этапы до промышленного контура.

## Локальный ML-релиз

На машине владельца данных команда `scripts/train_sensor_failure.py` читает
локальные журналы, выбирает модель без доступа к финальному test и атомарно
публикует `ml/models/sensor_failure/vN`. `GET /api/predictions` read-only
проверяет схему, evidence tier, model card и SHA-256; при отсутствии
доверенного экспорта возвращает `503 pending`. Подробный безопасный порядок —
в [LOCAL_VERIFY.md](docs/LOCAL_VERIFY.md).
