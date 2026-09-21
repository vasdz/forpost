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
`npm run dev` можно проверить только статус локального ответа:

```powershell
curl.exe -sS -o NUL -w "%{http_code}\n" http://127.0.0.1:3000/api/local-situation
```

Ответ `200` означает, что локальный снимок доступен. `503` означает только
недоступность снимка и не должен заменяться демонстрационным набором данных.

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
inference. Провал любого gate завершается сообщением без числовых данных
выгрузки и без артефакта. Повторное использование версии запрещено; для
следующего принятого релиза укажите `v2`, `v3` и так далее.

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
