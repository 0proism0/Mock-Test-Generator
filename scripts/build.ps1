#!/usr/bin/env pwsh
# Build the React front-end (app/web) into app/web/dist.
# The Python server (app/server.py) serves that folder at "/" when present.
#
# Usage:  pwsh scripts/build.ps1
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$web  = Join-Path $root "app/web"

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm not found on PATH. Install Node.js 20+ first."
}

Push-Location $web
try {
    if (-not (Test-Path "node_modules")) {
        if (Test-Path "package-lock.json") {
            Write-Host "[build] npm ci"
            npm ci
        } else {
            Write-Host "[build] npm install"
            npm install
        }
    }
    Write-Host "[build] npm run build"
    npm run build
}
finally {
    Pop-Location
}
Write-Host "[build] done -> app/web/dist"
