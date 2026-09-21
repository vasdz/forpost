# Аудит безопасности и периметра данных

Дата проверки: 21 сентября 2026 года.

## Итог

Контрольный прогон после завершающих исправлений выполнен на `ad4b64d`.
Перечисленные ниже проверки не выявили находок в проверенном исходном коде
и известных уязвимостей в проверенных зависимостях. Это результат заданного
периметра и набора инструментов, а не доказательство отсутствия всех уязвимостей.
Аудит выполнен локальными независимыми инструментами без Codex Security.
`data/raw`, `data/processed` и
`ml/models` не являлись target ни одного сканера и не передавались во внешние
сервисы.

К ранее закрытым supply-chain и browser-hardening проблемам добавлены:

- Vitest обновлён с уязвимой ветки до `4.1.11`, а coverage-provider закреплён
  на той же исправленной версии;
- уязвимый вложенный PostCSS из Next.js 15 заменён npm override на `8.5.28`;
- HTML-интерфейс Next.js получил глобальные CSP, anti-clickjacking, nosniff,
  referrer и permissions headers;
- Python dependency job больше не падает на собственных editable-пакетах:
  `pip-audit` проверяет отдельный hash-pinned production lock, а код
  `forpost-*` отдельно покрывают Ruff, Bandit, Semgrep и тесты;
- `data/**` и `ml/models/**` одновременно закрыты `.gitignore`, локальным
  guard, server-side guard и CI-периметром;
- локальный ML-релиз публикуется только атомарно после temporal validation/test,
  калибровки, проверки baseline и метрик. Последний реальный запуск не прошёл
  validation quality gate, поэтому небезопасный `v1` намеренно не создан.

## Проверенный периметр

- TypeScript/React/Next.js: `src`, конфигурация, build- и Git-скрипты;
- Python/FastAPI: `apps/api`, `packages`, `scripts`;
- GitHub Actions, hooks и perimeter guards;
- npm production/dev dependency graph;
- чистая временная Python 3.12-среда с editable-пакетами проекта;
- явный allowlist отслеживаемого кода и конфигурации для проверки секретов;
- ручная трассировка аутентификации, CSRF, RBAC, BFF proxy, payload limits,
  SQLite-запросов, idempotency и локальных файловых границ.

Локальные исходные и производные данные исключены `.gitignore`, pre-commit,
pre-push и CI perimeter guard. Стандартные Next.js launcher-команды слушают
только `127.0.0.1`; локальный снимок не использует управляемые клиентом
`Host`, `Origin` или `X-Forwarded-For` как аутентификацию.

## Результаты инструментов

- Bandit: 6941 строка кода, 0 находок;
- Semgrep: 292 правила, 195 отслеживаемых Git-целей, 0 находок;
- Ruff check: без замечаний; format check: 112 файлов уже отформатированы;
- TruffleHog: 459 chunks явного allowlist кода и конфигурации, 0 секретов;
- `npm audit`: 0 уязвимостей;
- чистая временная Python-среда: `pip check` — без конфликтов,
  `pip-audit` — без известных уязвимостей. Собственные editable-пакеты проекта
  пропущены dependency-аудитором; их исходники проверены статическими
  анализаторами и тестами. Это не сканирование содержимого model-артефактов;
- ESLint с security-правилами и TypeScript strict: без ошибок;
- Next.js production build: успешно, сгенерированы 14 страниц;
- Vitest: 188 тестов в 33 файлах, успешно;
- Python pytest: 377 тестов, успешно; два upstream deprecation warnings
  относятся к Starlette/httpx и anyio BlockingPortal;
- автономный `scripts/load_check.py`: 20 пользователей, 100 GET-запросов,
  0 ошибок, p95 89,686 мс на текущей машине.

Load runner использует собственный временный минимальный снимок и пустой
изолированный реестр моделей; рабочие каталоги данных не читаются. Запросы
выполняются внутри одного ASGI-процесса без сети, TLS, Next.js, браузера,
корпоративных пользователей, ML inference и write-нагрузки. Это локальное
наблюдение (`local_asgi_read_only_not_sla`), не подтверждение промышленного SLA.

CI coverage gate остаётся настроенным для `src` и Git-скриптов; свежие
проценты покрытия в этом контрольном отчёте не приводятся.

`run_security_audit.ps1` воспроизводит аудит с явным списком директорий без
`data`: Ruff, Bandit, Semgrep, npm audit, TruffleHog и clean-room pip-audit.
Временная Python-среда создаётся в системном каталоге temp и удаляется только
после проверки канонического безопасного префикса пути.

## Защитные свойства реализации

- FastAPI docs/OpenAPI отключены; API fail-closed при отсутствии доверенной
  идентификации;
- серверный service token даёт только read-only субъект и не допускается для
  человеческих write-операций;
- demo-режим включается только явными переменными окружения, выдача assertion
  ограничена loopback, секреты имеют минимальную длину и сравниваются
  constant-time;
- BFF хранит assertion в `HttpOnly`, `SameSite=Strict` cookie, write-маршруты
  требуют same-origin и совпадающий CSRF token;
- backend URL принимается только как чистый `http` loopback origin, пути API
  проходят allowlist-проверку, ответы обязаны быть JSON;
- Pydantic и BFF одновременно ограничивают схему, длину и тип request body;
- SQLite использует параметризованные запросы, транзакции, foreign keys,
  idempotency keys и цепочку хешей audit log;
- CSP запрещает object/embed и framing; production не разрешает
  `unsafe-eval`. `unsafe-inline` для script/style сохранён из-за механики
  hydration Next.js 15, поэтому пользовательский HTML нигде не рендерится.

## Остаточные архитектурные границы

Это безопасный локальный demo-контур, а не завершённый промышленный контур
КИИ. Для сетевого production-развёртывания обязательны внешний TLS reverse
proxy, корпоративный IdP/LDAP/AD с отзывом сессий и MFA, централизованный
неизменяемый SIEM-аудит, секрет-хранилище, backup/restore и server-side
pre-receive/DLP. До их подключения приложение должно оставаться на loopback;
demo identity и локальный SQLite не должны публиковаться в LAN или Интернет.
