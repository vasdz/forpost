[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

function Get-PythonInvocation {
  if (Get-Command py -ErrorAction SilentlyContinue) {
    return @{ Command = 'py'; Arguments = @('-3.12') }
  }
  if (Get-Command python -ErrorAction SilentlyContinue) {
    return @{ Command = 'python'; Arguments = @() }
  }
  throw 'Python 3.12+ не найден. Установите Python и повторите запуск.'
}

$pythonInvocation = Get-PythonInvocation
$pythonCommand = $pythonInvocation.Command
$pythonArguments = $pythonInvocation.Arguments
$pythonVersion = & $pythonCommand @pythonArguments -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
if ([version]$pythonVersion -lt [version]'3.12') {
  throw "Требуется Python 3.12+, найден Python $pythonVersion."
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  throw 'Node.js не найден. Установите поддерживаемый Node.js LTS и повторите запуск.'
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  throw 'npm не найден. Переустановите Node.js LTS и повторите запуск.'
}

Write-Host "Python $pythonVersion; Node $(node --version); npm $(npm --version)"

$venvPython = Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
  Write-Host 'Создание .venv...'
  & $pythonCommand @pythonArguments -m venv (Join-Path $PSScriptRoot '..\.venv')
}

if (-not (Test-Path $venvPython)) {
  throw 'Не удалось создать .venv.'
}

Push-Location (Join-Path $PSScriptRoot '..')
try {
  & $venvPython -m pip install --upgrade pip
  & $venvPython -m pip install --require-hashes -r requirements-prod.lock
  & $venvPython -m pip install pytest httpx ruff bandit
  & $venvPython -m pip install --no-build-isolation --no-deps -e ./packages/domain -e ./packages/prediction -e ./packages/connectors -e ./packages/platform -e ./apps/api
  & $venvPython -m pip check
  npm ci --ignore-scripts
} finally {
  Pop-Location
}

Write-Host ''
Write-Host 'Окружение подготовлено. Скрипт не читает data/raw, не создаёт snapshot и не обучает модель.'
Write-Host 'Проверка: npm run verify:submission'
Write-Host 'Запуск:  .\.venv\Scripts\Activate.ps1; npm run dev:stack'
