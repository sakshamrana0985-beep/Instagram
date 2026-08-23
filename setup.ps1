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

function Get-PythonCandidates {
    # Everything plausible, in preference order. Nothing is excluded up front:
    # the Microsoft Store stub lives in WindowsApps, but so does the py.exe that
    # the official Python install manager ships, so the only safe way to tell
    # them apart is to ask each one its version and believe the exit code.
    $candidates = @()

    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $launcher) {
        foreach ($ver in @("", "-3", "-3.14", "-3.13", "-3.12", "-3.11")) {
            $verArgs = @()
            if ($ver -ne "") { $verArgs = @($ver) }
            $candidates += @{ Exe = $launcher.Source; Args = $verArgs; Label = "py $ver".Trim() }
        }
    }

    foreach ($name in @("python", "python3", "python3.14", "python3.13", "python3.12", "python3.11")) {
        foreach ($cmd in @(Get-Command $name -All -ErrorAction SilentlyContinue)) {
            if ($cmd.Source) {
                $candidates += @{ Exe = $cmd.Source; Args = @(); Label = $cmd.Source }
            }
        }
    }

    # Installed but not on PATH - common with the install manager and the
    # classic installer when "Add to PATH" was missed.
    $globs = @(
        (Join-Path $env:LOCALAPPDATA "Python\bin\python3*.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python3*\python.exe"),
        (Join-Path $env:ProgramFiles "Python3*\python.exe")
    )
    foreach ($glob in $globs) {
        foreach ($found in @(Get-ChildItem $glob -ErrorAction SilentlyContinue)) {
            $candidates += @{ Exe = $found.FullName; Args = @(); Label = $found.FullName }
        }
    }

    return $candidates
}

function Find-Python {
    $script:Attempted = @()
    foreach ($candidate in Get-PythonCandidates) {
        if (Test-PythonVersion -Exe $candidate.Exe -PrefixArgs $candidate.Args) {
            return $candidate
        }
        $script:Attempted += $candidate.Label
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
    if ($script:Attempted.Count -gt 0) {
        Write-Host ""
        Write-Host "Tried, and none reported version 3.11 or newer:"
        foreach ($attempt in $script:Attempted) { Write-Host "  $attempt" }
    }
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
    Write-Host "Install failed. The lines above say why - send them over."
    exit 1
}

Write-Host ""
& $venvPython scripts\first_run.py @args
exit $LASTEXITCODE
