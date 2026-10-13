#!/usr/bin/env pwsh
# Auto-rebuild the React front-end on every change (vite build --watch -> app/web/dist).
# Leave it running while you edit app/web, then refresh http://localhost:8000.
#
# Usage:  pwsh scripts/watch.ps1
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$web  = Join-Path $root "app/web"

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm not found on PATH. Install Node.js 20+ first."
}

Push-Location $web
try {
    if (-not (Test-Path "node_modules")) {
        Write-Host "[watch] npm ci"
        npm ci
    }
    Write-Host "[watch] vite build --watch -> app/web/dist (Ctrl+C to stop)"
    npm run build:watch
}
finally {
    Pop-Location
}
