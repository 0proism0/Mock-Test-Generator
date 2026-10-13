#!/usr/bin/env pwsh
# Run MockTest Maker.
#
#   pwsh scripts/start.ps1        # Python server on http://localhost:8000
#                                 # (serves app/web/dist if built, else the legacy UI)
#   pwsh scripts/start.ps1 -Dev   # + Vite dev server on http://localhost:5173 (HMR, /api proxied)
param(
    [switch]$Dev
)
$ErrorActionPreference = "Stop"

$root      = Split-Path -Parent $PSScriptRoot
$server    = Join-Path $root "app/server.py"
$web       = Join-Path $root "app/web"
$distIndex = Join-Path $web "dist/index.html"

function Resolve-Python {
    if ($env:PYTHON) { return $env:PYTHON }
    $venvWin = Join-Path $root ".venv/Scripts/python.exe"
    $venvNix = Join-Path $root ".venv/bin/python"
    if (Test-Path $venvWin) { return $venvWin }
    if (Test-Path $venvNix) { return $venvNix }
    return "python"
}

$python = Resolve-Python

if ($Dev) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm not found on PATH. Install Node.js 20+ first."
    }
    Write-Host "[dev] Python API on http://localhost:8000 ..."
    $api = Start-Process -FilePath $python -ArgumentList $server -PassThru
    try {
        Push-Location $web
        try { npm run dev } finally { Pop-Location }
    }
    finally {
        if ($api -and -not $api.HasExited) { Stop-Process -Id $api.Id -Force }
    }
}
else {
    if (-not (Test-Path $distIndex)) {
        Write-Host "[start] app/web/dist not built - serving legacy UI. Run scripts/build.ps1 for the React app."
    }
    Write-Host "[start] http://localhost:8000"
    & $python $server
}
