#!/usr/bin/env sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repository_root"

if command -v python3 >/dev/null 2>&1; then
  python_command=python3
elif command -v python >/dev/null 2>&1; then
  python_command=python
else
  printf '%s\n' 'Python 3.12+ не найден. Установите Python и повторите запуск.' >&2
  exit 1
fi

python_version=$($python_command -c "import sys; print('.'.join(map(str, sys.version_info[:3])))")
$python_command -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' || {
  printf '%s\n' "Требуется Python 3.12+, найден Python $python_version." >&2
  exit 1
}

command -v node >/dev/null 2>&1 || { printf '%s\n' 'Node.js не найден.' >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { printf '%s\n' 'npm не найден.' >&2; exit 1; }
printf 'Python %s; Node %s; npm %s\n' "$python_version" "$(node --version)" "$(npm --version)"

if [ ! -x .venv/bin/python ]; then
  printf '%s\n' 'Создание .venv...'
  "$python_command" -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --require-hashes -r requirements-prod.lock
.venv/bin/python -m pip install pytest httpx ruff bandit
.venv/bin/python -m pip install --no-build-isolation --no-deps -e ./packages/domain -e ./packages/prediction -e ./packages/connectors -e ./packages/platform -e ./apps/api
.venv/bin/python -m pip check
npm ci --ignore-scripts

printf '%s\n' ''
printf '%s\n' 'Окружение подготовлено. Скрипт не читает data/raw, не создаёт snapshot и не обучает модель.'
printf '%s\n' 'Проверка: npm run verify:submission'
printf '%s\n' 'Запуск:  . .venv/bin/activate && npm run dev:stack'
