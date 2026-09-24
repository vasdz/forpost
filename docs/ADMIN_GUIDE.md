# Руководство администратора локального стенда

## Поддерживаемый контур

Требуются Node.js LTS, npm и Python 3.12+. Проверенный режим — локальная машина
Windows с binding `127.0.0.1`. Linux-команды разработки допустимы, но production
deployment, TLS, systemd, backup/RTO и корпоративный IdP пока не аттестованы.

## Чистая установка

```powershell
npm ci --ignore-scripts
py -3.12 -m venv .venv
$forpostPython = ".\.venv\Scripts\python.exe"
& $forpostPython -m pip install --upgrade pip
& $forpostPython -m pip install --require-hashes -r requirements-prod.lock
& $forpostPython -m pip install --no-build-isolation --no-deps -e .\packages\domain -e .\packages\prediction -e .\packages\connectors -e .\packages\platform -e .\apps\api
npm run hooks:install
```

Для тестовых и security-инструментов выполните дополнительные команды из
[LOCAL_VERIFY.md](LOCAL_VERIFY.md). Не запускайте внешние сканеры по `data/`.

## Данные и запуск

```powershell
$forpostPython = ".\.venv\Scripts\python.exe"
& $forpostPython scripts/build_local_snapshot.py
$env:FORPOST_DEMO_MODE = '1'
$env:FORPOST_DEMO_ACCESS_KEY = python -c "import secrets; print(secrets.token_hex(32))"
$env:FORPOST_DEMO_ASSERTION_SECRET = python -c "import secrets; print(secrets.token_hex(32))"
.\.venv\Scripts\Activate.ps1
npm run dev:stack
```

Открывайте только `http://127.0.0.1:3000`. Launcher сам создаёт общий временный
`FORPOST_API_SERVICE_TOKEN` для Next.js и FastAPI. Не фиксируйте секреты в `.env`,
Git, журнале терминала или снимках экрана.

Опциональные параметры: `FORPOST_LOCAL_SNAPSHOT` меняет путь снимка для Next.js;
`FORPOST_BACKEND_URL` и `FORPOST_API_SERVICE_TOKEN` нужны при раздельном локальном
запуске. Такой запуск обязан сохранить loopback и согласованный токен.

## Проверка готовности

```powershell
curl.exe -sS -o NUL -w "%{http_code}\n" http://127.0.0.1:3000/api/local-situation
git ls-files -- data
```

Для снимка ожидается `200`; `503` нельзя маскировать fixtures. FastAPI `/health`
намеренно возвращает `503 not_ready`, пока нет промышленного защищённого контура.
В Git допустим только `data/README.md`.

## Хранилища и восстановление

- Снимок: `data/processed/local-situation.json`, пересобирается вручную из raw.
- Demo-операции: `data/processed/demo-operations.sqlite3`.
- ML-релизы: `ml/models/<task>/vN`, версии неизменяемы.
- Отчёт оценки: `data/processed/ml-evaluation.json`.

Автоматических копий и подтверждённого RTO нет. Перед обслуживанием остановите
стек и создайте согласованную локальную копию `data/processed` и `ml/models` в
защищённом контуре владельца; не переносите её в Git или облако.

## Эксплуатационные проверки

Используйте [TEST_PROTOCOL.md](TEST_PROTOCOL.md). Логи не должны содержать тела
снимков, токены или строки raw. При `503` проверяйте наличие/права файлов и
валидность контрактов; не расширяйте лимиты и не отключайте fail-closed проверки.

## Известные ограничения

Нет TLS termination, AD/LDAP/MFA, PostgreSQL, внешнего help-desk, SIEM,
мониторинга SLO, автоматического backup и disaster recovery. Поэтому стенд нельзя
экспонировать в LAN/Интернет или использовать как промышленную систему.
