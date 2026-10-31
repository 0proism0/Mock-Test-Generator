@echo off
rem Auto-rebuild the React front-end on every change (vite build --watch -> app/web/dist).
rem Leave it running while you edit app/web, then refresh http://localhost:8000.
rem
rem Usage:  scripts\watch.bat
setlocal
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "WEB=%ROOT%\app\web"

where npm >nul 2>nul
if errorlevel 1 (
  echo [watch] npm not found on PATH. Install Node.js 20+ first.
  pause
  exit /b 1
)

pushd "%WEB%"
if errorlevel 1 (
  echo [watch] cannot enter "%WEB%"
  pause
  exit /b 1
)

if not exist "node_modules" (
  echo [watch] npm ci
  call npm ci
  if errorlevel 1 (
    popd
    echo [watch] dependency install failed
    pause
    exit /b 1
  )
)

echo [watch] vite build --watch -^> app\web\dist (Ctrl+C to stop)
call npm run build:watch
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
