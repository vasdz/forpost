# ПРОЕКТ: Ситуационный центр АО «Москоллектор»

## Статус
Получены реальные обезличенные данные организаторов: проект переходит из
фазы прототипа в фазу данных. Исходные файлы хранятся только локально в
`data/raw`, не коммитятся и не передаются внешним сервисам.
Стратегия: сохраняем контракт UI и меняем только слой данных — от
синтетического источника к локальным загрузчикам, затем к API.

## Контекст задачи
АО «Москоллектор»: 825 км коллекторов, 19.7 тыс. км кабелей.
Мониторинг сейчас реактивный, много ложных срабатываний.
Нужен веб-сервис с предиктивной ML-моделью прогнозирования аварий.

## 4 направления прогнозирования
1. Отказ датчика (контактные, объёмные, температурные, дымовые, газовые датчики СМВУ)
2. Пожарный риск (температура + дым + корреляция со сварочными работами АРМ-Контроль)
3. Несанкционированный доступ (СКУД, журналы допусков, аномальные паттерны)
4. Износ инфраструктуры (вентшахты, насосы, люки, конструкции)

## Источники данных
- Логи СМВУ за 12+ лет (.xlsx): ID датчика, время, тип события, адрес, результат проверки
- Журналы ОДС: сработок, неисправностей, планы пикетов
- Реестр оборудования ОЭ: фонды по районам, даты ввода, истории ремонтов
- АРМ-Контроль: допуски и заявки (организация, даты, ФИО, тип работ)
- Справочник нормативов и графики ТО/ППР

## Целевые метрики ML (на потом)
Precision > 0.7, Recall > 0.5, горизонт ≥ 24 ч, время прогноза < 5 мин

## Стек
Next.js 15 App Router + TypeScript strict + Tailwind CSS 4 + ECharts +
Framer Motion + Lucide React + Zustand + date-fns.
БД позже: Supabase. API позже: FastAPI или Next.js route handlers.

## Правила разработки
- Комментарии и UI-тексты на русском, идентификаторы на английском
- Код production-ready, без TODO и заглушек
- Все данные в UI идут ТОЛЬКО через слой /src/mocks (сейчас) или API (потом)
- Дизайн строго по docs/SPEC.md
- Доступность: WCAG 2.1 AA + ГОСТ Р 52872-2012

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
