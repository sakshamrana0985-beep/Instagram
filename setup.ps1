# Windows setup. In PowerShell, from the project folder:
#
#     .\setup.ps1
#
# If Windows refuses to run it:
#     Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
#
# Deliberately does NOT use $ErrorActionPreference = "Stop": pip and the py
# launcher both write ordinary progress and warnings to stderr, and under Stop
# PowerShell turns any of that into a fatal error. Exit codes are checked
# explicitly instead.
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

function Test-PythonVersion {
    param([string]$Exe, [string[]]$PrefixArgs)

    $probe = @($PrefixArgs) + @("-c", "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)")
    try {
        $null = & $Exe @probe 2>&1
    } catch {
        return $false
    }
    return ($LASTEXITCODE -eq 0)
}

function Find-Python {
    # Ordered best-first. "py" with no version argument uses whatever the
    # launcher considers current, which is what a fresh install leaves behind.
    $candidates = @(
        @{ Name = "py";      Args = @() },
        @{ Name = "py";      Args = @("-3") },
        @{ Name = "python";  Args = @() },
        @{ Name = "python3"; Args = @() }
    )

    foreach ($candidate in $candidates) {
        $cmd = Get-Command $candidate.Name -ErrorAction SilentlyContinue
        if ($null -eq $cmd) { continue }

        # The Microsoft Store alias is a stub that only opens the Store.
        if ($cmd.Source -like "*\WindowsApps\*") { continue }

        if (Test-PythonVersion -Exe $cmd.Source -PrefixArgs $candidate.Args) {
            return @{ Exe = $cmd.Source; Args = $candidate.Args }
        }
    }
    return $null
}

$python = Find-Python
if ($null -eq $python) {
    Write-Host ""
    Write-Host "Could not find Python 3.11 or newer."
    Write-Host ""
    Write-Host "If you just installed it, PATH only updates for NEW windows:"
    Write-Host "  1. Close this PowerShell window"
    Write-Host "  2. Open PowerShell again"
    Write-Host "  3. cd `$HOME\Instagram"
    Write-Host "  4. .\setup.ps1"
    Write-Host ""
    Write-Host "If you have not installed it: https://www.python.org/downloads/"
    Write-Host "and tick 'Add python.exe to PATH' on the installer's first screen."
    exit 1
}

$pyArgs = $python.Args
$version = (& $python.Exe @pyArgs --version 2>&1)
Write-Host "Using $version"

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating an isolated environment (.venv)..."
    $venvArgs = @($pyArgs) + @("-m", "venv", ".venv")
    & $python.Exe @venvArgs
    if (($LASTEXITCODE -ne 0) -or (-not (Test-Path $venvPython))) {
        Write-Host ""
        Write-Host "Could not create the environment. If .venv exists but is broken,"
        Write-Host "delete it and run this again:  Remove-Item -Recurse -Force .venv"
        exit 1
    }
}

Write-Host "Installing dependencies (a minute or two the first time)..."
& $venvPython -m pip install --quiet --upgrade pip
& $venvPython -m pip install --quiet -e ".[dev]"
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Install failed. The lines above say why — send them over."
    exit 1
}

Write-Host ""
& $venvPython scripts\first_run.py @args
exit $LASTEXITCODE
