# Реестр известных рисков

## R-001 — транзитивные уязвимости PostCSS в Next.js 15.5.25

**Статус:** закрыт 18 сентября 2026 года.
**Источник:** `npm audit --json`.
**Исходно затронутый путь:** `next@15.5.25` → `postcss@8.4.31`.

`npm audit` сообщает **1 high** и **1 moderate** агрегированных уязвимости.
В отчёте отсутствуют CVE-идентификаторы; указаны следующие GitHub Security
Advisory:

- GHSA-qx2v-qp2m-jg93 — XSS при неэкранированном `</style>` в CSS stringify
  (moderate, CWE-79);
- GHSA-6g55-p6wh-862q — чтение произвольного файла через
  контролируемый `sourceMappingURL` (high, CWE-22/CWE-200);
- GHSA-fxqj-rqcc-2cmp — неполное исправление чтения `.map`-файлов
  (moderate, CWE-22/CWE-200);
- GHSA-r28c-9q8g-f849 — path traversal при автозагрузке source map
  (high, CWE-22).

Npm override закрепляет `postcss@8.5.28` для всего дерева, включая Next.js;
`npm ls postcss` подтверждает deduplicated исправленную версию без invalid
узлов. Так сохранено обязательное требование Next.js 15 без уязвимой
транзитивной зависимости.

**Проверка закрытия:** `npm audit --audit-level=low` — 0 уязвимостей;
unit/coverage-тесты, TypeScript strict и production build выполняются на
обновлённом lockfile.
