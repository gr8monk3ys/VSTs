# Thin wrapper around download-plugins.py — all arguments pass through unchanged.
# The Python script is the single source of truth for plugin URLs, hash
# verification, and platform detection. See download-plugins.py for the real
# logic; this file exists so users can run `.\scripts\download-plugins.ps1` out
# of muscle memory.

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonScript = Join-Path $ScriptDir "download-plugins.py"

$python = $null
foreach ($cmd in @("python3", "python", "py")) {
    try {
        $version = & $cmd --version 2>&1
        if ($version -match "Python 3") {
            $python = $cmd
            break
        }
    } catch {}
}

if (-not $python) {
    Write-Host "Error: Python 3 not found. Install from https://python.org" -ForegroundColor Red
    exit 1
}

& $python $PythonScript @args
