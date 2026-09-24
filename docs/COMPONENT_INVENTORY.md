# Компоненты и библиотеки

Документ перечисляет компоненты, которые действительно входят в локальный
стенд. Точные версии всех прямых и транзитивных зависимостей зафиксированы в
`package-lock.json` и `requirements-prod.lock`; они являются первичными
машиночитаемыми перечнями. Этот обзор не заменяет SBOM и юридическую проверку
лицензий перед промышленной поставкой.

## Компоненты решения

| Компонент | Назначение | Реализация |
| --- | --- | --- |
| Web UI и BFF | интерфейс диспетчера, same-origin маршруты, CSRF/cookie-сессия | Next.js App Router, React, TypeScript |
| API | read-only выдача снимка и ML-экспорта, RBAC/ABAC, demo-операции | FastAPI, Pydantic, SlowAPI |
| Домен | типы объектов, инцидентов, обслуживания и мониторинга | `packages/domain` |
| Коннекторы | строгая локальная нормализация CSV/XLSX и построение снимка | pandas, NumPy, openpyxl |
| ML | point-in-time признаки, temporal split, calibration, gates и registry | scikit-learn, CatBoost, LightGBM, skops |
| Локальные операции | решения, simulated-черновики и hash-chain audit | Python `sqlite3`, `hashlib`, `hmac` |
| Визуализация | графики качества и observed-телеметрии | Apache ECharts, echarts-for-react |

`apps/web` — выведенный из эксплуатации Vite-клиент прежнего прототипа. Он не
является активным пользовательским интерфейсом и не входит в описанный выше
runtime-маршрут.

## Прямые runtime-зависимости

| Контур | Библиотеки |
| --- | --- |
| Web | Next.js, React, React DOM, Zustand, ECharts, echarts-for-react, Framer Motion, Lucide React, date-fns, clsx, tailwind-merge |
| Python API/данные | FastAPI, Uvicorn, Pydantic, SlowAPI, pandas, NumPy, openpyxl, PyYAML, idna, typing-extensions |
| Python ML | scikit-learn, skops, CatBoost, LightGBM |
| Сборка Python-пакетов | Hatchling, editables |

Версии Web-зависимостей фиксированы в корневых `package.json` и
`package-lock.json`. Ограничения прямых Python-зависимостей находятся в
`requirements-prod.in`, а точные версии и SHA-256 дистрибутивов — в
`requirements-prod.lock`. Файлы `pyproject.toml` внутри `apps/` и `packages/`
описывают зависимости отдельных workspace-пакетов.

## Лицензии и поставка

Для нативных ML-кандидатов сохранены полные upstream-тексты лицензий и ссылки в
[`licenses/README.md`](licenses/README.md): CatBoost 1.2.10 — Apache-2.0,
LightGBM 4.7.0 — MIT. Лицензионные файлы остальных библиотек устанавливаются
вместе с их дистрибутивами, но в репозитории пока нет полного отчёта по
транзитивным notices.

Перед промышленной поставкой необходимо сформировать SBOM из обоих lock-файлов,
собрать license notices для всех транзитивных компонентов, проверить
совместимость лицензий и подписать provenance сборки. Отсутствие этих артефактов
зафиксировано как ограничение, а не считается выполненным контролем.
