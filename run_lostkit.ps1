$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($root)) {
    $root = '.'
}

$venvPython = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    throw "Virtual environment not found at '$venvPython'. Run `py -3.11 -m venv .venv` from the project root first."
}

Write-Host "Launching LostKit with $venvPython"
Push-Location $root
try {
    & $venvPython 'main.py' @Args
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
