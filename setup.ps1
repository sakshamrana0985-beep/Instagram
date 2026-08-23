# Windows equivalent of setup.sh. In PowerShell, from the project folder:
#
#     .\setup.ps1
#
# If Windows refuses to run it, first run:
#     Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Find-Python {
    # The py launcher can select a version; plain python is whatever is first on PATH.
    foreach ($candidate in @("py -3.13", "py -3.12", "py -3.11", "py", "python3", "python")) {
        $parts = $candidate.Split(" ")
        $cmd = Get-Command $parts[0] -ErrorAction SilentlyContinue
        if ($null -eq $cmd) { continue }
        $exeArgs = @()
        if ($parts.Count -gt 1) { $exeArgs += $parts[1] }
        $probe = $exeArgs + @("-c", "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)")
        & $cmd.Source @probe 2>$null
        if ($LASTEXITCODE -eq 0) { return @{ Exe = $cmd.Source; Args = $exeArgs } }
    }
    return $null
}

$python = Find-Python
if ($null -eq $python) {
    Write-Host "Python 3.11 or newer was not found."
    Write-Host "Install it from https://www.python.org/downloads/ and tick 'Add python.exe to PATH'"
    Write-Host "during setup, then close this window, open PowerShell again, and re-run .\setup.ps1"
    exit 1
}

$pythonArgs = $python.Args
& $python.Exe @pythonArgs --version

if (-not (Test-Path .venv)) {
    Write-Host "Creating an isolated environment (.venv)..."
    $venvArgs = $pythonArgs + @("-m", "venv", ".venv")
    & $python.Exe @venvArgs
}

& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
Write-Host "Installing dependencies (a minute or two the first time)..."
& .\.venv\Scripts\python.exe -m pip install --quiet -e ".[dev]"

Write-Host ""
& .\.venv\Scripts\python.exe scripts\first_run.py @args
