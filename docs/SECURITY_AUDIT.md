# Аудит безопасности и периметра данных

Дата проверки: 18 сентября 2026 года.

## Итог

После исправлений подтверждённых уязвимостей в проверенном исходном коде,
Git-истории и разрешённых runtime-зависимостях не обнаружено. Аудит выполнен
локальными независимыми инструментами без Codex Security. `data/raw` и
`data/processed` не являлись target ни одного сканера и не передавались во
внешние сервисы.

Исправлены четыре проблемы контура:

- Vitest обновлён с уязвимой ветки до `4.1.11`, а coverage-provider закреплён
  на той же исправленной версии;
- уязвимый вложенный PostCSS из Next.js 15 заменён npm override на `8.5.28`;
- HTML-интерфейс Next.js получил глобальные CSP, anti-clickjacking, nosniff,
  referrer и permissions headers;
- Python dependency job больше не падает на собственных editable-пакетах:
  `pip-audit --skip-editable` проверяет стороннее дерево, а код `forpost-*`
  отдельно покрывают Ruff, Bandit, Semgrep и тесты.

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

- Bandit: 4 805 строк Python, 0 находок всех уровней;
- Semgrep: 292 применимых правила из локального набора и профилей TypeScript,
  React, OWASP Top 10 и secrets; 173 versioned-файла, 0 находок;
- Ruff check/format: без замечаний;
- TruffleHog: 580 chunks Git-истории, 0 проверенных и 0 неподтверждённых
  секретов;
- `npm audit --audit-level=low`: 0 уязвимостей;
- clean-room `pip-audit --skip-editable`: 0 известных уязвимостей в сторонних
  runtime-зависимостях, `pip check` — без конфликтов;
- ESLint с security-правилами и TypeScript strict: без ошибок;
- Vitest: 123 теста; Python pytest: 224 теста;
- coverage gate учитывает весь `src` и Git-скрипты и закрепляет фактический
  baseline как неухудшаемый ратчет: 68% statements, 58% branches,
  71% functions и 71% lines.

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
