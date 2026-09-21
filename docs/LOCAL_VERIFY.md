# Локальная безопасная проверка

Эти команды предназначены только для локальной рабочей копии. Они не должны
выполняться в CI на машине, где находится `data/`, и не должны перенаправлять
содержимое локального снимка в логи или внешние сервисы.

## Перед началом

1. Проверьте, что Git не отслеживает данные:

   ```powershell
   git check-ignore -v -- data/raw/verification-marker
   git ls-files -- data
   ```

   Первая команда должна назвать правило `/data/*`, а вторая может вывести
   только `data/README.md`. Любой другой путь означает нарушение периметра.

2. Установите versioned hooks после каждого нового clone:

   ```powershell
   npm run hooks:install
   git config --local --get core.hooksPath
   ```

   Ожидаемое значение — `.githooks`. Hooks не защищают от `--no-verify` и не
   заменяют обязательный server-side pre-receive/DLP на Git-хостинге.

3. Администратор Git-хостинга обязан установить server-side guard в каждый
   bare-репозиторий **до первого push с данными**. В `<bare-repo>/hooks/`
   скопируйте `scripts/server-hooks/pre-receive` как `pre-receive`, а
   `scripts/server-perimeter-guard.mjs` и `scripts/pre-commit-guard.mjs` — в
   `<bare-repo>/hooks/forpost-perimeter/`; дайте shell-hook право исполнения.
   Guard отклоняет пути `data/**`, типовые выгрузки/архивы вне `data/`, теги и
   служебные refs. Он должен выполняться под Node.js LTS и проверяться на
   тестовой ветке без данных. Пока администратор не подтвердил установку,
   локальные Git-меры не являются достаточной гарантией периметра.

4. Не запускайте приложение за reverse proxy, в Docker с опубликованным
   портом или на LAN. Команды `npm run dev` и `npm run start` привязаны к
   `127.0.0.1`; это обязательное условие маршрута локального снимка. Route
   Handler намеренно не использует `Host`, `Origin` или forwarded-заголовки
   как доказательство адреса клиента: их задаёт сам запрос. Любая публикация
   listener-а или проксирование этого маршрута является неподдерживаемой
   конфигурацией и запрещена.

## Изолированное окружение

Создайте и обслуживайте Python-окружение из Python 3.12+ в рабочей копии без
данных. Не устанавливайте зависимости в каталог `data/` и не запускайте
внешние сканеры из рабочей копии, где локальный снимок уже создан.

```powershell
$forpostPython = ".\.venv\Scripts\python.exe"
& $forpostPython -m pip install --upgrade pip
& $forpostPython -m pip install --require-hashes -r requirements-prod.lock
& $forpostPython -m pip install pytest httpx ruff bandit semgrep pip-audit
& $forpostPython -m pip install --no-build-isolation --no-deps -e .\packages\domain -e .\packages\prediction -e .\packages\connectors -e .\packages\platform -e .\apps\api
& $forpostPython -m pip check
```

Для первого воспроизводимого развёртывания используйте чистую рабочую копию без
`data/` и создайте `.venv` выбранным Python 3.12+. Не заменяйте существующее
окружение или локальные данные автоматическими скриптами без резервной копии.

## Сборка локального снимка

Запуск допустим только на машине владельца данных и только вручную:

```powershell
& $forpostPython scripts/build_local_snapshot.py
```

Команда пишет производный снимок только внутрь игнорируемого `data/` и выводит
только общее подтверждение. Не добавляйте её в CI, планировщик с внешними
логами или remote execution.

Общий лимит публичного JSON-снимка совпадает с лимитом серверного маршрута.
Если локальная подготовка не укладывается в него, она завершается ошибкой и
сохраняет прежний снимок; не повышайте лимит без отдельной проверки модели
данных и памяти процесса.

## Проверки кода

Выполняйте после установки зависимостей, не передавая `data/` в аргументы
инструментов:

```powershell
npm ci --ignore-scripts
npm run lint
npm run typecheck
npm test
npm run build

& $forpostPython -m pytest tests -q
& $forpostPython -m ruff check .
& $forpostPython -m ruff format --check .
& $forpostPython -m bandit -r apps packages scripts -c .bandit.yaml

$env:SEMGREP_SEND_METRICS = 'off'
$env:SEMGREP_ENABLE_VERSION_CHECK = '0'
semgrep scan --no-git-ignore --config semgrep.yml --error --exclude data --exclude ml/models --exclude node_modules --exclude .next --exclude .venv --exclude references --exclude .git --exclude .idea .

trufflehog filesystem .github .githooks apps/api packages scripts src docs ml/config.yaml requirements-prod.in requirements-prod.lock package.json package-lock.json pyproject.toml semgrep.yml .gitignore --no-verification --no-update --fail --exclude-paths=.trufflehog-exclude
```

