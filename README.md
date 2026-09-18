# ФОРПОСТ — ситуационный центр АО «Москоллектор»

ФОРПОСТ — веб-сервис поддержки диспетчерских решений для инженерных
коллекторов Москвы. Платформа показывает только подтверждённые обезличенные
наблюдения из локального снимка и не выдаёт их за прогноз, рекомендацию или
диагноз.

## Статус

Сейчас готов защищённый платформенный контур: интерфейс Next.js, локальный
адаптер обезличенных данных, fail-closed FastAPI, проверка Bearer-схемы,
RBAC-модель, аудит целостности, тесты и CI-гейты. Реальные прогнозы появятся
только после передачи ML-командой согласованного `docs/API_CONTRACT.md` и
валидированных артефактов. Пока контракт и артефакты отсутствуют, прогнозные
маршруты и страницы честно сообщают о недоступности, не генерируя
демонстрационные значения.

## Архитектура

```text
Локальные обезличенные источники (data/raw, не в Git)
    -> connectors / build_local_snapshot.py
    -> ограниченный data/processed/local-situation.json (локально)
    -> GET /api/local-situation (Next.js, no-store, только listener 127.0.0.1)
    -> React UI + Zustand timeline + доступные таблицы и графики

Внешний ML-контур (зона ML-команды)
    -> docs/API_CONTRACT.md + predictions.json / REST API
    -> GET /api/predictions: read-only импорт JSON-экспортов
    -> UI: probability, horizon, factors, решение диспетчера

Клиент / интеграции
    -> FastAPI /api/v1 (Bearer schema -> доверенный IdP -> RBAC)
    -> audit ledger -> в будущем неизменяемое внешнее хранилище
```

Границы намеренные: UI не читает `data/` напрямую; connectors не вычисляют
прогнозы; платформа не изменяет файлы в `ml/` или `models/`; внешние
интеграции пока read-only и fail-closed.

## Быстрый локальный запуск

1. Создайте Python-окружение и установите зависимости по
   [docs/LOCAL_VERIFY.md](docs/LOCAL_VERIFY.md). Не выполняйте внешние сканеры
   из рабочей копии с реальными данными.
2. На машине владельца данных вручную соберите ограниченный снимок:

   ```powershell
   & .\.venv\Scripts\python.exe scripts/build_local_snapshot.py
   ```

3. Установите frontend-зависимости и запустите UI:

   ```powershell
   npm ci --ignore-scripts
   npm run dev
   ```

`npm run dev` и `npm run start` запускают Next.js только на `127.0.0.1`.
Публикация порта, reverse proxy и LAN не поддерживаются для локального снимка.

## Данные и безопасность

- В Git допускается только [data/README.md](data/README.md); `data/raw` и
  `data/processed` игнорируются и блокируются guard-ом.
- Установите local Git hooks после clone: `npm run hooks:install`.
- CI проверяет периметр до остальных jobs на каждом push и pull request.
- Для фактической защиты Git-хостинга администратор обязан установить
  `pre-receive` из `scripts/server-hooks/`; порядок установки и проверок — в
  [docs/LOCAL_VERIFY.md](docs/LOCAL_VERIFY.md).
- API не принимает роли из клиентских заголовков. Отсутствующий или неверный
  Bearer-заголовок получает `401`; корректную схему без доступного IdP — `503`.

## Известные риски

`npm audit --omit=dev` выявляет 1 high и 1 moderate в транзитивном
`postcss@8.4.31` из `next@15.5.25`. Для устранения npm предлагает мажорное
обновление Next.js до 16.3.5. В текущем локальном профиле снижающими мерами
служат listener `127.0.0.1` и отсутствие обработки пользовательского CSS;
обновление назначено на период после хакатона. Полный перечень advisory,
обоснование и план — в [RISK_REGISTER.md](docs/RISK_REGISTER.md).

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
```

Полный безопасный порядок, включая Semgrep и TruffleHog, зафиксирован в
[docs/LOCAL_VERIFY.md](docs/LOCAL_VERIFY.md).

## Документация

- [SPEC.md](docs/SPEC.md) — продуктовые и UI-границы.
- [DATA_MAPPING.md](docs/DATA_MAPPING.md) — контракт локального снимка и
  соответствие Приложению 1 ТЗ.
- [TZ_COMPLIANCE.md](docs/TZ_COMPLIANCE.md) — честная построчная сверка с ТЗ.
- [SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md) — защита данных и ограничения.
- [DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) — безопасный пятиминутный показ.
- [ROADMAP.md](docs/ROADMAP.md) — этапы до промышленного контура.

## Передача от ML-команды

`GET /api/predictions` уже read-only читает корректные
`ml/models/<case>/v<N>/predictions.json` и возвращает `503` с `pending`, пока
экспортов нет. Платформенный слой не обучает модели и не дублирует inference.
После передачи и согласования `docs/API_CONTRACT.md` следующая работа —
контрактные тесты полей, REST-клиент и UI-поток верификации.
