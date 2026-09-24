# Протокол проверки локального стенда

## Условия

Проверка выполняется в чистой рабочей копии без публикации портов. Локальные
данные не печатаются и не отправляются во внешние сервисы. Зафиксируйте commit,
версии Node/Python и ОС в отдельном протоколе испытаний.

## Автоматические проверки

```powershell
$env:PATH = "$PWD\.venv\Scripts;$env:PATH"
npm run lint
npm run typecheck
npm test
& .\.venv\Scripts\python.exe -m pytest tests -q
& .\.venv\Scripts\python.exe -m ruff check .
& .\.venv\Scripts\python.exe -m ruff format --check .
& .\.venv\Scripts\python.exe -m bandit -r apps packages scripts -c .bandit.yaml
npm run build
node scripts/pre-commit-guard.mjs
git diff --check
git ls-files -- data
```

Критерий: exit code 0 у каждой команды; `git ls-files -- data` выводит только
`data/README.md`. Предупреждения фиксируются отдельно и не выдаются за успех
соответствующего контроля.

## Проверка нагрузки локального API

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/integration/test_load_check.py -q
& .\.venv\Scripts\python.exe scripts/load_check.py --users 20 --requests-per-user 5
```

Ожидаются `users: 20`, `requests: 100`, `errors: 0` и scope
`local_asgi_read_only_not_sla`. Это не проверка браузера, сети, write-нагрузки,
ML inference или промышленного SLA.

## Ручной приёмочный маршрут №3

| Шаг | Действие | Ожидаемый результат |
| --- | --- | --- |
| 1 | открыть `/notifications` с валидным prediction export | уведомления отсортированы по критичности/времени |
| 2 | открыть карточку | видны объект, вероятность, горизонт, версия, факторы и ограничения |
| 3 | сравнить с телеметрией | показаны только observed-события того же channel ID либо честное отсутствие |
| 4 | проверить рекомендацию | действие совпадает с текущим экспортом и не вычисляется UI |
| 5 | войти как диспетчер ОДС | появляется форма решения, сессия 5 минут |
| 6 | сохранить решение с причиной | отображается подтверждение audit record |
| 7 | создать черновик | backend возвращает derived-from-prediction simulated draft |
| 8 | открыть `/applications` | черновик виден; нет заявления об отправке во внешнюю ИС |

Негативные проверки: чужой Origin, неверный CSRF, лишние поля, неизвестный ID,
повреждённый manifest и отсутствующий экспорт должны завершаться отказом и не
создавать решение/черновик.

## Проверка качества ML

Сверьте статус отчёта, temporal split, purge, calibration и отдельные
validation/test метрики по [ML_METHODS.md](ML_METHODS.md). Serving разрешён
только отдельным валидным prediction export. Целевые gates ТЗ: precision > 0,70,
recall > 0,50, горизонт не менее 24 ч, batch inference менее 5 минут.

## Форма результата

Для каждого пункта фиксируются: дата, commit SHA, исполнитель, команда/шаг,
ожидаемый и фактический результат, статус PASS/FAIL, ссылка на локальный
артефакт без исходных данных. Не переносите реальные данные в отчёт.