Локальный Semgrep использует только `semgrep.yml`. Профили реестра Semgrep
разрешены лишь в CI на чистом checkout, где server-side policy уже исключила
`data/`; они не запускаются на машине с локальным набором.

Локальный TruffleHog получает явный список кода и конфигурации, а не корень
рабочей копии. Так `data/` не может стать его target даже при ошибке правила
исключения; regexp в `.trufflehog-exclude` дополнительно учитывает `/` и `\\`
на разных ОС. Legacy-пакет `apps/web` не входит в локальный скан: его
`node_modules` содержит опубликованные документационные строки, которые дают
ложные срабатывания; он остаётся под проверкой TruffleHog по отслеживаемой
истории в CI и отдельно проверяется своим build.

Для проверки маршрута не выводите JSON-снимок в консоль. После запуска
`npm run dev:stack` можно проверить только статус локального ответа:

```powershell
curl.exe -sS -o NUL -w "%{http_code}\n" http://127.0.0.1:3000/api/local-situation
```

Ответ `200` означает, что локальный снимок доступен. `503` означает только
недоступность снимка и не должен заменяться демонстрационным набором данных.

## Запуск локального стека и demo-сессии

После подготовки окружения и снимка активируйте Python-окружение, чтобы
launcher нашёл нужный `python`, и запустите одну команду:

```powershell
.\.venv\Scripts\Activate.ps1
npm run dev:stack
```

Launcher поднимает Next.js на `127.0.0.1:3000` и FastAPI на
`127.0.0.1:8000`, выдаёт им общий случайный service-token и завершает второй
процесс при остановке первого. На Windows используется `taskkill /PID /T /F`
без оболочки: завершается только созданное launcher дерево, включая worker
Next.js. На Unix сохраняются штатные SIGINT/SIGTERM. Windows-регрессия
`scripts/run-local-stack.windows.test.mjs` ограничена 60 секундами, проверяет
дочерние PID и освобождение 3000/8000; перед ней оба порта должны быть свободны.
Она запускает настоящий Next/FastAPI и тестового detached-потомка Next CLI,
который не завершится сам при выходе родителя; cleanup адресует только их PID.
Тест не завершает чужие процессы по имени или порту. `/health` остаётся `503 not_ready`: запуск
локального стенда не означает готовность защищённого промышленного контура.

Для показа действий диспетчера и панели оценки задайте переменные в той же
PowerShell-сессии **до** `npm run dev:stack`:

```powershell
$env:FORPOST_DEMO_MODE = '1'
$env:FORPOST_DEMO_ACCESS_KEY = python -c "import secrets; print(secrets.token_hex(32))"
$env:FORPOST_DEMO_ASSERTION_SECRET = python -c "import secrets; print(secrets.token_hex(32))"
npm run dev:stack
```

Не печатайте значения переменных и не коммитьте их. Для отчёта оценки откройте
страницу отказов датчиков и в панели качества нажмите «Войти в демо-режим ОДС».
Журнал и наличие инцидентов не требуются. Панель различает `401` (нет сессии)
и `503` (отчёт недоступен), после входа повторяет запрос. При ошибке входа
показывает сообщение и не использует service-token вместо личности.
Для действий в карточке сработки также доступно «Войти как диспетчер ОДС».
Подписанное demo-
утверждение действует 5 минут; BFF использует HttpOnly/SameSite cookies,
проверку origin и CSRF для записи. Это simulated-личность, а не LDAP/AD.
Demo-режим запрещено выставлять в LAN/Интернет, включая reverse proxy.

Решения инцидентов и черновики сохраняются в
`data/processed/demo-operations.sqlite3`. Решение требует причины, проверяет
переход статуса и Idempotency-Key; исправление ссылается на прежнее решение.
Черновик связан с текущим каноническим инцидентом и его каналом/объектом.
Раздел «Заявки» показывает локальные simulated-черновики; внешней отправки,
workflow help-desk и промышленного хранения пока нет. `/api/v1/maintenance`
остаётся недоступным: это отдельный ещё не подключённый контур ТО.

