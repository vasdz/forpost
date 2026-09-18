[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$projectRoot = Split-Path -Parent $PSCommandPath
$temporaryRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$auditEnvironment = Join-Path $temporaryRoot ("forpost-security-audit-" + [guid]::NewGuid().ToString('N'))

function Invoke-Checked {
    param(
        [Parameter(Mandatory)] [string] $Executable,
        [Parameter(ValueFromRemainingArguments)] [string[]] $Arguments
    )

    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Команда завершилась с кодом ${LASTEXITCODE}: $Executable $($Arguments -join ' ')"
    }
}

function Invoke-CheckedWithRetry {
    param(
        [Parameter(Mandatory)] [string] $Executable,
        [Parameter(Mandatory)] [int] $Attempts,
        [Parameter(ValueFromRemainingArguments)] [string[]] $Arguments
    )

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        & $Executable @Arguments
        if ($LASTEXITCODE -eq 0) {
            return
        }
        if ($attempt -lt $Attempts) {
            Start-Sleep -Seconds (2 * $attempt)
        }
    }
    throw "Команда не выполнена после ${Attempts} попыток: $Executable $($Arguments -join ' ')"
}

Push-Location $projectRoot
try {
    Invoke-Checked '.\.venv\Scripts\ruff.exe' 'check' '.'
    Invoke-Checked '.\.venv\Scripts\ruff.exe' 'format' '--check' '.'
    Invoke-Checked '.\.venv\Scripts\bandit.exe' '-r' 'apps' 'packages' 'scripts' '-c' '.bandit.yaml'

    $env:SEMGREP_SEND_METRICS = 'off'
    $env:SEMGREP_ENABLE_VERSION_CHECK = '0'
    Invoke-Checked '.\.venv\Scripts\semgrep.exe' 'scan' '--config' 'semgrep.yml' '--config' 'p/typescript' '--config' 'p/react' '--config' 'p/owasp-top-ten' '--config' 'p/secrets' '--error' '--exclude' 'node_modules' '--exclude' '.next' '--exclude' 'references' 'apps/api' 'packages' 'scripts' 'src' '.github' 'next.config.ts' 'vitest.config.mts' 'package.json' 'pyproject.toml'

    Invoke-CheckedWithRetry 'npm' 3 'audit' '--audit-level=low' '--fetch-timeout=60000' '--fetch-retries=3'
    Invoke-Checked 'trufflehog' 'filesystem' '.github' '.githooks' 'apps/api' 'packages' 'scripts' 'src' 'docs' 'package.json' 'package-lock.json' 'pyproject.toml' 'semgrep.yml' '.gitignore' '--no-verification' '--no-update' '--fail' '--exclude-paths=.trufflehog-exclude'

    Invoke-Checked 'py' '-3.12' '-m' 'venv' $auditEnvironment
    $auditPython = Join-Path $auditEnvironment 'Scripts\python.exe'
    Invoke-Checked $auditPython '-m' 'pip' 'install' '--disable-pip-version-check' '--upgrade' 'pip'
    Invoke-Checked $auditPython '-m' 'pip' 'install' '--disable-pip-version-check' 'pip-audit' 'hatchling' 'editables'
    Invoke-Checked $auditPython '-m' 'pip' 'install' '--disable-pip-version-check' '--no-build-isolation' '-e' '.\packages\domain' '-e' '.\packages\prediction' '-e' '.\packages\connectors' '-e' '.\packages\platform' '-e' '.\apps\api'
    Invoke-Checked $auditPython '-m' 'pip' 'check'
    Invoke-CheckedWithRetry $auditPython 3 '-X' 'utf8' '-m' 'pip_audit' '--skip-editable'
}
finally {
    Pop-Location
    $resolvedAuditEnvironment = [System.IO.Path]::GetFullPath($auditEnvironment)
    $expectedPrefix = Join-Path $temporaryRoot 'forpost-security-audit-'
    if (
        $resolvedAuditEnvironment.StartsWith($expectedPrefix, [System.StringComparison]::OrdinalIgnoreCase) -and
        [System.IO.Directory]::Exists($resolvedAuditEnvironment)
    ) {
        [System.IO.Directory]::Delete($resolvedAuditEnvironment, $true)
    }
}
