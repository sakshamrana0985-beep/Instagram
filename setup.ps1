# Windows equivalent of setup.sh. In PowerShell, from the project folder:
#
#     .\setup.ps1
#
# If Windows refuses to run it, first run:
#     Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Get-Command py -ErrorAction SilentlyContinue
if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if ($null -eq $python) {
    Write-Host "Python is not installed. Get it from https://www.python.org/downloads/ (tick 'Add to PATH')."
    exit 1
}

if (-not (Test-Path .venv)) {
    Write-Host "Creating an isolated environment (.venv)..."
    & $python.Source -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
Write-Host "Installing dependencies (a minute or two the first time)..."
& .\.venv\Scripts\python.exe -m pip install --quiet -e ".[dev]"

Write-Host ""
& .\.venv\Scripts\python.exe scripts\first_run.py @args