Topology и обычные read-маршруты BFF используют служебную роль ОДС внутри
loopback-стенда. Пользовательский `/api/model-evaluation` требует demo-сессии
и её `VIEW_RISKS`; без сессии ответ `401`. Прямой FastAPI также принимает
валидный service-token для чтения, а human-only запись им запрещена.

## Воспроизводимая проверка 20 пользователей

```powershell
& $forpostPython -m pytest tests/integration/test_load_check.py -q
& $forpostPython scripts/load_check.py --users 20 --requests-per-user 5
```

CLI и тесты используют временный детерминированный минимальный snapshot, пустой
изолированный реестр моделей и dependency override
настоящего ASGI-приложения, сохраняя реальную service-token аутентификацию.
Проверяются ровно 100 запросов от 20 конкурентных сессий, только GET,
неизменность снимка, ошибки 401/503/500, транспортные ошибки, кооперативный
таймаут и ненулевой exit code при отказе. Отдельные тесты запрещают обращения
к рабочим data/model-путям и проверяют восстановление bindings и удаление
временных артефактов даже при исключении.

CLI не читает существующие `data/raw`, `data/processed`, `ml/models`,
не создаёт заявку или SQLite и не требует снимка или отдельно запущенных серверов.
Два маршрута — `/api/availability` и `/api/v1/topology` — чередуются между
пользователями. Все ответы вне 2xx, транспортные ошибки и таймауты считаются
ошибками. Таймаут 10 секунд ограничивает кооперативную ASGI-работу, но не
прерывает блокирующий синхронный код. Одноразовый секрет создаётся внутри
процесса, после проверки прежнее окружение восстанавливается; секрет не выводится.

В stdout выводится один JSON: `users`, `requests`, `errors`, `p95_ms`,
`scope: local_asgi_read_only_not_sla`. p95 — nearest rank `ceil(0.95 * N)`
по длительностям всех запросов, включая ошибки; время измерено `perf_counter`.
Exit 0 возможен только для 20 пользователей, непустого прогона и нуля ошибок.
Повреждение собственного временного snapshot даёт ошибку topology, а не успешный прогон.

Это наблюдение на текущей машине без сети, TLS, Next.js, браузера, настоящих
20 корпоративных личностей и write-нагрузки. Здесь не измеряется ML inference
и не подтверждается SLA. Availability может отвечать `limited` с кодом 200:
успех чтения не доказывает наличие ML, СКУД, ТО или допусков. Runner не
использует ожидаемо недоступные `/health`, prediction/evaluation и maintenance
как критерий успеха; их готовность проверяется отдельно.

## Локальное обучение proxy-модели

Команду можно запускать только на машине владельца данных после проверки
снимка и только с новой, ещё не существующей версией:

```powershell
& $forpostPython scripts/train_sensor_failure.py --version v1
```

Pipeline потоково читает новые годовые партиции до набора непрерывного хвоста,
не печатает строки источника и не публикует частичный результат. Каталог
`ml/models/sensor_failure/v1` появляется атомарно только после прохождения
temporal validation/test, калибровки, quality gates и проверки времени
inference. Провал gate завершается безопасным reason code без model-релиза,
но с отдельным агрегированным `rejected` отчётом оценки. Повторное использование версии запрещено; для
следующего принятого релиза укажите `v2`, `v3` и так далее.

`data/processed/ml-evaluation.json` содержит последний атомарно записанный
отчёт; `GET /api/model-evaluation` и панель качества показывают его независимо
от serving. `horizon_hours` содержит фактический горизонт конфигурации:
строго целое от 1 до 8760 часов, `null` при ошибке конфигурации. Панель
показывает число часов или «Не определён», без подстановки 24 часов.
Старые отчёты без поля не проходят контракт и требуют нового локального запуска
обучения; исходный файл автоматически не переписывается.
У `rejected` нет test-метрик. Валидный отчёт не превращает
`/api/predictions` из `503 pending` в готовый прогноз. Не печатайте JSON отчёта
в общие логи: он локальный, хотя содержит только агрегаты. Ошибка записи
оставляет старый отчёт, поэтому проверяйте дату/версию; уже опубликованный
model-релиз при такой ошибке не откатывается.

`ml/models` игнорируется Git и не должен становиться целью внешнего сканера,
CI, синхронизации или удалённого backup без отдельного согласованного контура.

## Перед передачей кода

```powershell
node scripts/pre-commit-guard.mjs
git diff --cached --name-only
git ls-files -- data
```

В выводе двух последних команд не должно быть путей `data/`, кроме ровно
`data/README.md`. Не передавайте изменения, пока локальный guard или
server-side policy сообщает о нарушении.
