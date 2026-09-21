# Аудит безопасности и периметра данных

Дата проверки: 21 сентября 2026 года.

## Итог

После исправлений подтверждённых уязвимостей в проверенном исходном коде и
разрешённых runtime-зависимостях не обнаружено. Аудит выполнен локальными
независимыми инструментами без Codex Security. `data/raw`, `data/processed` и
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
- вся отслеживаемая Git-история на секреты;
- ручная трассировка аутентификации, CSRF, RBAC, BFF proxy, payload limits,
  SQLite-запросов, idempotency и локальных файловых границ.

Локальные исходные и производные данные исключены `.gitignore`, pre-commit,
pre-push и CI perimeter guard. Стандартные Next.js launcher-команды слушают
только `127.0.0.1`; локальный снимок не использует управляемые клиентом
`Host`, `Origin` или `X-Forwarded-For` как аутентификацию.

## Результаты инструментов

- Bandit: 0 находок;
- Semgrep: 2 локальных project-specific правила, 102 цели, 0 находок;
- Ruff check/format: без замечаний;
- TruffleHog: 424 chunks явного allowlist кода и конфигурации, 0 проверенных и 0 неподтверждённых
  секретов;
- полный `npm audit --audit-level=low` и production-only audit: 0 уязвимостей;
- `pip-audit --disable-pip -r requirements-prod.lock`: 0 известных
  уязвимостей, `pip check` — без конфликтов;
- ESLint с security-правилами и TypeScript strict: без ошибок;
- Next.js production build: успешно; Vitest: 132 теста; Python pytest: 272 теста;
- coverage gate учитывает весь `src` и Git-скрипты и закрепляет фактический
  baseline как неухудшаемый ратчет: 69,84% statements, 61,21% branches,
  73,24% functions и 73,27% lines.

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
